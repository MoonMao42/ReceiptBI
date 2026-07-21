import { Check, CircleAlert, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface AnalysisProgressProps {
  state?: string;
  status?: string;
}

type ProgressTone = "done" | "active" | "waiting" | "attention";

type ProductAnalysisState =
  | "understanding"
  | "waiting_confirmation"
  | "investigating"
  | "completed"
  | "needs_attention";

interface ProgressView {
  state: ProductAnalysisState;
  label: string;
  detail: string;
  tone: ProgressTone;
}

function currentWork(state?: string): ProgressView {
  switch (state) {
    case "waiting_confirmation":
      return {
        state: "waiting_confirmation",
        label: "等待你的确认",
        detail: "有一项会影响结论的业务判断需要你确认",
        tone: "waiting",
      };
    case "needs_attention":
      return {
        state: "needs_attention",
        label: "这份调查需要处理",
        detail: "当前进度已经保留，处理提示的问题后可以继续",
        tone: "attention",
      };
    case "completed":
      return {
        state: "completed",
        label: "调查已完成",
        detail: "报告和本次调查依据已经保存",
        tone: "done",
      };
    case "investigating":
      return {
        state: "investigating",
        label: "正在核对发现",
        detail: "比较数据、验证关系和异常",
        tone: "active",
      };
    case "understanding":
    default:
      return {
        state: "understanding",
        label: "正在理解数据",
        detail: "识别可用内容和需要确认的口径",
        tone: "active",
      };
  }
}

function safeProgressDetail(status: string | undefined, fallback: string): string {
  if (!status || status === "Analyzing...") return fallback;
  if (
    /\b(sql|python|schema|json|tool|agent|token|api)\b|工具|智能体|模型|提示词|代码|脚本/i.test(
      status
    )
  ) {
    return fallback;
  }
  return status.length > 72 ? `${status.slice(0, 72)}…` : status;
}

export function AnalysisProgress({ state, status }: AnalysisProgressProps) {
  const current = currentWork(state);
  const detail = safeProgressDetail(status, current.detail);

  return (
    <section
      aria-label="当前调查进度"
      className="w-full max-w-[920px] border-y border-border bg-card px-5 py-5 sm:px-6"
    >
      <div
        aria-atomic="true"
        aria-live="polite"
        data-progress-state={current.state}
        className="grid grid-cols-[28px_minmax(0,1fr)] gap-3"
      >
        <span
          aria-hidden="true"
          className={cn(
            "mt-0.5 flex h-7 w-7 items-center justify-center rounded-full border bg-card",
            current.tone === "done" && "border-primary bg-primary text-primary-foreground",
            current.tone === "active" && "border-primary text-primary",
            current.tone === "attention" && "border-warning text-warning",
            current.tone === "waiting" && "border-warning/60 text-warning"
          )}
        >
          {current.tone === "done" ? (
            <Check size={14} strokeWidth={2.5} />
          ) : current.tone === "active" ? (
            <Loader2 size={14} className="animate-spin" />
          ) : current.tone === "attention" ? (
            <CircleAlert size={14} />
          ) : (
            <span className="h-2 w-2 rounded-full bg-warning" />
          )}
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
            <h2
              className={cn(
                "text-sm font-semibold tracking-[-0.01em] text-foreground",
                current.tone === "attention" && "text-warning"
              )}
            >
              {current.label}
            </h2>
            <span className="text-[10px] font-medium tracking-[0.13em] text-primary">
              RECEIPTBI
            </span>
          </div>
          <p
            className={cn(
              "mt-1 text-xs leading-5 text-muted-foreground",
              current.tone === "attention" && "text-warning/80"
            )}
          >
            {detail}
          </p>
        </div>
      </div>
    </section>
  );
}
