import type { AnalysisArtifact, AnalysisRunSummary } from "@/lib/types/api";
import { normalizeChartSpec } from "@/lib/charts";
import type {
  ReportBlock,
  ReportBlockLayout,
  ReportBlockType,
  ReportPage,
} from "@/lib/reports";

let localSequence = 0;

export function createLocalId(kind: "page" | "block"): string {
  localSequence += 1;
  return `local-${kind}-${Date.now()}-${localSequence}`;
}

export const REPORT_BLOCK_OPTIONS: Array<{
  type: ReportBlockType;
  label: string;
  description: string;
}> = [
  { type: "metric", label: "指标", description: "突出一个重要数字" },
  { type: "chart", label: "图表", description: "呈现趋势或对比" },
  { type: "table", label: "表格", description: "展示明细或汇总" },
  { type: "text", label: "文字", description: "记录结论和说明" },
  { type: "evidence", label: "依据", description: "保留来源和判断依据" },
  { type: "filter", label: "筛选", description: "控制报告中的数据范围" },
];

export type ReportFilterOperator =
  | "contains"
  | "equals"
  | "not_equals"
  | "greater_than"
  | "greater_or_equal"
  | "less_than"
  | "less_or_equal";

export interface ActiveReportFilter {
  field: string;
  operator: ReportFilterOperator;
  value: string;
}

export function blockTypeLabel(type: ReportBlockType): string {
  return REPORT_BLOCK_OPTIONS.find((option) => option.type === type)?.label || "区块";
}

function defaultLayout(type: ReportBlockType): ReportBlockLayout {
  if (type === "metric" || type === "filter") return { x: 0, y: 0, w: 4, h: 2 };
  if (type === "text" || type === "evidence") return { x: 0, y: 0, w: 6, h: 3 };
  return { x: 0, y: 0, w: 6, h: 4 };
}

function defaultContent(type: ReportBlockType): Record<string, unknown> {
  if (type === "metric") return { value: "—", context: "" };
  if (type === "text") return { text: "" };
  if (type === "evidence") return { text: "" };
  if (type === "filter") return {};
  return { rows: [] };
}

function defaultConfig(type: ReportBlockType): Record<string, unknown> {
  if (type === "chart") {
    return {
      chart_type: "bar",
      orientation: "vertical",
      stack: "none",
      number_format: "auto",
      palette: "receiptbi",
      show_labels: false,
    };
  }
  if (type === "filter") {
    return {
      field: "",
      operator: "contains",
      placeholder: "输入筛选值",
    };
  }
  return {};
}

export function createManualBlock(type: ReportBlockType): ReportBlock {
  return {
    id: createLocalId("block"),
    block_type: type,
    title: blockTypeLabel(type),
    order_index: 0,
    source_kind: "manual",
    analysis_run_id: null,
    artifact_id: null,
    content: defaultContent(type),
    config: defaultConfig(type),
    layout: defaultLayout(type),
  };
}

export function applyReportBlockUpdates(
  block: ReportBlock,
  updates: Partial<ReportBlock>
): ReportBlock {
  const next: ReportBlock = {
    ...block,
    ...updates,
    // Provenance is system-owned. Editing presentation or copy must never
    // detach a block from the investigation evidence it came from.
    id: block.id,
    source_kind: block.source_kind,
    analysis_run_id: block.analysis_run_id,
    artifact_id: block.artifact_id,
    source_ref: block.source_ref,
    source_available: block.source_available,
  };
  const isManualEdit = ["block_type", "title", "content", "config"].some((key) =>
    Object.prototype.hasOwnProperty.call(updates, key)
  );
  if (block.source_kind !== "manual" && isManualEdit) {
    next.config = { ...next.config, manual_override: true };
  }
  return next;
}

export function createReportPage(title = "新页面", orderIndex = 0): ReportPage {
  return {
    id: createLocalId("page"),
    title,
    order_index: orderIndex,
    config: {},
    blocks: [],
  };
}

