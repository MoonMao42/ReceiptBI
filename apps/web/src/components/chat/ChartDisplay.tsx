"use client";

import { useId, useState } from "react";
import {
  AreaChart as AreaChartIcon,
  BarChart3,
  BarChartHorizontal,
  LineChart as LineChartIcon,
  PieChart as PieChartIcon,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
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
  getChartPalette,
  type ChartSpec,
  type ChartValueFormat,
  type ChartYEncoding,
} from "@/lib/charts";

interface ChartDisplayProps {
  spec: ChartSpec;
}

const TYPE_LABELS: Record<ChartSpec["type"], string> = {
  bar: "柱状图",
  horizontal_bar: "横向柱状图",
  line: "折线图",
  area: "面积图",
  pie: "饼图",
  scatter: "散点图",
};

const TOOLTIP_STYLE = {
  backgroundColor: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: "8px",
  color: "hsl(var(--foreground))",
};

// Deterministic local chart-type switching: the same data can be re-rendered
// without another LLM round-trip. Scatter is excluded because it needs a
// numeric x field, which arbitrary category data cannot guarantee.
const TYPE_OPTIONS: Array<{
  value: ChartSpec["type"];
  label: string;
  Icon: typeof BarChart3;
}> = [
  { value: "bar", label: "柱状图", Icon: BarChart3 },
  { value: "horizontal_bar", label: "横向柱状图", Icon: BarChartHorizontal },
  { value: "line", label: "折线图", Icon: LineChartIcon },
  { value: "area", label: "面积图", Icon: AreaChartIcon },
  { value: "pie", label: "饼图", Icon: PieChartIcon },
];

