import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReportBlockCard } from "@/components/reports/ReportBlockCard";
import { ReportPrintView } from "@/components/reports/ReportPrintView";
import type { ReportBlock, ReportDocument } from "@/lib/reports";
import messages from "@/messages/zh.json";

afterEach(cleanup);

const noop = vi.fn();

function textBlock(highlight: unknown): ReportBlock {
  return {
    id: "block-highlight",
    block_type: "text",
    title: "经营结论",
    order_index: 0,
    source_kind: "artifact",
    analysis_run_id: "run-1",
    artifact_id: "artifact-1",
    content: { text: "收入保持增长。" },
    config: { highlight },
    layout: { x: 0, y: 0, w: 12, h: 3 },
  };
}

function renderCard({
  editing = false,
  staticRendering = false,
  highlight = "  华东区贡献了主要增量。  ",
  text = "收入保持增长。",
}: {
  editing?: boolean;
  staticRendering?: boolean;
  highlight?: unknown;
  text?: string;
} = {}) {
  const block = textBlock(highlight);
  block.content.text = text;
  return render(
    <NextIntlClientProvider locale="zh" messages={messages}>
      <ReportBlockCard
        block={block}
        editing={editing}
        selected={false}
        staticRendering={staticRendering}
        onSelect={noop}
        onMove={noop}
        onResize={noop}
        onDuplicate={noop}
        onDelete={noop}
      />
    </NextIntlClientProvider>
  );
}

describe("ReportBlockCard highlight", () => {
  it("shows a non-empty string highlight in editing mode", () => {
    renderCard({ editing: true });

    const note = screen.getByRole("note", { name: "重点" });
    expect(note).toHaveTextContent("重点");
    expect(note).toHaveTextContent("华东区贡献了主要增量。");
  });

  it("keeps the highlight visible in reading mode", () => {
    renderCard();

    expect(screen.getByRole("note", { name: "重点" })).toHaveTextContent(
      "华东区贡献了主要增量。"
    );
  });

  it("normalizes accidental repeated punctuation in report prose", () => {
    renderCard({
      text: "收入保持增长。。。。。",
      highlight: "需要关注退款率变化！！！！",
    });

    expect(screen.getByText("收入保持增长。")).toBeInTheDocument();
    expect(screen.getByRole("note", { name: "重点" })).toHaveTextContent(
      "需要关注退款率变化！"
    );
  });

  it("keeps the highlight visible in the static print view", () => {
    const block = textBlock("需要关注退款率变化。");
    const report: ReportDocument = {
      id: "report-1",
      project_id: "project-1",
      title: "月度经营报告",
      description: "",
      status: "draft",
      version: 1,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
      pages: [
        {
          id: "page-1",
          title: "概览",
          order_index: 0,
          config: {},
          blocks: [block],
        },
      ],
    };

    render(
      <NextIntlClientProvider locale="zh" messages={messages}>
        <ReportPrintView report={report} filterValues={{}} />
      </NextIntlClientProvider>
    );

    expect(
      screen.getByRole("note", { name: "重点", hidden: true })
    ).toHaveTextContent(
      "需要关注退款率变化。"
    );
  });

  it.each([
    ["pure whitespace", "   \n  "],
    ["number", 42],
    ["object", { text: "不应显示" }],
    ["array", ["不应显示"]],
    ["null", null],
  ])("does not render an unknown %s highlight value", (_label, highlight) => {
    renderCard({ highlight });

    expect(screen.queryByRole("note", { name: "重点" })).not.toBeInTheDocument();
  });
});
