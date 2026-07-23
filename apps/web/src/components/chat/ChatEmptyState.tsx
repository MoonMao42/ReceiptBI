"use client";

import type { ReactNode } from "react";
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Database,
  FileStack,
  Loader2,
  Radar,
  Sparkles,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type {
  AnalysisRunSummary,
  Project,
  ProjectDataSource,
  StandingAnalysis,
  SuggestedQuestion,
} from "@/lib/types/api";
import { cn } from "@/lib/utils";

interface ChatEmptyStateProps {
  project?: Project;
  sources: ProjectDataSource[];
  standingAnalyses: StandingAnalysis[];
  recentRuns: AnalysisRunSummary[];
  suggestedQuestions: SuggestedQuestion[];
  suggestionsLoading: boolean;
  settingsLoaded: boolean;
  selfAnalysisEnabled: boolean;
  canGenerateSuggestions: boolean;
  suggestionsError?: string | null;
  composer: ReactNode;
  activityLoading: boolean;
  checkingStandingId?: string | null;
  standingFeedback?: Record<string, string>;
  onOpenData: () => void;
  onOpenSettings: () => void;
  onGenerateSuggestions: () => void;
  onUsePrompt: (prompt: string) => void;
  onOpenReport: (conversationId: string, analysisRunId: string) => void;
  onCheckStanding: (standing: StandingAnalysis) => void;
}