export function reflowBlocks(blocks: ReportBlock[]): ReportBlock[] {
  let x = 0;
  let y = 0;
  let rowHeight = 1;
  return blocks.map((block, orderIndex) => {
    const w = Math.max(3, Math.min(12, Math.round(block.layout.w || 6)));
    const h = Math.max(2, Math.min(8, Math.round(block.layout.h || 3)));
    if (x > 0 && x + w > 12) {
      x = 0;
      y += rowHeight;
      rowHeight = 1;
    }
    const next = { ...block, order_index: orderIndex, layout: { x, y, w, h } };
    x += w;
    rowHeight = Math.max(rowHeight, h);
    if (x >= 12) {
      x = 0;
      y += rowHeight;
      rowHeight = 1;
    }
    return next;
  });
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function contentRows(
  content: Record<string, unknown>
): { key: "rows" | "data" | "items" | "values"; rows: Record<string, unknown>[] } | null {
  for (const key of ["rows", "data", "items", "values"] as const) {
    const value = content[key];
    if (!Array.isArray(value)) continue;
    const rows = value.filter(
      (item): item is Record<string, unknown> => record(item) !== null
    );
    return { key, rows };
  }
  return null;
}

export function reportFilterFields(blocks: ReportBlock[]): string[] {
  const fields = new Set<string>();
  for (const block of blocks) {
    if (block.block_type !== "chart" && block.block_type !== "table") continue;
    const collection = contentRows(block.content);
    for (const row of collection?.rows || []) {
      Object.keys(row).forEach((field) => fields.add(field));
    }
  }
  return [...fields].sort((left, right) => left.localeCompare(right, "zh-CN"));
}

function normalizedComparable(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value).trim().toLocaleLowerCase();
}

function matchesFilter(
  candidate: unknown,
  filter: ActiveReportFilter
): boolean {
  const expected = filter.value.trim();
  const actualText = normalizedComparable(candidate);
  const expectedText = normalizedComparable(expected);
  if (filter.operator === "contains") return actualText.includes(expectedText);
  if (filter.operator === "equals") return actualText === expectedText;
  if (filter.operator === "not_equals") return actualText !== expectedText;

  const actualNumber =
    typeof candidate === "number" ? candidate : Number(String(candidate ?? "").trim());
  const expectedNumber = Number(expected);
  if (!Number.isFinite(actualNumber) || !Number.isFinite(expectedNumber)) return false;
  if (filter.operator === "greater_than") return actualNumber > expectedNumber;
  if (filter.operator === "greater_or_equal") return actualNumber >= expectedNumber;
  if (filter.operator === "less_than") return actualNumber < expectedNumber;
  if (filter.operator === "less_or_equal") return actualNumber <= expectedNumber;
  return true;
}

export function applyStaticReportFilters(
  block: ReportBlock,
  filters: ActiveReportFilter[]
): ReportBlock {
  if (
    (block.block_type !== "chart" && block.block_type !== "table") ||
    !filters.length
  ) {
    return block;
  }
  const collection = contentRows(block.content);
  if (!collection) return block;
  let rows = collection.rows;
  const sourceRowCount = rows.length;
  let applied = false;
  for (const filter of filters) {
    if (!filter.field || !filter.value.trim()) continue;
    if (!rows.some((row) => Object.prototype.hasOwnProperty.call(row, filter.field))) {
      continue;
    }
    if (
      filter.operator !== "contains" &&
      filter.operator !== "equals" &&
      filter.operator !== "not_equals" &&
      !Number.isFinite(Number(filter.value.trim()))
    ) {
      continue;
    }
    rows = rows.filter((row) =>
      Object.prototype.hasOwnProperty.call(row, filter.field)
        ? matchesFilter(row[filter.field], filter)
        : false
    );
    applied = true;
  }
  if (!applied) return block;
  return {
    ...block,
    content: {
      ...block.content,
      [collection.key]: rows,
      _filter_applied: true,
      _filter_source_rows: sourceRowCount,
    },
  };
}

function firstValue(payload: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" || typeof value === "number") return value;
  }
  for (const value of Object.values(payload)) {
    const nested = record(value);
    if (!nested) continue;
    const result = firstValue(nested, keys);
    if (result !== undefined) return result;
  }
  return undefined;
}

function artifactBlockType(kind: AnalysisArtifact["kind"]): ReportBlockType {
  if (kind === "metric") return "metric";
  if (kind === "chart") return "chart";
  if (kind === "table" || kind === "result_snapshot") return "table";
  if (kind === "evidence" || kind === "file") return "evidence";
  return "text";
}

function evidenceStatus(value: unknown): string {
  if (value === "verified" || value === "passed" || value === "success") return "已通过";
  if (value === "failed" || value === "rejected") return "未通过";
  if (value === "definition_only") return "已记录，尚待验证";
  return "已核对";
}

