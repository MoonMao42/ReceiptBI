"use client";

import { LayoutPanelTop, Settings2 } from "lucide-react";
import type { ReactNode } from "react";
import {
  CHART_PALETTE_OPTIONS,
  type ChartPaletteId,
  type ChartValueFormat,
} from "@/lib/charts";
import type { ReportBlock, ReportBlockType, ReportPage } from "@/lib/reports";
import {
  REPORT_BLOCK_OPTIONS,
  blockTypeLabel,
  reportFilterFields,
} from "./report-blocks";

interface ReportPropertyPanelProps {
  page: ReportPage;
  block: ReportBlock | null;
  onChangePage: (updates: Partial<ReportPage>) => void;
  onChangeBlock: (updates: Partial<ReportBlock>) => void;
}

const CHART_VALUE_FORMAT_OPTIONS: ReadonlyArray<{
  value: ChartValueFormat;
  label: string;
}> = [
  { value: "auto", label: "自动" },
  { value: "number", label: "数值" },
  { value: "integer", label: "整数" },
  { value: "compact", label: "紧凑（万/亿）" },
  { value: "currency", label: "人民币" },
  { value: "percent", label: "百分比" },
];

function chartValueFormat(value: unknown): ChartValueFormat {
  return CHART_VALUE_FORMAT_OPTIONS.some((option) => option.value === value)
    ? (value as ChartValueFormat)
    : "auto";
}

function chartPalette(value: unknown): ChartPaletteId {
  return CHART_PALETTE_OPTIONS.some((option) => option.value === value)
    ? (value as ChartPaletteId)
    : "receiptbi";
}

function configRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function chartSeriesLabels(value: unknown): Record<string, string> {
  return Object.fromEntries(
    Object.entries(configRecord(value)).flatMap(([key, label]) =>
      typeof label === "string" && label.trim() ? [[key, label] as const] : []
    )
  );
}

function chartSeriesFormats(value: unknown): Record<string, ChartValueFormat> {
  return Object.fromEntries(
    Object.entries(configRecord(value)).flatMap(([key, format]) =>
      CHART_VALUE_FORMAT_OPTIONS.some((option) => option.value === format)
        ? [[key, format as ChartValueFormat] as const]
        : []
    )
  );
}

function FieldLabel({ children }: { children: ReactNode }) {
  return <span className="mb-1.5 block text-[11px] font-medium text-muted-foreground">{children}</span>;
}

function textContent(block: ReportBlock): string {
  const keys = block.block_type === "metric" ? ["value"] : ["text", "summary", "description"];
  for (const key of keys) {
    const value = block.content[key];
    if (typeof value === "string" || typeof value === "number") return String(value);
  }
  return "";
}

function blockColumns(block: ReportBlock): string[] {
  for (const key of ["rows", "data", "items", "values"]) {
    const rows = block.content[key];
    if (!Array.isArray(rows)) continue;
    const first = rows.find(
      (row): row is Record<string, unknown> =>
        typeof row === "object" && row !== null && !Array.isArray(row)
    );
    if (first) return Object.keys(first);
  }
  return [];
}

function numericBlockColumns(block: ReportBlock): string[] {
  for (const key of ["rows", "data", "items", "values"]) {
    const rows = block.content[key];
    if (!Array.isArray(rows)) continue;
    const records = rows.filter(
      (row): row is Record<string, unknown> =>
        typeof row === "object" && row !== null && !Array.isArray(row)
    );
    const columns = new Set<string>();
    for (const row of records) {
      for (const [column, value] of Object.entries(row)) {
        if (typeof value === "number" && Number.isFinite(value)) columns.add(column);
      }
    }
    return [...columns];
  }
  return [];
}

