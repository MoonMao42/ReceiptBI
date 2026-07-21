import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProjectReportIndex } from "@/components/chat/ProjectReportIndex";
import type { AnalysisRunSummary } from "@/lib/types/api";

function report(
  id: string,
  title: string,
  conversationId: string | null,
  updatedAt: string
): AnalysisRunSummary {
  return {
    id,
    project_id: "project-1",
    conversation_id: conversationId,
    query: title,
    state: "completed",
    stage: "completed",
    report: { title },
    checkpoint: {},
    created_at: updatedAt,
    updated_at: updatedAt,
  };
}

describe("ProjectReportIndex", () => {
  it("pins the current run and orders the remaining reports by latest update", () => {
    render(
      <ProjectReportIndex
        runs={[
          report("run-current", "当前季度", "conversation-current", "2026-06-01T00:00:00Z"),
          report("run-old", "五月经营", "conversation-old", "2026-07-01T00:00:00Z"),
          report("run-new", "六月经营", "conversation-new", "2026-07-08T00:00:00Z"),
          report("run-orphan", "未归档运行", null, "2026-07-09T00:00:00Z"),
        ]}
        currentAnalysisRunId="run-current"
        onOpenReport={vi.fn()}
      />
    );

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("当前季度");
    expect(items[1]).toHaveTextContent("六月经营");
    expect(items[2]).toHaveTextContent("五月经营");
    expect(screen.queryByText("未归档运行")).not.toBeInTheDocument();
  });

  it("opens a report with its conversation and analysis run identities", () => {
    const onOpenReport = vi.fn();
    render(
      <ProjectReportIndex
        runs={[report("run-1", "门店表现", "conversation-1", "2026-07-08T00:00:00Z")]}
        onOpenReport={onOpenReport}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /打开调查：门店表现/ }));
    expect(onOpenReport).toHaveBeenCalledWith("conversation-1", "run-1");
  });
});
