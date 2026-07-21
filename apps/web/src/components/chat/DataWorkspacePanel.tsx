"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  BookOpenText,
  Check,
  CheckCircle2,
  ChevronDown,
  Database,
  FileSpreadsheet,
  History,
  Loader2,
  Plus,
  RefreshCw,
  RotateCcw,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import type {
  ConnectionSummary,
  PreflightIssue,
  ProjectDataSource,
  SemanticEntry,
} from "@/lib/types/api";
import { useProjectStore } from "@/lib/stores/project";
import { cn } from "@/lib/utils";
import { VisualCleaningEditor } from "./VisualCleaningEditor";

interface DataWorkspacePanelProps {
  open: boolean;
  onClose: () => void;
  onConfigureConnection: () => void;
  connections?: ConnectionSummary[];
  view?: "sources" | "understanding";
  onViewChange?: (view: "sources" | "understanding") => void;
}

function sourceStatus(status: string) {
  if (status === "ready") return { label: "可以分析", tone: "text-success bg-success/[0.06]" };
  if (status === "needs_confirmation") {
    return { label: "有口径待确认", tone: "text-warning bg-warning/[0.06]" };
  }
  if (status === "error") return { label: "需要处理", tone: "text-destructive bg-destructive/[0.06]" };
  return { label: "正在整理", tone: "text-muted-foreground bg-muted" };
}

function inferredColumnNames(schema: Record<string, unknown> | undefined): string[] {
  const columns = schema?.columns;
  if (!Array.isArray(columns)) return [];
  return columns
    .map((column) =>
      column && typeof column === "object" && "name" in column
        ? String(column.name || "").trim()
        : ""
    )
    .filter(Boolean);
}

const FIELD_WORDS: Record<string, string> = {
  unit: "单位",
  price: "价格",
  cost: "成本",
  total: "总计",
  amount: "金额",
  revenue: "收入",
  sales: "销售额",
  order: "订单",
  id: "编号",
  date: "日期",
  time: "时间",
  store: "门店",
  shop: "门店",
  channel: "渠道",
  category: "品类",
  product: "商品",
  quantity: "数量",
  qty: "数量",
  discount: "折扣",
  refund: "退款",
  profit: "利润",
};

function businessFieldLabel(value: string): string | null {
  const normalized = value.trim().replace(/([a-z])([A-Z])/g, "$1_$2").toLowerCase();
  const parts = normalized.split(/[_\s.-]+/).filter(Boolean);
  if (!parts.length || !parts.every((part) => FIELD_WORDS[part])) return null;
  return parts.map((part) => FIELD_WORDS[part]).join("");
}

function businessIssueTitle(issue: PreflightIssue): string {
  const fieldMatch = issue.title.match(/^([^“”]+?)\s*中有\s*(\d+)\s*个(.+)$/);
  if (fieldMatch) {
    const [, rawField, count, description] = fieldMatch;
    const label = businessFieldLabel(rawField);
    if (label) return `${label}有 ${count} 个${description}`;
    if (issue.code === "possible_outliers") return `发现 ${count} 个明显偏离的数值`;
    if (issue.code === "invalid_currency_values") return `发现 ${count} 个无法识别的金额`;
    if (issue.code === "invalid_date_values") return `发现 ${count} 个无法识别的日期`;
  }
  const duplicateKeyMatch = issue.title.match(/^(.+?)\s+有\s+(\d+)\s+条重复出现$/);
  if (duplicateKeyMatch && issue.code === "duplicate_business_keys") {
    const [, rawField, count] = duplicateKeyMatch;
    const label = businessFieldLabel(rawField);
    return label
      ? `${label}有 ${count} 条重复出现`
      : `发现 ${count} 条可能重复的业务编号`;
  }
  return issue.title;
}

function businessColumnSummary(values: unknown): string | null {
  if (!Array.isArray(values) || !values.length) return null;
  const known = Array.from(
    new Set(
      values
        .map((value) => businessFieldLabel(String(value)))
        .filter((value): value is string => Boolean(value))
    )
  );
  const hiddenCount = values.length - known.length;
  return [known.join("、"), hiddenCount > 0 ? `另有 ${hiddenCount} 项` : ""]
    .filter(Boolean)
    .join("，");
}

function knowledgeKindLabel(kind: SemanticEntry["entry_type"]): string {
  if (kind === "metric") return "指标口径";
  if (kind === "dimension") return "数据粒度";
  if (kind === "relationship") return "数据关联";
  if (kind === "cleaning_rule") return "整理方式";
  if (kind === "verified_query") return "已验证方法";
  return "业务口径";
}

