import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import { SemanticInventoryProgress } from "@/components/semantic/SemanticInventoryProgress";
import type { SemanticInventoryJob } from "@/lib/types/api";
import zhMessages from "@/messages/zh.json";

function stoppedJob(): SemanticInventoryJob {
  return {
    id: "job-stopped",
    project_id: "project-1",
    source_id: "source-1",
    status: "cancelled",
    depth: "structure",
    locale: "zh",
    tables: [],
    progress: {
      total: 87,
      queued: 0,
      running: 0,
      succeeded: 23,
      failed: 0,
      cancelled: 64,
    },
    candidate_count: 31,
    reviewable_count: 23,
    items: [],
    created_at: "2026-07-23T00:00:00Z",
    completed_at: "2026-07-23T00:01:00Z",
  };
}

describe("SemanticInventoryProgress", () => {
  it("does not count stopped tables as completed progress", () => {
    render(
      <NextIntlClientProvider locale="zh" messages={zhMessages}>
        <SemanticInventoryProgress
          job={stoppedJob()}
          sourceName="经营数据库"
          onRetry={vi.fn()}
          onRefresh={vi.fn()}
          onCancel={vi.fn()}
          onReview={vi.fn()}
        />
      </NextIntlClientProvider>
    );

    expect(screen.getByText("进度 23 / 87 张表 · 31 条待核对内容")).toBeTruthy();
    expect(screen.queryByText(/87 \/ 87/)).toBeNull();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "23");
    expect(screen.getByText("已停止")).toBeTruthy();
  });
});
