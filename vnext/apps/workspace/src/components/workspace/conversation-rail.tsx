"use client";

import { ArrowUp, CheckCircle2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";

type ConversationRailProps = {
  inputId: string;
  onRegenerate: () => void;
  onQuestionChange: (question: string) => void;
  question: string;
  sectionId: string;
};

export function ConversationRail({
  inputId,
  onQuestionChange,
  onRegenerate,
  question,
  sectionId,
}: ConversationRailProps) {
  return (
    <section className="flex h-full min-h-0 flex-col bg-canvas" id={sectionId}>
      <header className="border-b px-5 py-4">
        <div className="text-xs text-muted">本月经营分析</div>
        <h1 className="mt-1 text-base font-semibold">华东和华北的净利润趋势</h1>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6">
        <div className="ml-auto max-w-[88%] rounded-2xl rounded-br-md bg-foreground px-4 py-3 text-sm leading-6 text-canvas">
          对比上个月华东和华北的净利润，并分析下个月可能的趋势。
        </div>

        <div className="mt-7 flex gap-3">
          <div className="grid size-8 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent">
            <Sparkles aria-hidden="true" className="size-4" />
          </div>
          <div className="min-w-0 text-sm leading-6">
            <p className="m-0 font-medium">华北增速更快，华东贡献仍然领先。</p>
            <p className="mt-2 text-muted">
              过去六个月两区净利润持续上升；华北最近两个月的增长斜率更高。完整图表和依据已放到右侧画布。
            </p>
            <button className="mt-3 text-sm font-medium text-accent hover:underline" onClick={onRegenerate} type="button">
              重新生成画布
            </button>
          </div>
        </div>

        <div className="mt-8 flex items-center gap-2 rounded-xl bg-surface px-3 py-2 text-xs text-muted">
          <CheckCircle2 aria-hidden="true" className="size-3.5 text-success" />
          示例口径预览 · 尚未执行真实查询
        </div>
      </div>

      <form className="border-t bg-canvas p-4" onSubmit={(event) => event.preventDefault()}>
        <label className="sr-only" htmlFor={inputId}>
          继续追问
        </label>
        <div className="flex items-end gap-2 rounded-2xl border bg-surface-raised p-2 shadow-sm">
          <textarea
            className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted"
            id={inputId}
            onChange={(event) => onQuestionChange(event.target.value)}
            placeholder="继续追问，或要求调整图表…"
            rows={1}
            value={question}
          />
          <Button aria-label="发送问题" disabled={question.trim().length === 0} size="icon" type="submit">
            <ArrowUp aria-hidden="true" className="size-4" />
          </Button>
        </div>
        <p className="mb-0 mt-2 text-center text-[11px] text-muted">原型仅演示交互；尚未接入 LLM 与数据执行</p>
      </form>
    </section>
  );
}
