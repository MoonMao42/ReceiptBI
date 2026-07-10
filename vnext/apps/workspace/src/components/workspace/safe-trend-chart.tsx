"use client";

import type { KeyboardEvent } from "react";
import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";

import { revenueTrend } from "./sample-data";

const chartData = revenueTrend.map((item) => ({ ...item }));

const series = [
  { dataKey: "north", label: "华北", token: "var(--chart-primary)" },
  { dataKey: "south", label: "华东", token: "var(--chart-secondary)" },
] as const;

type DrilldownDotProps = {
  cx?: number;
  cy?: number;
  payload?: (typeof chartData)[number];
};

type SafeTrendChartProps = {
  onPrepareDrilldown: (month: string) => void;
};

export function SafeTrendChart({ onPrepareDrilldown }: SafeTrendChartProps) {
  const [selectedMonth, setSelectedMonth] = useState<string>();

  const selectMonth = (month: string) => {
    setSelectedMonth(month);
  };

  const handleDotKeyDown = (
    event: KeyboardEvent<SVGCircleElement>,
    month: string,
  ) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectMonth(month);
    }
  };

  const renderDrilldownDot = ({ cx, cy, payload }: DrilldownDotProps) => {
    if (cx === undefined || cy === undefined || payload === undefined) {
      return null;
    }

    return (
      <circle
        aria-label={`准备下钻 ${payload.month}`}
        className="cursor-pointer outline-none focus:stroke-[4]"
        cx={cx}
        cy={cy}
        fill="var(--canvas)"
        focusable="true"
        onClick={() => selectMonth(payload.month)}
        onKeyDown={(event) => handleDotKeyDown(event, payload.month)}
        r={4.5}
        role="button"
        stroke="var(--chart-primary)"
        strokeWidth={2.5}
        tabIndex={0}
      />
    );
  };

  return (
    <div>
      <div
        aria-label="华北和华东最近六个月净利润趋势图"
        className="h-[330px] w-full"
        role="group"
      >
        <ResponsiveContainer height="100%" width="100%">
          <AreaChart accessibilityLayer data={chartData}>
            <defs>
              {series.map((item) => (
                <linearGradient id={`fill-${item.dataKey}`} key={item.dataKey} x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor={item.token} stopOpacity={0.2} />
                  <stop offset="95%" stopColor={item.token} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid stroke="var(--border)" strokeDasharray="4 6" vertical={false} />
            <XAxis axisLine={false} dataKey="month" tick={{ fill: "var(--muted)", fontSize: 12 }} tickLine={false} />
            <YAxis
              axisLine={false}
              tick={{ fill: "var(--muted)", fontSize: 12 }}
              tickFormatter={(value: number) => `${value}万`}
              tickLine={false}
              width={52}
            />
            <Tooltip
              contentStyle={{
                background: "var(--canvas)",
                border: "1px solid var(--border)",
                borderRadius: 12,
                boxShadow: "var(--shadow-soft)",
              }}
              formatter={(value) => [`${String(value)} 万元`]}
            />
            <Legend formatter={(value) => series.find((item) => item.dataKey === value)?.label ?? value} />
            {series.map((item) => (
              <Area
                dataKey={item.dataKey}
                dot={item.dataKey === "north" ? renderDrilldownDot : false}
                fill={`url(#fill-${item.dataKey})`}
                isAnimationActive={false}
                key={item.dataKey}
                name={item.dataKey}
                stroke={item.token}
                strokeWidth={2.5}
                type="monotone"
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {selectedMonth ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-accent-soft px-4 py-3 text-sm">
          <div>
            <span className="font-medium">准备深入查看 {selectedMonth}</span>
            <span className="ml-2 text-muted">只会写入追问草稿，不会自动执行。</span>
          </div>
          <div className="flex gap-2">
            <Button onClick={() => setSelectedMonth(undefined)} variant="ghost">
              取消
            </Button>
            <Button
              onClick={() => {
                onPrepareDrilldown(selectedMonth);
                setSelectedMonth(undefined);
              }}
            >
              写入追问草稿
            </Button>
          </div>
        </div>
      ) : null}

      <details className="mt-4 text-sm">
        <summary className="cursor-pointer text-muted hover:text-foreground">查看无障碍数据表</summary>
        <div className="mt-3 overflow-x-auto rounded-xl border">
          <table className="w-full border-collapse text-left">
            <thead className="bg-surface text-xs text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">月份</th>
                <th className="px-3 py-2 font-medium">华北</th>
                <th className="px-3 py-2 font-medium">华东</th>
              </tr>
            </thead>
            <tbody>
              {chartData.map((row) => (
                <tr className="border-t" key={row.month}>
                  <td className="px-3 py-2">{row.month}</td>
                  <td className="px-3 py-2">{row.north} 万元</td>
                  <td className="px-3 py-2">{row.south} 万元</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
