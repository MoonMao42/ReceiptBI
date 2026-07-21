"use client";

import {
  ArrowLeft,
  ArrowRight,
  BookOpenText,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Filter,
  Loader2,
  PencilLine,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  UserCheck,
  X,
} from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api/client";
import { useProjectStore } from "@/lib/stores/project";
import { useChatStore } from "@/lib/stores/chat";
import { PENDING_TASK_STORAGE_KEY, PROJECT_STORAGE_KEY } from "@/lib/storage/legacy";
import type {
  Project,
  ProjectDataSource,
  SemanticBatchAction,
  SemanticBatchResult,
  SemanticEntry,
  SemanticKnowledgePage,
  SemanticSourceScope,
} from "@/lib/types/api";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;

type EntryTypeFilter = SemanticEntry["entry_type"] | "all";
type StateFilter = SemanticEntry["state"] | "all";
type ValidityFilter = SemanticEntry["validity"] | "all";
type SourceScopeFilter = SemanticSourceScope | "file";
type SourceFilterValue = "all" | `scope:${SourceScopeFilter}` | `source:${string}`;
type EditorScopeValue = "preserve" | "scope:project" | `source:${string}`;

const TYPE_OPTIONS: Array<{ value: EntryTypeFilter; label: string }> = [
  { value: "all", label: "全部内容" },
  { value: "relationship", label: "数据关联" },
  { value: "metric", label: "指标" },
  { value: "dimension", label: "维度" },
  { value: "business_rule", label: "业务口径" },
  { value: "cleaning_rule", label: "整理规则" },
];

const STATE_OPTIONS: Array<{ value: StateFilter; label: string }> = [
  { value: "all", label: "全部状态" },
  { value: "candidate", label: "待处理" },
  { value: "confirmed", label: "已记住" },
  { value: "locked", label: "已锁定" },
];

const VALIDITY_OPTIONS: Array<{ value: ValidityFilter; label: string }> = [
  { value: "all", label: "全部有效性" },
  { value: "unverified", label: "待验证" },
  { value: "active", label: "可使用" },
  { value: "stale", label: "已忽略/停用" },
];

const EDITABLE_TYPE_OPTIONS = TYPE_OPTIONS.filter(
  (option): option is { value: SemanticEntry["entry_type"]; label: string } =>
    option.value !== "all"
);

const EDITABLE_STATE_OPTIONS: Array<{ value: SemanticEntry["state"]; label: string }> = [
  { value: "candidate", label: "待核对" },
  { value: "confirmed", label: "已确认" },
  { value: "locked", label: "已锁定" },
];

const SOURCE_SCOPE_GROUPS: Array<{
  scope: Exclude<SemanticSourceScope, "project" | "cross_source" | "unresolved">;
  label: string;
  allLabel: string;
}> = [
  { scope: "local_database", label: "本地数据库", allLabel: "全部本地数据库" },
  { scope: "remote_database", label: "在线数据库", allLabel: "全部在线数据库" },
  { scope: "excel", label: "Excel", allLabel: "全部 Excel" },
  { scope: "csv", label: "CSV", allLabel: "全部 CSV" },
  { scope: "parquet", label: "Parquet", allLabel: "全部 Parquet" },
  { scope: "json", label: "JSON", allLabel: "全部 JSON" },
  { scope: "other_file", label: "其他文件", allLabel: "全部其他文件" },
];

interface RelationshipEndpoint {
  source_logical_name?: string;
  source_kind?: "file" | "connection";
  table_or_view?: string;
  column?: string;
  data_type?: string;
  schema_signature?: string;
}

interface RelationshipDefinition {
  version?: 1;
  left?: RelationshipEndpoint;
  right?: RelationshipEndpoint;
  cardinality?: string | null;
  normalization?: string;
  default_join?: string;
  minimum_left_match_rate?: number;
  maximum_expansion_ratio?: number;
}

interface SourceColumn {
  name: string;
  type: string;
}

interface SourceTable {
  name: string;
  columns: SourceColumn[];
}

