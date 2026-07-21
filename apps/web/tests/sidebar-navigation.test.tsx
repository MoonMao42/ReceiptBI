import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/components/chat/Sidebar";
import type { AnalysisRunSummary } from "@/lib/types/api";

const mocks = vi.hoisted(() => ({
  renameProject: vi.fn().mockResolvedValue(undefined),
  clearConversation: vi.fn(),
  selectProject: vi.fn(),
  createProject: vi.fn(),
}));

vi.mock("@/lib/stores/chat", () => ({
  useChatStore: () => ({ clearConversation: mocks.clearConversation }),
}));

vi.mock("@/lib/stores/project", () => ({
  useProjectStore: () => ({
    projects: [
      { id: "project-1", name: "财务分析" },
      { id: "project-2", name: "历史项目" },
    ],
    currentProjectId: "project-1",
    selectProject: mocks.selectProject,
    createProject: mocks.createProject,
    renameProject: mocks.renameProject,
  }),
}));

function report(
  id: string,
  title: string,
  conversationId: string,
  state: AnalysisRunSummary["state"] = "completed"
): AnalysisRunSummary {
  return {
    id,
    project_id: "project-1",
    conversation_id: conversationId,
    query: title,
    state,
    stage: state,
    report: { title },
    checkpoint: {},
    created_at: "2026-07-01T00:00:00Z",
    updated_at: id === "run-1" ? "2026-07-01T00:00:00Z" : "2026-07-02T00:00:00Z",
  };
}

describe("Sidebar", () => {
  beforeEach(() => {
    mocks.clearConversation.mockReset();
    mocks.selectProject.mockReset();
    mocks.createProject.mockReset();
  });

  it("offers an explicit project rename action", async () => {
    mocks.renameProject.mockClear();
    render(<Sidebar isOpen onToggle={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "财务分析" }));
    fireEvent.click(screen.getByRole("button", { name: "重命名当前项目" }));
    fireEvent.change(screen.getByRole("textbox", { name: "侧栏项目名称" }), {
      target: { value: "  七月经营复盘  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存侧栏项目名称" }));

    await waitFor(() =>
      expect(mocks.renameProject).toHaveBeenCalledWith("project-1", "七月经营复盘")
    );
  });

  it("uses the middle rail for analysis runs without restoring conversation controls", () => {
    const onOpenReport = vi.fn();
    render(
      <Sidebar
        isOpen
        onToggle={vi.fn()}
        reportRuns={[
          report("run-1", "收入变化", "conversation-1"),
          report("run-2", "退款异常", "conversation-2", "needs_attention"),
        ]}
        currentConversationId="conversation-1"
        currentAnalysisRunId="run-1"
        onOpenReport={onOpenReport}
      />
    );

    expect(screen.getByText("财务分析")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始新调查" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "报表" })).toHaveAttribute(
      "href",
      "/projects/project-1/reports"
    );
    expect(screen.getByRole("link", { name: "项目理解" })).toHaveAttribute(
      "href",
      "/projects/project-1/understanding"
    );
    expect(screen.getByRole("link", { name: "设置" })).toHaveAttribute(
      "href",
      "/settings"
    );
    expect(screen.getByRole("region", { name: "项目调查" })).toBeInTheDocument();

    const current = screen.getByRole("button", { name: /当前调查：收入变化/ });
    expect(current).toHaveAttribute("aria-current", "page");
    fireEvent.click(current);
    expect(onOpenReport).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /打开调查：退款异常/ }));
    expect(onOpenReport).toHaveBeenCalledWith("conversation-2", "run-2");

    expect(screen.queryByText("调查记录")).not.toBeInTheDocument();
    expect(screen.queryByText("每次调查都会留在这里，方便下次继续。")).not.toBeInTheDocument();
  });

  it("keeps saved project conversations on navigation and forgets only when starting over", () => {
    render(<Sidebar isOpen onToggle={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "财务分析" }));
    fireEvent.click(screen.getByRole("button", { name: "历史项目" }));
    expect(mocks.clearConversation).toHaveBeenLastCalledWith({ forget: false });
    expect(mocks.selectProject).toHaveBeenCalledWith("project-2");

    fireEvent.click(screen.getByRole("button", { name: "开始新调查" }));
    expect(mocks.clearConversation).toHaveBeenLastCalledWith({
      forget: true,
      projectId: "project-1",
    });
  });

  it("creates a project without deleting or inheriting the current project pointer", () => {
    render(<Sidebar isOpen onToggle={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "财务分析" }));
    fireEvent.click(screen.getByRole("button", { name: "新建项目" }));

    expect(mocks.clearConversation).toHaveBeenCalledWith({ forget: false });
    expect(mocks.createProject).toHaveBeenCalledTimes(1);
  });

  it("keeps report choices focusable but prevents switching during a running investigation", () => {
    const onOpenReport = vi.fn();
    render(
      <Sidebar
        isOpen
        onToggle={vi.fn()}
        reportRuns={[
          report("run-1", "收入变化", "conversation-1", "investigating"),
          report("run-2", "退款异常", "conversation-2"),
        ]}
        currentAnalysisRunId="run-1"
        reportSwitchDisabled
        onOpenReport={onOpenReport}
      />
    );

    const historyReport = screen.getByRole("button", { name: /打开调查：退款异常/ });
    expect(historyReport).toHaveAttribute("aria-disabled", "true");
    historyReport.focus();
    expect(historyReport).toHaveFocus();
    fireEvent.click(historyReport);
    expect(onOpenReport).not.toHaveBeenCalled();
  });
});