function validationLabel(item: Record<string, unknown>): string {
  if (typeof item.purpose === "string" && item.purpose.trim()) return item.purpose.trim();
  if (item.kind === "relationship_validation") return "数据关联已核对";
  if (item.kind === "relationship_application") return "数据关联已用于本次分析";
  if (item.kind === "golden_regression_validation") return "关键结果已回归核对";
  return "分析结果已核对";
}

function validationDetail(item: Record<string, unknown>): string {
  const profile = record(item.profile);
  const rowCount = profile?.returned_rows ?? profile?.materialized_rows ?? profile?.rows;
  if (typeof rowCount === "number") return `${rowCount.toLocaleString("zh-CN")} 行数据已核对`;
  if (Array.isArray(profile?.columns) && profile.columns.length) {
    return `${profile.columns.length} 个字段已核对`;
  }
  return evidenceStatus(item.status);
}

function humanEvidenceItems(payload: Record<string, unknown>): Record<string, unknown>[] {
  const items: Record<string, unknown>[] = [];
  if (Array.isArray(payload.validations)) {
    for (const candidate of payload.validations) {
      const item = record(candidate);
      if (!item) continue;
      items.push({ label: validationLabel(item), text: validationDetail(item) });
    }
  }
  if (Array.isArray(payload.correction_applications)) {
    for (const candidate of payload.correction_applications) {
      const item = record(candidate);
      if (!item) continue;
      items.push({
        label:
          typeof item.rule_value === "string" && item.rule_value.trim()
            ? `业务调整：${item.rule_value.trim()}`
            : "业务调整已核对",
        text:
          typeof item.summary === "string" && item.summary.trim()
            ? item.summary.trim()
            : evidenceStatus(item.status),
      });
    }
  }
  for (const key of ["evidence", "checks", "items"] as const) {
    const values = payload[key];
    if (!Array.isArray(values)) continue;
    for (const candidate of values) {
      if (typeof candidate === "string" && candidate.trim()) {
        items.push({ label: candidate.trim(), text: "已核对" });
        continue;
      }
      const item = record(candidate);
      if (!item) continue;
      const label = firstValue(item, ["label", "title", "summary", "message", "purpose"]);
      if (typeof label === "string" && label.trim()) {
        items.push({ label: label.trim(), text: evidenceStatus(item.status) });
      }
    }
  }
  return items;
}

function formatChangeNumber(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value)
    : String(value ?? "—");
}

function changeLine(change: Record<string, unknown>): string {
  const metric = typeof change.metric === "string" ? change.metric : "指标";
  const delta = typeof change.delta === "number" ? change.delta : null;
  const percent = typeof change.percent_change === "number" ? change.percent_change : null;
  const suffix =
    percent !== null
      ? `，${percent >= 0 ? "+" : ""}${(percent * 100).toFixed(1)}%`
      : delta !== null
        ? `，变化 ${delta >= 0 ? "+" : ""}${formatChangeNumber(delta)}`
        : "";
  return `${metric}：${formatChangeNumber(change.before)} → ${formatChangeNumber(change.after)}${suffix}`;
}

function changeBriefText(payload: Record<string, unknown>): string {
  const lines = [
    payload.status === "material_change"
      ? "发现值得关注的变化。"
      : "本次变化未超过关注范围。",
  ];
  if (Array.isArray(payload.overall)) {
    for (const candidate of payload.overall.slice(0, 4)) {
      const item = record(candidate);
      if (item) lines.push(changeLine(item));
    }
  }
  if (Array.isArray(payload.top_drivers) && payload.top_drivers.length) {
    lines.push("主要变化来源：");
    for (const candidate of payload.top_drivers.slice(0, 5)) {
      const driver = record(candidate);
      const key = record(driver?.key);
      const change = record(driver?.change);
      if (!driver || !change) continue;
      const keyLabel = key
        ? Object.values(key).map((value) => String(value)).join(" · ")
        : "分组";
      lines.push(`${keyLabel}：${changeLine(change)}`);
    }
  } else if (Array.isArray(payload.by_key) && payload.by_key.length) {
    lines.push(`${payload.by_key.length} 个分组发生变化。`);
  }
  return lines.join("\n");
}