export function ChatEmptyState({
  project,
  sources,
  standingAnalyses,
  suggestedQuestions,
  suggestionsLoading,
  settingsLoaded,
  selfAnalysisEnabled,
  canGenerateSuggestions,
  suggestionsError,
  composer,
  checkingStandingId,
  standingFeedback = {},
  onOpenData,
  onGenerateSuggestions,
  onUsePrompt,
  onCheckStanding,
}: ChatEmptyStateProps) {
  const t = useTranslations("chatEmpty");

  function standingState(standing: StandingAnalysis) {
    if (standing.state === "needs_attention") {
      return {
        label: t("statePending"),
        tone: "text-warning",
        dot: "bg-warning",
      };
    }
    if (standing.state === "paused") {
      return {
        label: t("statePaused"),
        tone: "text-muted-foreground",
        dot: "bg-muted-foreground/40",
      };
    }
    if (standing.in_flight) {
      return { label: t("stateChecking"), tone: "text-primary", dot: "bg-primary" };
    }
    return { label: t("standingTitle"), tone: "text-success", dot: "bg-success" };
  }

  const readySources = sources.filter((source) =>
    ["ready", "needs_confirmation"].includes(source.status)
  );
  const unresolvedSources = sources.filter((source) => source.status !== "ready");
  return (
    <div
      data-testid="project-work-surface"
      className="min-h-0 flex-1 overflow-y-auto bg-background"
      aria-label={project?.name ? `${project.name}${t("workspaceTitle")}` : t("workspaceTitle")}
    >
      <div className="mx-auto min-h-full w-full max-w-[1080px] px-5 pb-12 pt-9 sm:px-8 sm:pb-16 sm:pt-12 lg:px-12">
        <section className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-3 text-[11px] font-medium text-muted-foreground">
            <div className="flex min-w-0 items-center gap-2">
              <span className="h-2 w-2 shrink-0 bg-primary" />
              <span className="truncate">{project?.name || t("projectFallback")}</span>
              <span aria-hidden="true">·</span>
              <span>{t("workspaceTitle")}</span>
            </div>
            {readySources.length > 0 && (
              <button
                type="button"
                onClick={onOpenData}
                className="inline-flex items-center gap-2 text-muted-foreground transition-colors hover:text-primary"
              >
                {readySources.some((source) => source.kind === "connection") ? (
                  <Database size={13} />
                ) : (
                  <FileStack size={13} />
                )}
                {t("readySources", { count: readySources.length })}
              </button>
            )}
          </div>

          <h1 className="mt-7 max-w-3xl text-[34px] font-semibold leading-[1.08] tracking-[-0.045em] text-foreground sm:text-[44px]">
            {t("title")}
          </h1>

          <div className="mt-7">{composer}</div>
        </section>

        {readySources.length > 0 && (!settingsLoaded || selfAnalysisEnabled) && (
          <section className="mt-10 max-w-[920px] border-t border-border pt-5">
            <div className="flex items-center gap-4">
              <h2 className="text-[11px] font-semibold tracking-[0.12em] text-muted-foreground">
                {t("description")}
              </h2>
            </div>
            {!settingsLoaded ? (
              <div className="mt-3 flex items-center gap-2 py-4 text-xs text-muted-foreground">
                <Loader2 size={13} className="animate-spin" />
                {t("loadingSuggestionSettings")}
              </div>
            ) : suggestionsLoading ? (
              <div className="mt-3 flex items-center gap-2 py-4 text-xs text-muted-foreground">
                <Loader2 size={13} className="animate-spin" />
                {t("loadingSuggestions")}
              </div>
            ) : suggestedQuestions.length > 0 ? (
              <div className="mt-2 divide-y divide-border border-y border-border">
                {suggestedQuestions.map((suggestion, index) => (
                  <button
                    key={`${suggestion.prompt}-${index}`}
                    type="button"
                    onClick={() => onUsePrompt(suggestion.prompt)}
                    className="group grid w-full grid-cols-[32px_minmax(0,1fr)_18px] items-start gap-3 py-3.5 text-left"
                  >
                    <span className="pt-0.5 font-mono text-[11px] text-primary">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span>
                      <span className="block text-sm font-medium leading-6 text-foreground transition-colors group-hover:text-primary">
                        {suggestion.label}
                      </span>
                      <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
                        {suggestion.reason}
                      </span>
                    </span>
                    <ArrowRight
                      size={15}
                      className="mt-1 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
                    />
                  </button>
                ))}
              </div>
            ) : (
              <div className="mt-3 border border-border bg-card px-4 py-4">
                <p className="text-xs leading-5 text-muted-foreground">
                  {suggestionsError || t("suggestionsRequireClick")}
                </p>
                <button
                  type="button"
                  disabled={!canGenerateSuggestions}
                  onClick={onGenerateSuggestions}
                  className="mt-3 inline-flex items-center gap-2 bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Sparkles size={13} />
                  {suggestionsError ? t("retrySuggestions") : t("generateSuggestions")}
                </button>
              </div>
            )}
          </section>
        )}

        {(sources.length > 0 || standingAnalyses.length > 0) && (
          <section
            className={cn(
              "mt-8 grid border-y border-border",
              sources.length > 0 && standingAnalyses.length > 0 && "md:grid-cols-2"
            )}
          >
            {sources.length > 0 && (
              <button
                type="button"
                onClick={onOpenData}
                className={cn(
                  "flex items-start gap-3 px-1 py-5 text-left md:px-5 md:first:pl-1",
                  standingAnalyses.length > 0 && "md:border-r md:border-border"
                )}
              >
                {unresolvedSources.length ? (
                  <CircleAlert size={16} className="mt-0.5 shrink-0 text-warning" />
                ) : (
                  <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-success" />
                )}
                <span>
                  <span className="block text-sm font-medium text-foreground">{t("data")}</span>
                  <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                    {unresolvedSources.length
                      ? t("issuesCount", { count: unresolvedSources.length })
                      : readySources.slice(0, 2).map((source) => source.name).join(" · ")}
                  </span>
                </span>
              </button>
            )}

            {standingAnalyses.length > 0 && (
              <div
                className={cn(
                  "px-1 py-5 md:px-5",
                  sources.length > 0 && "border-t border-border md:border-t-0"
                )}
              >
                <div className="flex items-start gap-3">
                  <Radar size={16} className="mt-0.5 shrink-0 text-primary" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-medium text-foreground">{t("standingTitle")}</span>
                      <span className="text-[11px] text-muted-foreground">
                        {t("itemsCount", { count: standingAnalyses.length })}
                      </span>
                    </div>
                    <div className="mt-2 space-y-2">
                      {standingAnalyses.slice(0, 2).map((standing) => {
                        const state = standingState(standing);
                        const checking = checkingStandingId === standing.id;
                        return (
                          <div key={standing.id} className="flex items-start gap-2 text-xs">
                            <span className={cn("mt-1.5 h-1.5 w-1.5 shrink-0", state.dot)} />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-foreground">
                                {standing.name}
                              </span>
                              <span className={cn("mt-0.5 block text-[11px]", state.tone)}>
                                {standingFeedback[standing.id] || state.label}
                              </span>
                            </span>
                            {standing.state === "active" && (
                              <button
                                type="button"
                                disabled={checking}
                                onClick={() => onCheckStanding(standing)}
                                className="shrink-0 font-semibold text-primary hover:underline disabled:opacity-50"
                              >
                                {checking ? t("checking") : t("checkChanges")}
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
