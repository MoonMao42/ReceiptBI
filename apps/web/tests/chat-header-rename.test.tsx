import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatHeader } from "@/components/chat/ChatHeader";
import type { Project } from "@/lib/types/api";
import enMessages from "@/messages/en.json";
import zhMessages from "@/messages/zh.json";

const originalLanguage = document.documentElement.lang;

const project = {
  id: "project-1",
  name: "新的分析项目",
  description: null,
  status: "active",
  extra_data: {},
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
} satisfies Project;

function renderHeader(
  onRenameProject = vi.fn().mockResolvedValue(undefined),
  locale: "en" | "zh" = "zh"
) {
  document.documentElement.lang = locale;
  render(
    <NextIntlClientProvider
      locale={locale}
      messages={locale === "en" ? enMessages : zhMessages}
    >
      <ChatHeader
        onToggleSidebar={vi.fn()}
        onToggleData={vi.fn()}
        project={project}
        readySources={0}
        totalSources={0}
        onRenameProject={onRenameProject}
      />
    </NextIntlClientProvider>
  );
  return onRenameProject;
}

describe("project title rename", () => {
  afterEach(() => {
    document.documentElement.lang = originalLanguage;
  });

  it("opens project understanding when business definitions are waiting for review", () => {
    const onToggleData = vi.fn();
    const onOpenUnderstanding = vi.fn();
    render(
      <NextIntlClientProvider locale="zh" messages={zhMessages}>
        <ChatHeader
          onToggleSidebar={vi.fn()}
          onToggleData={onToggleData}
          onOpenUnderstanding={onOpenUnderstanding}
          project={project}
          readySources={2}
          totalSources={2}
          pendingUnderstandingCount={3}
        />
      </NextIntlClientProvider>
    );

    const button = screen.getByRole("button", { name: "数据，待核对 3" });
    expect(button).toHaveTextContent("待核对 3");
    expect(screen.getByText("2 项数据可用")).toBeInTheDocument();
    expect(screen.queryByText("数据与理解")).not.toBeInTheDocument();
    fireEvent.click(button);

    expect(onOpenUnderstanding).toHaveBeenCalledOnce();
    expect(onToggleData).not.toHaveBeenCalled();
  });

  it("does not invent a project title or zero-source status", () => {
    const { container } = render(
      <NextIntlClientProvider locale="zh" messages={zhMessages}>
        <ChatHeader
          onToggleSidebar={vi.fn()}
          onToggleData={vi.fn()}
          readySources={0}
          totalSources={0}
        />
      </NextIntlClientProvider>
    );

    expect(screen.queryByText("准备分析项目")).not.toBeInTheDocument();
    expect(screen.queryByText("可以先提问，需要时再补数据")).not.toBeInTheDocument();
    expect(container.querySelector(".bg-amber-500")).toBeNull();
    expect(screen.getByRole("button", { name: "数据" })).toHaveTextContent("数据");
  });

  it("saves the trimmed name with Enter", async () => {
    const onRenameProject = renderHeader();
    fireEvent.click(screen.getByRole("button", { name: "重命名项目：新的分析项目" }));

    const input = screen.getByRole("textbox", { name: "项目名称" });
    fireEvent.change(input, { target: { value: "  七月门店复盘  " } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(onRenameProject).toHaveBeenCalledWith("七月门店复盘"));
    expect(screen.queryByRole("textbox", { name: "项目名称" })).not.toBeInTheDocument();
  });

  it("cancels with Escape", () => {
    const onRenameProject = renderHeader();
    fireEvent.click(screen.getByRole("button", { name: "重命名项目：新的分析项目" }));

    const input = screen.getByRole("textbox", { name: "项目名称" });
    fireEvent.change(input, { target: { value: "不保存" } });
    fireEvent.keyDown(input, { key: "Escape" });

    expect(onRenameProject).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "重命名项目：新的分析项目" })).toBeInTheDocument();
  });

  it("keeps the editor open and shows a local error when saving fails", async () => {
    const onRenameProject = vi.fn().mockRejectedValue(new Error("offline"));
    renderHeader(onRenameProject);
    fireEvent.click(screen.getByRole("button", { name: "重命名项目：新的分析项目" }));

    const input = screen.getByRole("textbox", { name: "项目名称" });
    fireEvent.change(input, { target: { value: "七月门店复盘" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(await screen.findByRole("alert")).toHaveTextContent("项目名称保存失败，请重试");
    expect(screen.getByRole("textbox", { name: "项目名称" })).toBeInTheDocument();
  });

  it("shows safe retry copy without leaking API detail in English", async () => {
    const onRenameProject = vi.fn().mockRejectedValue({
      isAxiosError: true,
      message: "Request failed with status code 409",
      response: {
        status: 409,
        data: { detail: "项目名称已经存在" },
      },
    });
    renderHeader(onRenameProject, "en");
    fireEvent.click(
      screen.getByRole("button", { name: "Rename project: 新的分析项目" })
    );

    const input = screen.getByRole("textbox", { name: "Project name" });
    fireEvent.change(input, { target: { value: "July review" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The request could not be completed. Please retry."
    );
    expect(screen.queryByText("项目名称已经存在")).not.toBeInTheDocument();
  });
});