function formatChartValue(
  value: unknown,
  format: ChartValueFormat = "auto",
): string {
  if (value === null || value === undefined) return "—";
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return String(value);
  }
  switch (format) {
    case "integer":
      return new Intl.NumberFormat("zh-CN", {
        maximumFractionDigits: 0,
      }).format(value);
    case "compact":
      return new Intl.NumberFormat("zh-CN", {
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(value);
    case "currency":
      return new Intl.NumberFormat("zh-CN", {
        style: "currency",
        currency: "CNY",
        maximumFractionDigits: 2,
      }).format(value);
    case "percent":
      return new Intl.NumberFormat("zh-CN", {
        style: "percent",
        maximumFractionDigits: 1,
      }).format(value);
    case "number":
      return new Intl.NumberFormat("zh-CN", {
        maximumFractionDigits: 2,
      }).format(value);
    default:
      return new Intl.NumberFormat("zh-CN", {
        maximumFractionDigits: 4,
      }).format(value);
  }
}

function encodingLabel(encoding: { field: string; label?: string }): string {
  return encoding.label || encoding.field;
}

function chartSummary(spec: ChartSpec, chartType: ChartSpec["type"]): string {
  const x = spec.encoding.x;
  const series = spec.encoding.y.map(encodingLabel).join("、");
  return `${spec.title || "分析结果图"}，${TYPE_LABELS[chartType]}，${
    x ? `按${encodingLabel(x)}展示` : "未指定分类字段"
  }，指标为${series}，共 ${spec.data.length} 条记录。`;
}

export function ChartDisplay({ spec }: ChartDisplayProps) {
  const instanceId = useId().replace(/:/g, "");
  const [typeOverride, setTypeOverride] = useState<ChartSpec["type"] | null>(
    null,
  );
  const chartType = typeOverride ?? spec.type;
  const x = spec.encoding.x;
  const y = spec.encoding.y;
  const palette = getChartPalette(spec.presentation.palette);
  const stacked = spec.presentation.stack !== "none";
  const percentStack = spec.presentation.stack === "percent";
  const horizontal =
    chartType === "horizontal_bar" ||
    spec.presentation.orientation === "horizontal";
  const summary = chartSummary(spec, chartType);
  const chartId = `chart-${spec.data_ref?.result_hash?.slice(0, 12) || instanceId}`;

  if (!x || y.length === 0 || spec.data.length === 0) {
    return (
      <div className="mt-4 flex h-48 items-center justify-center bg-secondary text-muted-foreground">
        暂无可显示的数据
      </div>
    );
  }

  const findEncoding = (
    name: unknown,
    dataKey?: unknown,
  ): ChartYEncoding | undefined => {
    const renderedKey = typeof dataKey === "string" ? dataKey : "";
    const renderedName = String(name);
    return y.find(
      (item) =>
        item.field === renderedKey ||
        item.field === renderedName ||
        encodingLabel(item) === renderedName,
    );
  };
  const tooltip = (
    <Tooltip
      contentStyle={TOOLTIP_STYLE}
      formatter={(value, name, item) => {
        const encoding = findEncoding(name, item.dataKey);
        return [
          // stackOffset="expand" normalizes only the rendered stack. Tooltip
          // payloads still contain the original measure, so preserve its own
          // format instead of turning values such as 120 into 12,000%.
          formatChartValue(value, encoding?.format),
          encoding ? encodingLabel(encoding) : String(name),
        ];
      }}
    />
  );

  const renderChart = () => {
    switch (chartType) {
      case "bar":
      case "horizontal_bar":
        return (
          <BarChart
            data={spec.data}
            layout={horizontal ? "vertical" : "horizontal"}
            stackOffset={percentStack ? "expand" : "none"}
          >
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            {horizontal ? (
              <>
                <XAxis
                  type="number"
                  tick={{ fontSize: 12 }}
                  tickFormatter={(value) =>
                    formatChartValue(
                      value,
                      percentStack ? "percent" : y[0]?.format,
                    )
                  }
                  className="stroke-muted-foreground"
                  label={
                    y.length === 1
                      ? {
                          value: encodingLabel(y[0]),
                          position: "insideBottom",
                          offset: -4,
                        }
                      : undefined
                  }
                />
                <YAxis
                  type="category"
                  dataKey={x.field}
                  tick={{ fontSize: 12 }}
                  width={80}
                  className="stroke-muted-foreground"
                />
              </>
            ) : (
              <>
                <XAxis
                  dataKey={x.field}
                  tick={{ fontSize: 12 }}
                  className="stroke-muted-foreground"
                  label={
                    x.label
                      ? { value: x.label, position: "insideBottom", offset: -4 }
                      : undefined
                  }
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  tickFormatter={(value) =>
                    formatChartValue(
                      value,
                      percentStack ? "percent" : y[0]?.format,
                    )
                  }
                  className="stroke-muted-foreground"
                />
              </>
            )}
            {tooltip}
            <Legend />
            {y.map((encoding, index) => (
              <Bar
                key={encoding.field}
                dataKey={encoding.field}
                name={encodingLabel(encoding)}
                fill={palette[index % palette.length]}
                stackId={stacked ? "series" : undefined}
                radius={stacked ? 0 : [4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        );

      case "line":
        return (
          <LineChart data={spec.data}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              dataKey={x.field}
              tick={{ fontSize: 12 }}
              className="stroke-muted-foreground"
              label={
                x.label
                  ? { value: x.label, position: "insideBottom", offset: -4 }
                  : undefined
              }
            />
            <YAxis
              tick={{ fontSize: 12 }}
              tickFormatter={(value) => formatChartValue(value, y[0]?.format)}
              className="stroke-muted-foreground"
            />
            {tooltip}
            <Legend />
            {y.map((encoding, index) => (
              <Line
                key={encoding.field}
                type="monotone"
                dataKey={encoding.field}
                name={encodingLabel(encoding)}
                stroke={palette[index % palette.length]}
                strokeWidth={2}
                dot={{
                  fill: palette[index % palette.length],
                  strokeWidth: 2,
                }}
              />
            ))}
          </LineChart>
        );

      case "area":
        return (
          <AreaChart
            data={spec.data}
            stackOffset={percentStack ? "expand" : "none"}
          >
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              dataKey={x.field}
              tick={{ fontSize: 12 }}
              className="stroke-muted-foreground"
              label={
                x.label
                  ? { value: x.label, position: "insideBottom", offset: -4 }
                  : undefined
              }
            />
            <YAxis
              tick={{ fontSize: 12 }}
              tickFormatter={(value) =>
                formatChartValue(
                  value,
                  percentStack ? "percent" : y[0]?.format,
                )
              }
              className="stroke-muted-foreground"
            />
            {tooltip}
            <Legend />
            {y.map((encoding, index) => (
              <Area
                key={encoding.field}
                type="monotone"
                dataKey={encoding.field}
                name={encodingLabel(encoding)}
                stroke={palette[index % palette.length]}
                fill={palette[index % palette.length]}
                fillOpacity={0.2}
                strokeWidth={2}
                stackId={stacked ? "series" : undefined}
              />
            ))}
          </AreaChart>
        );

      case "pie": {
        const value = y[0];
        return (
          <PieChart>
            <Pie
              data={spec.data}
              dataKey={value.field}
              nameKey={x.field}
              name={encodingLabel(value)}
              cx="50%"
              cy="50%"
              outerRadius={80}
              label={({ name, percent }) =>
                `${name}: ${(percent * 100).toFixed(0)}%`
              }
            >
              {spec.data.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={palette[index % palette.length]}
                />
              ))}
            </Pie>
            {tooltip}
            <Legend />
          </PieChart>
        );
      }

      case "scatter": {
        const value = y[0];
        return (
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              type="number"
              dataKey={x.field}
              name={encodingLabel(x)}
              tick={{ fontSize: 12 }}
              className="stroke-muted-foreground"
            />
            <YAxis
              type="number"
              dataKey={value.field}
              name={encodingLabel(value)}
              tick={{ fontSize: 12 }}
              tickFormatter={(axisValue) =>
                formatChartValue(axisValue, value.format)
              }
              className="stroke-muted-foreground"
            />
            {tooltip}
            <Legend />
            <Scatter
              name={encodingLabel(value)}
              data={spec.data}
              fill={palette[0]}
            />
          </ScatterChart>
        );
      }
    }
  };

  return (
    <figure className="mt-4 bg-card p-4" aria-labelledby={`${chartId}-title`}>
      <figcaption
        id={`${chartId}-title`}
        className="mb-3 flex items-center justify-between gap-3"
      >
        <span
          className={
            spec.title ? "text-sm font-medium text-foreground" : "sr-only"
          }
        >
          {spec.title || "分析结果图"}
        </span>
        <span
          className="flex items-center gap-0.5 border border-border bg-background p-0.5"
          role="group"
          aria-label="切换图表类型"
        >
          {TYPE_OPTIONS.map(({ value, label, Icon }) => {
            const active = chartType === value;
            return (
              <button
                key={value}
                type="button"
                title={label}
                aria-label={label}
                aria-pressed={active}
                onClick={() => setTypeOverride(value)}
                className={`flex h-6 w-6 items-center justify-center transition-colors ${
                  active
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Icon size={13} />
              </button>
            );
          })}
        </span>
      </figcaption>
      <div className="h-64" role="img" aria-label={summary}>
        <ResponsiveContainer width="100%" height="100%">
          {renderChart()}
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <caption>{summary}</caption>
        <thead>
          <tr>
            <th scope="col">{encodingLabel(x)}</th>
            {y.map((encoding) => (
              <th key={encoding.field} scope="col">
                {encodingLabel(encoding)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spec.data.map((row, rowIndex) => (
            <tr key={rowIndex}>
              <th scope="row">{String(row[x.field] ?? "—")}</th>
              {y.map((encoding) => (
                <td key={encoding.field}>
                  {formatChartValue(row[encoding.field], encoding.format)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