export function ReportPropertyPanel({
  page,
  block,
  onChangePage,
  onChangeBlock,
}: ReportPropertyPanelProps) {
  const columns = block ? blockColumns(block) : [];
  const numericColumns = block ? numericBlockColumns(block) : [];
  const chartType =
    block && typeof block.config.chart_type === "string"
      ? block.config.chart_type
      : "bar";
  const singleSeriesChart = chartType === "pie" || chartType === "scatter";
  const configuredSeries = block
    ? Array.isArray(block.config.y_keys)
      ? block.config.y_keys.filter(
          (key): key is string => typeof key === "string" && numericColumns.includes(key)
        )
      : typeof block.config.y_key === "string" && numericColumns.includes(block.config.y_key)
        ? [block.config.y_key]
        : numericColumns.slice(0, 1)
    : [];
  const selectedSeries = singleSeriesChart
    ? configuredSeries.slice(0, 1)
    : configuredSeries;
  const seriesLabels = block ? chartSeriesLabels(block.config.series_labels) : {};
  const seriesFormats = block ? chartSeriesFormats(block.config.series_formats) : {};
  const chartOrientation =
    block &&
    (block.config.orientation === "vertical" || block.config.orientation === "horizontal")
      ? block.config.orientation
      : chartType === "horizontal_bar"
        ? "horizontal"
        : "vertical";
  const supportsOrientation = chartType === "bar" || chartType === "horizontal_bar";
  const supportsStack = supportsOrientation || chartType === "area";
  const editableDataChart =
    block?.block_type === "chart" && typeof block.content.image_url !== "string";
  const filterFields = reportFilterFields(page.blocks);
  return (
    <aside className="flex h-full min-h-0 w-[300px] shrink-0 flex-col border-l border-border bg-card">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-5">
        {block ? <Settings2 size={15} className="text-primary" /> : <LayoutPanelTop size={15} className="text-primary" />}
        <h2 className="text-xs font-semibold">{block ? "区块设置" : "页面设置"}</h2>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        {!block ? (
          <div className="space-y-5">
            <label className="block">
              <FieldLabel>页面名称</FieldLabel>
              <input
                value={page.title}
                maxLength={160}
                onChange={(event) => onChangePage({ title: event.target.value })}
                className="h-9 w-full border border-input bg-background px-3 text-sm outline-none focus:border-primary"
              />
            </label>
            <p className="text-xs leading-5 text-muted-foreground">
              选择画布中的区块后，可以修改它的内容、图表和大小。
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            <label className="block">
              <FieldLabel>区块类型</FieldLabel>
              <select
                value={block.block_type}
                onChange={(event) => onChangeBlock({ block_type: event.target.value as ReportBlockType })}
                className="h-9 w-full border border-input bg-background px-3 text-sm outline-none focus:border-primary"
              >
                {REPORT_BLOCK_OPTIONS.map((option) => (
                  <option key={option.type} value={option.type}>{option.label}</option>
                ))}
              </select>
            </label>

            <label className="block">
              <FieldLabel>标题</FieldLabel>
              <input
                value={block.title}
                aria-label="区块标题"
                maxLength={200}
                onChange={(event) => onChangeBlock({ title: event.target.value })}
                placeholder={blockTypeLabel(block.block_type)}
                className="h-9 w-full border border-input bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus:border-primary"
              />
            </label>

            {(block.block_type === "text" || block.block_type === "evidence") && (
              <label className="block">
                <FieldLabel>{block.block_type === "evidence" ? "依据说明" : "正文"}</FieldLabel>
                <textarea
                  value={textContent(block)}
                  onChange={(event) => onChangeBlock({ content: { ...block.content, text: event.target.value } })}
                  rows={8}
                  className="w-full resize-y border border-input bg-background px-3 py-2.5 text-sm leading-6 outline-none focus:border-primary"
                />
              </label>
            )}

            {block.block_type === "metric" && (
              <>
                <label className="block">
                  <FieldLabel>显示数值</FieldLabel>
                  <input
                    value={textContent(block)}
                    onChange={(event) => onChangeBlock({ content: { ...block.content, value: event.target.value } })}
                    className="h-9 w-full border border-input bg-background px-3 text-sm outline-none focus:border-primary"
                  />
                </label>
                <label className="block">
                  <FieldLabel>补充说明</FieldLabel>
                  <input
                    value={typeof block.content.context === "string" ? block.content.context : ""}
                    onChange={(event) => onChangeBlock({ content: { ...block.content, context: event.target.value } })}
                    className="h-9 w-full border border-input bg-background px-3 text-sm outline-none focus:border-primary"
                  />
                </label>
              </>
            )}

            {block.block_type === "chart" && (
              <div className="space-y-4">
                <label className="block">
                  <FieldLabel>图表样式</FieldLabel>
                  {typeof block.content.image_url === "string" ? (
                    <div className="flex h-9 items-center border border-input bg-muted/30 px-3 text-sm text-muted-foreground">
                      调查生成的图片
                    </div>
                  ) : (
                    <select
                      aria-label="图表样式"
                      value={chartType}
                      onChange={(event) => {
                        const nextType = event.target.value;
                        const nextSingleSeries =
                          nextType === "pie" || nextType === "scatter";
                        const nextSeries = nextSingleSeries
                          ? selectedSeries.slice(0, 1)
                          : selectedSeries;
                        const nextSupportsStack =
                          (nextType === "bar" ||
                            nextType === "horizontal_bar" ||
                            nextType === "area") &&
                          nextSeries.length >= 2;
                        onChangeBlock({
                          config: {
                            ...block.config,
                            chart_type: nextType,
                            y_key: nextSeries[0] || "",
                            y_keys: nextSeries,
                            orientation:
                              nextType === "horizontal_bar"
                                ? "horizontal"
                                : "vertical",
                            stack: nextSupportsStack
                              ? block.config.stack === "normal" ||
                                block.config.stack === "percent"
                                ? block.config.stack
                                : "none"
                              : "none",
                          },
                        });
                      }}
                      className="h-9 w-full border border-input bg-background px-3 text-sm outline-none focus:border-primary"
                    >
                      <option value="bar">柱状图</option>
                      <option value="horizontal_bar">横向条形图</option>
                      <option value="line">折线图</option>
                      <option value="area">面积图</option>
                      <option value="pie">环形图</option>
                      <option value="scatter">散点图</option>
                    </select>
                  )}
                </label>
                {columns.length > 1 && (
                  <div className="grid grid-cols-2 gap-3">
                    <label>
                      <FieldLabel>分类或横轴</FieldLabel>
                      <select
                        value={typeof block.config.x_key === "string" ? block.config.x_key : columns[0]}
                        onChange={(event) => onChangeBlock({ config: { ...block.config, x_key: event.target.value } })}
                        className="h-9 w-full border border-input bg-background px-2 text-xs outline-none focus:border-primary"
                      >
                        {columns.map((column) => <option key={column}>{column}</option>)}
                      </select>
                    </label>
                    <fieldset>
                      <FieldLabel>数值系列</FieldLabel>
                      <div className="max-h-28 overflow-y-auto border border-input bg-background px-2 py-1.5">
                        {numericColumns.map((column) => (
                          <label key={column} className="flex cursor-pointer items-center gap-2 py-1 text-xs">
                            <input
                              type={singleSeriesChart ? "radio" : "checkbox"}
                              name={singleSeriesChart ? `chart-series-${block.id}` : undefined}
                              checked={selectedSeries.includes(column)}
                              onChange={(event) => {
                                const next = singleSeriesChart
                                  ? event.target.checked
                                    ? [column]
                                    : selectedSeries
                                  : event.target.checked
                                    ? [...selectedSeries, column]
                                    : selectedSeries.filter((item) => item !== column);
                                onChangeBlock({
                                  config: {
                                    ...block.config,
                                    y_key: next[0] || "",
                                    y_keys: next,
                                    stack:
                                      supportsStack && next.length >= 2
                                        ? block.config.stack || "none"
                                        : "none",
                                  },
                                });
                              }}
                              className="h-3.5 w-3.5 accent-[hsl(var(--primary))]"
                            />
                            <span className="truncate">{column}</span>
                          </label>
                        ))}
                        {!numericColumns.length && (
                          <span className="block py-1 text-[11px] text-muted-foreground">
                            没有可用的数值字段
                          </span>
                        )}
                      </div>
                    </fieldset>
                  </div>
                )}
                {editableDataChart && selectedSeries.length > 0 && (
                  <div className="space-y-2 border-t border-border pt-4">
                    <FieldLabel>系列显示</FieldLabel>
                    {selectedSeries.map((series) => (
                      <div key={series} className="grid grid-cols-[minmax(0,1fr)_112px] gap-2">
                        <label className="min-w-0">
                          <span className="sr-only">{series}显示名称</span>
                          <input
                            aria-label={`${series}显示名称`}
                            value={seriesLabels[series] || ""}
                            maxLength={80}
                            placeholder={series}
                            onChange={(event) => {
                              const nextLabels = { ...seriesLabels };
                              const nextLabel = event.target.value;
                              if (nextLabel.trim()) nextLabels[series] = nextLabel;
                              else delete nextLabels[series];
                              const nextConfig = { ...block.config };
                              if (Object.keys(nextLabels).length) {
                                nextConfig.series_labels = nextLabels;
                              } else {
                                delete nextConfig.series_labels;
                              }
                              onChangeBlock({ config: nextConfig });
                            }}
                            className="h-9 w-full border border-input bg-background px-2 text-xs outline-none placeholder:text-muted-foreground focus:border-primary"
                          />
                        </label>
                        <label>
                          <span className="sr-only">{series}数值格式</span>
                          <select
                            aria-label={`${series}数值格式`}
                            value={seriesFormats[series] || ""}
                            onChange={(event) => {
                              const nextFormats = { ...seriesFormats };
                              const nextFormat = event.target.value;
                              if (nextFormat) {
                                nextFormats[series] = chartValueFormat(nextFormat);
                              } else {
                                delete nextFormats[series];
                              }
                              const nextConfig = { ...block.config };
                              if (Object.keys(nextFormats).length) {
                                nextConfig.series_formats = nextFormats;
                              } else {
                                delete nextConfig.series_formats;
                              }
                              onChangeBlock({ config: nextConfig });
                            }}
                            className="h-9 w-full border border-input bg-background px-2 text-xs outline-none focus:border-primary"
                          >
                            <option value="">跟随默认</option>
                            {CHART_VALUE_FORMAT_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                        </label>
                      </div>
                    ))}
                  </div>
                )}
                {editableDataChart && (
                  <div className="grid grid-cols-2 gap-3 border-t border-border pt-4">
                    <label>
                      <FieldLabel>方向</FieldLabel>
                      <select
                        aria-label="图表方向"
                        value={supportsOrientation ? chartOrientation : "vertical"}
                        disabled={!supportsOrientation}
                        onChange={(event) =>
                          onChangeBlock({
                            config: { ...block.config, orientation: event.target.value },
                          })
                        }
                        className="h-9 w-full border border-input bg-background px-2 text-xs outline-none focus:border-primary disabled:bg-muted/35 disabled:text-muted-foreground"
                      >
                        <option value="vertical">纵向</option>
                        <option value="horizontal">横向</option>
                      </select>
                    </label>
                    <label>
                      <FieldLabel>堆叠</FieldLabel>
                      <select
                        aria-label="图表堆叠"
                        value={
                          supportsStack &&
                          selectedSeries.length >= 2 &&
                          (block.config.stack === "normal" || block.config.stack === "percent")
                            ? block.config.stack
                            : "none"
                        }
                        disabled={!supportsStack || selectedSeries.length < 2}
                        onChange={(event) =>
                          onChangeBlock({
                            config: { ...block.config, stack: event.target.value },
                          })
                        }
                        className="h-9 w-full border border-input bg-background px-2 text-xs outline-none focus:border-primary disabled:bg-muted/35 disabled:text-muted-foreground"
                      >
                        <option value="none">不堆叠</option>
                        <option value="normal">标准堆叠</option>
                        <option value="percent">百分比堆叠</option>
                      </select>
                    </label>
                    <label>
                      <FieldLabel>默认数值格式</FieldLabel>
                      <select
                        aria-label="图表数值格式"
                        value={chartValueFormat(block.config.number_format)}
                        onChange={(event) =>
                          onChangeBlock({
                            config: { ...block.config, number_format: event.target.value },
                          })
                        }
                        className="h-9 w-full border border-input bg-background px-2 text-xs outline-none focus:border-primary"
                      >
                        {CHART_VALUE_FORMAT_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <FieldLabel>配色方案</FieldLabel>
                      <select
                        aria-label="图表配色方案"
                        value={chartPalette(block.config.palette)}
                        onChange={(event) =>
                          onChangeBlock({
                            config: { ...block.config, palette: event.target.value },
                          })
                        }
                        className="h-9 w-full border border-input bg-background px-2 text-xs outline-none focus:border-primary"
                      >
                        {CHART_PALETTE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="col-span-2 flex cursor-pointer items-center gap-2 border border-input bg-background px-3 py-2 text-xs">
                      <input
                        type="checkbox"
                        aria-label="显示数据标签"
                        checked={block.config.show_labels === true}
                        onChange={(event) =>
                          onChangeBlock({
                            config: { ...block.config, show_labels: event.target.checked },
                          })
                        }
                        className="h-3.5 w-3.5 accent-[hsl(var(--primary))]"
                      />
                      显示数据标签
                    </label>
                  </div>
                )}
              </div>
            )}

            {block.block_type === "filter" && (
              <div className="space-y-4">
                <label className="block">
                  <FieldLabel>筛选字段</FieldLabel>
                  <select
                    value={typeof block.config.field === "string" ? block.config.field : ""}
                    onChange={(event) =>
                      onChangeBlock({ config: { ...block.config, field: event.target.value } })
                    }
                    disabled={!filterFields.length}
                    className="h-9 w-full border border-input bg-background px-3 text-sm outline-none focus:border-primary disabled:text-muted-foreground"
                  >
                    <option value="">
                      {filterFields.length ? "选择字段" : "当前页面没有可筛选的数据"}
                    </option>
                    {filterFields.map((field) => <option key={field}>{field}</option>)}
                  </select>
                </label>
                <label className="block">
                  <FieldLabel>匹配方式</FieldLabel>
                  <select
                    value={typeof block.config.operator === "string" ? block.config.operator : "contains"}
                    onChange={(event) =>
                      onChangeBlock({ config: { ...block.config, operator: event.target.value } })
                    }
                    className="h-9 w-full border border-input bg-background px-3 text-sm outline-none focus:border-primary"
                  >
                    <option value="contains">包含</option>
                    <option value="equals">等于</option>
                    <option value="not_equals">不等于</option>
                    <option value="greater_than">大于</option>
                    <option value="greater_or_equal">大于或等于</option>
                    <option value="less_than">小于</option>
                    <option value="less_or_equal">小于或等于</option>
                  </select>
                </label>
                <label className="block">
                  <FieldLabel>输入提示</FieldLabel>
                  <input
                    value={typeof block.config.placeholder === "string" ? block.config.placeholder : ""}
                    onChange={(event) => onChangeBlock({ config: { ...block.config, placeholder: event.target.value } })}
                    className="h-9 w-full border border-input bg-background px-3 text-sm outline-none focus:border-primary"
                  />
                </label>
                <p className="text-[11px] leading-5 text-muted-foreground">
                  仅筛选当前页面中包含该字段的图表和表格；其他内容不会改变。
                </p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 border-t border-border pt-5">
              <label>
                <FieldLabel>宽度</FieldLabel>
                <select
                  value={block.layout.w}
                  onChange={(event) => onChangeBlock({ layout: { ...block.layout, w: Number(event.target.value) } })}
                  className="h-9 w-full border border-input bg-background px-2 text-xs outline-none focus:border-primary"
                >
                  <option value={3}>四分之一</option>
                  <option value={4}>三分之一</option>
                  <option value={6}>一半</option>
                  <option value={8}>三分之二</option>
                  <option value={12}>整行</option>
                </select>
              </label>
              <label>
                <FieldLabel>高度</FieldLabel>
                <select
                  value={block.layout.h}
                  onChange={(event) => onChangeBlock({ layout: { ...block.layout, h: Number(event.target.value) } })}
                  className="h-9 w-full border border-input bg-background px-2 text-xs outline-none focus:border-primary"
                >
                  <option value={2}>紧凑</option>
                  <option value={3}>标准</option>
                  <option value={4}>较高</option>
                  <option value={6}>大幅</option>
                </select>
              </label>
            </div>

            {block.source_kind !== "manual" && (
              <p className="border-t border-border pt-4 text-[11px] leading-5 text-muted-foreground">
                {block.source_available === false
                  ? "原调查内容已不可用；报告中保留的内容仍可继续编辑。"
                  : block.config.manual_override === true
                  ? "内容已经人工调整；原调查和来源仍会保留。"
                  : "这个区块来自一次调查。你可以自由修改；原调查仍会保留。"}
              </p>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
