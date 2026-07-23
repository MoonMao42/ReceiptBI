"use client";

import { Loader2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import type { AnalysisRunSummary } from "@/lib/types/api";
import { cn } from "@/lib/utils";

const MAX_VISIBLE_REPORTS = 12;

export interface ProjectReportIndexProps {
  runs: AnalysisRunSummary[];
  onOpenReport: (conversationId: string, analysisRunId: string) => void;
  currentConversationId?: string | null;
  currentAnalysisRunId?: string | null;
  isLoading?: boolean;
  disabled?: boolean;
}

function runTimestamp(run: AnalysisRunSummary): number {
  const value = Date.parse(run.updated_at);
  return Number.isNaN(value) ? 0 : value;
}

function reportTitle(run: AnalysisRunSummary, t: (key: string) => string): string {
  return run.report.title?.trim() || run.query.trim() || t("unnamedRun");
}

function compactDate(value: string, locale: string, t: (key: string) => string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return t("recent");
  return new Intl.DateTimeFormat(locale, {
    month: "numeric",
    day: "numeric",
  }).format(date);
}

function runStateLabel(
  state: AnalysisRunSummary["state"],
  t: (key: string) => string
): string {
  if (state === "waiting_confirmation") return t("statePending");
  if (state === "investigating") return t("stateInvestigating");
  if (state === "completed") return t("stateCompleted");
  if (state === "needs_attention") return t("stateNeedsAttention");
  return t("statePreparing");
}

function stateDotClass(state: AnalysisRunSummary["state"]): string {
  if (state === "completed") return "bg-primary";
  if (state === "needs_attention") return "bg-destructive";
  if (state === "waiting_confirmation") return "bg-warning";
  return "bg-primary/40";
}

function selectVisibleRuns(
  runs: AnalysisRunSummary[],
  currentConversationId?: string | null,
  currentAnalysisRunId?: string | null
): { runs: AnalysisRunSummary[]; currentRunId?: string } {
  const orderedRuns = runs
    .filter((run) => Boolean(run.conversation_id))
    .sort((left, right) => runTimestamp(right) - runTimestamp(left));
  const currentRun =
    (currentAnalysisRunId
      ? orderedRuns.find((run) => run.id === currentAnalysisRunId)
      : undefined) ||
    (currentConversationId
      ? orderedRuns.find((run) => run.conversation_id === currentConversationId)
      : undefined);

  if (!currentRun) {
    return {
      runs: orderedRuns.slice(0, MAX_VISIBLE_REPORTS),
      currentRunId: currentAnalysisRunId || undefined,
    };
  }

  return {
    runs: [currentRun, ...orderedRuns.filter((run) => run.id !== currentRun.id)].slice(
      0,
      MAX_VISIBLE_REPORTS
    ),
    currentRunId: currentRun.id,
  };
}

export function ProjectReportIndex({
  runs,
  onOpenReport,
  currentConversationId,
  currentAnalysisRunId,
  isLoading = false,
  disabled = false,
}: ProjectReportIndexProps) {
  const locale = useLocale();
  const t = useTranslations("projectReports");
  const { runs: visibleRuns, currentRunId } = selectVisibleRuns(
    runs,
    currentConversationId,
    currentAnalysisRunId
  );

  return (
    <section
      data-testid="project-report-index"
      aria-label={t("investigationsAria")}
      className="flex h-full min-h-0 flex-col"
    >
      <div className="flex shrink-0 items-center justify-between gap-3 px-[18px] pb-2 pt-4">
        <h2 className="text-[9px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          {t("sectionTitle")}
        </h2>
        <span className="inline-flex min-w-4 items-center justify-end text-[10px] tabular-nums text-muted-foreground">
          {isLoading ? (
            <Loader2 size={11} className="animate-spin" aria-label={t("loadingAria")} />
          ) : (
            visibleRuns.length
          )}
        </span>
      </div>

      {visibleRuns.length ? (
        <ol className="min-h-0 flex-1 overflow-y-auto pb-3 [scrollbar-width:thin]">
          {visibleRuns.map((run) => {
            const title = reportTitle(run, t);
            const state = runStateLabel(run.state, t);
            const date = compactDate(run.updated_at, locale, t);
            const isCurrent = run.id === currentRunId;
            const openingDisabled = disabled || isCurrent || !run.conversation_id;

            return (
              <li key={run.id}>
                <button
                  type="button"
                  data-analysis-run-id={run.id}
                  data-current-report={isCurrent ? "true" : undefined}
                  aria-current={isCurrent ? "page" : undefined}
                  aria-disabled={openingDisabled}
                  aria-label={
                    isCurrent
                      ? t("currentRunAria", { title, state, date })
                      : t("openRunAria", { title, state, date })
                  }
                  title={disabled && !isCurrent ? t("waitingTooltip") : undefined}
                  onClick={() => {
                    if (!openingDisabled && run.conversation_id) {
                      onOpenReport(run.conversation_id, run.id);
                    }
                  }}
                  className={cn(
                    "group relative w-full border-l-2 px-4 py-2.5 text-left transition-colors focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary",
                    isCurrent
                      ? "border-primary bg-primary/[0.055]"
                      : "border-transparent hover:bg-primary/[0.025]",
                    disabled && !isCurrent && "cursor-not-allowed opacity-50"
                  )}
                >
                  <span
                    className={cn(
                      "block line-clamp-2 text-[12px] font-medium leading-[1.45] text-foreground",
                      !isCurrent && "group-hover:text-primary"
                    )}
                  >
                    {title}
                  </span>
                  <span className="mt-1.5 flex items-center gap-1.5 text-[10px] text-muted-foreground">
                    <span
                      aria-hidden="true"
                      className={cn("h-1.5 w-1.5 shrink-0 rounded-full", stateDotClass(run.state))}
                    />
                    <span>{isCurrent ? t("currentBadge") : state}</span>
                    <span aria-hidden="true">·</span>
                    <span>{date}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      ) : (
        <div className="px-[18px] py-5 text-[11px] text-muted-foreground">
          {isLoading ? "" : t("noRuns")}
        </div>
      )}
    </section>
  );
}
