"use client";

import { CheckCircle2, Loader2, RefreshCw, Square } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import type { SemanticInventoryJob } from "@/lib/types/api";
import {
  semanticInventoryJobHasReviewableItems,
  semanticInventoryJobIsActive,
} from "@/components/semantic/semantic-inventory";

type Translate = (key: string, values?: Record<string, string | number>) => string;

interface SemanticInventoryProgressProps {
  job: SemanticInventoryJob;
  sourceName: string;
  busyAction?: "retry" | "cancel" | null;
  error?: string | null;
  onRetry: () => void;
  onRefresh: () => void;
  onCancel: () => void;
  onReview: () => void;
}

function statusLabel(job: SemanticInventoryJob, t: Translate): string {
  if (job.status === "queued") return t("status.queued");
  if (job.status === "running") return t("status.running");
  if (job.status === "completed") {
    return job.depth === "structure"
      ? t("status.completedStructure")
      : t("status.completed");
  }
  if (job.status === "completed_with_errors") return t("status.completedWithErrors");
  if (job.status === "cancelled") return t("status.cancelled");
  return t("status.failed");
}

export function SemanticInventoryProgress({
  job,
  sourceName,
  busyAction,
  error,
  onRetry,
  onRefresh,
  onCancel,
  onReview,
}: SemanticInventoryProgressProps) {
  const locale = useLocale();
  const t = useTranslations("projectUnderstanding.inventoryJob") as Translate;
  const active = semanticInventoryJobIsActive(job);
  const reviewable = semanticInventoryJobHasReviewableItems(job);
  const failedItems =
    job.failed_item_preview || job.items.filter((item) => item.status === "failed");
  const failedCount = job.progress.failed;
  const retryable = job.retryable === true || failedItems.some((item) => item.retryable);
  const failedTableNames = new Intl.ListFormat(locale, {
    style: "short",
    type: "conjunction",
  }).format(failedItems.slice(0, 3).map((item) => item.table));
  // A stopped table was never processed. Keep it out of both the visible
  // progress and the bar so cancelling cannot turn a partial run into 100%.
  const processed = job.progress.succeeded + job.progress.failed;
  const percent = job.progress.total
    ? Math.min(100, Math.round((processed / job.progress.total) * 100))
    : 0;
  const candidateCount =
    job.candidate_count ??
    job.items.reduce((total, item) => total + item.candidate_count, 0);

  return (
    <section
      role="status"
      aria-label={t("aria", { source: sourceName })}
      className="border border-border bg-secondary/25 px-4 py-3"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2 text-sm font-medium">
            {active ? (
              <Loader2 size={15} className="shrink-0 animate-spin text-primary" />
            ) : job.status === "completed" ? (
              <CheckCircle2 size={15} className="shrink-0 text-primary" />
            ) : null}
            <span className="truncate">{sourceName}</span>
            <span className="shrink-0 text-muted-foreground">
              {statusLabel(job, t)}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("progress", { done: processed, total: job.progress.total })}
            {candidateCount > 0
              ? ` · ${t("resultCount", { count: candidateCount })}`
              : ""}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          {reviewable ? (
            <button
              type="button"
              disabled={Boolean(busyAction)}
              onClick={onReview}
              className="h-8 border border-primary/40 px-3 text-xs font-medium text-primary hover:border-primary disabled:opacity-40"
            >
              {t("review")}
            </button>
          ) : null}
          {retryable && !active ? (
            <button
              type="button"
              disabled={Boolean(busyAction)}
              onClick={onRetry}
              className="inline-flex h-8 items-center gap-1.5 border border-border px-3 text-xs font-medium hover:border-primary/50 disabled:opacity-40"
            >
              {busyAction === "retry" ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <RefreshCw size={13} />
              )}
              {t("retry")}
            </button>
          ) : null}
          {active ? (
            <button
              type="button"
              disabled={Boolean(busyAction)}
              onClick={onCancel}
              className="inline-flex h-8 items-center gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground disabled:opacity-40"
            >
              {busyAction === "cancel" ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Square size={12} />
              )}
              {t("cancel")}
            </button>
          ) : null}
        </div>
      </div>

      {job.progress.total > 0 ? (
        <div
          className="mt-3 h-1 bg-border"
          role="progressbar"
          aria-label={t("progress", {
            done: processed,
            total: job.progress.total,
          })}
          aria-valuemin={0}
          aria-valuemax={job.progress.total}
          aria-valuenow={processed}
        >
          <div
            className="h-full bg-primary transition-[width]"
            style={{ width: `${percent}%` }}
          />
        </div>
      ) : null}

      {failedCount > 0 ? (
        <p className="mt-2 line-clamp-2 text-xs text-warning">
          {failedItems.length
            ? t(failedCount > failedItems.length ? "failedTablesMore" : "failedTables", {
                count: failedCount,
                tables: failedTableNames,
              })
            : t("failedCount", { count: failedCount })}
        </p>
      ) : null}

      {error ? (
        <div className="mt-2 flex items-center justify-between gap-3 text-xs text-destructive">
          <span>{error}</span>
          <button type="button" onClick={onRefresh} className="shrink-0 font-medium hover:underline">
            {t("retryStatus")}
          </button>
        </div>
      ) : null}
    </section>
  );
}
