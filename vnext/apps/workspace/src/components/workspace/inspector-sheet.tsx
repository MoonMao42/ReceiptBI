"use client";

import { useState } from "react";

import { Sheet, SheetContent } from "@/components/ui/sheet";
import { cn } from "@/lib/cn";

type InspectorSheetProps = {
  onOpenChange: (open: boolean) => void;
  open: boolean;
};

const tabs = ["语义", "查询", "本地分析", "血缘"] as const;
type InspectorTab = (typeof tabs)[number];

const content: Record<InspectorTab, { body: string; label: string; value: string }[]> = {
  查询: [
    { label: "执行方式", value: "计划：只读", body: "真实接入后仅访问已批准的数据范围。" },
    { label: "数据量", value: "示例 12 行", body: "当前只用于演示结果布局。" },
    { label: "耗时", value: "未执行", body: "尚未连接本地数据库。" },
  ],
  本地分析: [
    { label: "运行位置", value: "此设备", body: "分析数据未离开本机。" },
    { label: "分析方法", value: "计划：趋势外推", body: "后续使用固定、可复现的分析步骤。" },
    { label: "状态", value: "未执行", body: "当前没有启动分析舱。" },
  ],
  血缘: [
    { label: "来源", value: "销售数据", body: "订单、区域和退款三个受管对象。" },
    { label: "结果", value: "净利润趋势", body: "图表与摘要共享同一份结果数据。" },
  ],
  语义: [
    { label: "指标", value: "净利润", body: "订单收入减去退款与履约成本。" },
    { label: "维度", value: "销售区域", body: "华东与华北使用统一地域映射。" },
    { label: "时间", value: "自然月", body: "按本地时区的闭开区间计算。" },
  ],
};

export function InspectorSheet({ onOpenChange, open }: InspectorSheetProps) {
  const [tab, setTab] = useState<InspectorTab>("语义");

  return (
    <Sheet onOpenChange={onOpenChange} open={open}>
      <SheetContent description="当前展示交互原型的示例依据；尚未执行真实查询。" title="结果依据">
        <div aria-label="检查器分类" className="grid grid-cols-4 rounded-xl bg-surface p-1" role="tablist">
          {tabs.map((item) => (
            <button
              aria-selected={tab === item}
              className={cn(
                "rounded-lg px-2 py-2 text-xs font-medium text-muted",
                tab === item && "bg-canvas text-foreground shadow-sm",
              )}
              key={item}
              onClick={() => setTab(item)}
              role="tab"
              type="button"
            >
              {item}
            </button>
          ))}
        </div>

        <div className="mt-6 space-y-3">
          {content[tab].map((item) => (
            <section className="rounded-xl border p-4" key={item.label}>
              <div className="flex items-center justify-between gap-4">
                <h3 className="m-0 text-sm font-medium">{item.label}</h3>
                <span className="text-sm text-accent">{item.value}</span>
              </div>
              <p className="mb-0 mt-2 text-sm leading-6 text-muted">{item.body}</p>
            </section>
          ))}
        </div>

        <details className="mt-6 border-t pt-5 text-sm">
          <summary className="cursor-pointer font-medium">开发者详情</summary>
          <pre className="mt-3 overflow-x-auto rounded-xl bg-surface p-4 font-mono text-xs leading-5 text-muted">
            semantic-query@1 · prototype · no execution
          </pre>
        </details>
      </SheetContent>
    </Sheet>
  );
}