function isBusinessFacingKnowledge(entry: SemanticEntry): boolean {
  if (entry.entry_type === "verified_query") return false;
  if (
    entry.entry_type === "cleaning_rule" &&
    /^[\[{]/.test(entry.value.trim())
  ) {
    return false;
  }
  return true;
}

export function getPendingUnderstandingCount(knowledge: SemanticEntry[]): number {
  const visibleKnowledge = knowledge
    .filter(isBusinessFacingKnowledge)
    .filter((entry) => !(entry.state === "candidate" && entry.validity === "stale"));
  return visibleKnowledge.filter((entry) => entry.state === "candidate").length;
}

function knowledgeDisplayValue(entry: SemanticEntry): string {
  if (entry.entry_type === "relationship" && entry.state === "candidate") {
    return "发现两份数据可能可以关联；第一次使用前会检查匹配率和重复扩张。";
  }
  return entry.value.replace(/\b[a-zA-Z][a-zA-Z0-9_.-]*\b/g, (token) => {
    const lastPart = token.split(".").at(-1) || token;
    const businessLabel = businessFieldLabel(lastPart);
    if (businessLabel) return businessLabel;
    return token.includes("_") || token.includes(".") || /[a-z][A-Z]/.test(token)
      ? "相关字段"
      : token;
  });
}

function revisionTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间待确认";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function UnderstandingMap({
  sources,
  knowledgeCount,
  relationshipCount,
}: {
  sources: ProjectDataSource[];
  knowledgeCount: number;
  relationshipCount: number;
}) {
  const firstSource = sources[0];
  const secondSource = sources[1];

  if (!firstSource) {
    return (
      <button
        type="button"
        className="flex min-h-40 w-full items-center justify-center border border-dashed border-border bg-background/70 px-6 text-center text-xs leading-5 text-muted-foreground"
      >
        加入数据后，这里会展示 ReceiptBI 理解到的来源、关联和业务口径。
      </button>
    );
  }

  return (
    <div className="overflow-x-auto border border-border bg-background/70">
      <div className="relative h-[220px] min-w-[590px]" aria-label="项目数据理解关系图">
        <svg
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 h-full w-full text-primary/45"
          viewBox="0 0 590 220"
          preserveAspectRatio="none"
        >
          <path
            d="M 180 72 C 226 72, 224 142, 270 142"
            fill="none"
            stroke="currentColor"
            strokeDasharray="6 6"
            strokeLinecap="round"
            strokeWidth="1.5"
          />
          {secondSource && (
            <path
              d="M 420 72 C 374 72, 376 142, 330 142"
              fill="none"
              stroke="currentColor"
              strokeDasharray="6 6"
              strokeLinecap="round"
              strokeWidth="1.5"
            />
          )}
        </svg>

        {[firstSource, secondSource]
          .filter((source): source is ProjectDataSource => Boolean(source))
          .map((source, index) => (
          <div
            key={`${source.id}-${index}`}
            className={cn(
              "absolute top-7 w-[160px] border border-primary/20 bg-card px-3.5 py-3",
              index === 0 ? "left-5" : "right-5"
            )}
          >
            <div className="flex items-center gap-2 text-[10px] font-semibold tracking-[0.12em] text-muted-foreground">
              {source.kind === "connection" ? <Database size={13} /> : <FileSpreadsheet size={13} />}
              数据来源
            </div>
            <div className="mt-2 truncate text-sm font-semibold text-foreground">{source.name}</div>
            <div className="mt-1 text-[11px] text-success">可以分析</div>
          </div>
          ))}

        <div className="absolute bottom-6 left-1/2 w-[180px] -translate-x-1/2 border border-success/40 bg-success/[0.06] px-4 py-3">
          <div className="flex items-center gap-2 text-[10px] font-semibold tracking-[0.12em] text-success">
            <BookOpenText size={13} />
            项目理解
          </div>
          <div className="mt-2 text-sm font-semibold text-foreground">{knowledgeCount} 条项目理解</div>
          <div className="mt-1 text-[11px] text-muted-foreground">
            {relationshipCount ? `${relationshipCount} 条关联路径` : "关联会在用到时验证"}
          </div>
        </div>
      </div>
    </div>
  );
}

