import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReportIndexPage } from "@/components/reports/ReportIndexPage";
import { useChatStore } from "@/lib/stores/chat";
import enMessages from "@/messages/en.json";
import zhMessages from "@/messages/zh.json";

const mocks = vi.hoisted(() => ({
  listReports: vi.fn(),
  createReport: vi.fn(),
  deleteReport: vi.fn(),
}));

vi.mock("@/lib/reports", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/reports")>();
  return { ...actual, ...mocks };
});

describe("ReportIndexPage", () => {
  beforeEach(() => {
    mocks.listReports.mockReset();
    mocks.createReport.mockReset();
    mocks.deleteReport.mockReset();
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.getItem).mockReturnValue(null);
    useChatStore.setState({
      currentConversationId: null,
      currentConversationMeta: null,
      lastProjectId: null,
    });
  });

  it("carries the source conversation through a report and back to the project", async () => {
    mocks.listReports.mockResolvedValue([
      {
        id: "report-1",
        project_id: "project-1",
        title: "经营概览",
        description: "七月复盘",
        status: "draft",
        version: 1,
        page_count: 1,
        block_count: 2,
        created_at: "2026-07-19T00:00:00Z",
        updated_at: "2026-07-19T01:00:00Z",
      },
    ]);
    useChatStore.setState({
      currentConversationId: "conversation-1",
      lastProjectId: "project-1",
    });

    render(
      <NextIntlClientProvider locale="zh" messages={zhMessages}>
        <ReportIndexPage projectId="project-1" />
      </NextIntlClientProvider>
    );

    expect(await screen.findByRole("link", { name: /经营概览/ })).toHaveAttribute(
      "href",
      "/projects/project-1/reports/report-1?fromConversation=conversation-1"
    );
    expect(screen.getByRole("link", { name: "返回项目" })).toHaveAttribute(
      "href",
      "/?conversation=conversation-1"
    );
  });

  it("shows a single recovery state instead of presenting an API error as an empty report list", async () => {
    mocks.listReports.mockRejectedValue(new Error("报告没有加载完成，请重试。"));

    render(
      <NextIntlClientProvider locale="zh" messages={zhMessages}>
        <ReportIndexPage projectId="project-1" />
      </NextIntlClientProvider>
    );

    expect(await screen.findByRole("heading", { name: "报告暂时没有打开" })).toBeInTheDocument();
    expect(screen.getByText("报告没有加载完成，请重试。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
    expect(screen.queryByText("从一张空白报告开始")).not.toBeInTheDocument();
  });

  it("uses English copy for the report list and newly persisted defaults", async () => {
    mocks.listReports.mockResolvedValue([]);
    mocks.createReport.mockResolvedValue({ id: "report-new" });

    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <ReportIndexPage projectId="project-1" />
      </NextIntlClientProvider>
    );

    expect(await screen.findByRole("heading", { name: "Start with a blank report" })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "New report" })[0]);

    await waitFor(() => expect(mocks.createReport).toHaveBeenCalledTimes(1));
    expect(mocks.createReport.mock.calls[0][1]).toMatchObject({
      title: "New report",
      pages: [expect.objectContaining({ title: "Overview" })],
    });
  });
});
