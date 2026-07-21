"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Legend,
  LabelList,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  CHART_PALETTE_OPTIONS,
  getChartPalette,
  type ChartPaletteId,
  type ChartStack,
  type ChartValueFormat,
} from "@/lib/charts";
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  Copy,
  Trash2,
} from "lucide-react";
import type { ReportBlock } from "@/lib/reports";
import { cn } from "@/lib/utils";

interface ReportBlockCardProps {
  block: ReportBlock;
  editing: boolean;
  selected: boolean;
  staticRendering?: boolean;
  onSelect: () => void;
  onMove: (direction: -1 | 1) => void;
  onResize: (direction: -1 | 1) => void;
  onDuplicate: () => void;
  onDelete: () => void;
  filterValue?: string;
  onFilterValueChange?: (value: string) => void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function textValue(content: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = content[key];
    if (typeof value === "string" || typeof value === "number") return String(value);
  }
  return "";
}

function rowsFromContent(content: Record<string, unknown>): Record<string, unknown>[] {
  const candidates = [content.rows, content.data, content.items, content.values];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      return candidate.filter(isRecord);
    }
  }
  return [];
}

function chartKeys(
  rows: Record<string, unknown>[],
  config: Record<string, unknown>
): { x: string; ys: string[] } | null {
  const first = rows[0];
  if (!first) return null;
  const keys = Object.keys(first);
  const isNumericField = (key: string) =>
    keys.includes(key) && rows.some((row) => typeof row[key] === "number");
  const configuredX = typeof config.x_key === "string" ? config.x_key : "";
  const configuredY = typeof config.y_key === "string" ? config.y_key : "";
  const configuredYs = Array.isArray(config.y_keys)
    ? config.y_keys.filter(
        (key): key is string => typeof key === "string" && isNumericField(key)
      )
    : [];
  const x = configuredX && keys.includes(configuredX) ? configuredX : keys[0];
  const fallbackY =
    configuredY && isNumericField(configuredY)
      ? configuredY
      : keys.find((key) => typeof first[key] === "number" && key !== x) || keys[1];
  const ys = configuredYs.length ? configuredYs : fallbackY ? [fallbackY] : [];
  return x && ys.length ? { x, ys } : null;
}

const CHART_VALUE_FORMATS = new Set<ChartValueFormat>([
  "auto",
  "number",
  "integer",
  "compact",
  "currency",
  "percent",
]);

function chartValueFormat(value: unknown): ChartValueFormat {
  return CHART_VALUE_FORMATS.has(value as ChartValueFormat)
    ? (value as ChartValueFormat)
    : "auto";
}

function chartPalette(value: unknown): ChartPaletteId {
  return CHART_PALETTE_OPTIONS.some((option) => option.value === value)
    ? (value as ChartPaletteId)
    : "receiptbi";
}

function chartStack(value: unknown): ChartStack {
  return value === "normal" || value === "percent" ? value : "none";
}

function chartSeriesLabels(value: unknown): Record<string, string> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(
    Object.entries(value).flatMap(([key, label]) => {
      if (typeof label !== "string") return [];
      const cleanLabel = label.trim().slice(0, 80);
      return cleanLabel ? [[key, cleanLabel] as const] : [];
    })
  );
}

function chartSeriesFormats(value: unknown): Record<string, ChartValueFormat> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(
    Object.entries(value).flatMap(([key, format]) =>
      CHART_VALUE_FORMATS.has(format as ChartValueFormat)
        ? [[key, format as ChartValueFormat] as const]
        : []
    )
  );
}

function formatChartValue(value: unknown, format: ChartValueFormat): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value ?? "—");
  if (format === "integer") {
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
  }
  if (format === "compact") {
    return new Intl.NumberFormat("zh-CN", {
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value);
  }
  if (format === "currency") {
    return new Intl.NumberFormat("zh-CN", {
      style: "currency",
      currency: "CNY",
      maximumFractionDigits: 2,
    }).format(value);
  }
  if (format === "percent") {
    return new Intl.NumberFormat("zh-CN", {
      style: "percent",
      maximumFractionDigits: 1,
    }).format(value);
  }
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value);
}

function EmptyBlock({ message }: { message: string }) {
  return (
    <div className="flex min-h-24 items-center justify-center border border-dashed border-border bg-muted/20 px-5 text-center text-xs leading-5 text-muted-foreground">
      {message}
    </div>
  );
}