export function DataWorkspacePanel({
  open,
  onClose,
  onConfigureConnection,
  connections,
  view,
  onViewChange,
}: DataWorkspacePanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [localView, setLocalView] = useState<"sources" | "understanding">("sources");
  const activeView = view || localView;
  const changeView = (nextView: "sources" | "understanding") => {
    if (view === undefined) setLocalView(nextView);
    onViewChange?.(nextView);
  };
  const [expandedSourceId, setExpandedSourceId] = useState<string | null>(null);
  const [expandedRecipeHistoryIds, setExpandedRecipeHistoryIds] = useState<string[]>([]);
  const [pendingRecipeRestore, setPendingRecipeRestore] = useState<{
    recipeId: string;
    revisionId: string;
  } | null>(null);
  const [recipeHistoryFeedback, setRecipeHistoryFeedback] = useState<{
    recipeId: string;
    message: string;
  } | null>(null);
  const [removingSourceId, setRemovingSourceId] = useState<string | null>(null);
  const [cleaningSourceId, setCleaningSourceId] = useState<string | null>(null);
  const [sourceFeedback, setSourceFeedback] = useState<{
    sourceId: string;
    tone: "success" | "error";
    message: string;
  } | null>(null);
  const [templateSourceById, setTemplateSourceById] = useState<Record<string, string>>({});
  const [templateFeedback, setTemplateFeedback] = useState<{
    templateId: string;
    tone: "success" | "error";
    message: string;
  } | null>(null);
  const {
    currentProjectId,
    sources,
    preflightReports,
    recipes,
    recipeRevisionsByRecipe,
    recipeRevisionLoadingByRecipe,
    recipeRevisionRestoringByRecipe,
    recipeRevisionErrorByRecipe,
    recipeTemplates,
    recipeTemplatePreviewById,
    recipeTemplateAction,
    knowledge,
    knowledgeTotal,
    pendingKnowledgeCount,
    relationshipKnowledgeCount,
    isUploading,
    sourceAction,
    error,
    uploadFile,
    attachConnection,
    profileSource,
    loadRecipeRevisions,
    restoreRecipeRevision,
    previewRecipeTemplate,
    bindRecipeTemplate,
    reorganizeSource,
    acceptReplacement,
    keepTrustedSource,
    removeSource,
  } = useProjectStore();

  const attachedConnections = new Set(
    sources.map((source) => source.connection_id).filter(Boolean)
  );

  const acceptFile = (file?: File) => {
    if (file) void uploadFile(file);
  };

  const performSourceAction = async (
    sourceId: string,
    action: () => Promise<void>,
    successMessage: string
  ) => {
    setSourceFeedback(null);
    try {
      await action();
      setSourceFeedback({ sourceId, tone: "success", message: successMessage });
    } catch {
      setSourceFeedback({
        sourceId,
        tone: "error",
        message: "这次处理没有完成，请查看上方提示后重试。",
      });
    }
  };

  const toggleRecipeHistory = (recipeId: string) => {
    const opening = !expandedRecipeHistoryIds.includes(recipeId);
    setExpandedRecipeHistoryIds((current) =>
      opening ? [...current, recipeId] : current.filter((id) => id !== recipeId)
    );
    if (!opening) {
      if (pendingRecipeRestore?.recipeId === recipeId) setPendingRecipeRestore(null);
      return;
    }
    if (recipeHistoryFeedback?.recipeId === recipeId) setRecipeHistoryFeedback(null);
    if (
      !(recipeId in recipeRevisionsByRecipe) &&
      !recipeRevisionLoadingByRecipe[recipeId]
    ) {
      void loadRecipeRevisions(recipeId).catch(() => undefined);
    }
  };

  const performRecipeRestore = async (recipeId: string, revisionId: string) => {
    setRecipeHistoryFeedback(null);
    try {
      await restoreRecipeRevision(recipeId, revisionId);
      setPendingRecipeRestore(null);
      setRecipeHistoryFeedback({
        recipeId,
        message: "已恢复这套整理方法；点击“重新应用”后才会用于当前分析。",
      });
    } catch {
      setPendingRecipeRestore(null);
    }
  };

  const performTemplatePreview = async (templateId: string, sourceId: string) => {
    setTemplateFeedback(null);
    try {
      await previewRecipeTemplate(templateId, sourceId);
    } catch {
      setTemplateFeedback({
        templateId,
        tone: "error",
        message: "没有完成试运行，当前分析数据保持不变。",
      });
    }
  };

  const performTemplateBind = async (templateId: string) => {
    setTemplateFeedback(null);
    try {
      await bindRecipeTemplate(templateId);
      setTemplateFeedback({
        templateId,
        tone: "success",
        message: "已用于这份数据；原文件没有改变。",
      });
    } catch {
      setTemplateFeedback({
        templateId,
        tone: "error",
        message: "数据刚刚发生了变化，请重新查看后再应用。",
      });
    }
  };

  const visibleKnowledge = knowledge
    .filter(isBusinessFacingKnowledge)
    .filter((entry) => !(entry.state === "candidate" && entry.validity === "stale"))
    .sort((left, right) => {
      const priority = { candidate: 0, confirmed: 1, locked: 2 };
      return priority[left.state] - priority[right.state];
    });
  const displayedKnowledge = visibleKnowledge.slice(0, 8);
  const cleaningSource = sources.find((source) => source.id === cleaningSourceId);
  const cleaningRecipe = recipes.find(
    (recipe) => recipe.data_source_id === cleaningSourceId,
  );
  const cleaningReport = preflightReports.find(
    (report) => report.data_source_id === cleaningSourceId,
  );
  const cleaningColumns = Array.from(
    new Set(
      [
        ...(cleaningSource?.profile_data.sample || []).flatMap((row) =>
          Object.keys(row),
        ),
        ...inferredColumnNames(cleaningReport?.inferred_schema),
      ],
    ),
  );

  return (
    <>
    <aside
      className={cn(
        "fixed inset-0 z-40 h-full w-full overflow-hidden border-l border-border bg-card shadow-2xl transition-transform duration-200 md:inset-y-0 md:left-auto md:right-0 md:w-[540px] md:max-w-[calc(100vw-2rem)]",
        open ? "translate-x-0" : "pointer-events-none translate-x-full border-l-0"
      )}
      aria-hidden={!open}
      inert={!open}
    >
      <div className="flex h-full w-full min-w-0 flex-col">
        <div className="flex items-start justify-between px-5 py-5">
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              {activeView === "sources" ? "数据" : "数据理解"}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="关闭数据工作区"
          >
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-2 border-y border-border px-5" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeView === "sources"}
            onClick={() => changeView("sources")}
            className={cn(
              "border-b-2 px-1 py-3 text-sm font-medium transition-colors",
              activeView === "sources"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            数据来源
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeView === "understanding"}
            onClick={() => changeView("understanding")}
            className={cn(
              "border-b-2 px-1 py-3 text-sm font-medium transition-colors",
              activeView === "understanding"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            数据理解
            {pendingKnowledgeCount > 0 && (
              <span className="ml-1.5 bg-warning/15 px-1.5 py-0.5 text-[10px] text-warning">
                {pendingKnowledgeCount}
              </span>
            )}
          </button>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
          {activeView === "sources" ? (
            <>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.xls,.xlsx,.parquet,.json"
            className="hidden"
            onChange={(event) => acceptFile(event.target.files?.[0])}
          />
          <button
            type="button"
            disabled={!currentProjectId || isUploading}
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              acceptFile(event.dataTransfer.files?.[0]);
            }}
            className={cn(
              "flex w-full flex-col items-center border border-dashed px-5 py-7 text-center transition-colors",
              dragging
                ? "border-primary bg-primary/5"
                : "border-border bg-muted/30 hover:border-primary/60 hover:bg-primary/5"
            )}
          >
            {isUploading ? (
              <Loader2 className="animate-spin text-primary" size={24} />
            ) : (
              <UploadCloud className="text-primary" size={24} />
            )}
            <span className="mt-3 text-sm font-semibold text-foreground">
              {isUploading ? "正在识别、整理和检查…" : "加入一份文件"}
            </span>
            <span className="mt-1 text-xs text-muted-foreground">
              Excel、CSV、Parquet、JSON
            </span>
          </button>

          {error && (
            <div className="flex gap-2 border border-destructive/30 bg-destructive/[0.06] px-3 py-3 text-xs leading-5 text-destructive">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              {error}
            </div>
          )}

          {recipeTemplates.length > 0 && (
            <section>
              <div className="mb-3 flex items-end justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    项目记住的整理方法
                  </h3>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    先看变化，确认后才会用于当前分析。
                  </p>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {recipeTemplates.length} 套
                </span>
              </div>
              <div className="space-y-2">
                {recipeTemplates.map((template) => {
                  const compatibleSources = sources.filter((source) =>
                    template.compatible_source_ids.includes(source.id)
                  );
                  const selectedSourceId =
                    templateSourceById[template.id] || compatibleSources[0]?.id || "";
                  const preview = recipeTemplatePreviewById[template.id];
                  const visiblePreview =
                    preview?.source_id === selectedSourceId ? preview : undefined;
                  const busy = recipeTemplateAction?.templateId === template.id;
                  const rowsRemoved = visiblePreview
                    ? visiblePreview.before.rows - visiblePreview.after.rows
                    : 0;
                  const columnsChanged = visiblePreview
                    ? visiblePreview.after.columns - visiblePreview.before.columns
                    : 0;
                  const feedback =
                    templateFeedback?.templateId === template.id
                      ? templateFeedback
                      : null;
                  return (
                    <div
                      key={template.id}
                      className="border border-border bg-background px-3 py-3"
                    >
                      <div className="flex items-start gap-3">
                        <History size={17} className="mt-0.5 shrink-0 text-primary" />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-foreground">
                            {template.name}
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            保留了 {template.revision_count} 次调整记录
                          </div>
                        </div>
                      </div>

                      {compatibleSources.length > 0 ? (
                        <div className="mt-3 space-y-2 border-t border-border pt-3">
                          {compatibleSources.length > 1 && (
                            <label className="block text-xs text-muted-foreground">
                              用于哪份数据
                              <select
                                value={selectedSourceId}
                                onChange={(event) =>
                                  setTemplateSourceById((current) => ({
                                    ...current,
                                    [template.id]: event.target.value,
                                  }))
                                }
                                className="mt-1.5 w-full border border-border bg-card px-2.5 py-2 text-sm text-foreground outline-none focus:border-primary"
                              >
                                {compatibleSources.map((source) => (
                                  <option key={source.id} value={source.id}>
                                    {source.name}
                                  </option>
                                ))}
                              </select>
                            </label>
                          )}
                          {!visiblePreview && (
                            <button
                              type="button"
                              disabled={busy || !selectedSourceId}
                              onClick={() =>
                                void performTemplatePreview(template.id, selectedSourceId)
                              }
                              className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline disabled:opacity-50"
                            >
                              {busy && recipeTemplateAction?.kind === "preview" ? (
                                <Loader2 size={13} className="animate-spin" />
                              ) : (
                                <RefreshCw size={13} />
                              )}
                              看看会有什么变化
                            </button>
                          )}

                          {visiblePreview && (
                            <div className="border border-success/30 bg-success/[0.05] px-3 py-3">
                              <div className="grid grid-cols-2 gap-3">
                                <div>
                                  <div className="text-[11px] text-muted-foreground">整理前</div>
                                  <div className="mt-1 text-sm font-semibold text-foreground">
                                    {visiblePreview.before.rows.toLocaleString()} 行 · {visiblePreview.before.columns} 项内容
                                  </div>
                                </div>
                                <div>
                                  <div className="text-[11px] text-muted-foreground">整理后</div>
                                  <div className="mt-1 text-sm font-semibold text-foreground">
                                    {visiblePreview.after.rows.toLocaleString()} 行 · {visiblePreview.after.columns} 项内容
                                  </div>
                                </div>
                              </div>
                              <div className="mt-2 text-xs leading-5 text-muted-foreground">
                                {rowsRemoved > 0
                                  ? `会排除 ${rowsRemoved.toLocaleString()} 行不进入分析。`
                                  : "记录数量不会改变。"}
                                {columnsChanged !== 0
                                  ? ` 内容项会${columnsChanged > 0 ? "增加" : "减少"} ${Math.abs(columnsChanged)} 项。`
                                  : " 内容项数量不会改变。"}
                              </div>
                              {visiblePreview.issues.slice(0, 4).map((issue, index) => (
                                <div
                                  key={`${issue.code}-${index}`}
                                  className="mt-1.5 flex items-start gap-1.5 text-xs leading-5 text-muted-foreground"
                                >
                                  <CheckCircle2
                                    size={13}
                                    className="mt-0.5 shrink-0 text-success"
                                  />
                                  {businessIssueTitle(issue)}
                                </div>
                              ))}
                              <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
                                当前分析数据尚未改变。
                              </p>
                              <div className="mt-3 flex flex-wrap gap-3">
                                {visiblePreview.can_apply && (
                                  <button
                                    type="button"
                                    disabled={busy}
                                    onClick={() => void performTemplateBind(template.id)}
                                    className="inline-flex items-center gap-1.5 bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                                  >
                                    {busy && recipeTemplateAction?.kind === "bind" ? (
                                      <Loader2 size={13} className="animate-spin" />
                                    ) : (
                                      <Check size={13} />
                                    )}
                                    使用这套方法
                                  </button>
                                )}
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={() =>
                                    void performTemplatePreview(template.id, selectedSourceId)
                                  }
                                  className="text-xs font-semibold text-muted-foreground hover:text-primary disabled:opacity-50"
                                >
                                  重新查看
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      ) : (
                        <p className="mt-3 border-t border-border pt-3 text-xs leading-5 text-muted-foreground">
                          当前没有需要绑定的数据；这套方法仍会留在项目中供新数据复用。
                        </p>
                      )}

                      {feedback && (
                        <div
                          role={feedback.tone === "error" ? "alert" : "status"}
                          className={cn(
                            "mt-3 border px-3 py-2 text-xs leading-5",
                            feedback.tone === "success"
                              ? "border-success/30 bg-success/[0.06] text-success"
                              : "border-destructive/30 bg-destructive/[0.06] text-destructive"
                          )}
                        >
                          {feedback.message}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          <section>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground">项目里的数据</h3>
              <span className="text-xs text-muted-foreground">{sources.length} 项</span>
            </div>
            <div className="space-y-2">
              {sources.map((source) => {
                const report = preflightReports.find(
                  (item) => item.data_source_id === source.id
                );
                const recipe = recipes.find(
                  (item) => item.data_source_id === source.id
                );
                const recipeHistoryOpen = recipe
                  ? expandedRecipeHistoryIds.includes(recipe.id)
                  : false;
                const recipeRevisions = recipe
                  ? recipeRevisionsByRecipe[recipe.id] || []
                  : [];
                const replacement = report?.source_snapshot?.replacement;
                const isPendingReplacement =
                  (source.profile_data.activation_state === "pending_confirmation" &&
                    Boolean(source.profile_data.replacement_of)) ||
                  (replacement?.status === "pending_confirmation" &&
                    Boolean(
                      replacement.replaces_source_id || replacement.active_source_id
                    ));
                const status = isPendingReplacement
                  ? { label: "等你选择", tone: "text-warning bg-warning/[0.06]" }
                  : sourceStatus(source.status);
                const needsAction =
                  source.status === "needs_confirmation" || source.status === "error";
                const detailsOpen = expandedSourceId === source.id;
                const removing = removingSourceId === source.id;
                const busy = sourceAction?.sourceId === source.id;
                const drift = report?.source_snapshot?.schema_drift;
                return (
                  <div key={source.id} className="border border-border bg-background px-3 py-3">
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 text-primary">
                        {source.kind === "file" ? (
                          <FileSpreadsheet size={18} />
                        ) : (
                          <Database size={18} />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-foreground">
                          {source.name}
                        </div>
                        <div className="mt-1 text-xs leading-5 text-muted-foreground">
                          {report?.summary || source.profile_data.summary || "正在了解这份数据"}
                        </div>
                      </div>
                      <span className={cn("shrink-0 px-2 py-1 text-[11px]", status.tone)}>
                        {status.label}
                      </span>
                    </div>

                    {source.kind === "file" && (
                      <div className="mt-3 border-t border-border pt-3">
                        <button
                          type="button"
                          onClick={() => setCleaningSourceId(source.id)}
                          className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
                        >
                          <FileSpreadsheet size={13} />
                          整理数据
                        </button>
                      </div>
                    )}

                    {source.status === "attached" && (
                      <div className="mt-3 border-t border-border pt-3">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() =>
                            void performSourceAction(
                              source.id,
                              () => profileSource(source.id),
                              "已经了解完这份数据。"
                            )
                          }
                          className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline disabled:opacity-50"
                        >
                          {busy && sourceAction?.kind === "profile" ? (
                            <Loader2 size={13} className="animate-spin" />
                          ) : (
                            <Database size={13} />
                          )}
                          了解这份数据
                        </button>
                      </div>
                    )}

                    {needsAction && (
                      <div className="mt-3 border-t border-border pt-3">
                        {isPendingReplacement && (
                          <div className="mb-3 border border-warning/30 bg-warning/[0.06] px-3 py-3 text-xs leading-5 text-warning">
                            <p>
                              这版数据还没有用于分析。看过变化后，请明确选择以后使用哪一版。
                            </p>
                            <div className="mt-2 flex flex-wrap gap-2">
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() =>
                                  void performSourceAction(
                                    source.id,
                                    () => acceptReplacement(source.id),
                                    "已接受这版；今后的调查会使用它，上个可信版本仍保留在历史中。"
                                  )
                                }
                                className="inline-flex items-center gap-1.5 bg-primary px-3 py-2 font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                              >
                                {busy && sourceAction?.kind === "accept_replacement" ? (
                                  <Loader2 size={13} className="animate-spin" />
                                ) : (
                                  <Check size={13} />
                                )}
                                接受这版并用于以后
                              </button>
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() =>
                                  void performSourceAction(
                                    source.id,
                                    () => keepTrustedSource(source.id),
                                    "已继续使用上个可信版本；这版不会用于调查。"
                                  )
                                }
                                className="inline-flex items-center gap-1.5 border border-warning/40 bg-background px-3 py-2 font-semibold text-foreground hover:border-primary hover:text-primary disabled:opacity-50"
                              >
                                {busy && sourceAction?.kind === "keep_trusted" ? (
                                  <Loader2 size={13} className="animate-spin" />
                                ) : (
                                  <RotateCcw size={13} />
                                )}
                                继续使用上个可信版本
                              </button>
                            </div>
                          </div>
                        )}
                        <div className="flex flex-wrap gap-x-3 gap-y-2 text-xs">
                          <button
                            type="button"
                            aria-expanded={detailsOpen}
                            onClick={() =>
                              setExpandedSourceId(detailsOpen ? null : source.id)
                            }
                            className="inline-flex items-center gap-1 font-semibold text-foreground hover:text-primary"
                          >
                            <ChevronDown
                              size={13}
                              className={cn("transition-transform", detailsOpen && "rotate-180")}
                            />
                            查看变化
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            title="只会重新检查和整理，不会启用这版数据"
                            onClick={() =>
                              void performSourceAction(
                                source.id,
                                () => reorganizeSource(source.id),
                                "已重新尝试整理；如果变化仍会影响结论，仍需你明确选择。"
                              )
                            }
                            className="inline-flex items-center gap-1 text-muted-foreground hover:text-primary disabled:opacity-50"
                          >
                            {busy && sourceAction?.kind === "reorganize" ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : (
                              <RefreshCw size={12} />
                            )}
                            重新整理
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => setRemovingSourceId(source.id)}
                            className="inline-flex items-center gap-1 text-muted-foreground hover:text-destructive disabled:opacity-50"
                          >
                            <Trash2 size={12} />
                            移除来源
                          </button>
                        </div>

                        {removing && (
                          <div className="mt-3 border border-destructive/30 bg-destructive/[0.06] px-3 py-3 text-xs leading-5 text-destructive">
                            <p>
                              只会移除 ReceiptBI 保存的工作副本和项目记录；原始文件或数据库不会改变。
                            </p>
                            <div className="mt-2 flex gap-3">
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() =>
                                  void performSourceAction(
                                    source.id,
                                    async () => {
                                      await removeSource(source.id);
                                      setRemovingSourceId(null);
                                    },
                                    "来源已移除。"
                                  )
                                }
                                className="inline-flex items-center gap-1 font-semibold text-destructive hover:underline disabled:opacity-50"
                              >
                                {busy && sourceAction?.kind === "remove" && (
                                  <Loader2 size={12} className="animate-spin" />
                                )}
                                确认移除
                              </button>
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => setRemovingSourceId(null)}
                                className="text-muted-foreground hover:text-foreground disabled:opacity-50"
                              >
                                取消
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {sourceFeedback?.sourceId === source.id && (
                      <div
                        role={sourceFeedback.tone === "error" ? "alert" : "status"}
                        className={cn(
                          "mt-3 border px-3 py-2 text-xs leading-5",
                          sourceFeedback.tone === "success"
                            ? "border-success/30 bg-success/[0.06] text-success"
                            : "border-destructive/30 bg-destructive/[0.06] text-destructive"
                        )}
                      >
                        {sourceFeedback.message}
                      </div>
                    )}

                    {report?.issues?.length && (!needsAction || detailsOpen) ? (
                      <div className="mt-3 border-t border-border pt-2">
                        {needsAction && (
                          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                            {source.status === "error" ? "没有完成的原因" : "这次发现的变化"}
                          </div>
                        )}
                        {report.issues.slice(0, needsAction ? 8 : 3).map((issue, issueIndex) => (
                          <div
                            key={`${issue.code}-${issue.title}-${issueIndex}`}
                            className={cn(
                              "flex items-start gap-2 py-1 text-xs",
                              issue.automatic ? "text-muted-foreground" : "text-warning"
                            )}
                          >
                            {issue.automatic ? (
                              <CheckCircle2
                                size={13}
                                className="mt-0.5 shrink-0 text-success"
                              />
                            ) : (
                              <AlertCircle
                                size={13}
                                className="mt-0.5 shrink-0 text-warning"
                              />
                            )}
                            {businessIssueTitle(issue)}
                          </div>
                        ))}
                        {drift && detailsOpen && (
                          <div className="mt-2 border-l-2 border-primary/40 bg-muted/40 px-2.5 py-2 text-xs leading-5 text-muted-foreground">
                            {businessColumnSummary(drift.added_columns) ? (
                              <div>新增内容：{businessColumnSummary(drift.added_columns)}</div>
                            ) : null}
                            {businessColumnSummary(drift.removed_columns) ? (
                              <div>本期缺少：{businessColumnSummary(drift.removed_columns)}</div>
                            ) : null}
                            {drift.type_changes?.length ? (
                              <div>
                                记录方式变化：
                                {businessColumnSummary(
                                  drift.type_changes.map((item) => item.column).filter(Boolean)
                                ) || `${drift.type_changes.length} 项`}
                              </div>
                            ) : null}
                          </div>
                        )}
                        {report.ambiguities?.length ? (
                          <div className="mt-2 flex items-start gap-2 border-l-2 border-warning/50 bg-warning/[0.06] px-2.5 py-2 text-xs leading-5 text-warning">
                            <AlertCircle size={13} className="mt-0.5 shrink-0 text-warning" />
                            <span>
                              发现 {report.ambiguities.length} 项可能影响结论的业务口径；
                              只有当前调查用到时才会请你确认。
                            </span>
                          </div>
                        ) : null}
                        {needsAction && detailsOpen && (
                          <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
                            ReceiptBI 只在工作副本中整理；原始文件和数据库保持不变。
                          </p>
                        )}
                      </div>
                    ) : null}

                    {recipe && (
                      <div className="mt-3 border-t border-border pt-3">
                        <div className="flex items-center justify-between gap-3">
                          <button
                            type="button"
                            aria-expanded={recipeHistoryOpen}
                            onClick={() => toggleRecipeHistory(recipe.id)}
                            className="inline-flex items-center gap-1.5 text-xs font-semibold text-foreground hover:text-primary"
                          >
                            <History size={12} />
                            整理方法记录
                            {recipeRevisions.length ? ` ${recipeRevisions.length}` : ""}
                            <ChevronDown
                              size={12}
                              className={cn(
                                "transition-transform",
                                recipeHistoryOpen && "rotate-180"
                              )}
                            />
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() =>
                              void performSourceAction(
                                source.id,
                                () => reorganizeSource(source.id),
                                "已按当前整理方法重新检查；影响结论的变化仍会等你确认。"
                              )
                            }
                            className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-primary disabled:opacity-50"
                          >
                            {busy && sourceAction?.kind === "reorganize" ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : (
                              <RefreshCw size={12} />
                            )}
                            重新应用
                          </button>
                        </div>

                        {recipeHistoryOpen && (
                          <div className="mt-3">
                            {recipeRevisionLoadingByRecipe[recipe.id] && (
                              <div
                                role="status"
                                className="flex items-center gap-2 py-2 text-xs text-muted-foreground"
                              >
                                <Loader2 size={13} className="animate-spin" />
                                正在读取整理方法记录…
                              </div>
                            )}
                            {!recipeRevisionLoadingByRecipe[recipe.id] &&
                              recipeRevisionErrorByRecipe[recipe.id] && (
                                <div
                                  role="alert"
                                  className="border border-destructive/30 bg-destructive/[0.06] px-3 py-2 text-xs leading-5 text-destructive"
                                >
                                  <p>{recipeRevisionErrorByRecipe[recipe.id]}</p>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      void loadRecipeRevisions(recipe.id).catch(
                                        () => undefined
                                      )
                                    }
                                    className="mt-1 font-semibold hover:underline"
                                  >
                                    重试
                                  </button>
                                </div>
                              )}
                            {!recipeRevisionLoadingByRecipe[recipe.id] &&
                              !recipeRevisionErrorByRecipe[recipe.id] &&
                              recipeRevisions.length > 0 && (
                                <ol className="ml-1 space-y-3 border-l border-border pl-4">
                                  {recipeRevisions.map((revision) => {
                                    const current =
                                      revision.id === recipe.active_revision_id;
                                    const pending =
                                      pendingRecipeRestore?.recipeId === recipe.id &&
                                      pendingRecipeRestore.revisionId === revision.id;
                                    const restoring =
                                      recipeRevisionRestoringByRecipe[recipe.id];
                                    const formattedTime = revisionTime(
                                      revision.created_at
                                    );
                                    const summary =
                                      revision.reason ||
                                      (revision.state === "candidate"
                                        ? "这版整理方法仍在等待核对。"
                                        : revision.state === "reverted"
                                          ? "恢复了一套较早的整理方法。"
                                          : "这版整理方法已经核对。");
                                    return (
                                      <li key={revision.id} className="relative">
                                        <span
                                          aria-hidden="true"
                                          className={cn(
                                            "absolute -left-[21px] top-1.5 h-2 w-2 rounded-full border-2 border-background",
                                            current ? "bg-success" : "bg-muted-foreground/30"
                                          )}
                                        />
                                        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                                          <time dateTime={revision.created_at}>
                                            {formattedTime}
                                          </time>
                                          {current && (
                                            <span className="bg-success/[0.06] px-1.5 py-0.5 text-success">
                                              {recipe.status === "reverted"
                                                ? "待重新应用"
                                                : "当前方法"}
                                            </span>
                                          )}
                                        </div>
                                        <p className="mt-1 text-xs leading-5 text-foreground">
                                          {summary}
                                        </p>
                                        {!current && !pending && (
                                          <button
                                            type="button"
                                            disabled={Boolean(restoring)}
                                            aria-label={`恢复 ${formattedTime} 的整理方法`}
                                            onClick={() =>
                                              setPendingRecipeRestore({
                                                recipeId: recipe.id,
                                                revisionId: revision.id,
                                              })
                                            }
                                            className="mt-1 text-[11px] font-semibold text-primary hover:underline disabled:opacity-50"
                                          >
                                            恢复这一版
                                          </button>
                                        )}
                                        {pending && (
                                          <div className="mt-2 border border-warning/30 bg-warning/[0.06] px-2.5 py-2 text-[11px] leading-5 text-warning">
                                            <p>
                                              恢复后不会立刻改变当前分析；你还需要点击“重新应用”。
                                            </p>
                                            <div className="mt-1.5 flex gap-3">
                                              <button
                                                type="button"
                                                disabled={Boolean(restoring)}
                                                onClick={() =>
                                                  void performRecipeRestore(
                                                    recipe.id,
                                                    revision.id
                                                  )
                                                }
                                                className="font-semibold text-primary hover:underline disabled:opacity-50"
                                              >
                                                {restoring === revision.id
                                                  ? "正在恢复…"
                                                  : "确认恢复"}
                                              </button>
                                              <button
                                                type="button"
                                                disabled={Boolean(restoring)}
                                                onClick={() =>
                                                  setPendingRecipeRestore(null)
                                                }
                                                className="text-muted-foreground hover:text-foreground disabled:opacity-50"
                                              >
                                                取消
                                              </button>
                                            </div>
                                          </div>
                                        )}
                                      </li>
                                    );
                                  })}
                                </ol>
                              )}
                            {recipeHistoryFeedback?.recipeId === recipe.id && (
                              <div
                                role="status"
                                className="mt-3 border border-success/30 bg-success/[0.06] px-3 py-2 text-xs leading-5 text-success"
                              >
                                {recipeHistoryFeedback.message}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
              {!sources.length && (
                <div className="border border-border px-4 py-5 text-center text-xs leading-5 text-muted-foreground">
                  暂无数据
                </div>
              )}
            </div>
          </section>

          {connections?.some((item) => !attachedConnections.has(item.id)) && (
            <section>
              <h3 className="mb-3 text-sm font-semibold text-foreground">连接现有数据库</h3>
              <div className="space-y-2">
                {connections
                  .filter((connection) => !attachedConnections.has(connection.id))
                  .map((connection) => (
                    <button
                      key={connection.id}
                      disabled={isUploading}
                      onClick={() => void attachConnection(connection.id, connection.name)}
                      className="flex w-full items-center gap-3 border border-border bg-background px-3 py-3 text-left transition-colors hover:border-primary/50 hover:bg-primary/5 disabled:opacity-50"
                    >
                      <Database size={17} className="text-primary" />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-foreground">
                          {connection.name}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {connection.driver.toUpperCase()}
                        </div>
                      </div>
                      <Plus size={16} className="text-muted-foreground" />
                    </button>
                  ))}
              </div>
            </section>
          )}

          {!connections?.length && (
            <section className="border border-border bg-background px-4 py-4">
              <h3 className="text-sm font-semibold text-foreground">需要查询数据库？</h3>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                先建立一个只读连接，再回到这里把它加入当前项目。
              </p>
              <button
                type="button"
                onClick={onConfigureConnection}
                className="mt-3 inline-flex items-center gap-2 bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground"
              >
                <Plus size={14} />
                连接数据库
              </button>
            </section>
          )}
            </>
          ) : (
            <div className="space-y-5">
              <section className="border-y border-border py-4">
                <div className="flex items-start gap-3">
                  <BookOpenText size={18} className="mt-0.5 shrink-0 text-primary" />
                  <div>
                    <h3 className="text-sm font-semibold text-foreground">
                      项目理解
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      当前项目的口径与关联。
                    </p>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-3 divide-x divide-border border-y border-border py-3 text-center">
                  <div>
                    <div className="text-lg font-semibold text-foreground">
                      {knowledgeTotal}
                    </div>
                    <div className="text-[10px] text-muted-foreground">全部</div>
                  </div>
                  <div>
                    <div className="text-lg font-semibold text-foreground">
                      {pendingKnowledgeCount}
                    </div>
                    <div className="text-[10px] text-muted-foreground">待核对</div>
                  </div>
                  <div>
                    <div className="text-lg font-semibold text-foreground">
                      {relationshipKnowledgeCount}
                    </div>
                    <div className="text-[10px] text-muted-foreground">关联</div>
                  </div>
                </div>
                {currentProjectId && (
                  <Link
                    href={`/projects/${currentProjectId}/understanding`}
                    className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-primary hover:underline"
                  >
                    查看全部
                    <ArrowRight size={13} />
                  </Link>
                )}
              </section>

              <section>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-foreground">关系概览</h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      来源、关联和口径都在当前项目内维护。
                    </p>
                  </div>
                  <span className="text-[11px] text-muted-foreground">横向滑动查看</span>
                </div>
                <UnderstandingMap
                  sources={sources}
                  knowledgeCount={knowledgeTotal}
                  relationshipCount={relationshipKnowledgeCount}
                />
              </section>

              <section className="space-y-3" aria-label="项目理解预览">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-foreground">最近内容</h3>
                  <span className="text-[11px] text-muted-foreground">最多显示 8 条</span>
                </div>

                {displayedKnowledge.map((entry) => (
                  <article
                    key={entry.id}
                    className="border-b border-border px-1 py-3 last:border-b-0"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="text-[10px] font-semibold tracking-[0.12em] text-muted-foreground">
                        {knowledgeKindLabel(entry.entry_type)}
                      </div>
                      <span className="shrink-0 text-[10px] text-muted-foreground">
                        {entry.validity === "stale"
                          ? "未采用"
                          : entry.state === "locked"
                            ? "已锁定"
                            : entry.state === "confirmed"
                              ? "已记住"
                              : "待核对"}
                      </span>
                    </div>
                    <p className="mt-1.5 line-clamp-2 text-xs leading-5 text-foreground">
                      {knowledgeDisplayValue(entry)}
                    </p>
                  </article>
                ))}

                {!displayedKnowledge.length && (
                  <div className="border-y border-border px-4 py-6 text-center">
                    <BookOpenText size={20} className="mx-auto text-primary" />
                    <div className="mt-2 text-sm font-medium text-foreground">
                      暂无项目理解
                    </div>
                  </div>
                )}

                {currentProjectId && (
                  <Link
                    href={`/projects/${currentProjectId}/understanding`}
                    className="inline-flex w-full items-center justify-center gap-2 bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground"
                  >
                    管理项目理解
                    <ArrowRight size={14} />
                  </Link>
                )}
              </section>
            </div>
          )}
        </div>
      </div>
    </aside>
    {cleaningSource?.kind === "file" && (
      <VisualCleaningEditor
        key={cleaningSource.id}
        source={cleaningSource}
        columns={cleaningColumns}
        recipeOperations={cleaningRecipe?.operations || []}
        onClose={() => setCleaningSourceId(null)}
      />
    )}
    </>
  );
}