interface SemanticEditorDraft {
  key: string;
  value: string;
  entryType: SemanticEntry["entry_type"];
  state: SemanticEntry["state"];
  scopeSource: EditorScopeValue;
  definitionText: string;
  leftSourceId: string;
  leftTable: string;
  leftColumn: string;
  rightSourceId: string;
  rightTable: string;
  rightColumn: string;
  normalization: "exact" | "trim_casefold" | "identifier" | "auto";
  cardinality: "" | "one_to_one" | "one_to_many" | "many_to_one" | "many_to_many";
  defaultJoin: "left" | "inner";
  minimumLeftMatchRate: string;
  maximumExpansionRatio: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function relationshipDefinition(entry: SemanticEntry): RelationshipDefinition | null {
  if (entry.entry_type !== "relationship" || !isRecord(entry.definition)) return null;
  return entry.definition as RelationshipDefinition;
}

function endpointLabel(endpoint?: RelationshipEndpoint): string {
  if (!endpoint) return "尚未指定";
  const location = [endpoint.table_or_view, endpoint.column].filter(Boolean).join(".");
  return [endpoint.source_logical_name, location].filter(Boolean).join(" · ") || "尚未指定";
}

function projectSourceLogicalName(source: ProjectDataSource): string {
  const logicalName = source.profile_data.logical_name;
  return typeof logicalName === "string" && logicalName.trim()
    ? logicalName.trim()
    : source.name;
}

function projectSourceScope(
  source: ProjectDataSource
): Exclude<SemanticSourceScope, "project" | "cross_source" | "unresolved"> {
  const profileDriver = source.profile_data.driver;
  const format = String(
    source.format || (typeof profileDriver === "string" ? profileDriver : "")
  ).toLowerCase();
  if (source.kind === "connection") {
    return format === "sqlite" || format === "sqlite3" || format === "duckdb"
      ? "local_database"
      : "remote_database";
  }
  if (format === "csv") return "csv";
  if (["xlsx", "xls", "xlsb", "xlsm", "excel"].includes(format)) return "excel";
  if (format === "parquet") return "parquet";
  if (format === "json" || format === "jsonl" || format === "ndjson") return "json";
  return "other_file";
}

function sourcesInScope(
  sources: ProjectDataSource[],
  scope: Exclude<SemanticSourceScope, "project" | "cross_source" | "unresolved">
): ProjectDataSource[] {
  return sources.filter((source) => projectSourceScope(source) === scope);
}

function sourceIdsFromEntry(entry: SemanticEntry | null): string[] {
  if (!entry) return [];
  const ids = entry.evidence.flatMap((item) => {
    if (!Array.isArray(item.source_ids)) return [];
    return item.source_ids.filter(
      (sourceId): sourceId is string => typeof sourceId === "string" && Boolean(sourceId)
    );
  });
  if (!ids.length) {
    ids.push(
      ...(entry.source_refs || []).flatMap((source) =>
        source.source_id ? [source.source_id] : []
      )
    );
  }
  return Array.from(new Set(ids));
}

function editorScopeValue(
  entry: SemanticEntry | null,
  sources: ProjectDataSource[]
): EditorScopeValue {
  if (!entry) return "scope:project";
  if (entry.source_scope === "cross_source" || entry.source_scope === "unresolved") {
    return "preserve";
  }
  const sourceIds = sourceIdsFromEntry(entry);
  if (sourceIds.length === 1 && sources.some((source) => source.id === sourceIds[0])) {
    return `source:${sourceIds[0]}`;
  }
  if (!sourceIds.length && entry.source_scope === "project") return "scope:project";
  return "preserve";
}

function semanticSourceLabel(entry: SemanticEntry): string {
  if (entry.source_scope === "project") return "项目通用";
  if (entry.source_scope === "unresolved") return "待归类";
  const names = Array.from(
    new Set(
      (entry.source_refs || [])
        .map((source) => source.logical_name || source.name)
        .filter(Boolean)
      )
  );
  if (!names.length && entry.entry_type === "relationship") {
    const relationship = relationshipDefinition(entry);
    names.push(
      ...Array.from(
        new Set(
          [relationship?.left?.source_logical_name, relationship?.right?.source_logical_name]
            .filter((name): name is string => Boolean(name))
        )
      )
    );
  }
  const namesLabel =
    names.length === 1
      ? names[0]
      : names.length === 2
        ? names.join("、")
        : names.length > 2
          ? `${names.slice(0, 2).join("、")} 等 ${names.length} 项`
          : "";
  if (entry.source_scope === "cross_source") {
    return namesLabel ? `跨数据源 · ${namesLabel}` : "跨数据源";
  }
  if (namesLabel) return namesLabel;
  const labels: Record<SemanticSourceScope, string> = {
    project: "项目通用",
    local_database: "本地数据库",
    remote_database: "在线数据库",
    csv: "CSV",
    excel: "Excel",
    parquet: "Parquet",
    json: "JSON",
    other_file: "其他文件",
    cross_source: "跨数据源",
    unresolved: "待归类",
  };
  return entry.source_scope ? labels[entry.source_scope] : "待归类";
}

function definitionOwnsSourceScope(draft: SemanticEditorDraft): boolean {
  if (draft.entryType === "relationship") return true;
  if (!draft.definitionText.trim()) return false;
  try {
    const definition: unknown = JSON.parse(draft.definitionText);
    return (
      isRecord(definition) &&
      (definition.kind === "aggregate_metric" ||
        definition.kind === "business_rule_strategy")
    );
  } catch {
    return false;
  }
}

function SourceFilterOptions({ sources }: { sources: ProjectDataSource[] }) {
  return (
    <>
      <option value="all">全部项目理解</option>
      <optgroup label="项目">
        <option value="scope:project">项目通用</option>
        <option value="scope:cross_source">跨数据源</option>
        <option value="scope:unresolved">待归类</option>
      </optgroup>
      {sources.some((source) => source.kind === "file") && (
        <optgroup label="文件">
          <option value="scope:file">全部文件</option>
        </optgroup>
      )}
      {SOURCE_SCOPE_GROUPS.map((group) => {
        const groupedSources = sourcesInScope(sources, group.scope);
        if (!groupedSources.length) return null;
        return (
          <optgroup key={group.scope} label={group.label}>
            <option value={`scope:${group.scope}`}>{group.allLabel}</option>
            {groupedSources.map((source) => (
              <option key={source.id} value={`source:${source.id}`}>
                {source.name}
              </option>
            ))}
          </optgroup>
        );
      })}
    </>
  );
}

function EditorScopeOptions({
  sources,
  preserveLabel,
}: {
  sources: ProjectDataSource[];
  preserveLabel?: string;
}) {
  return (
    <>
      {preserveLabel && <option value="preserve">{preserveLabel}</option>}
      <option value="scope:project">项目通用</option>
      {SOURCE_SCOPE_GROUPS.map((group) => {
        const groupedSources = sourcesInScope(sources, group.scope);
        if (!groupedSources.length) return null;
        return (
          <optgroup key={group.scope} label={group.label}>
            {groupedSources.map((source) => (
              <option key={source.id} value={`source:${source.id}`}>
                {source.name}
              </option>
            ))}
          </optgroup>
        );
      })}
    </>
  );
}

function normalizeSourceColumns(value: unknown): SourceColumn[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((column) => {
    if (!isRecord(column) || typeof column.name !== "string" || !column.name.trim()) return [];
    return [
      {
        name: column.name.trim(),
        type:
          typeof column.type === "string"
            ? column.type
            : typeof column.dtype === "string"
              ? column.dtype
              : "unknown",
      },
    ];
  });
}

function sourceTables(source?: ProjectDataSource): SourceTable[] {
  if (!source) return [];
  if (source.kind === "file") {
    const schema = isRecord(source.profile_data.schema) ? source.profile_data.schema : {};
    return [
      {
        name: projectSourceLogicalName(source),
        columns: normalizeSourceColumns(schema.columns),
      },
    ];
  }
  if (!Array.isArray(source.profile_data.tables)) return [];
  return source.profile_data.tables.flatMap((table) => {
    if (!isRecord(table) || typeof table.name !== "string" || !table.name.trim()) return [];
    return [
      {
        name: table.name.trim(),
        columns: normalizeSourceColumns(table.columns),
      },
    ];
  });
}

function sourceForEndpoint(
  sources: ProjectDataSource[],
  endpoint?: RelationshipEndpoint
): ProjectDataSource | undefined {
  if (!endpoint) return undefined;
  return sources.find(
    (source) =>
      projectSourceLogicalName(source) === endpoint.source_logical_name &&
      (!endpoint.source_kind || source.kind === endpoint.source_kind)
  );
}

function relationshipDraft(
  entry: SemanticEntry | null,
  sources: ProjectDataSource[]
): SemanticEditorDraft {
  const definition = entry ? relationshipDefinition(entry) : null;
  return {
    key: entry?.key || "",
    value: entry?.value || "",
    entryType: entry?.entry_type || "business_rule",
    state: entry?.state || "candidate",
    scopeSource: editorScopeValue(entry, sources),
    definitionText:
      entry?.entry_type !== "relationship" && entry?.definition
        ? JSON.stringify(entry.definition, null, 2)
        : "",
    leftSourceId: sourceForEndpoint(sources, definition?.left)?.id || "",
    leftTable: definition?.left?.table_or_view || "",
    leftColumn: definition?.left?.column || "",
    rightSourceId: sourceForEndpoint(sources, definition?.right)?.id || "",
    rightTable: definition?.right?.table_or_view || "",
    rightColumn: definition?.right?.column || "",
    normalization:
      definition?.normalization === "exact" ||
      definition?.normalization === "trim_casefold" ||
      definition?.normalization === "identifier"
        ? definition.normalization
        : "auto",
    cardinality:
      definition?.cardinality === "one_to_one" ||
      definition?.cardinality === "one_to_many" ||
      definition?.cardinality === "many_to_one" ||
      definition?.cardinality === "many_to_many"
        ? definition.cardinality
        : "",
    defaultJoin: definition?.default_join === "inner" ? "inner" : "left",
    minimumLeftMatchRate: String(definition?.minimum_left_match_rate ?? 0.8),
    maximumExpansionRatio: String(definition?.maximum_expansion_ratio ?? 1.2),
  };
}

async function schemaSignature(columns: SourceColumn[]): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error("当前环境不能生成字段结构签名，请刷新后重试。");
  }
  const payload = JSON.stringify(
    columns
      .map((column) => ({ name: column.name, type: column.type || "unknown" }))
      .sort((left, right) => {
        if (left.name !== right.name) return left.name < right.name ? -1 : 1;
        if (left.type === right.type) return 0;
        return left.type < right.type ? -1 : 1;
      })
  );
  const digest = await globalThis.crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(payload)
  );
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function relationshipEndpointFromDraft(
  sources: ProjectDataSource[],
  sourceId: string,
  tableName: string,
  columnName: string,
  existing?: RelationshipEndpoint
): Promise<Required<RelationshipEndpoint>> {
  const source = sources.find((item) => item.id === sourceId);
  const normalizedTable = tableName.trim();
  const normalizedColumn = columnName.trim();
  if (!source) {
    if (
      existing?.source_logical_name &&
      existing.source_kind &&
      existing.table_or_view === normalizedTable &&
      existing.column === normalizedColumn &&
      existing.data_type &&
      existing.schema_signature
    ) {
      return existing as Required<RelationshipEndpoint>;
    }
    throw new Error("请选择这条关联使用的数据来源。");
  }
  const table = sourceTables(source).find((item) => item.name === normalizedTable);
  if (!table) throw new Error(`数据来源中没有找到表“${normalizedTable}”。`);
  const column = table.columns.find((item) => item.name === normalizedColumn);
  if (!column) throw new Error(`表“${normalizedTable}”中没有找到字段“${normalizedColumn}”。`);
  return {
    source_logical_name: projectSourceLogicalName(source),
    source_kind: source.kind,
    table_or_view: table.name,
    column: column.name,
    data_type: column.type,
    schema_signature: await schemaSignature(table.columns),
  };
}

