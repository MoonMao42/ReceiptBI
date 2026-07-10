"use client";

import { PanelRightOpen } from "lucide-react";
import { domAnimation, LazyMotion, m } from "motion/react";

import { Button } from "@/components/ui/button";

import { ChartSkeleton } from "./chart-skeleton";
import { SafeTrendChart } from "./safe-trend-chart";

type ResultCanvasProps = {
  loading: boolean;
  onOpenInspector: () => void;
  onPrepareDrilldown: (month: string) => void;
  resultId: string;
};

const metrics = [
  { change: "+18.4%", label: "华北净利润", value: "104 万" },
  { change: "+10.5%", label: "华东净利润", value: "84 万" },
  { change: "20 万", label: "区域差额", value: "20 万" },
] as const;

export function ResultCanvas({
  loading,
  onOpenInspector,
  onPrepareDrilldown,
  resultId,
}: ResultCanvasProps) {
  return (
    <main aria-busy={loading} className="min-h-0 flex-1 overflow-y-auto bg-background" id={resultId}>
      <div className="mx-auto min-h-full max-w-6xl px-5 py-5 md:px-8 md:py-7">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs text-muted">
              <span className="rounded-full bg-accent-soft px-2 py-1 font-medium text-accent">交互原型</span>
              <span>示例数据 · 尚未连接本地数据库</span>
            </div>
            <h2 className="mb-0 mt-4 text-2xl font-semibold tracking-tight md:text-[28px]">华北增速领先，华东仍贡献更多利润</h2>
            <p className="mb-0 mt-2 max-w-3xl text-sm leading-6 text-muted md:text-base">
              两个区域近六个月均保持增长。华北增长更快，但当前规模仍比华东低约 20 万元。
            </p>
          </div>
          <div className="flex items-center gap-1">
            <Button onClick={onOpenInspector} variant="outline">
              <PanelRightOpen aria-hidden="true" className="size-4" />
              依据
            </Button>
          </div>
        </header>

        <LazyMotion features={domAnimation}>
          <m.div animate={{ opacity: 1, y: 0 }} initial={{ opacity: 0, y: 8 }} key={loading ? "loading" : "ready"} transition={{ duration: 0.24 }}>
            {loading ? (
              <div className="mt-8">
                <ChartSkeleton />
              </div>
            ) : (
              <>
                <section aria-label="关键指标" className="mt-8 grid gap-px overflow-hidden rounded-2xl border bg-border sm:grid-cols-3">
                  {metrics.map((metric) => (
                    <div className="bg-canvas px-5 py-5" key={metric.label}>
                      <div className="text-sm text-muted">{metric.label}</div>
                      <div className="mt-2 flex items-end justify-between gap-3">
                        <strong className="text-2xl font-semibold tracking-tight">{metric.value}</strong>
                        <span className="text-xs font-medium text-success">{metric.change}</span>
                      </div>
                    </div>
                  ))}
                </section>

                <section className="mt-6 rounded-2xl bg-canvas p-5 shadow-[var(--shadow-soft)] md:p-7">
                  <div className="flex flex-wrap items-end justify-between gap-3">
                    <div>
                      <h3 className="m-0 text-lg font-semibold">净利润趋势</h3>
                      <p className="mb-0 mt-1 text-sm text-muted">单位：万元 · 点击折线节点可准备下钻</p>
                    </div>
                    <div className="text-xs text-muted">最近 6 个月</div>
                  </div>
                  <div className="mt-6">
                    <SafeTrendChart onPrepareDrilldown={onPrepareDrilldown} />
                  </div>
                </section>

                <section className="mt-6 grid gap-4 pb-10 md:grid-cols-3">
                  {[
                    ["增长驱动", "华北的企业客户复购贡献了主要增量。"],
                    ["需要关注", "华东毛利率改善，但退款率仍高于华北。"],
                    ["下一步", "建议检查华东 6 月退款上升的产品类别。"],
                  ].map(([title, body]) => (
                    <div className="border-t pt-4" key={title}>
                      <h3 className="m-0 text-sm font-semibold">{title}</h3>
                      <p className="mb-0 mt-2 text-sm leading-6 text-muted">{body}</p>
                    </div>
                  ))}
                </section>
              </>
            )}
          </m.div>
        </LazyMotion>
      </div>
    </main>
  );
}