function artifactContent(artifact: AnalysisArtifact): Record<string, unknown> {
  const payload = { ...artifact.payload };
  const type = artifactBlockType(artifact.kind);
  if (artifact.kind === "change_brief") {
    return { ...payload, text: changeBriefText(payload) };
  }
  if (artifact.kind === "chart") {
    if (payload.format === "png" && typeof payload.relative_path === "string") {
      return {
        ...payload,
        image_url: `/api/v1/projects/${artifact.project_id}/analysis-runs/${artifact.analysis_run_id}/artifacts/${artifact.id}/file`,
      };
    }
    const chart = normalizeChartSpec(payload.chart);
    if (chart) {
      return {
        ...payload,
        rows: chart.data,
      };
    }
  }
  if (type === "metric") {
    return {
      ...payload,
      value:
        firstValue(payload, ["value", "metric_value", "amount", "result", "total"]) ??
        "—",
      context:
        firstValue(payload, ["context", "summary", "description", "note"]) ?? "",
    };
  }
  if (type === "text" || type === "evidence") {
    const evidenceItems = type === "evidence" ? humanEvidenceItems(payload) : [];
    return {
      ...payload,
      ...(type === "evidence"
        ? {
            items: evidenceItems.length
              ? evidenceItems
              : [
                  {
                    label: "调查依据已保留",
                    text: "可在原调查中查看完整核对记录",
                  },
                ],
          }
        : {}),
      text:
        firstValue(payload, ["text", "summary", "content", "description", "value"]) ??
        "",
    };
  }
  return payload;
}

export function artifactToReportBlock(artifact: AnalysisArtifact): ReportBlock {
  const type = artifactBlockType(artifact.kind);
  const chart =
    artifact.kind === "chart" ? normalizeChartSpec(artifact.payload.chart) : null;
  const legacyChart = artifact.kind === "chart" ? record(artifact.payload.chart) : null;
  const isPng = artifact.kind === "chart" && artifact.payload.format === "png";
  const chartType =
    chart?.type || (typeof legacyChart?.type === "string" ? legacyChart.type : "bar");
  const xKey = chart?.encoding.x?.field;
  const yKeys = chart?.encoding.y.map((encoding) => encoding.field) || [];
  const numberFormat = chart?.encoding.y[0]?.format;
  const seriesLabels = chart
    ? Object.fromEntries(
        chart.encoding.y.flatMap((encoding) => {
          const label = encoding.label?.trim();
          return label ? [[encoding.field, label] as const] : [];
        })
      )
    : {};
  const seriesFormats = chart
    ? Object.fromEntries(
        chart.encoding.y.flatMap((encoding) =>
          encoding.format ? [[encoding.field, encoding.format] as const] : []
        )
      )
    : {};
  return {
    id: createLocalId("block"),
    block_type: type,
    title:
      (typeof chart?.title === "string" && chart.title.trim()) ||
      (typeof legacyChart?.title === "string" && legacyChart.title.trim()) ||
      artifact.title ||
      blockTypeLabel(type),
    order_index: 0,
    source_kind: "artifact",
    analysis_run_id: artifact.analysis_run_id,
    artifact_id: artifact.id,
    content: artifactContent(artifact),
    config:
      artifact.kind === "chart"
        ? {
            chart_type: isPng ? "image" : chartType,
            ...(xKey ? { x_key: xKey } : {}),
            ...(yKeys[0] ? { y_key: yKeys[0] } : {}),
            ...(yKeys.length ? { y_keys: yKeys } : {}),
            ...(chart
              ? {
                  orientation: chart.presentation.orientation,
                  stack: chart.presentation.stack,
                  palette: chart.presentation.palette,
                  ...(numberFormat ? { number_format: numberFormat } : {}),
                  ...(Object.keys(seriesLabels).length ? { series_labels: seriesLabels } : {}),
                  ...(Object.keys(seriesFormats).length ? { series_formats: seriesFormats } : {}),
                }
              : {}),
          }
        : defaultConfig(type),
    layout: defaultLayout(type),
  };
}

export function analysisSummaryToReportBlock(run: AnalysisRunSummary): ReportBlock {
  return {
    id: createLocalId("block"),
    block_type: "text",
    title: run.report.title?.trim() || run.query.trim() || "调查摘要",
    order_index: 0,
    source_kind: "analysis_run",
    analysis_run_id: run.id,
    artifact_id: null,
    content: {
      text:
        (typeof run.report.summary === "string" && run.report.summary.trim()) ||
        run.query.trim(),
    },
    config: {},
    layout: defaultLayout("text"),
  };
}