async function editorDefinition(
  draft: SemanticEditorDraft,
  sources: ProjectDataSource[],
  entry: SemanticEntry | null
): Promise<Record<string, unknown> | null> {
  if (draft.entryType === "relationship") {
    const current = entry ? relationshipDefinition(entry) : null;
    const minimumLeftMatchRate = Number(draft.minimumLeftMatchRate);
    const maximumExpansionRatio = Number(draft.maximumExpansionRatio);
    if (
      !Number.isFinite(minimumLeftMatchRate) ||
      minimumLeftMatchRate < 0 ||
      minimumLeftMatchRate > 1
    ) {
      throw new Error("左侧匹配率需要填写 0 到 1 之间的数值。");
    }
    if (!Number.isFinite(maximumExpansionRatio) || maximumExpansionRatio < 1) {
      throw new Error("最大行数扩张倍数不能小于 1。");
    }
    return {
      version: 1,
      left: await relationshipEndpointFromDraft(
        sources,
        draft.leftSourceId,
        draft.leftTable,
        draft.leftColumn,
        current?.left
      ),
      right: await relationshipEndpointFromDraft(
        sources,
        draft.rightSourceId,
        draft.rightTable,
        draft.rightColumn,
        current?.right
      ),
      normalization: draft.normalization,
      cardinality: draft.cardinality || null,
      default_join: draft.defaultJoin,
      minimum_left_match_rate: minimumLeftMatchRate,
      maximum_expansion_ratio: maximumExpansionRatio,
    };
  }

  const raw = draft.definitionText.trim();
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("扩展定义不是有效的 JSON，请检查括号和引号。");
  }
  if (!isRecord(parsed)) throw new Error("扩展定义必须是一个 JSON 对象。");
  const kind = parsed.kind;
  const definitionVariant =
    kind === "aggregate_metric"
      ? "aggregate_metric"
      : kind === "business_rule_strategy"
        ? "business_rule_strategy"
        : kind === "relationship" ||
            ((kind === undefined || kind === null) && ("left" in parsed || "right" in parsed))
          ? "relationship"
          : "raw";
  const expectedEntryType = {
    relationship: "relationship",
    aggregate_metric: "metric",
    business_rule_strategy: "business_rule",
  } as const;
  const compatibilityError = {
    relationship: "数据关联定义只能用于数据关联类型。",
    aggregate_metric: "聚合指标定义只能用于指标类型。",
    business_rule_strategy: "业务规则执行定义只能用于业务口径类型。",
  } as const;
  if (
    definitionVariant !== "raw" &&
    draft.entryType !== expectedEntryType[definitionVariant]
  ) {
    throw new Error(compatibilityError[definitionVariant]);
  }
  return parsed;
}

export function semanticTypeLabel(type: SemanticEntry["entry_type"]): string {
  return TYPE_OPTIONS.find((item) => item.value === type)?.label || "项目理解";
}

function governanceLabel(entry: SemanticEntry): string {
  if (entry.validity === "stale" || entry.is_active === false) return "已忽略";
  if (entry.state === "locked") return "已锁定";
  if (entry.execution_state === "verified") return "已验证";
  if (entry.state === "confirmed") return "已记住";
  return entry.validity === "unverified" ? "待验证" : "待核对";
}

function governanceTone(entry: SemanticEntry): string {
  if (entry.validity === "stale" || entry.is_active === false) return "text-muted-foreground";
  if (entry.execution_state === "verified") return "text-success";
  if (entry.state === "locked" || entry.state === "confirmed") return "text-primary";
  return "text-warning";
}

function evidenceLabel(entry: SemanticEntry): string {
  const kinds = new Set(entry.evidence.map((item) => String(item.kind || "")));
  if (kinds.has("declared_foreign_key")) return "数据库约束";
  if (kinds.has("relationship_validation")) return "完整数据验证";
  if (kinds.has("semantic_execution_verification")) return "系统探测验证";
  if (kinds.has("semantic_human_attestation")) return "人工确认验证";
  if (kinds.has("matching_column_names")) return "同名字段";
  if (kinds.has("user_correction")) return "人工修正";
  if (kinds.has("user_confirmation")) return "人工确认";
  return entry.evidence.length ? `${entry.evidence.length} 项依据` : "暂无依据";
}

export function semanticSignalLabel(entry: SemanticEntry): string {
  if (entry.validity === "stale" || entry.is_active === false) return "已停用";
  if (entry.execution_state === "verified") return "完整数据已验证";
  if (entry.state === "locked") return "人工锁定";
  if (entry.state === "confirmed") return "人工确认";

  const kinds = new Set(entry.evidence.map((item) => String(item.kind || "")));
  if (kinds.has("declared_foreign_key")) return "数据库约束";
  if (kinds.has("relationship_validation")) return "已有验证记录";
  if (kinds.has("user_correction") || kinds.has("user_confirmation")) return "人工提供";
  if (kinds.has("matching_column_names")) {
    if (entry.confidence >= 0.7) return "较强线索";
    if (entry.confidence >= 0.62) return "中等线索";
    return "初步线索";
  }
  return "待核对";
}

function updatedLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "最近更新";
  return `${date.getMonth() + 1}月${date.getDate()}日更新`;
}

function entryTitle(entry: SemanticEntry): string {
  if (entry.entry_type !== "relationship") return entry.value || entry.key;
  const definition = relationshipDefinition(entry);
  if (!definition) return entry.value || entry.key;
  return `${endpointLabel(definition.left)} → ${endpointLabel(definition.right)}`;
}

function canQueueValidation(entry: SemanticEntry): boolean {
  return entry.allowed_actions.includes("queue_validation");
}

function canRemember(entry: SemanticEntry): boolean {
  return entry.allowed_actions.includes("remember");
}

function canIgnore(entry: SemanticEntry): boolean {
  return entry.allowed_actions.includes("ignore");
}

function canRestore(entry: SemanticEntry): boolean {
  return entry.allowed_actions.includes("restore");
}

function canAttest(entry: SemanticEntry): boolean {
  return entry.allowed_actions.includes("attest");
}

function actionAllowed(action: SemanticBatchAction, entries: SemanticEntry[]): boolean {
  if (!entries.length) return false;
  if (action === "ignore") return entries.every(canIgnore);
  if (action === "queue_validation") return entries.every(canQueueValidation);
  if (action === "attest") return entries.every(canAttest);
  if (action === "remember") return entries.every(canRemember);
  return entries.every(canRestore);
}

function errorMessage(error: unknown): string {
  if (isRecord(error) && isRecord(error.response)) {
    const data = error.response.data;
    if (isRecord(data) && typeof data.detail === "string") return data.detail;
    if (isRecord(data) && Array.isArray(data.detail)) {
      const messages = data.detail.flatMap((item) => {
        if (!isRecord(item) || typeof item.msg !== "string") return [];
        return [item.msg.replace(/^Value error,\s*/i, "")];
      });
      if (messages.length) return messages.join("；");
    }
  }
  if (error instanceof Error && error.message) return error.message;
  return "当前内容没有加载完成，请重试。";
}

export function ProjectUnderstandingWorkspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [sources, setSources] = useState<ProjectDataSource[]>([]);
  const [page, setPage] = useState<SemanticKnowledgePage | null>(null);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const [entryType, setEntryType] = useState<EntryTypeFilter>("relationship");
  const [state, setState] = useState<StateFilter>("all");
  const [validity, setValidity] = useState<ValidityFilter>("all");
  const [sourceFilter, setSourceFilter] = useState<SourceFilterValue>("all");
  const [leftTable, setLeftTable] = useState("");
  const [rightTable, setRightTable] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [batchAction, setBatchAction] = useState<SemanticBatchAction | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [editorEntry, setEditorEntry] = useState<SemanticEntry | null | undefined>(undefined);
  const [editorDraft, setEditorDraft] = useState<SemanticEditorDraft>(() =>
    relationshipDraft(null, [])
  );
  const [editorError, setEditorError] = useState<string | null>(null);
  const [savingEditor, setSavingEditor] = useState(false);
  const [reloadVersion, setReloadVersion] = useState(0);

  useEffect(() => {
    localStorage.setItem(PROJECT_STORAGE_KEY, projectId);
    if (useProjectStore.getState().currentProjectId !== projectId) {
      useProjectStore.setState({ currentProjectId: projectId });
    }
  }, [projectId]);

  useEffect(() => {
    let active = true;
    void Promise.allSettled([
      api.get(`/api/v1/projects/${projectId}`),
      api.get(`/api/v1/projects/${projectId}/sources`),
    ]).then(([projectResult, sourceResult]) => {
      if (!active) return;
      setProject(
        projectResult.status === "fulfilled"
          ? (projectResult.value.data.data as Project)
          : null
      );
      setSources(
        sourceResult.status === "fulfilled" && Array.isArray(sourceResult.value.data.data)
          ? (sourceResult.value.data.data as ProjectDataSource[])
          : []
      );
    });
    return () => {
      active = false;
    };
  }, [projectId]);

  useEffect(() => {
    const controller = new AbortController();
    setSelectedIds(new Set());
    setLoading(true);
    setError(null);
    const params: Record<string, string | number | boolean> = {
      offset,
      limit: PAGE_SIZE,
      business_facing_only: true,
    };
    if (deferredSearch) params.search = deferredSearch;
    if (entryType !== "all") params.entry_type = entryType;
    if (state !== "all") params.state = state;
    if (validity !== "all") params.validity = validity;
    if (sourceFilter.startsWith("source:")) {
      params.source_id = sourceFilter.slice("source:".length);
    } else if (sourceFilter.startsWith("scope:")) {
      params.source_scope = sourceFilter.slice("scope:".length);
    }
    if (leftTable.trim()) params.left_table = leftTable.trim();
    if (rightTable.trim()) params.right_table = rightTable.trim();

    void api
      .get(`/api/v1/projects/${projectId}/knowledge/page`, {
        params,
        signal: controller.signal,
      })
      .then((response) => response.data.data as SemanticKnowledgePage)
      .then((nextPage) => {
        if (controller.signal.aborted) return;
        if (nextPage.items.some((entry) => !Array.isArray(entry.allowed_actions))) {
          throw new Error("项目理解的操作权限没有加载完成，请刷新重试。");
        }
        if (nextPage.total === 0 && nextPage.offset > 0) {
          setOffset(0);
          return;
        }
        if (nextPage.total > 0 && nextPage.offset >= nextPage.total) {
          setOffset(Math.floor((nextPage.total - 1) / PAGE_SIZE) * PAGE_SIZE);
          return;
        }
        setPage(nextPage);
        setActiveId((current) =>
          current && nextPage.items.some((entry) => entry.id === current)
            ? current
            : nextPage.items[0]?.id || null
        );
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted) setError(errorMessage(requestError));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [
    deferredSearch,
    entryType,
    leftTable,
    offset,
    projectId,
    reloadVersion,
    rightTable,
    sourceFilter,
    state,
    validity,
  ]);

  useEffect(() => {
    setOffset(0);
  }, [deferredSearch, entryType, state, validity, sourceFilter, leftTable, rightTable]);

  const selectedEntries = useMemo(
    () => (page?.items || []).filter((entry) => selectedIds.has(entry.id)),
    [page, selectedIds]
  );
  const activeEntry = page?.items.find((entry) => entry.id === activeId) || null;
  const selectableEntries = (page?.items || []).filter(
    (entry) =>
      !loading &&
      Boolean(entry.active_revision_id) &&
      (canQueueValidation(entry) ||
        canRemember(entry) ||
        canIgnore(entry) ||
        canRestore(entry))
  );
  const allPageSelected =
    selectableEntries.length > 0 && selectableEntries.every((entry) => selectedIds.has(entry.id));
  const somePageSelected =
    !allPageSelected && selectableEntries.some((entry) => selectedIds.has(entry.id));
  const currentPage = page ? Math.floor(page.offset / page.limit) + 1 : 1;
  const pageCount = page ? Math.max(1, Math.ceil(page.total / page.limit)) : 1;
  const activeFilterCount =
    Number(state !== "all") +
    Number(validity !== "all") +
    Number(Boolean(leftTable.trim())) +
    Number(Boolean(rightTable.trim()));

  const toggleSelection = (entryId: string) => {
    if (loading) return;
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(entryId)) next.delete(entryId);
      else next.add(entryId);
      return next;
    });
  };

  const togglePageSelection = () => {
    if (loading) return;
    setSelectedIds(
      allPageSelected ? new Set() : new Set(selectableEntries.map((entry) => entry.id))
    );
  };

  const openEditor = (entry: SemanticEntry | null) => {
    setEditorEntry(entry);
    setEditorDraft(relationshipDraft(entry, sources));
    setEditorError(null);
    setFeedback(null);
  };

  const closeEditor = () => {
    if (savingEditor) return;
    setEditorEntry(undefined);
    setEditorError(null);
  };

  const updateEditorDraft = <Key extends keyof SemanticEditorDraft>(
    key: Key,
    value: SemanticEditorDraft[Key]
  ) => {
    setEditorDraft((current) => ({ ...current, [key]: value }));
  };

  const saveEditor = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const key = editorDraft.key.trim();
    const value = editorDraft.value.trim();
    if (!key) {
      setEditorError("请填写名称。");
      return;
    }
    if (!value) {
      setEditorError("请填写业务定义。");
      return;
    }
    if (editorEntry && !editorEntry.active_revision_id) {
      setEditorError("当前版本信息没有加载完成，请刷新后再编辑。");
      return;
    }

    setSavingEditor(true);
    setEditorError(null);
    try {
      const definition = await editorDefinition(editorDraft, sources, editorEntry || null);
      const relationshipSourceIds = Array.from(
        new Set(
          [editorDraft.leftSourceId, editorDraft.rightSourceId].filter(
            (source): source is string => editorDraft.entryType === "relationship" && Boolean(source)
          )
        )
      );
      const priorEvidence = editorEntry?.evidence || [];
      const evidenceWithoutDeclaration = priorEvidence.filter(
        (item) => item.kind !== "user_declaration"
      );
      let evidence: Record<string, unknown>[];
      if (editorDraft.entryType === "relationship") {
        evidence = relationshipSourceIds.length
          ? [
              ...evidenceWithoutDeclaration,
              { kind: "user_declaration", source_ids: relationshipSourceIds },
            ]
          : priorEvidence.length
            ? priorEvidence
            : [{ kind: "user_declaration" }];
      } else if (definitionOwnsSourceScope(editorDraft) || editorDraft.scopeSource === "preserve") {
        evidence = priorEvidence.length ? priorEvidence : [{ kind: "user_declaration" }];
      } else {
        const selectedSourceId = editorDraft.scopeSource.startsWith("source:")
          ? editorDraft.scopeSource.slice("source:".length)
          : "";
        evidence = [
          ...evidenceWithoutDeclaration,
          selectedSourceId
            ? { kind: "user_declaration", source_ids: [selectedSourceId] }
            : { kind: "user_declaration" },
        ];
      }
      const basePayload = {
        key,
        value,
        entry_type: editorDraft.entryType,
        state: editorDraft.state,
        confidence:
          editorDraft.state === "candidate"
            ? editorEntry?.confidence ?? 0.5
            : 1,
        definition,
        validity:
          editorDraft.entryType === "relationship"
            ? editorEntry?.validity === "stale"
              ? "unverified"
              : editorEntry?.validity || "unverified"
            : "active",
        evidence,
        source: "user" as const,
      };
      const response = editorEntry
        ? await api.put(`/api/v1/projects/${projectId}/knowledge/${editorEntry.id}`, {
            expected_active_revision_id: editorEntry.active_revision_id,
            ...basePayload,
          })
        : await api.post(`/api/v1/projects/${projectId}/knowledge`, {
            ...basePayload,
          });
      const saved = response.data.data as SemanticEntry;
      setEditorEntry(undefined);
      setEntryType(saved.entry_type);
      setState("all");
      setValidity("all");
      setSearch(saved.key);
      setOffset(0);
      setActiveId(saved.id);
      setFeedback(editorEntry ? "业务定义已更新。" : "业务定义已添加。可继续核对或验证。");
      setReloadVersion((current) => current + 1);
    } catch (requestError) {
      setEditorError(errorMessage(requestError));
    } finally {
      setSavingEditor(false);
    }
  };

  const runBatch = async (
    action: SemanticBatchAction,
    entries: SemanticEntry[] = selectedEntries
  ) => {
    if (loading || !actionAllowed(action, entries)) return;
    setBatchAction(action);
    setError(null);
    setFeedback(null);
    try {
      const response = await api.post(
        `/api/v1/projects/${projectId}/knowledge/batch`,
        {
          action,
          items: entries.map((entry) => ({
            entry_id: entry.id,
            expected_active_revision_id: entry.active_revision_id,
          })),
        }
      );
      const result = response.data.data as SemanticBatchResult;
      if (action === "queue_validation" && result.validation_prompt) {
        localStorage.setItem(PROJECT_STORAGE_KEY, projectId);
        sessionStorage.setItem(
          PENDING_TASK_STORAGE_KEY,
          JSON.stringify({
            query: result.validation_prompt,
            projectId,
            validationSelection: result.validation_selection,
          })
        );
        // The parked validation task is a new investigation: leave any open
        // conversation so the home workspace shows the pending card.
        useChatStore.getState().clearConversation({ forget: true, projectId });
        router.push("/");
        return;
      }
      setFeedback(
        action === "ignore"
          ? `已将 ${result.items.length} 条移出当前列表。`
          : action === "restore"
            ? `已恢复 ${result.items.length} 条内容。`
            : `已记住 ${result.items.length} 条经过验证的内容。`
      );
      setReloadVersion((current) => current + 1);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBatchAction(null);
    }
  };

  const editorLeftSource = sources.find((source) => source.id === editorDraft.leftSourceId);
  const editorRightSource = sources.find((source) => source.id === editorDraft.rightSourceId);
  const editorLeftTables = sourceTables(editorLeftSource);
  const editorRightTables = sourceTables(editorRightSource);
  const editorLeftColumns =
    editorLeftTables.find((table) => table.name === editorDraft.leftTable)?.columns || [];
  const editorRightColumns =
    editorRightTables.find((table) => table.name === editorDraft.rightTable)?.columns || [];

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-background text-foreground">
      <header className="flex min-h-16 shrink-0 items-center justify-between border-b border-border px-5 md:px-8">
        <div className="flex min-w-0 items-center gap-4">
          <button
            type="button"
            onClick={() => router.push("/")}
            className="inline-flex h-9 items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft size={16} />
            返回项目
          </button>
          <span className="h-5 w-px bg-border" />
          <div className="min-w-0 truncate text-sm font-semibold">
            {project?.name || "当前项目"}
          </div>
        </div>
      </header>

      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <section className="shrink-0 border-b border-border px-5 py-6 md:px-8">
          <div className="flex flex-col justify-between gap-5 xl:flex-row xl:items-end">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">项目理解</h1>
              <p className="mt-2 text-sm text-muted-foreground">管理指标、业务口径和数据关联。</p>
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-2 xl:max-w-5xl xl:flex-row">
              <label className="relative min-w-0 flex-1">
                <Search
                  size={16}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                />
                <input
                  aria-label="搜索项目理解"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="搜索名称、字段或口径"
                  className="h-10 w-full border border-border bg-background pl-9 pr-9 text-sm outline-none transition-colors focus:border-primary"
                />
                {search && (
                  <button
                    type="button"
                    aria-label="清除搜索"
                    onClick={() => setSearch("")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
                  >
                    <X size={14} />
                  </button>
                )}
              </label>
              <select
                aria-label="适用数据"
                value={sourceFilter}
                onChange={(event) => {
                  setOffset(0);
                  setSourceFilter(event.target.value as SourceFilterValue);
                }}
                className="h-10 max-w-full border border-border bg-background px-3 text-sm outline-none focus:border-primary xl:w-48"
              >
                <SourceFilterOptions sources={sources} />
              </select>
              <select
                aria-label="内容类型"
                value={entryType}
                onChange={(event) => setEntryType(event.target.value as EntryTypeFilter)}
                className="h-10 border border-border bg-background px-3 text-sm outline-none focus:border-primary"
              >
                {TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setAdvancedOpen((current) => !current)}
                aria-expanded={advancedOpen}
                aria-controls="semantic-advanced-filters"
                className={cn(
                  "inline-flex h-10 items-center justify-center gap-2 border px-3 text-sm transition-colors",
                  advancedOpen || activeFilterCount
                    ? "border-primary bg-primary/5 text-primary"
                    : "border-border text-muted-foreground hover:text-foreground"
                )}
              >
                <Filter size={15} />
                筛选{activeFilterCount ? ` · ${activeFilterCount}` : ""}
              </button>
              <button
                type="button"
                onClick={() => openEditor(null)}
                className="inline-flex h-10 shrink-0 items-center justify-center gap-2 bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
              >
                <Plus size={15} />
                新增定义
              </button>
            </div>
          </div>

          {advancedOpen && (
            <div
              id="semantic-advanced-filters"
              className="mt-4 grid gap-3 border-t border-border pt-4 sm:grid-cols-2 lg:grid-cols-4"
            >
              <select
                aria-label="治理状态"
                value={state}
                onChange={(event) => setState(event.target.value as StateFilter)}
                className="h-9 border border-border bg-background px-3 text-sm outline-none focus:border-primary"
              >
                {STATE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select
                aria-label="有效性"
                value={validity}
                onChange={(event) => setValidity(event.target.value as ValidityFilter)}
                className="h-9 border border-border bg-background px-3 text-sm outline-none focus:border-primary"
              >
                {VALIDITY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <input
                value={leftTable}
                onChange={(event) => setLeftTable(event.target.value)}
                placeholder="左侧表"
                aria-label="左侧表"
                className="h-9 border border-border bg-background px-3 text-sm outline-none focus:border-primary"
              />
              <input
                value={rightTable}
                onChange={(event) => setRightTable(event.target.value)}
                placeholder="右侧表"
                aria-label="右侧表"
                className="h-9 border border-border bg-background px-3 text-sm outline-none focus:border-primary"
              />
            </div>
          )}
        </section>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden xl:flex-row">
          <section
            aria-label="项目理解列表"
            className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
          >
            <div className="flex min-h-12 shrink-0 items-center justify-between border-b border-border px-5 md:px-8">
              <div className="text-sm text-muted-foreground">
                {loading && !page ? "正在加载" : `共 ${page?.total || 0} 条`}
                {selectedIds.size ? ` · 已选 ${selectedIds.size} 条` : ""}
              </div>
              <button
                type="button"
                aria-label="刷新列表"
                onClick={() => setReloadVersion((current) => current + 1)}
                className="p-2 text-muted-foreground transition-colors hover:text-foreground"
              >
                <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
              </button>
            </div>

            {error && (
              <div role="alert" className="mx-5 mt-4 flex shrink-0 items-center gap-2 bg-destructive/[0.06] px-3 py-2 text-sm text-destructive md:mx-8">
                <CircleAlert size={15} />
                <span className="flex-1">{error}</span>
                <button type="button" onClick={() => setReloadVersion((current) => current + 1)} className="font-medium">
                  重试
                </button>
              </div>
            )}
            {feedback && (
              <div role="status" className="mx-5 mt-4 flex shrink-0 items-center gap-2 bg-success/[0.06] px-3 py-2 text-sm text-success md:mx-8">
                <Check size={15} />
                {feedback}
              </div>
            )}

            <div className="min-h-0 flex-1 overflow-auto overscroll-contain">
              <table className="w-full min-w-[860px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-border text-[11px] font-medium text-muted-foreground">
                    <th className="w-14 px-5 py-3 text-center md:px-8">
                      <input
                        type="checkbox"
                        aria-label="选择本页"
                        checked={allPageSelected}
                        aria-checked={somePageSelected ? "mixed" : allPageSelected}
                        ref={(element) => {
                          if (element) element.indeterminate = somePageSelected;
                        }}
                        disabled={loading || selectableEntries.length === 0}
                        onChange={togglePageSelection}
                        className="accent-primary disabled:opacity-40"
                      />
                    </th>
                    <th className="px-3 py-3">名称与范围</th>
                    <th className="w-28 px-3 py-3">类型</th>
                    <th className="w-28 px-3 py-3">状态</th>
                    <th className="w-28 px-3 py-3">依据</th>
                    <th className="w-32 px-3 py-3">线索强度</th>
                    <th className="w-12 px-3 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {loading && !page ? (
                    <tr>
                      <td colSpan={7} className="h-56 text-center text-sm text-muted-foreground">
                        <Loader2 size={18} className="mx-auto mb-2 animate-spin" />
                        正在加载
                      </td>
                    </tr>
                  ) : page?.items.length ? (
                    page.items.map((entry) => {
                      const selected = selectedIds.has(entry.id);
                      const active = activeId === entry.id;
                      return (
                        <tr
                          key={entry.id}
                          aria-selected={active}
                          tabIndex={0}
                          onClick={() => setActiveId(entry.id)}
                          onKeyDown={(event) => {
                            if (event.currentTarget !== event.target) return;
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              setActiveId(entry.id);
                            }
                          }}
                          className={cn(
                            "cursor-pointer border-b border-border/80 transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/40",
                            active && "bg-primary/[0.045]"
                          )}
                        >
                          <td className="px-5 py-4 text-center md:px-8" onClick={(event) => event.stopPropagation()}>
                            <input
                              type="checkbox"
                              aria-label={`选择 ${entryTitle(entry)}`}
                              checked={selected}
                              disabled={!selectableEntries.some((item) => item.id === entry.id)}
                              onChange={() => toggleSelection(entry.id)}
                              className="accent-primary disabled:opacity-40"
                            />
                          </td>
                          <td className="max-w-0 px-3 py-4">
                            <div className="block w-full min-w-0 text-left">
                              <span className="block truncate text-sm font-medium text-foreground">
                                {entryTitle(entry)}
                              </span>
                              <span className="mt-1 block truncate text-xs text-muted-foreground">
                                适用数据 · {semanticSourceLabel(entry)} · {updatedLabel(entry.updated_at)}
                              </span>
                            </div>
                          </td>
                          <td className="px-3 py-4 text-xs text-muted-foreground">{semanticTypeLabel(entry.entry_type)}</td>
                          <td className={cn("px-3 py-4 text-xs font-medium", governanceTone(entry))}>
                            {governanceLabel(entry)}
                          </td>
                          <td className="px-3 py-4 text-xs text-muted-foreground">{evidenceLabel(entry)}</td>
                          <td className="px-3 py-4 text-xs text-muted-foreground">{semanticSignalLabel(entry)}</td>
                          <td className="px-3 py-4 text-muted-foreground">
                            <button
                              type="button"
                              aria-label={`查看 ${entryTitle(entry)}`}
                              onClick={() => setActiveId(entry.id)}
                              className="-m-2 inline-flex p-2 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                            >
                              <ChevronRight size={15} />
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={7} className="h-56 text-center">
                        <BookOpenText size={20} className="mx-auto mb-3 text-muted-foreground" />
                        <div className="text-sm font-medium">没有符合条件的内容</div>
                        <div className="mt-1 text-xs text-muted-foreground">调整搜索或筛选条件。</div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex min-h-16 shrink-0 items-center justify-between border-t border-border px-5 md:px-8">
              <div className="text-xs text-muted-foreground">
                第 {currentPage} / {pageCount} 页
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  aria-label="上一页"
                  disabled={!page || page.offset === 0 || loading}
                  onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
                  className="p-2 text-muted-foreground hover:text-foreground disabled:opacity-30"
                >
                  <ChevronLeft size={16} />
                </button>
                <button
                  type="button"
                  aria-label="下一页"
                  disabled={!page?.has_more || loading}
                  onClick={() => setOffset(page?.next_offset ?? offset + PAGE_SIZE)}
                  className="p-2 text-muted-foreground hover:text-foreground disabled:opacity-30"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </section>

          <aside
            aria-label="项目理解详情"
            className="max-h-[42dvh] min-h-0 w-full shrink-0 overflow-y-auto overscroll-contain border-t border-border bg-card xl:max-h-none xl:w-[360px] xl:border-l xl:border-t-0"
          >
            {activeEntry ? (
              <div className="p-6">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-medium text-muted-foreground">{semanticTypeLabel(activeEntry.entry_type)}</div>
                    <h2 className="mt-2 text-lg font-semibold leading-7">{entryTitle(activeEntry)}</h2>
                  </div>
                  <span className={cn("shrink-0 text-xs font-medium", governanceTone(activeEntry))}>
                    {governanceLabel(activeEntry)}
                  </span>
                </div>

                {activeEntry.entry_type === "relationship" && relationshipDefinition(activeEntry) ? (
                  <div className="mt-6 border-y border-border py-5">
                    <div className="space-y-3">
                      <div>
                        <div className="text-[10px] text-muted-foreground">左侧</div>
                        <div className="mt-1 text-sm">{endpointLabel(relationshipDefinition(activeEntry)?.left)}</div>
                      </div>
                      <ArrowRight size={14} className="text-muted-foreground" />
                      <div>
                        <div className="text-[10px] text-muted-foreground">右侧</div>
                        <div className="mt-1 text-sm">{endpointLabel(relationshipDefinition(activeEntry)?.right)}</div>
                      </div>
                    </div>
                    <div className="mt-4 border-t border-border pt-4">
                      <div className="text-[10px] text-muted-foreground">说明</div>
                      <div className="mt-1 text-sm leading-6">{activeEntry.value}</div>
                    </div>
                  </div>
                ) : (
                  <p className="mt-5 border-y border-border py-5 text-sm leading-6">{activeEntry.value}</p>
                )}

                <dl className="mt-5 grid grid-cols-2 gap-x-5 gap-y-4 text-xs">
                  <div className="col-span-2">
                    <dt className="text-muted-foreground">适用数据</dt>
                    <dd className="mt-1 font-medium">{semanticSourceLabel(activeEntry)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">依据</dt>
                    <dd className="mt-1 font-medium">{evidenceLabel(activeEntry)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">线索强度</dt>
                    <dd className="mt-1 font-medium">{semanticSignalLabel(activeEntry)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">添加方式</dt>
                    <dd className="mt-1 font-medium">
                      {activeEntry.source === "user"
                        ? "人工维护"
                        : activeEntry.source === "verified_analysis"
                          ? "调查验证"
                          : activeEntry.source === "imported"
                            ? "历史迁入"
                            : "自动发现"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">版本</dt>
                    <dd className="mt-1 font-medium">{activeEntry.revision_number || "—"}</dd>
                  </div>
                </dl>

                {activeEntry.execution_details?.summary && (
                  <div className="mt-5 border border-border bg-secondary/40 px-3 py-3 text-xs leading-5">
                    <div className="font-medium text-muted-foreground">验证依据</div>
                    <p className="mt-1 text-foreground">
                      {activeEntry.execution_details.summary}
                    </p>
                  </div>
                )}

                <div className="mt-6 space-y-2">
                  <button
                    type="button"
                    disabled={
                      !activeEntry.active_revision_id ||
                      activeEntry.is_active === false ||
                      loading ||
                      Boolean(batchAction)
                    }
                    onClick={() => openEditor(activeEntry)}
                    className="inline-flex w-full items-center justify-center gap-2 border border-border px-4 py-2.5 text-sm text-foreground hover:border-primary/50 disabled:opacity-50"
                  >
                    <PencilLine size={14} />
                    修改业务定义
                  </button>
                  {canQueueValidation(activeEntry) && (
                    <button
                      type="button"
                      disabled={loading || Boolean(batchAction)}
                      onClick={() => void runBatch("queue_validation", [activeEntry])}
                      className="inline-flex w-full items-center justify-center gap-2 bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
                    >
                      <ShieldCheck size={15} />
                      {activeEntry.entry_type === "relationship"
                        ? "验证这条关系"
                        : "用真实数据验证"}
                    </button>
                  )}
                  {canAttest(activeEntry) && (
                    <button
                      type="button"
                      disabled={loading || Boolean(batchAction)}
                      onClick={() => void runBatch("attest", [activeEntry])}
                      className="inline-flex w-full items-center justify-center gap-2 border border-primary/50 px-4 py-2.5 text-sm font-medium text-primary hover:bg-primary/5 disabled:opacity-50"
                    >
                      <UserCheck size={15} />
                      我确认无误，直接可用
                    </button>
                  )}
                  {canRemember(activeEntry) && (
                    <button
                      type="button"
                      disabled={loading || Boolean(batchAction)}
                      onClick={() => void runBatch("remember", [activeEntry])}
                      className="inline-flex w-full items-center justify-center gap-2 bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
                    >
                      <Check size={15} />
                      记住这条内容
                    </button>
                  )}
                  {canIgnore(activeEntry) && (
                    <button
                      type="button"
                      disabled={loading || Boolean(batchAction)}
                      onClick={() => void runBatch("ignore", [activeEntry])}
                      className="w-full px-4 py-2 text-sm text-muted-foreground hover:text-foreground disabled:opacity-50"
                    >
                      不采用
                    </button>
                  )}
                  {canRestore(activeEntry) && (
                    <button
                      type="button"
                      disabled={loading || Boolean(batchAction)}
                      onClick={() => void runBatch("restore", [activeEntry])}
                      className="inline-flex w-full items-center justify-center gap-2 border border-border px-4 py-2.5 text-sm text-foreground hover:border-primary/50 disabled:opacity-50"
                    >
                      <RefreshCw size={14} />
                      重新考虑
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex h-56 items-center justify-center p-6 text-center text-sm text-muted-foreground xl:h-full">
                选择一条内容查看详情
              </div>
            )}
          </aside>
        </div>
      </main>

      {editorEntry !== undefined && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/25 p-4">
          <section
            role="dialog"
            aria-modal="true"
            aria-label={editorEntry ? "编辑业务定义" : "新增业务定义"}
            className="flex max-h-[min(860px,calc(100dvh-2rem))] w-full max-w-3xl flex-col overflow-hidden bg-background shadow-2xl"
          >
            <div className="flex shrink-0 items-start justify-between border-b border-border px-6 py-5">
              <div>
                <h2 className="text-xl font-semibold">
                  {editorEntry ? "编辑业务定义" : "新增业务定义"}
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  指标、口径和关联都可以由你维护。
                </p>
              </div>
              <button
                type="button"
                aria-label="关闭编辑器"
                disabled={savingEditor}
                onClick={closeEditor}
                className="p-2 text-muted-foreground hover:text-foreground disabled:opacity-40"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={saveEditor} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              <div className="space-y-5 px-6 py-6">
                {editorError && (
                  <div role="alert" className="flex items-start gap-2 bg-destructive/[0.06] px-3 py-2.5 text-sm text-destructive">
                    <CircleAlert size={15} className="mt-0.5 shrink-0" />
                    <span>{editorError}</span>
                  </div>
                )}

                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="space-y-2 text-sm font-medium">
                    <span>定义类型</span>
                    <select
                      aria-label="定义类型"
                      value={editorDraft.entryType}
                      onChange={(event) =>
                        updateEditorDraft(
                          "entryType",
                          event.target.value as SemanticEntry["entry_type"]
                        )
                      }
                      className="h-10 w-full border border-border bg-background px-3 font-normal outline-none focus:border-primary"
                    >
                      {EDITABLE_TYPE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="space-y-2 text-sm font-medium">
                    <span>采用状态</span>
                    <select
                      aria-label="采用状态"
                      value={editorDraft.state}
                      onChange={(event) =>
                        updateEditorDraft("state", event.target.value as SemanticEntry["state"])
                      }
                      className="h-10 w-full border border-border bg-background px-3 font-normal outline-none focus:border-primary"
                    >
                      {EDITABLE_STATE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <label className="block space-y-2 text-sm font-medium">
                  <span>名称</span>
                  <input
                    aria-label="名称"
                    value={editorDraft.key}
                    onChange={(event) => updateEditorDraft("key", event.target.value)}
                    maxLength={160}
                    placeholder="例如：净收入"
                    className="h-10 w-full border border-border bg-background px-3 text-sm font-normal outline-none focus:border-primary"
                  />
                </label>

                <label className="block space-y-2 text-sm font-medium">
                  <span>业务定义</span>
                  <textarea
                    aria-label="业务定义"
                    value={editorDraft.value}
                    onChange={(event) => updateEditorDraft("value", event.target.value)}
                    rows={3}
                    placeholder="用业务语言说明它是什么、何时适用。"
                    className="w-full resize-y border border-border bg-background px-3 py-2.5 text-sm font-normal leading-6 outline-none focus:border-primary"
                  />
                </label>

                {editorDraft.entryType !== "relationship" &&
                  (definitionOwnsSourceScope(editorDraft) ? (
                    <div className="border-y border-border py-4 text-sm">
                      <div className="text-xs text-muted-foreground">适用数据</div>
                      <div className="mt-1 font-medium">
                        {editorEntry ? semanticSourceLabel(editorEntry) : "随当前定义"}
                      </div>
                    </div>
                  ) : (
                    <label className="block space-y-2 text-sm font-medium">
                      <span>适用数据</span>
                      <select
                        aria-label="适用范围"
                        value={editorDraft.scopeSource}
                        onChange={(event) =>
                          updateEditorDraft(
                            "scopeSource",
                            event.target.value as EditorScopeValue
                          )
                        }
                        className="h-10 w-full border border-border bg-background px-3 font-normal outline-none focus:border-primary"
                      >
                        <EditorScopeOptions
                          sources={sources}
                          preserveLabel={
                            editorDraft.scopeSource === "preserve"
                              ? `保持当前范围 · ${editorEntry ? semanticSourceLabel(editorEntry) : "待归类"}`
                              : undefined
                          }
                        />
                      </select>
                    </label>
                  ))}

                {editorDraft.entryType === "relationship" ? (
                  <div className="space-y-5 border-t border-border pt-5">
                    <div>
                      <h3 className="text-sm font-semibold">关联字段</h3>
                      <p className="mt-1 text-xs text-muted-foreground">选择两侧的来源、表和字段。</p>
                    </div>

                    {(["left", "right"] as const).map((side) => {
                      const isLeft = side === "left";
                      const sourceValue = isLeft
                        ? editorDraft.leftSourceId
                        : editorDraft.rightSourceId;
                      const tableValue = isLeft ? editorDraft.leftTable : editorDraft.rightTable;
                      const columnValue = isLeft ? editorDraft.leftColumn : editorDraft.rightColumn;
                      const tables = isLeft ? editorLeftTables : editorRightTables;
                      const columns = isLeft ? editorLeftColumns : editorRightColumns;
                      const sideLabel = isLeft ? "左侧" : "右侧";
                      return (
                        <fieldset key={side} className="grid gap-3 sm:grid-cols-3">
                          <legend className="mb-2 text-xs font-medium text-muted-foreground">{sideLabel}</legend>
                          <label className="space-y-1.5 text-xs font-medium">
                            <span>数据来源</span>
                            <select
                              aria-label={`${sideLabel}数据来源`}
                              value={sourceValue}
                              onChange={(event) =>
                                setEditorDraft((current) => ({
                                  ...current,
                                  [isLeft ? "leftSourceId" : "rightSourceId"]: event.target.value,
                                  [isLeft ? "leftTable" : "rightTable"]: "",
                                  [isLeft ? "leftColumn" : "rightColumn"]: "",
                                }))
                              }
                              className="h-10 w-full border border-border bg-background px-3 text-sm font-normal outline-none focus:border-primary"
                            >
                              <option value="">请选择</option>
                              {sources.map((source) => (
                                <option key={source.id} value={source.id}>
                                  {source.name}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="space-y-1.5 text-xs font-medium">
                            <span>表或视图</span>
                            <input
                              aria-label={`${sideLabel}表或视图`}
                              list={`semantic-${side}-tables`}
                              value={tableValue}
                              onChange={(event) =>
                                updateEditorDraft(
                                  isLeft ? "leftTable" : "rightTable",
                                  event.target.value
                                )
                              }
                              className="h-10 w-full border border-border bg-background px-3 text-sm font-normal outline-none focus:border-primary"
                            />
                            <datalist id={`semantic-${side}-tables`}>
                              {tables.map((table) => (
                                <option key={table.name} value={table.name} />
                              ))}
                            </datalist>
                          </label>
                          <label className="space-y-1.5 text-xs font-medium">
                            <span>字段</span>
                            <input
                              aria-label={`${sideLabel}字段`}
                              list={`semantic-${side}-columns`}
                              value={columnValue}
                              onChange={(event) =>
                                updateEditorDraft(
                                  isLeft ? "leftColumn" : "rightColumn",
                                  event.target.value
                                )
                              }
                              className="h-10 w-full border border-border bg-background px-3 text-sm font-normal outline-none focus:border-primary"
                            />
                            <datalist id={`semantic-${side}-columns`}>
                              {columns.map((column) => (
                                <option key={column.name} value={column.name} />
                              ))}
                            </datalist>
                          </label>
                        </fieldset>
                      );
                    })}

                    <div className="grid gap-3 sm:grid-cols-3">
                      <label className="space-y-1.5 text-xs font-medium">
                        <span>连接方式</span>
                        <select
                          aria-label="连接方式"
                          value={editorDraft.defaultJoin}
                          onChange={(event) =>
                            updateEditorDraft("defaultJoin", event.target.value as "left" | "inner")
                          }
                          className="h-10 w-full border border-border bg-background px-3 text-sm font-normal outline-none focus:border-primary"
                        >
                          <option value="left">保留左侧全部记录</option>
                          <option value="inner">只保留匹配记录</option>
                        </select>
                      </label>
                      <label className="space-y-1.5 text-xs font-medium">
                        <span>对应关系</span>
                        <select
                          aria-label="对应关系"
                          value={editorDraft.cardinality}
                          onChange={(event) =>
                            updateEditorDraft(
                              "cardinality",
                              event.target.value as SemanticEditorDraft["cardinality"]
                            )
                          }
                          className="h-10 w-full border border-border bg-background px-3 text-sm font-normal outline-none focus:border-primary"
                        >
                          <option value="">尚未确定</option>
                          <option value="one_to_one">一对一</option>
                          <option value="one_to_many">一对多</option>
                          <option value="many_to_one">多对一</option>
                          <option value="many_to_many">多对多</option>
                        </select>
                      </label>
                      <label className="space-y-1.5 text-xs font-medium">
                        <span>字段对齐</span>
                        <select
                          aria-label="字段对齐"
                          value={editorDraft.normalization}
                          onChange={(event) =>
                            updateEditorDraft(
                              "normalization",
                              event.target.value as SemanticEditorDraft["normalization"]
                            )
                          }
                          className="h-10 w-full border border-border bg-background px-3 text-sm font-normal outline-none focus:border-primary"
                        >
                          <option value="auto">自动选择</option>
                          <option value="exact">完全一致</option>
                          <option value="trim_casefold">忽略空格和大小写</option>
                          <option value="identifier">按编号对齐</option>
                        </select>
                      </label>
                    </div>

                    <details className="border-t border-border pt-4">
                      <summary className="cursor-pointer text-xs font-medium text-muted-foreground">验证边界</summary>
                      <div className="mt-3 grid gap-3 sm:grid-cols-2">
                        <label className="space-y-1.5 text-xs font-medium">
                          <span>最低左侧匹配率</span>
                          <input
                            aria-label="最低左侧匹配率"
                            type="number"
                            min="0"
                            max="1"
                            step="0.01"
                            value={editorDraft.minimumLeftMatchRate}
                            onChange={(event) =>
                              updateEditorDraft("minimumLeftMatchRate", event.target.value)
                            }
                            className="h-10 w-full border border-border bg-background px-3 text-sm font-normal outline-none focus:border-primary"
                          />
                        </label>
                        <label className="space-y-1.5 text-xs font-medium">
                          <span>最大行数扩张倍数</span>
                          <input
                            aria-label="最大行数扩张倍数"
                            type="number"
                            min="1"
                            step="0.01"
                            value={editorDraft.maximumExpansionRatio}
                            onChange={(event) =>
                              updateEditorDraft("maximumExpansionRatio", event.target.value)
                            }
                            className="h-10 w-full border border-border bg-background px-3 text-sm font-normal outline-none focus:border-primary"
                          />
                        </label>
                      </div>
                    </details>
                  </div>
                ) : (
                  <details className="border-t border-border pt-5">
                    <summary className="cursor-pointer text-sm font-medium">高级定义（可选）</summary>
                    <label className="mt-4 block space-y-2 text-xs font-medium text-muted-foreground">
                      <span>结构化 JSON</span>
                      <textarea
                        aria-label="扩展定义"
                        value={editorDraft.definitionText}
                        onChange={(event) => updateEditorDraft("definitionText", event.target.value)}
                        rows={7}
                        spellCheck={false}
                        placeholder={'例如 {"version": 1, "kind": "aggregate_metric", ...}'}
                        className="w-full resize-y border border-border bg-background px-3 py-2.5 font-mono text-xs font-normal leading-5 text-foreground outline-none focus:border-primary"
                      />
                    </label>
                  </details>
                )}

                <p className="text-xs leading-5 text-muted-foreground">
                  已确认和已锁定表示你认可这条定义；会影响计算的内容仍需通过执行验证。
                </p>
              </div>

              <div className="sticky bottom-0 flex items-center justify-end gap-2 border-t border-border bg-background px-6 py-4">
                <button
                  type="button"
                  disabled={savingEditor}
                  onClick={closeEditor}
                  className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground disabled:opacity-40"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={savingEditor}
                  className="inline-flex items-center gap-2 bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
                >
                  {savingEditor && <Loader2 size={14} className="animate-spin" />}
                  {editorEntry ? "保存修改" : "添加定义"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {selectedEntries.length > 0 && (
        <div className="fixed bottom-5 left-1/2 z-30 flex w-[min(720px,calc(100vw-2rem))] -translate-x-1/2 flex-wrap items-center gap-2 bg-foreground px-4 py-3 text-background shadow-2xl">
          <div className="mr-auto text-sm">已选 {selectedEntries.length} 条</div>
          <button
            type="button"
            disabled={loading || !actionAllowed("queue_validation", selectedEntries) || Boolean(batchAction)}
            onClick={() => void runBatch("queue_validation")}
            className="px-3 py-1.5 text-sm disabled:opacity-35"
          >
            验证所选
          </button>
          <button
            type="button"
            disabled={loading || !actionAllowed("attest", selectedEntries) || Boolean(batchAction)}
            onClick={() => void runBatch("attest")}
            className="px-3 py-1.5 text-sm disabled:opacity-35"
          >
            确认无误
          </button>
          <button
            type="button"
            disabled={loading || !actionAllowed("remember", selectedEntries) || Boolean(batchAction)}
            onClick={() => void runBatch("remember")}
            className="px-3 py-1.5 text-sm disabled:opacity-35"
          >
            记住所选
          </button>
          <button
            type="button"
            disabled={loading || !actionAllowed("ignore", selectedEntries) || Boolean(batchAction)}
            onClick={() => void runBatch("ignore")}
            className="px-3 py-1.5 text-sm disabled:opacity-35"
          >
            不采用
          </button>
          <button
            type="button"
            disabled={loading || !actionAllowed("restore", selectedEntries) || Boolean(batchAction)}
            onClick={() => void runBatch("restore")}
            className="px-3 py-1.5 text-sm disabled:opacity-35"
          >
            重新考虑
          </button>
          <button type="button" aria-label="清除选择" onClick={() => setSelectedIds(new Set())} className="p-1.5 opacity-70 hover:opacity-100">
            <X size={15} />
          </button>
          {batchAction && <Loader2 size={15} className="animate-spin" />}
        </div>
      )}
    </div>
  );
}