function KpiBlock({ block }: { block: ReportBlock }) {
  const value = textValue(block.content, ["value", "metric", "amount", "result"]);
  const context = textValue(block.content, ["context", "note", "summary", "description"]);
  const change = textValue(block.content, ["change", "delta", "comparison"]);
  return (
    <div className="flex h-full min-h-24 flex-col justify-end">
      <div className="text-[clamp(1.75rem,3vw,3.25rem)] font-semibold leading-none tracking-[-0.045em] text-foreground">
        {value || "—"}
      </div>
      {(change || context) && (
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {change && <span className="font-medium text-primary">{change}</span>}
          {context && <span>{context}</span>}
        </div>
      )}
    </div>
  );
}

function ChartBlock({
  block,
  staticRendering = false,
}: {
  block: ReportBlock;
  staticRendering?: boolean;
}) {
  const imageUrl = typeof block.content.image_url === "string" ? block.content.image_url : "";
  if (imageUrl) {
    return (
      <div className="relative h-full min-h-44 w-full overflow-hidden bg-muted/15">
        <Image
          src={imageUrl}
          alt={block.title}
          fill
          unoptimized
          sizes="(max-width: 1280px) 100vw, 60vw"
          className="object-contain"
        />
      </div>
    );
  }
  const rows = rowsFromContent(block.content);
  const keys = chartKeys(rows, block.config);
  if (!rows.length || !keys) {
    return (
      <EmptyBlock
        message={block.content._filter_applied === true ? "当前筛选下没有数据" : "选择要呈现的数据"}
      />
    );
  }
  const chartType = typeof block.config.chart_type === "string" ? block.config.chart_type : "bar";
  const supportedTypes = new Set(["bar", "horizontal_bar", "line", "area", "pie", "scatter"]);
  if (!supportedTypes.has(chartType)) {
    return <EmptyBlock message="这个图表样式暂时无法显示，请在编辑中重新选择" />;
  }
  const numericKeys = Object.keys(rows[0]).filter((key) =>
    rows.some((row) => typeof row[key] === "number")
  );
  if (chartType === "scatter" && numericKeys.length < 2) {
    return <EmptyBlock message="散点图需要两个数值字段" />;
  }
  const scatterXKey =
    typeof block.config.x_key === "string" && numericKeys.includes(block.config.x_key)
      ? block.config.x_key
      : numericKeys[0];
  const scatterYKey =
    typeof block.config.y_key === "string" && numericKeys.includes(block.config.y_key)
      ? block.config.y_key
      : numericKeys.find((key) => key !== scatterXKey) || numericKeys[1];
  const orientation =
    block.config.orientation === "horizontal" || block.config.orientation === "vertical"
      ? block.config.orientation
      : chartType === "horizontal_bar"
        ? "horizontal"
        : "vertical";
  const stack =
    chartType === "bar" || chartType === "horizontal_bar" || chartType === "area"
      ? chartStack(block.config.stack)
      : "none";
  const stackId = stack === "none" || keys.ys.length < 2 ? undefined : "report-series";
  const numberFormat = chartValueFormat(block.config.number_format);
  const seriesLabels = chartSeriesLabels(block.config.series_labels);
  const seriesFormats = chartSeriesFormats(block.config.series_formats);
  const resolvedSeriesFormats = keys.ys.map(
    (key) => seriesFormats[key] || numberFormat
  );
  const sharedSeriesFormat = resolvedSeriesFormats.every(
    (format) => format === resolvedSeriesFormats[0]
  )
    ? resolvedSeriesFormats[0]
    : numberFormat;
  const axisNumberFormat =
    stack === "percent" && stackId ? "percent" : sharedSeriesFormat;
  const showLabels = block.config.show_labels === true;
  const colors = getChartPalette(chartPalette(block.config.palette));
  const isHorizontalBar =
    (chartType === "bar" || chartType === "horizontal_bar") && orientation === "horizontal";
  const seriesLabel = (key: string) => seriesLabels[key] || key;
  const seriesFormat = (key: string) => seriesFormats[key] || numberFormat;
  const formatSeriesValue = (key: string, value: unknown) =>
    formatChartValue(value, seriesFormat(key));
  const seriesKeyFromName = (name: unknown) => {
    const candidate = String(name ?? "");
    return keys.ys.find(
      (key) => key === candidate || seriesLabel(key) === candidate
    );
  };
  const tooltipFormatter = (value: unknown, name: unknown) => {
    const key = seriesKeyFromName(name);
    return [
      key ? formatSeriesValue(key, value) : formatChartValue(value, numberFormat),
      key ? seriesLabel(key) : String(name ?? ""),
    ];
  };
  const common = (
    <>
      <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="2 4" vertical={false} />
      <XAxis dataKey={keys.x} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
      <YAxis
        tick={{ fontSize: 10 }}
        tickLine={false}
        axisLine={false}
        width={52}
        tickFormatter={(value) => formatChartValue(value, axisNumberFormat)}
      />
      <Tooltip
        formatter={tooltipFormatter}
        contentStyle={{
          border: "1px solid hsl(var(--border))",
          background: "hsl(var(--popover))",
          color: "hsl(var(--popover-foreground))",
          borderRadius: 4,
          fontSize: 12,
        }}
      />
      {keys.ys.length > 1 && <Legend wrapperStyle={{ fontSize: 10 }} />}
    </>
  );

  return (
    <div className="h-full min-h-44 w-full" aria-label={`${block.title}图表`}>
      <ResponsiveContainer width="100%" height="100%">
        {chartType === "line" ? (
          <LineChart data={rows} margin={{ top: showLabels ? 24 : 12, right: 10, bottom: 0, left: 0 }}>
            {common}
            {keys.ys.map((key, index) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                name={seriesLabel(key)}
                isAnimationActive={!staticRendering}
                stroke={colors[index % colors.length]}
                strokeWidth={2}
                dot={{ r: 2, fill: colors[index % colors.length] }}
              >
                {showLabels && (
                  <LabelList
                    dataKey={key}
                    position="top"
                    formatter={(value: unknown) => formatSeriesValue(key, value)}
                  />
                )}
              </Line>
            ))}
          </LineChart>
        ) : chartType === "area" ? (
          <AreaChart
            data={rows}
            stackOffset={stack === "percent" && stackId ? "expand" : "none"}
            margin={{ top: showLabels ? 24 : 12, right: 10, bottom: 0, left: 0 }}
          >
            {common}
            {keys.ys.map((key, index) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                name={seriesLabel(key)}
                isAnimationActive={!staticRendering}
                stroke={colors[index % colors.length]}
                fill={colors[index % colors.length]}
                fillOpacity={0.14}
                strokeWidth={2}
                stackId={stackId}
              >
                {showLabels && (
                  <LabelList
                    dataKey={key}
                    position="top"
                    formatter={(value: unknown) => formatSeriesValue(key, value)}
                  />
                )}
              </Area>
            ))}
          </AreaChart>
        ) : chartType === "pie" ? (
          <PieChart>
            <Tooltip
              formatter={(value) => [
                formatSeriesValue(keys.ys[0], value),
                seriesLabel(keys.ys[0]),
              ]}
            />
            <Pie
              data={rows}
              dataKey={keys.ys[0]}
              name={seriesLabel(keys.ys[0])}
              nameKey={keys.x}
              isAnimationActive={!staticRendering}
              innerRadius="46%"
              outerRadius="78%"
              paddingAngle={1}
              label={
                showLabels
                  ? ({ name, value }) =>
                      `${String(name ?? "")}: ${formatSeriesValue(keys.ys[0], value)}`
                  : false
              }
            >
              {rows.map((_, index) => (
                <Cell key={index} fill={colors[index % colors.length]} />
              ))}
            </Pie>
          </PieChart>
        ) : chartType === "scatter" ? (
          <ScatterChart margin={{ top: 12, right: 10, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="2 4" />
            <XAxis
              dataKey={scatterXKey}
              name={scatterXKey}
              type="number"
              tick={{ fontSize: 10 }}
              tickLine={false}
              tickFormatter={(value) => formatChartValue(value, numberFormat)}
            />
            <YAxis
              dataKey={scatterYKey}
              name={seriesLabel(scatterYKey)}
              type="number"
              tick={{ fontSize: 10 }}
              tickLine={false}
              width={52}
              tickFormatter={(value) => formatSeriesValue(scatterYKey, value)}
            />
            <Tooltip cursor={{ strokeDasharray: "2 4" }} formatter={tooltipFormatter} />
            <Scatter
              data={rows}
              name={seriesLabel(scatterYKey)}
              fill={colors[0]}
              isAnimationActive={!staticRendering}
            >
              {showLabels && (
                <LabelList
                  dataKey={scatterYKey}
                  position="top"
                  formatter={(value: unknown) => formatSeriesValue(scatterYKey, value)}
                />
              )}
            </Scatter>
          </ScatterChart>
        ) : isHorizontalBar ? (
          <BarChart
            data={rows}
            layout="vertical"
            stackOffset={stack === "percent" && stackId ? "expand" : "none"}
            margin={{ top: 12, right: showLabels ? 54 : 12, bottom: 0, left: 8 }}
          >
            <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="2 4" horizontal={false} />
            <XAxis
              type="number"
              tick={{ fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => formatChartValue(value, axisNumberFormat)}
            />
            <YAxis dataKey={keys.x} type="category" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={72} />
            <Tooltip formatter={tooltipFormatter} />
            {keys.ys.length > 1 && <Legend wrapperStyle={{ fontSize: 10 }} />}
            {keys.ys.map((key, index) => (
              <Bar key={key} dataKey={key} name={seriesLabel(key)} fill={colors[index % colors.length]} radius={[0, 2, 2, 0]} isAnimationActive={!staticRendering} stackId={stackId}>
                {showLabels && (
                  <LabelList
                    dataKey={key}
                    position="right"
                    formatter={(value: unknown) => formatSeriesValue(key, value)}
                  />
                )}
              </Bar>
            ))}
          </BarChart>
        ) : (
          <BarChart
            data={rows}
            stackOffset={stack === "percent" && stackId ? "expand" : "none"}
            margin={{ top: showLabels ? 24 : 12, right: 10, bottom: 0, left: 0 }}
          >
            {common}
            {keys.ys.map((key, index) => (
              <Bar key={key} dataKey={key} name={seriesLabel(key)} fill={colors[index % colors.length]} radius={[2, 2, 0, 0]} isAnimationActive={!staticRendering} stackId={stackId}>
                {showLabels && (
                  <LabelList
                    dataKey={key}
                    position="top"
                    formatter={(value: unknown) => formatSeriesValue(key, value)}
                  />
                )}
              </Bar>
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function TableBlock({ block }: { block: ReportBlock }) {
  const rows = rowsFromContent(block.content);
  const [page, setPage] = useState(0);
  const pageSize = 50;
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  useEffect(() => {
    setPage((current) => Math.min(current, pageCount - 1));
  }, [pageCount]);
  if (!rows.length) {
    return (
      <EmptyBlock
        message={block.content._filter_applied === true ? "当前筛选下没有明细" : "选择要呈现的明细"}
      />
    );
  }
  const columns = Object.keys(rows[0]).slice(0, 8);
  const pageRows = rows.slice(page * pageSize, (page + 1) * pageSize);
  const sourceRows =
    typeof block.content._filter_source_rows === "number"
      ? block.content._filter_source_rows
      : rows.length;
  const totalRows =
    typeof block.content.rows_count === "number" ? block.content.rows_count : sourceRows;
  const start = page * pageSize + 1;
  const end = Math.min(rows.length, (page + 1) * pageSize);
  return (
    <div className="flex h-full min-h-0 flex-col border border-border">
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full min-w-[520px] border-collapse text-left text-xs">
        <thead className="sticky top-0 bg-muted/80 backdrop-blur">
          <tr>
            {columns.map((column) => (
              <th key={column} className="border-b border-border px-3 py-2.5 font-semibold">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {pageRows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-b border-border/70 last:border-b-0">
              {columns.map((column) => (
                <td key={column} className="max-w-52 truncate px-3 py-2.5 text-muted-foreground">
                  {String(row[column] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        </table>
      </div>
      <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-border bg-card px-3 py-2 text-[10px] text-muted-foreground">
        <span>
          {block.content._filter_applied === true
            ? `筛选后 ${rows.length} 行（基于报告保留的 ${sourceRows} 行）`
            : totalRows > rows.length
              ? `报告保留前 ${rows.length} / 共 ${totalRows} 行`
              : `共 ${rows.length} 行`}
          {rows.length > pageSize ? ` · 当前 ${start}–${end}` : ""}
        </span>
        {pageCount > 1 && (
          <span className="flex items-center border border-border">
            <button type="button" aria-label="上一页明细" disabled={page === 0} onClick={() => setPage((current) => Math.max(0, current - 1))} className="p-1.5 hover:bg-muted disabled:opacity-30">
              <ChevronLeft size={12} />
            </button>
            <span className="min-w-12 text-center tabular-nums">{page + 1} / {pageCount}</span>
            <button type="button" aria-label="下一页明细" disabled={page >= pageCount - 1} onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))} className="p-1.5 hover:bg-muted disabled:opacity-30">
              <ChevronRight size={12} />
            </button>
          </span>
        )}
      </footer>
    </div>
  );
}

function TextBlock({ block }: { block: ReportBlock }) {
  const text = textValue(block.content, ["text", "summary", "description", "value"]);
  return text ? (
    <p className="whitespace-pre-wrap text-sm leading-7 text-foreground/85">{text}</p>
  ) : (
    <EmptyBlock message="写下结论、说明或下一步" />
  );
}

function EvidenceBlock({ block }: { block: ReportBlock }) {
  const rows = rowsFromContent(block.content);
  const text = textValue(block.content, ["text", "summary", "description", "value"]);
  return (
    <div className="border-l-2 border-primary/55 pl-4 text-sm leading-6">
      {text && <p className="text-foreground/85">{text}</p>}
      {rows.length > 0 && (
        <ul className={cn("space-y-3", text && "mt-3")}>
          {rows.slice(0, 12).map((item, index) => {
            const label = textValue(item, [
                "label",
                "title",
                "summary",
                "message",
                "purpose",
                "value",
              ]) || `已核对依据 ${index + 1}`;
            const detail = textValue(item, ["text", "detail", "status"]);
            return (
              <li key={index}>
                <span className="block text-sm font-medium text-foreground/85">{label}</span>
                {detail && detail !== label && (
                  <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
                    {detail}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {!text && !rows.length && <span className="text-muted-foreground">尚未添加依据</span>}
    </div>
  );
}

function FilterBlock({
  block,
  value = "",
  onChange,
}: {
  block: ReportBlock;
  value?: string;
  onChange?: (value: string) => void;
}) {
  const placeholder = textValue(block.config, ["placeholder"]) || "全部";
  const field = textValue(block.config, ["field"]);
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="min-w-44 text-xs font-medium text-muted-foreground">
        {block.title}
        <input
          value={value}
          onChange={(event) => onChange?.(event.target.value)}
          disabled={!field}
          placeholder={field ? placeholder : "请先选择筛选字段"}
          className="mt-2 h-9 w-full border border-input bg-background px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary disabled:bg-muted/35"
        />
        <span className="mt-1.5 block text-[10px] font-normal text-muted-foreground">
          {field ? `当前页面 · ${field}` : "尚未设置字段"}
        </span>
      </label>
    </div>
  );
}

export function ReportBlockCard({
  block,
  editing,
  selected,
  staticRendering = false,
  onSelect,
  onMove,
  onResize,
  onDuplicate,
  onDelete,
  filterValue,
  onFilterValueChange,
}: ReportBlockCardProps) {
  return (
    <article
      data-report-block={block.id}
      onClick={() => editing && onSelect()}
      className={cn(
        "group relative flex h-full min-h-0 flex-col border bg-card px-5 pb-5 pt-4 text-card-foreground transition-colors",
        editing ? "cursor-pointer hover:border-primary/50" : "border-border",
        editing && selected ? "border-primary ring-2 ring-primary/10" : "border-border"
      )}
    >
      <header className="mb-4 flex min-h-6 items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold tracking-[-0.01em]">{block.title}</h3>
          {typeof block.content.subtitle === "string" && block.content.subtitle && (
            <p className="mt-1 truncate text-xs text-muted-foreground">{block.content.subtitle}</p>
          )}
          {block.config.manual_override === true && (
            <span className="mt-1.5 inline-flex bg-warning/10 px-1.5 py-0.5 text-[9px] font-medium text-warning">
              人工调整
            </span>
          )}
        </div>
        {editing && (
          <div
            className="flex shrink-0 items-center border border-border bg-background"
            onClick={(event) => event.stopPropagation()}
          >
            <button type="button" onClick={() => onMove(-1)} aria-label="区块上移" className="p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
              <ArrowUp size={13} />
            </button>
            <button type="button" onClick={() => onMove(1)} aria-label="区块下移" className="p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
              <ArrowDown size={13} />
            </button>
            <button type="button" onClick={() => onResize(-1)} aria-label="缩小区块" className="p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
              <ChevronLeft size={13} />
            </button>
            <button type="button" onClick={() => onResize(1)} aria-label="放大区块" className="p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
              <ChevronRight size={13} />
            </button>
            <button type="button" onClick={onDuplicate} aria-label="复制区块" className="p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
              <Copy size={13} />
            </button>
            <button type="button" onClick={onDelete} aria-label="删除区块" className="p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive">
              <Trash2 size={13} />
            </button>
          </div>
        )}
      </header>

      <div className="min-h-0 flex-1">
        {block.block_type === "metric" && <KpiBlock block={block} />}
        {block.block_type === "chart" && (
          <ChartBlock block={block} staticRendering={staticRendering} />
        )}
        {block.block_type === "table" && <TableBlock block={block} />}
        {block.block_type === "text" && <TextBlock block={block} />}
        {block.block_type === "evidence" && <EvidenceBlock block={block} />}
        {block.block_type === "filter" && (
          <FilterBlock
            block={block}
            value={filterValue}
            onChange={onFilterValueChange}
          />
        )}
      </div>
    </article>
  );
}
