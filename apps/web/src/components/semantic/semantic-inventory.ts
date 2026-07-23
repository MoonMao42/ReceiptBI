import type {
  SemanticInventoryJob,
  SemanticInventoryJobItem,
  SemanticInventoryJobItemPage,
  SemanticInventoryJobItemPhase,
  SemanticInventoryJobItemStatus,
  SemanticInventoryJobStatus,
} from "@/lib/types/api";

const JOB_STATUSES = new Set<SemanticInventoryJobStatus>([
  "queued",
  "running",
  "completed",
  "completed_with_errors",
  "cancelled",
  "failed",
]);

const ITEM_STATUSES = new Set<SemanticInventoryJobItemStatus>([
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
]);

const ITEM_PHASES = new Set<SemanticInventoryJobItemPhase>([
  "structure",
  "sample",
  "recommend",
  "complete",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function optionalString(value: unknown): string | null | undefined {
  return value === null ? null : typeof value === "string" ? value : undefined;
}

function nonNegativeNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : 0;
}

export function normalizeSemanticInventoryJobItem(
  value: unknown
): SemanticInventoryJobItem | null {
  if (!isRecord(value)) return null;
  const status = stringValue(value.status) as SemanticInventoryJobItemStatus;
  const phase = stringValue(value.phase) as SemanticInventoryJobItemPhase;
  const id = stringValue(value.id);
  const table = stringValue(value.table);
  if (!id || !table || !ITEM_STATUSES.has(status) || !ITEM_PHASES.has(phase)) return null;
  const retryable = typeof value.retryable === "boolean" ? value.retryable : false;
  const code = optionalString(value.code);
  const message = optionalString(value.message);
  const recommendationBatchId = optionalString(value.recommendation_batch_id);
  const startedAt = optionalString(value.started_at);
  const completedAt = optionalString(value.completed_at);
  const ordinal =
    typeof value.ordinal === "number" &&
    Number.isFinite(value.ordinal) &&
    value.ordinal >= 0
      ? value.ordinal
      : undefined;
  return {
    id,
    ...(ordinal !== undefined ? { ordinal } : {}),
    table,
    status,
    phase,
    attempt_count: nonNegativeNumber(value.attempt_count),
    candidate_count: nonNegativeNumber(value.candidate_count),
    retryable,
    ...(code !== undefined ? { code } : {}),
    ...(message !== undefined ? { message } : {}),
    ...(recommendationBatchId !== undefined
      ? { recommendation_batch_id: recommendationBatchId }
      : {}),
    ...(startedAt !== undefined ? { started_at: startedAt } : {}),
    ...(completedAt !== undefined ? { completed_at: completedAt } : {}),
  };
}

export function normalizeSemanticInventoryJob(value: unknown): SemanticInventoryJob | null {
  if (!isRecord(value) || !isRecord(value.progress) || !Array.isArray(value.items)) return null;
  const status = stringValue(value.status) as SemanticInventoryJobStatus;
  const depth = stringValue(value.depth);
  const locale = stringValue(value.locale);
  const id = stringValue(value.id);
  const projectId = stringValue(value.project_id);
  const sourceId = stringValue(value.source_id);
  const items = value.items.map(normalizeSemanticInventoryJobItem);
  if (
    !id ||
    !projectId ||
    !sourceId ||
    !JOB_STATUSES.has(status) ||
    !["structure", "sampled"].includes(depth) ||
    !["zh", "en"].includes(locale) ||
    items.some((item) => item === null)
  ) {
    return null;
  }
  const modelId = optionalString(value.model_id);
  const retryable =
    typeof value.retryable === "boolean" ? value.retryable : undefined;
  const startedAt = optionalString(value.started_at);
  const completedAt = optionalString(value.completed_at);
  const nextReviewItem =
    value.next_review_item === null
      ? null
      : value.next_review_item === undefined
        ? undefined
        : normalizeSemanticInventoryJobItem(value.next_review_item);
  if (value.next_review_item !== undefined && nextReviewItem === null && value.next_review_item !== null) {
    return null;
  }
  const failedItemPreview = Array.isArray(value.failed_item_preview)
    ? value.failed_item_preview.map(normalizeSemanticInventoryJobItem)
    : undefined;
  if (failedItemPreview?.some((item) => item === null)) return null;
  const candidateCount =
    typeof value.candidate_count === "number" &&
    Number.isFinite(value.candidate_count) &&
    value.candidate_count >= 0
      ? value.candidate_count
      : undefined;
  const reviewableCount =
    typeof value.reviewable_count === "number" &&
    Number.isFinite(value.reviewable_count) &&
    value.reviewable_count >= 0
      ? value.reviewable_count
      : undefined;
  return {
    id,
    project_id: projectId,
    source_id: sourceId,
    status,
    depth: depth as SemanticInventoryJob["depth"],
    locale: locale as SemanticInventoryJob["locale"],
    ...(modelId !== undefined ? { model_id: modelId } : {}),
    tables: Array.isArray(value.tables)
      ? value.tables.filter((table): table is string => typeof table === "string")
      : [],
    progress: {
      total: nonNegativeNumber(value.progress.total),
      queued: nonNegativeNumber(value.progress.queued),
      running: nonNegativeNumber(value.progress.running),
      succeeded: nonNegativeNumber(value.progress.succeeded),
      failed: nonNegativeNumber(value.progress.failed),
      cancelled: nonNegativeNumber(value.progress.cancelled),
    },
    items: items as SemanticInventoryJobItem[],
    ...(retryable !== undefined ? { retryable } : {}),
    ...(candidateCount !== undefined ? { candidate_count: candidateCount } : {}),
    ...(reviewableCount !== undefined ? { reviewable_count: reviewableCount } : {}),
    ...(nextReviewItem !== undefined ? { next_review_item: nextReviewItem } : {}),
    ...(failedItemPreview !== undefined
      ? { failed_item_preview: failedItemPreview as SemanticInventoryJobItem[] }
      : {}),
    created_at: stringValue(value.created_at),
    ...(startedAt !== undefined ? { started_at: startedAt } : {}),
    ...(completedAt !== undefined ? { completed_at: completedAt } : {}),
  };
}

export function normalizeSemanticInventoryJobItemPage(
  value: unknown
): SemanticInventoryJobItemPage | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null;
  const jobId = stringValue(value.job_id);
  const items = value.items.map(normalizeSemanticInventoryJobItem);
  const nextAfterOrdinal =
    value.next_after_ordinal === null
      ? null
      : typeof value.next_after_ordinal === "number" &&
          Number.isFinite(value.next_after_ordinal) &&
          value.next_after_ordinal >= 0
        ? value.next_after_ordinal
        : undefined;
  if (
    !jobId ||
    items.some((item) => item === null) ||
    typeof value.has_more !== "boolean" ||
    nextAfterOrdinal === undefined
  ) {
    return null;
  }
  return {
    job_id: jobId,
    items: items as SemanticInventoryJobItem[],
    next_after_ordinal: nextAfterOrdinal,
    has_more: value.has_more,
  };
}

