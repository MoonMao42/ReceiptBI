import { describe, expect, it } from "vitest";
import {
  normalizeSemanticInventoryJob,
  normalizeSemanticInventoryJobItemPage,
  semanticInventoryReviewItem,
  semanticInventoryTablesMatch,
} from "@/components/semantic/semantic-inventory";

function completedJob(tables: string[]) {
  return normalizeSemanticInventoryJob({
    id: "job-review",
    project_id: "project-1",
    source_id: "source-1",
    status: "completed",
    depth: "structure",
    locale: "zh",
    tables,
    progress: {
      total: tables.length,
      queued: 0,
      running: 0,
      succeeded: tables.length,
      failed: 0,
      cancelled: 0,
    },
    items: tables.map((table, index) => ({
      id: `item-${index}`,
      table,
      status: "succeeded",
      phase: "complete",
      attempt_count: 1,
      retryable: false,
      recommendation_batch_id: `batch-${index}`,
      candidate_count: 1,
    })),
    created_at: "2026-07-22T00:00:00Z",
  });
}

describe("semantic inventory contract", () => {
  it("keeps same-named tables in different schemas distinct", () => {
    expect(semanticInventoryTablesMatch("sales.orders", "sales.orders")).toBe(true);
    expect(semanticInventoryTablesMatch("sales.orders", "archive.orders")).toBe(false);
    expect(semanticInventoryTablesMatch("sales.orders", "orders")).toBe(false);
  });

  it("uses server progress totals instead of assuming the returned item count is the total", () => {
    const job = normalizeSemanticInventoryJob({
      id: "job-1",
      project_id: "project-1",
      source_id: "source-1",
      status: "running",
      depth: "structure",
      locale: "zh",
      tables: [],
      progress: {
        total: 1200,
        queued: 1199,
        running: 1,
        succeeded: 0,
        failed: 0,
        cancelled: 0,
      },
      items: [
        {
          id: "item-1",
          table: "sales.orders",
          status: "running",
          phase: "structure",
          attempt_count: 1,
          retryable: true,
          candidate_count: 0,
        },
      ],
      created_at: "2026-07-22T00:00:00Z",
    });

    expect(job?.progress.total).toBe(1200);
    expect(job?.items).toHaveLength(1);
  });

  it("keeps a large completed job bounded while exposing its first reviewable table", () => {
    const reviewItem = {
      id: "item-900",
      ordinal: 900,
      table: "public.orders_2024",
      status: "succeeded",
      phase: "complete",
      attempt_count: 1,
      retryable: false,
      recommendation_batch_id: "batch-900",
      candidate_count: 12,
    };
    const job = normalizeSemanticInventoryJob({
      id: "job-large",
      project_id: "project-1",
      source_id: "source-1",
      status: "completed_with_errors",
      depth: "structure",
      locale: "zh",
      candidate_count: 12000,
      reviewable_count: 999,
      next_review_item: reviewItem,
      failed_item_preview: [
        {
          ...reviewItem,
          id: "item-3",
          ordinal: 3,
          table: "private.ledger",
          status: "failed",
          phase: "structure",
          recommendation_batch_id: null,
          candidate_count: 0,
          retryable: true,
        },
      ],
      tables: [],
      progress: {
        total: 50000,
        queued: 0,
        running: 0,
        succeeded: 49999,
        failed: 1,
        cancelled: 0,
      },
      items: [],
      retryable: true,
      created_at: "2026-07-22T00:00:00Z",
    });

    expect(job?.items).toEqual([]);
    expect(job?.candidate_count).toBe(12000);
    expect(semanticInventoryReviewItem(job!)?.table).toBe("public.orders_2024");
  });

  it("normalizes only bounded cursor pages of job items", () => {
    const page = normalizeSemanticInventoryJobItemPage({
      job_id: "job-large",
      items: [
        {
          id: "item-20",
          ordinal: 20,
          table: "public.orders",
          status: "succeeded",
          phase: "complete",
          attempt_count: 1,
          retryable: false,
          recommendation_batch_id: "batch-20",
          candidate_count: 5,
        },
      ],
      next_after_ordinal: 20,
      has_more: true,
    });

    expect(page?.items[0]?.ordinal).toBe(20);
    expect(page?.next_after_ordinal).toBe(20);
    expect(page?.has_more).toBe(true);
  });

  it("maps a qualified inventory row to a unique source-local table scope", () => {
    const job = completedJob(["public.orders", "public.customers"]);
    expect(job).not.toBeNull();
    expect(semanticInventoryReviewItem(job!, "orders")?.table).toBe("public.orders");
  });

  it("refuses a basename bridge when a job contains cross-schema duplicates", () => {
    const job = completedJob(["sales.orders", "archive.orders"]);
    expect(job).not.toBeNull();
    expect(semanticInventoryReviewItem(job!, "orders")).toBeNull();
    expect(semanticInventoryReviewItem(job!, "sales.orders")?.table).toBe(
      "sales.orders"
    );
  });
});
