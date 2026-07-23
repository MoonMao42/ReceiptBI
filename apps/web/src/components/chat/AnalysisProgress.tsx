import { Check, CircleAlert, Loader2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

interface AnalysisProgressProps {
  state?: string;
  stage?: string;
  status?: string;
}

type ProgressTone = "done" | "active" | "waiting" | "attention";

type ProductAnalysisState =
  | "understanding"
  | "waiting_confirmation"
  | "investigating"
  | "completed"
  | "needs_attention";

type AnalysisProgressKey =
  | "awaiting"
  | "awaitingDesc"
  | "needsAttention"
  | "needsAttentionDesc"
  | "completed"
  | "completedDesc"
  | "verifying"
  | "verifyingDesc"
  | "understanding"
  | "understandingDesc"
  | "preparingDesc"
  | "contextReadyDesc"
  | "restoringDesc"
  | "savedMethodDesc"
  | "preparingMaterialsDesc"
  | "readingDatabaseDesc"
  | "readingFilesDesc"
  | "checkingDataDesc"
  | "finalValidationDesc"
  | "relatingSourcesDesc"
  | "aggregatingDesc"
  | "confirmedDefinitionsDesc"
  | "visualizingDesc"
  | "relationshipValidationDesc"
  | "supplementalAnalysisDesc"
  | "capabilitiesDesc"
  | "recordingUnderstandingDesc"
  | "businessExplanationUnavailableDesc"
  | "brand";

interface ProgressView {
  state: ProductAnalysisState;
  label: string;
  detail: string;
  tone: ProgressTone;
}

function currentWork(
  state: string | undefined,
  t: (key: AnalysisProgressKey) => string
): ProgressView {
  switch (state) {
    case "waiting_confirmation":
      return {
        state: "waiting_confirmation",
        label: t("awaiting"),
        detail: t("awaitingDesc"),
        tone: "waiting",
      };
    case "needs_attention":
      return {
        state: "needs_attention",
        label: t("needsAttention"),
        detail: t("needsAttentionDesc"),
        tone: "attention",
      };
    case "completed":
      return {
        state: "completed",
        label: t("completed"),
        detail: t("completedDesc"),
        tone: "done",
      };
    case "investigating":
      return {
        state: "investigating",
        label: t("verifying"),
        detail: t("verifyingDesc"),
        tone: "active",
      };
    case "understanding":
    default:
      return {
        state: "understanding",
        label: t("understanding"),
        detail: t("understandingDesc"),
        tone: "active",
      };
  }
}

const STAGE_DETAIL_KEYS: Record<string, AnalysisProgressKey> = {
  start: "preparingDesc",
  context_ready: "contextReadyDesc",
  understanding: "understandingDesc",
  restoring: "restoringDesc",
  prepared: "preparingDesc",
  confirmation_processing: "awaitingDesc",
  data_received: "preparingMaterialsDesc",
  investigating: "verifyingDesc",
  analyzing: "verifyingDesc",
  routing: "preparingMaterialsDesc",
  generating_sql: "checkingDataDesc",
  executing: "checkingDataDesc",
  processing: "verifyingDesc",
  visualizing: "visualizingDesc",
  summarizing: "aggregatingDesc",
  waiting_confirmation: "awaitingDesc",
  needs_attention: "needsAttentionDesc",
  paused: "needsAttentionDesc",
  completed: "completedDesc",
  restore_saved_steps: "restoringDesc",
  understand_data: "understandingDesc",
  confirmation_required: "awaitingDesc",
  check_saved_method: "savedMethodDesc",
  investigate: "verifyingDesc",
  project_context_checked: "contextReadyDesc",
  prepare_materials: "preparingMaterialsDesc",
  read_database: "readingDatabaseDesc",
  read_files: "readingFilesDesc",
  validate_results: "finalValidationDesc",
  relate_sources: "relatingSourcesDesc",
  aggregate_results: "aggregatingDesc",
  check_confirmed_definitions: "confirmedDefinitionsDesc",
  render_chart: "visualizingDesc",
  validate_relationships: "relationshipValidationDesc",
  supplemental_analysis: "supplementalAnalysisDesc",
  prepare_capabilities: "capabilitiesDesc",
  record_understanding: "recordingUnderstandingDesc",
  more_data_required: "needsAttentionDesc",
  complete_report: "completedDesc",
  business_explanation_unavailable: "businessExplanationUnavailableDesc",
};

const KNOWN_STATUS_KEYS: Record<string, AnalysisProgressKey> = {
  "开始处理请求": "preparingDesc",
  "processing request": "preparingDesc",
  "执行上下文已准备": "contextReadyDesc",
  "execution context ready": "contextReadyDesc",
  "正在分析": "verifyingDesc",
  analyzing: "verifyingDesc",
  "正在路由": "preparingMaterialsDesc",
  routing: "preparingMaterialsDesc",
  "正在生成 sql": "checkingDataDesc",
  "generating sql": "checkingDataDesc",
  "正在执行": "checkingDataDesc",
  executing: "checkingDataDesc",
  "正在处理": "verifyingDesc",
  processing: "verifyingDesc",
  "正在生成图表": "visualizingDesc",
  "generating chart": "visualizingDesc",
  "正在总结": "aggregatingDesc",
  summarizing: "aggregatingDesc",
  "正在恢复上次已保存的调查步骤": "restoringDesc",
  "正在理解数据和业务口径": "understandingDesc",
  "正在按已保存的方法核对当前数据": "savedMethodDesc",
  "正在调查数据并核对结论": "verifyingDesc",
  "已检查当前项目的数据和业务口径": "contextReadyDesc",
  "正在按真实数据结构整理调查所需资料": "preparingMaterialsDesc",
  "正在读取与问题相关的数据库资料": "readingDatabaseDesc",
  "正在读取与问题相关的文件资料": "readingFilesDesc",
  "正在验证最终结果": "finalValidationDesc",
  "正在关联不同来源的数据": "relatingSourcesDesc",
  "正在汇总关键结果": "aggregatingDesc",
  "正在按已确认的业务口径核对数据": "confirmedDefinitionsDesc",
  "正在生成并核对结果图": "visualizingDesc",
  "正在核对数据之间的关联是否可靠": "relationshipValidationDesc",
  "正在执行补充分析": "supplementalAnalysisDesc",
  "正在准备这次分析需要的能力": "capabilitiesDesc",
  "正在记录可复用的业务理解": "recordingUnderstandingDesc",
  "有一个会影响结论的业务口径需要确认": "awaitingDesc",
  "还需要补充少量相关数据才能继续": "needsAttentionDesc",
  "调查完成，正在整理报告": "completedDesc",
  "数据结果已经核对，业务解释未能补充":
    "businessExplanationUnavailableDesc",
};

function normalizedStatus(value: string): string {
  return value.trim().replace(/[.。…]+$/u, "").toLocaleLowerCase("en");
}

function isSameLanguage(value: string, locale: string): boolean {
  const hasHan = /\p{Script=Han}/u.test(value);
  const hasLatin = /\p{Script=Latin}/u.test(value);
  return locale.toLowerCase().startsWith("zh")
    ? hasHan
    : hasLatin && !hasHan;
}

function safeProgressDetail(
  stage: string | undefined,
  status: string | undefined,
  locale: string,
  fallback: string,
  t: (key: AnalysisProgressKey) => string
): string {
  const stageKey = STAGE_DETAIL_KEYS[stage?.trim().toLowerCase() || ""];
  const stageFallback = stageKey ? t(stageKey) : fallback;
  if (!status?.trim()) return stage ? stageFallback : fallback;

  const normalized = normalizedStatus(status);
  const knownKey = KNOWN_STATUS_KEYS[normalized];
  if (knownKey) return t(knownKey);

  if (
    /\b(sql|python|schema|json|tool|agent|token|api|https?|exception|traceback|stack|debug|internal|model|prompt|script|code|request id)\b|工具|智能体|模型|提示词|代码|脚本|异常堆栈|调试|内部错误|请求编号/i.test(
      status
    ) ||
    !isSameLanguage(status, locale)
  ) {
    return stage ? stageFallback : fallback;
  }
  return status.length > 72 ? `${status.slice(0, 72)}…` : status;
}

export function AnalysisProgress({ state, stage, status }: AnalysisProgressProps) {
  const locale = useLocale();
  const t = useTranslations("analysisProgress");
  const current = currentWork(state || stage, t);
  const detail = safeProgressDetail(stage, status, locale, current.detail, t);

  return (
    <section
      aria-label={t("currentProgressAria")}
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
              {t("brand")}
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