export function semanticInventoryJobIsActive(job: SemanticInventoryJob): boolean {
  return job.status === "queued" || job.status === "running";
}

export function semanticInventoryJobHasReviewableItems(job: SemanticInventoryJob): boolean {
  return (
    (job.reviewable_count || 0) > 0 ||
    Boolean(job.next_review_item?.recommendation_batch_id) ||
    job.items.some(
    (item) => item.status === "succeeded" && Boolean(item.recommendation_batch_id)
    )
  );
}

export function semanticInventoryReviewItem(
  job: SemanticInventoryJob,
  table?: string | null
): SemanticInventoryJobItem | null {
  const normalizedTable = table?.trim().toLocaleLowerCase("en");
  const reviewable = [
    ...(job.next_review_item ? [job.next_review_item] : []),
    ...job.items,
  ].filter(
    (item) => item.status === "succeeded" && Boolean(item.recommendation_batch_id)
  );
  if (!normalizedTable) return reviewable[0] || null;

  const exact = reviewable.find((item) =>
    semanticInventoryTablesMatch(item.table, normalizedTable)
  );
  if (exact) return exact;

  // A database source owns one namespace. Scope nodes intentionally keep the
  // source-local relation name while inventory rows keep schema.table for
  // selection and display. Bridge those contracts only when the basename is
  // unique inside this exact job; otherwise fail closed instead of guessing.
  if (normalizedTable.includes(".")) return null;
  const basenameMatches = reviewable.filter(
    (item) => item.table.trim().toLocaleLowerCase("en").split(".").at(-1) === normalizedTable
  );
  return basenameMatches.length === 1 ? basenameMatches[0] : null;
}

export function semanticInventoryTablesMatch(left: string, right: string): boolean {
  const normalizedLeft = left.trim().toLocaleLowerCase("en");
  const normalizedRight = right.trim().toLocaleLowerCase("en");
  return Boolean(normalizedLeft && normalizedRight && normalizedLeft === normalizedRight);
}

export function requestStatus(error: unknown): number | null {
  if (!isRecord(error)) return null;
  const response = isRecord(error.response) ? error.response : null;
  return typeof response?.status === "number" ? response.status : null;
}
