import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReportWorkspace } from "@/components/reports/ReportWorkspace";
import { ReportPrintView } from "@/components/reports/ReportPrintView";
import { ReportPropertyPanel } from "@/components/reports/ReportPropertyPanel";
import { createInvestigationReportDraft } from "@/components/reports/report-draft";
import {
  applyReportBlockUpdates,
  applyStaticReportFilters,
  artifactToReportBlock,
} from "@/components/reports/report-blocks";
import type { ReportDocument } from "@/lib/reports";
import { useChatStore } from "@/lib/stores/chat";
import type { AnalysisArtifact, AnalysisRunSummary } from "@/lib/types/api";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

const {
  getReport,
  updateReport,
  exportReportExcel,
  listReportAnalysisRuns,
  listRunArtifacts,
} = vi.hoisted(() => ({
  getReport: vi.fn(),
  updateReport: vi.fn(),
  exportReportExcel: vi.fn(),
  listReportAnalysisRuns: vi.fn(),
  listRunArtifacts: vi.fn(),
}));

vi.mock("@/lib/reports", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/reports")>();
  return {
    ...actual,
    getReport,
    updateReport,
    exportReportExcel,
    listReportAnalysisRuns,
    listRunArtifacts,
  };
});

const report: ReportDocument = {
  id: "report-1",
  project_id: "project-1",
  title: "经营概览",
  description: "本月经营重点",
  status: "draft",
  version: 1,
  created_at: "2026-07-19T01:00:00Z",
  updated_at: "2026-07-19T02:00:00Z",
  pages: [
    {
      id: "page-1",
      title: "概览",
      order_index: 0,
      config: {},
      version: 1,
      blocks: [
        {
          id: "block-1",
          block_type: "text",
          title: "本月结论",
          order_index: 0,
          source_kind: "manual",
          analysis_run_id: null,
          artifact_id: null,
          content: { text: "收入稳步增长" },
          config: {},
          layout: { x: 0, y: 0, w: 6, h: 3 },
          version: 1,
        },
      ],
    },
  ],
};

describe("ReportWorkspace", () => {
  beforeEach(() => {
    getReport.mockReset();
    updateReport.mockReset();
    exportReportExcel.mockReset();
    listReportAnalysisRuns.mockReset();
    listRunArtifacts.mockReset();
    getReport.mockResolvedValue(structuredClone(report));
    exportReportExcel.mockResolvedValue(
      new Blob(["report"], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      })
    );
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.getItem).mockReturnValue(null);
    useChatStore.setState({
      currentConversationId: null,
      currentConversationMeta: null,
      lastProjectId: null,
    });
    updateReport.mockImplementation(async (_projectId, _reportId, input) => ({
      ...structuredClone(report),
      ...input,
      version: 2,
      updated_at: "2026-07-19T03:00:00Z",
    }));
  });

  afterEach(cleanup);

  it("switches from a clean reading view into a fully editable report", async () => {
    render(<ReportWorkspace projectId="project-1" reportId="report-1" />);

    expect(await screen.findByText("收入稳步增长")).toBeInTheDocument();
    expect(screen.queryByLabelText("区块标题")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "编辑报告" }));
    fireEvent.click(screen.getByRole("button", { name: "添加内容" }));
    fireEvent.click(screen.getByRole("button", { name: /指标.*突出一个重要数字/ }));

    const title = screen.getByLabelText("区块标题");
    fireEvent.change(title, { target: { value: "本月收入" } });
    expect(screen.getByText("本月收入")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(updateReport).toHaveBeenCalledTimes(1));
    expect(updateReport.mock.calls[0][2]).toMatchObject({
      expected_version: 1,
      title: "经营概览",
    });
    expect(updateReport.mock.calls[0][2].pages[0].blocks).toHaveLength(2);
  });

  it("duplicates an investigation block as an independent manual block", async () => {
    const sourceBlock = {
      id: "artifact-block-1",
      block_type: "text" as const,
      title: "调查结论",
      order_index: 0,
      source_kind: "artifact" as const,
      analysis_run_id: "run-1",
      artifact_id: "artifact-1",
      source_ref: { result_name: "monthly_summary" },
      source_available: true,
      content: { text: "收入增长", details: { region: "华东" } },
      config: { manual_override: true, emphasis: "strong" },
      layout: { x: 0, y: 0, w: 6, h: 3 },
      version: 4,
      created_at: "2026-07-19T01:00:00Z",
      updated_at: "2026-07-19T02:00:00Z",
    };
    getReport.mockResolvedValue({
      ...structuredClone(report),
      pages: [
        {
          ...structuredClone(report.pages[0]),
          blocks: [sourceBlock],
        },
      ],
    });

    render(<ReportWorkspace projectId="project-1" reportId="report-1" />);
    await screen.findByText("收入增长");
    fireEvent.click(screen.getByRole("button", { name: "编辑报告" }));
    fireEvent.click(screen.getByRole("button", { name: "复制区块" }));
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(updateReport).toHaveBeenCalledTimes(1));

    const savedBlocks = updateReport.mock.calls[0][2].pages[0].blocks;
    const copy = savedBlocks.find(
      (block: { title: string }) => block.title === "调查结论 副本"
    );
    expect(copy).toBeDefined();
    if (!copy) throw new Error("复制区块未保存");
    expect(copy).toMatchObject({
      source_kind: "manual",
      analysis_run_id: null,
      artifact_id: null,
      content: sourceBlock.content,
      config: { emphasis: "strong" },
    });
    expect(copy.content).not.toBe(sourceBlock.content);
    expect(copy.config).not.toBe(sourceBlock.config);
    for (const field of [
      "source_ref",
      "source_available",
      "version",
      "created_at",
      "updated_at",
    ]) {
      expect(copy).not.toHaveProperty(field);
    }
    expect(copy.config).not.toHaveProperty("manual_override");
    expect(savedBlocks[0]).toMatchObject({
      source_kind: "artifact",
      analysis_run_id: "run-1",
      artifact_id: "artifact-1",
    });
  });

  it("preserves the source conversation when returning to the report list", async () => {
    useChatStore.setState({
      currentConversationId: "conversation-1",
      lastProjectId: "project-1",
    });

    render(<ReportWorkspace projectId="project-1" reportId="report-1" />);

    await screen.findByText("收入稳步增长");
    expect(screen.getByRole("link", { name: "返回报告列表" })).toHaveAttribute(
      "href",
      "/projects/project-1/reports?fromConversation=conversation-1"
    );
  });

  it("adds editable blocks from a completed investigation", async () => {
    listReportAnalysisRuns.mockResolvedValue([
      {
        id: "run-1",
        project_id: "project-1",
        conversation_id: "conversation-1",
        query: "分析月度收入",
        state: "completed",
        stage: "completed",
        report: { title: "收入调查", summary: "收入较上月增长" },
        checkpoint: {},
        created_at: "2026-07-19T01:00:00Z",
        updated_at: "2026-07-19T02:00:00Z",
      },
    ]);
    listRunArtifacts.mockResolvedValue([
      {
        id: "artifact-1",
        project_id: "project-1",
        analysis_run_id: "run-1",
        kind: "metric",
        title: "月度收入",
        payload: { value: "128 万元", context: "较上月 +8%" },
        technical_details: {},
        created_at: "2026-07-19T01:00:00Z",
        updated_at: "2026-07-19T01:00:00Z",
      },
    ]);

    render(<ReportWorkspace projectId="project-1" reportId="report-1" />);
    await screen.findByText("收入稳步增长");
    fireEvent.click(screen.getByRole("button", { name: "编辑报告" }));
    fireEvent.click(screen.getByRole("button", { name: "智能整理" }));
    fireEvent.click(await screen.findByRole("button", { name: /收入调查/ }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /调查摘要/ }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /月度收入/ }));
    fireEvent.click(screen.getByRole("button", { name: /加入当前页面/ }));

    expect(screen.getByText("月度收入")).toBeInTheDocument();
    expect(screen.getByText("128 万元")).toBeInTheDocument();
    expect(screen.getByLabelText("区块标题")).toHaveValue("月度收入");
    fireEvent.change(screen.getByRole("textbox", { name: "显示数值" }), {
      target: { value: "130 万元" },
    });
    expect(screen.getByText("人工调整")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(updateReport).toHaveBeenCalledTimes(1));
    const imported = updateReport.mock.calls[0][2].pages[0].blocks.find(
      (block: { artifact_id?: string }) => block.artifact_id === "artifact-1"
    );
    expect(imported.config.manual_override).toBe(true);
  });

  it("opens the requested investigation when entering from an analysis result", async () => {
    listReportAnalysisRuns.mockResolvedValue([
      {
        id: "run-direct",
        project_id: "project-1",
        query: "查看渠道表现",
        state: "completed",
        stage: "completed",
        report: { title: "渠道调查", summary: "线上渠道增长" },
        checkpoint: {},
        created_at: "2026-07-19T01:00:00Z",
        updated_at: "2026-07-19T02:00:00Z",
      },
    ]);
    listRunArtifacts.mockResolvedValue([]);

    render(
      <ReportWorkspace
        projectId="project-1"
        reportId="report-1"
        initialRunId="run-direct"
      />
    );

    expect(await screen.findByText("选择内容")).toBeInTheDocument();
    expect(screen.getByText("渠道调查")).toBeInTheDocument();
    await waitFor(() =>
      expect(listRunArtifacts).toHaveBeenCalledWith(
        "project-1",
        "run-direct",
        expect.any(AbortSignal)
      )
    );
  });

  it("keeps edits made while an earlier save is still in flight", async () => {
    const firstSave = deferred<ReportDocument>();
    updateReport.mockReturnValueOnce(firstSave.promise);

    render(<ReportWorkspace projectId="project-1" reportId="report-1" />);
    await screen.findByText("收入稳步增长");
    fireEvent.click(screen.getByRole("button", { name: "编辑报告" }));

    const title = screen.getByRole("textbox", { name: "报告标题" });
    fireEvent.change(title, { target: { value: "第一版标题" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(updateReport).toHaveBeenCalledTimes(1));

    fireEvent.change(title, { target: { value: "第二版标题" } });
    await act(async () => {
      firstSave.resolve({
        ...structuredClone(report),
        title: "第一版标题",
        version: 2,
        updated_at: "2026-07-19T03:00:00Z",
      });
      await firstSave.promise;
    });

    await waitFor(() => expect(title).toHaveValue("第二版标题"));
    expect(screen.getByText("有尚未保存的修改")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(updateReport).toHaveBeenCalledTimes(2));
    expect(updateReport.mock.calls[1][2]).toMatchObject({
      expected_version: 2,
      title: "第二版标题",
    });
  });

  it("applies a configured filter to the current page table", async () => {
    getReport.mockResolvedValue({
      ...structuredClone(report),
      pages: [
        {
          ...structuredClone(report.pages[0]),
          blocks: [
            {
              id: "filter-1",
              block_type: "filter",
              title: "地区筛选",
              order_index: 0,
              source_kind: "manual",
              content: {},
              config: { field: "地区", operator: "equals", placeholder: "输入地区" },
              layout: { x: 0, y: 0, w: 4, h: 2 },
            },
            {
              id: "table-1",
              block_type: "table",
              title: "门店明细",
              order_index: 1,
              source_kind: "artifact",
              content: {
                rows: [
                  { 地区: "华东", 门店: "上海" },
                  { 地区: "华南", 门店: "深圳" },
                ],
              },
              config: {},
              layout: { x: 4, y: 0, w: 8, h: 4 },
            },
          ],
        },
      ],
    });

    render(<ReportWorkspace projectId="project-1" reportId="report-1" />);
    expect(await screen.findByText("深圳")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: /地区筛选/ }), {
      target: { value: "华东" },
    });
    expect(screen.getByText("上海")).toBeInTheDocument();
    expect(screen.queryByText("深圳")).not.toBeInTheDocument();
    expect(screen.getByText(/筛选后 1 行/)).toBeInTheDocument();
  });

  it("paginates retained table rows instead of silently cutting them off", async () => {
    getReport.mockResolvedValue({
      ...structuredClone(report),
      pages: [
        {
          ...structuredClone(report.pages[0]),
          blocks: [
            {
              id: "table-many",
              block_type: "table",
              title: "全部明细",
              order_index: 0,
              source_kind: "artifact",
              content: { rows: Array.from({ length: 60 }, (_, index) => ({ 行号: `行 ${index + 1}` })) },
              config: {},
              layout: { x: 0, y: 0, w: 12, h: 6 },
            },
          ],
        },
      ],
    });

    render(<ReportWorkspace projectId="project-1" reportId="report-1" />);
    expect(await screen.findByText(/共 60 行 · 当前 1–50/)).toBeInTheDocument();
    expect(screen.queryByText("行 60")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "下一页明细" }));
    expect(screen.getByText("行 60")).toBeInTheDocument();
    expect(screen.getByText(/当前 51–60/)).toBeInTheDocument();
  });

  it("keeps both editor side panels reachable on narrow screens", async () => {
    render(<ReportWorkspace projectId="project-1" reportId="report-1" />);
    await screen.findByText("收入稳步增长");
    fireEvent.click(screen.getByRole("button", { name: "编辑报告" }));

    fireEvent.click(screen.getByRole("button", { name: "展开页面目录" }));
    expect(screen.getByRole("heading", { name: "页面与区块" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "收起页面目录" }));
    expect(screen.queryByRole("heading", { name: "页面与区块" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "展开设置" }));
    expect(screen.getByRole("heading", { name: "页面设置" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "页面设置" })).not.toBeInTheDocument();
  });

  it("ignores a stale artifact response after switching investigations", async () => {
    const runA = {
      id: "run-a",
      project_id: "project-1",
      query: "调查 A 问题",
      state: "completed" as const,
      stage: "completed",
      report: { title: "调查 A", summary: "A 摘要" },
      checkpoint: {},
      created_at: "2026-07-19T01:00:00Z",
      updated_at: "2026-07-19T02:00:00Z",
    };
    const runB = {
      ...runA,
      id: "run-b",
      query: "调查 B 问题",
      report: { title: "调查 B", summary: "B 摘要" },
    };
    const artifactsA = deferred<Awaited<ReturnType<typeof listRunArtifacts>> >();
    const artifactsB = deferred<Awaited<ReturnType<typeof listRunArtifacts>> >();
    listReportAnalysisRuns.mockResolvedValue([runA, runB]);
    listRunArtifacts.mockImplementation((_projectId, runId) =>
      runId === "run-a" ? artifactsA.promise : artifactsB.promise
    );

    render(<ReportWorkspace projectId="project-1" reportId="report-1" />);
    await screen.findByText("收入稳步增长");
    fireEvent.click(screen.getByRole("button", { name: "编辑报告" }));
    fireEvent.click(screen.getByRole("button", { name: "智能整理" }));
    fireEvent.click(await screen.findByRole("button", { name: /调查 A/ }));
    fireEvent.click(screen.getByRole("button", { name: "返回调查列表" }));
    fireEvent.click(await screen.findByRole("button", { name: /调查 B/ }));

    await act(async () => {
      artifactsB.resolve([
        {
          id: "artifact-b",
          project_id: "project-1",
          analysis_run_id: "run-b",
          kind: "metric",
          title: "B 指标",
          payload: { value: 20 },
          technical_details: {},
          created_at: "2026-07-19T01:00:00Z",
          updated_at: "2026-07-19T01:00:00Z",
        },
      ]);
      await artifactsB.promise;
    });
    expect(await screen.findByText("B 指标")).toBeInTheDocument();

    await act(async () => {
      artifactsA.resolve([
        {
          id: "artifact-a",
          project_id: "project-1",
          analysis_run_id: "run-a",
          kind: "metric",
          title: "A 指标（过期响应）",
          payload: { value: 10 },
          technical_details: {},
          created_at: "2026-07-19T01:00:00Z",
          updated_at: "2026-07-19T01:00:00Z",
        },
      ]);
      await artifactsA.promise;
    });
    expect(screen.getByText("B 指标")).toBeInTheDocument();
    expect(screen.queryByText("A 指标（过期响应）")).not.toBeInTheDocument();
  });

  it("appends a complete editable draft without replacing existing pages", async () => {
    const run: AnalysisRunSummary = {
      id: "run-draft",
      project_id: "project-1",
      query: "整理月度经营情况",
      state: "completed",
      stage: "completed",
      report: { title: "月度经营报告", summary: "收入增长，回款保持稳定。" },
      checkpoint: {},
      created_at: "2026-07-19T01:00:00Z",
      updated_at: "2026-07-19T02:00:00Z",
    };
    const artifacts: AnalysisArtifact[] = [
      {
        id: "metric-draft",
        project_id: "project-1",
        analysis_run_id: run.id,
        kind: "metric",
        title: "本月收入",
        payload: { value: "128 万元" },
        technical_details: {},
        created_at: run.created_at,
        updated_at: run.updated_at,
      },
      {
        id: "table-draft",
        project_id: "project-1",
        analysis_run_id: run.id,
        kind: "table",
        title: "区域明细",
        payload: { rows: [{ 地区: "华东", 收入: 80 }] },
        technical_details: {},
        created_at: run.created_at,
        updated_at: run.updated_at,
      },
      {
        id: "evidence-draft",
        project_id: "project-1",
        analysis_run_id: run.id,
        kind: "evidence",
        title: "核对依据",
        payload: { checks: ["收入汇总已核对"] },
        technical_details: {},
        created_at: run.created_at,
        updated_at: run.updated_at,
      },
    ];
    listReportAnalysisRuns.mockResolvedValue([run]);
    listRunArtifacts.mockResolvedValue(artifacts);

    render(<ReportWorkspace projectId="project-1" reportId="report-1" />);
    await screen.findByText("收入稳步增长");
    fireEvent.click(screen.getByRole("button", { name: "编辑报告" }));
    fireEvent.click(screen.getByRole("button", { name: "智能整理" }));
    fireEvent.click(await screen.findByRole("button", { name: /月度经营报告/ }));
    fireEvent.click(await screen.findByRole("button", { name: "生成初稿" }));

    expect(screen.getAllByText("结论摘要")).toHaveLength(2);
    expect(screen.getAllByText("本月收入")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(updateReport).toHaveBeenCalledTimes(1));

    const savedPages = updateReport.mock.calls[0][2].pages;
    expect(savedPages.map((page: { title: string }) => page.title)).toEqual([
      "概览",
      "概览 2",
      "明细",
      "依据",
    ]);
    expect(savedPages[0].blocks[0].content.text).toBe("收入稳步增长");
    expect(
      savedPages.flatMap((page: { blocks: Array<{ artifact_id?: string }> }) => page.blocks)
    ).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ artifact_id: "metric-draft" }),
        expect.objectContaining({ artifact_id: "table-draft" }),
        expect.objectContaining({ artifact_id: "evidence-draft" }),
      ])
    );
  });

  it("saves current edits before exporting Excel", async () => {
    const downloadClick = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    render(<ReportWorkspace projectId="project-1" reportId="report-1" />);
    await screen.findByText("收入稳步增长");
    fireEvent.click(screen.getByRole("button", { name: "编辑报告" }));
    fireEvent.change(screen.getByRole("textbox", { name: "报告标题" }), {
      target: { value: "最新经营报告" },
    });
    fireEvent.click(screen.getByRole("button", { name: "导出报告" }));
    fireEvent.click(screen.getByRole("button", { name: "导出 Excel" }));

    await waitFor(() => expect(exportReportExcel).toHaveBeenCalledWith("project-1", "report-1"));
    expect(updateReport).toHaveBeenCalledTimes(1);
    expect(updateReport.mock.invocationCallOrder[0]).toBeLessThan(
      exportReportExcel.mock.invocationCallOrder[0]
    );
    expect(updateReport.mock.calls[0][2].title).toBe("最新经营报告");
    downloadClick.mockRestore();
  });
});

describe("createInvestigationReportDraft", () => {
  const run: AnalysisRunSummary = {
    id: "run-compose",
    project_id: "project-1",
    query: "分析本月经营",
    state: "completed",
    stage: "completed",
    report: { title: "本月经营", summary: "经营表现稳定。" },
    checkpoint: {},
    created_at: "2026-07-19T01:00:00Z",
    updated_at: "2026-07-19T02:00:00Z",
  };

  const artifact = (
    id: string,
    kind: AnalysisArtifact["kind"],
    title: string,
    payload: Record<string, unknown>
  ): AnalysisArtifact => ({
    id,
    project_id: "project-1",
    analysis_run_id: run.id,
    kind,
    title,
    payload,
    technical_details: {},
    created_at: run.created_at,
    updated_at: run.updated_at,
  });

  it("builds overview, details and evidence from one investigation", () => {
    const draft = createInvestigationReportDraft(run, [
      artifact("report-copy", "report", "重复摘要", { text: "不应重复导入" }),
      artifact("metric-1", "metric", "收入", { value: 128 }),
      artifact("chart-1", "chart", "收入趋势", {
        chart: {
          type: "line",
          title: "收入趋势",
          data: [{ 月份: "七月", 收入: 128 }],
          xKey: "月份",
          yKeys: ["收入"],
        },
      }),
      artifact("table-1", "table", "区域明细", {
        rows: [{ 地区: "华东", 收入: 80 }],
      }),
      artifact("evidence-1", "evidence", "核对依据", {
        checks: ["汇总结果已核对"],
      }),
      artifact("empty-evidence", "file", "内部附件", {}),
    ]);

    expect(draft.title).toBe("本月经营");
    expect(draft.pages.map((page) => page.title)).toEqual(["概览", "明细", "依据"]);
    expect(draft.pages[0].blocks.map((block) => block.title)).toEqual([
      "结论摘要",
      "收入",
      "收入趋势",
    ]);
    expect(draft.pages[1].blocks).toEqual([
      expect.objectContaining({ artifact_id: "table-1", block_type: "table" }),
    ]);
    expect(draft.pages[2].blocks).toEqual([
      expect.objectContaining({ artifact_id: "evidence-1", block_type: "evidence" }),
    ]);
    expect(draft.pages.flatMap((page) => page.blocks).some((block) => block.title === "重复摘要")).toBe(false);
    expect(draft.pages.flatMap((page) => page.blocks).some((block) => block.artifact_id === "empty-evidence")).toBe(false);
  });

  it("omits empty detail and evidence pages", () => {
    const draft = createInvestigationReportDraft(run, [
      artifact("metric-only", "metric", "收入", { value: 128 }),
    ]);
    expect(draft.pages.map((page) => page.title)).toEqual(["概览"]);
  });
});

describe("ReportPropertyPanel chart presentation", () => {
  it("emits only approved presentation values without offering frontend aggregation", () => {
    const chartBlock = {
      id: "chart-properties",
      block_type: "chart" as const,
      title: "收入趋势",
      order_index: 0,
      source_kind: "artifact" as const,
      analysis_run_id: "run-1",
      artifact_id: "artifact-1",
      content: {
        rows: [
          { 月份: "六月", 收入: 100, 利润: 20 },
          { 月份: "七月", 收入: 128, 利润: 28 },
        ],
      },
      config: {
        chart_type: "bar",
        x_key: "月份",
        y_key: "收入",
        y_keys: ["收入", "利润"],
      },
      layout: { x: 0, y: 0, w: 6, h: 4 },
    };
    const onChangeBlock = vi.fn();
    render(
      <ReportPropertyPanel
        page={{ ...structuredClone(report.pages[0]), blocks: [chartBlock] }}
        block={chartBlock}
        onChangePage={vi.fn()}
        onChangeBlock={onChangeBlock}
      />
    );

    fireEvent.change(screen.getByLabelText("图表方向"), {
      target: { value: "horizontal" },
    });
    fireEvent.change(screen.getByLabelText("图表堆叠"), {
      target: { value: "percent" },
    });
    fireEvent.change(screen.getByLabelText("图表数值格式"), {
      target: { value: "compact" },
    });
    fireEvent.change(screen.getByLabelText("图表配色方案"), {
      target: { value: "categorical" },
    });
    fireEvent.click(screen.getByLabelText("显示数据标签"));
    expect(screen.getByLabelText("收入数值格式")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("收入显示名称"), {
      target: { value: "销售收入" },
    });
    fireEvent.change(screen.getByLabelText("利润数值格式"), {
      target: { value: "currency" },
    });

    for (const expected of [
      { orientation: "horizontal" },
      { stack: "percent" },
      { number_format: "compact" },
      { palette: "categorical" },
      { show_labels: true },
      { series_labels: { 收入: "销售收入" } },
      { series_formats: { 利润: "currency" } },
    ]) {
      expect(onChangeBlock).toHaveBeenCalledWith({
        config: expect.objectContaining(expected),
      });
    }
    expect(screen.queryByLabelText(/聚合/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "区块数据" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "更多显示设置" })).not.toBeInTheDocument();
  });

  it("clips series and clears stacking when switching to pie or scatter", () => {
    const chartBlock = {
      id: "chart-switch-single",
      block_type: "chart" as const,
      title: "收入与利润",
      order_index: 0,
      source_kind: "artifact" as const,
      content: {
        rows: [
          { 月份: "六月", 收入: 100, 利润: 20 },
          { 月份: "七月", 收入: 128, 利润: 28 },
        ],
      },
      config: {
        chart_type: "bar",
        x_key: "月份",
        y_key: "收入",
        y_keys: ["收入", "利润"],
        orientation: "horizontal",
        stack: "percent",
      },
      layout: { x: 0, y: 0, w: 6, h: 4 },
    };
    const onChangeBlock = vi.fn();
    render(
      <ReportPropertyPanel
        page={{ ...structuredClone(report.pages[0]), blocks: [chartBlock] }}
        block={chartBlock}
        onChangePage={vi.fn()}
        onChangeBlock={onChangeBlock}
      />
    );

    fireEvent.change(screen.getByLabelText("图表样式"), {
      target: { value: "pie" },
    });

    expect(onChangeBlock).toHaveBeenLastCalledWith({
      config: expect.objectContaining({
        chart_type: "pie",
        y_key: "收入",
        y_keys: ["收入"],
        orientation: "vertical",
        stack: "none",
      }),
    });
  });

  it("offers one numeric series at a time for pie and scatter", () => {
    const chartBlock = {
      id: "chart-single-series",
      block_type: "chart" as const,
      title: "收入构成",
      order_index: 0,
      source_kind: "artifact" as const,
      content: {
        rows: [
          { 地区: "华东", 收入: 100, 利润: 20 },
          { 地区: "华南", 收入: 80, 利润: 18 },
        ],
      },
      config: {
        chart_type: "pie",
        x_key: "地区",
        y_key: "收入",
        y_keys: ["收入", "利润"],
        stack: "normal",
      },
      layout: { x: 0, y: 0, w: 6, h: 4 },
    };
    const onChangeBlock = vi.fn();
    render(
      <ReportPropertyPanel
        page={{ ...structuredClone(report.pages[0]), blocks: [chartBlock] }}
        block={chartBlock}
        onChangePage={vi.fn()}
        onChangeBlock={onChangeBlock}
      />
    );

    const revenue = screen.getByRole("radio", { name: "收入" });
    const profit = screen.getByRole("radio", { name: "利润" });
    expect(revenue).toBeChecked();
    expect(profit).not.toBeChecked();
    expect(screen.getByLabelText("图表堆叠")).toBeDisabled();
    expect(screen.getByLabelText("图表堆叠")).toHaveValue("none");

    fireEvent.click(profit);
    expect(onChangeBlock).toHaveBeenLastCalledWith({
      config: expect.objectContaining({
        y_key: "利润",
        y_keys: ["利润"],
        stack: "none",
      }),
    });
  });
});

describe("ReportPrintView", () => {
  it("renders every report page for printing", () => {
    const secondPage = {
      ...structuredClone(report.pages[0]),
      id: "page-2",
      title: "明细",
      order_index: 1,
      blocks: [
        {
          ...structuredClone(report.pages[0].blocks[0]),
          id: "block-2",
          title: "区域结论",
          content: { text: "华东表现稳定" },
        },
      ],
    };
    const { container } = render(
      <ReportPrintView
        report={{ ...structuredClone(report), pages: [...structuredClone(report.pages), secondPage] }}
        filterValues={{}}
      />
    );

    expect(container.querySelectorAll(".report-print-page")).toHaveLength(2);
    expect(screen.getByText("收入稳步增长")).toBeInTheDocument();
    expect(screen.getByText("华东表现稳定")).toBeInTheDocument();
  });
});

describe("artifactToReportBlock", () => {
  it("keeps source provenance while making an artifact editable", () => {
    const block = artifactToReportBlock({
      id: "artifact-1",
      project_id: "project-1",
      analysis_run_id: "run-1",
      kind: "metric",
      title: "回款金额",
      payload: { metric_value: 3200, summary: "本周回款" },
      technical_details: {},
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    });

    expect(block).toMatchObject({
      block_type: "metric",
      source_kind: "artifact",
      artifact_id: "artifact-1",
      analysis_run_id: "run-1",
      content: { value: 3200, context: "本周回款" },
    });
  });

  it("unpacks structured chart data and its selected axes", () => {
    const block = artifactToReportBlock({
      id: "chart-1",
      project_id: "project-1",
      analysis_run_id: "run-1",
      kind: "chart",
      title: "默认标题",
      payload: {
        chart: {
          type: "area",
          title: "收入趋势",
          data: [{ month: "一月", revenue: 12, profit: 3 }],
          xKey: "month",
          yKeys: ["revenue", "profit"],
        },
      },
      technical_details: {},
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    });

    expect(block).toMatchObject({
      title: "收入趋势",
      content: { rows: [{ month: "一月", revenue: 12, profit: 3 }] },
      config: {
        chart_type: "area",
        x_key: "month",
        y_key: "revenue",
        y_keys: ["revenue", "profit"],
      },
    });
  });

  it("imports the approved v1 chart presentation into editable report settings", () => {
    const block = artifactToReportBlock({
      id: "chart-v1",
      project_id: "project-1",
      analysis_run_id: "run-1",
      kind: "chart",
      title: "默认标题",
      payload: {
        chart: {
          version: 1,
          type: "bar",
          title: "区域收入",
          data_ref: { result_name: "regional_revenue", result_hash: "sha256:abc" },
          encoding: {
            x: { field: "地区", kind: "category" },
            y: [
              {
                field: "收入",
                label: "销售收入",
                kind: "number",
                aggregate: "sum",
                format: "compact",
              },
              {
                field: "利润",
                label: "利润率",
                kind: "number",
                aggregate: "sum",
                format: "percent",
              },
            ],
          },
          presentation: {
            orientation: "horizontal",
            stack: "normal",
            palette: "categorical",
          },
          data: [{ 地区: "华东", 收入: 128, 利润: 28 }],
        },
      },
      technical_details: {},
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    });

    expect(block).toMatchObject({
      title: "区域收入",
      content: { rows: [{ 地区: "华东", 收入: 128, 利润: 28 }] },
      config: {
        chart_type: "bar",
        x_key: "地区",
        y_key: "收入",
        y_keys: ["收入", "利润"],
        orientation: "horizontal",
        stack: "normal",
        palette: "categorical",
        number_format: "compact",
        series_labels: { 收入: "销售收入", 利润: "利润率" },
        series_formats: { 收入: "compact", 利润: "percent" },
      },
    });
    expect(block.config).not.toHaveProperty("aggregate");
  });

  it("keeps the immutable file endpoint for a PNG chart", () => {
    const block = artifactToReportBlock({
      id: "chart-image-1",
      project_id: "project-1",
      analysis_run_id: "run-1",
      kind: "chart",
      title: "分布图",
      payload: { format: "png", relative_path: "project-1/chart.png" },
      technical_details: {},
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    });

    expect(block.config.chart_type).toBe("image");
    expect(block.content.image_url).toBe(
      "/api/v1/projects/project-1/analysis-runs/run-1/artifacts/chart-image-1/file"
    );
  });

  it("turns validation evidence into readable items", () => {
    const block = artifactToReportBlock({
      id: "evidence-1",
      project_id: "project-1",
      analysis_run_id: "run-1",
      kind: "evidence",
      title: "核对依据",
      payload: {
        validations: [
          {
            kind: "relationship_validation",
            status: "verified",
            profile: { returned_rows: 42 },
          },
        ],
        correction_applications: [
          { rule_value: "退款按净额计入", summary: "已应用到本次结果" },
        ],
      },
      technical_details: {},
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    });

    expect(block.content.items).toEqual([
      { label: "数据关联已核对", text: "42 行数据已核对" },
      { label: "业务调整：退款按净额计入", text: "已应用到本次结果" },
    ]);
  });

  it("turns a change brief into a readable narrative", () => {
    const block = artifactToReportBlock({
      id: "change-1",
      project_id: "project-1",
      analysis_run_id: "run-1",
      kind: "change_brief",
      title: "经营变化",
      payload: {
        status: "material_change",
        overall: [
          { metric: "收入", before: 100, after: 120, percent_change: 0.2 },
        ],
        top_drivers: [
          {
            key: { 地区: "华东" },
            change: { metric: "收入", before: 40, after: 55, delta: 15 },
          },
        ],
      },
      technical_details: {},
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    });

    expect(block.content.text).toContain("发现值得关注的变化");
    expect(block.content.text).toContain("收入：100 → 120，+20.0%");
    expect(block.content.text).toContain("华东：收入：40 → 55，变化 +15");
  });
});

describe("applyStaticReportFilters", () => {
  it("filters only blocks that expose the selected field", () => {
    const chart = {
      id: "chart-filter",
      block_type: "chart" as const,
      title: "收入趋势",
      order_index: 0,
      source_kind: "artifact" as const,
      content: {
        rows: [
          { 地区: "华东", 收入: 12 },
          { 地区: "华南", 收入: 8 },
        ],
      },
      config: {},
      layout: { x: 0, y: 0, w: 6, h: 4 },
    };

    const filtered = applyStaticReportFilters(chart, [
      { field: "地区", operator: "equals", value: "华东" },
    ]);
    expect(filtered.content.rows).toEqual([{ 地区: "华东", 收入: 12 }]);
    expect(filtered.content._filter_source_rows).toBe(2);
    expect(
      applyStaticReportFilters(chart, [
        { field: "不存在", operator: "equals", value: "华东" },
      ])
    ).toBe(chart);
  });
});

describe("applyReportBlockUpdates", () => {
  it("marks title and presentation changes as manual without rewriting provenance", () => {
    const sourceRef = {
      source_kind: "artifact",
      artifact_title: "收入趋势",
      retained_at: "2026-07-19T00:00:00Z",
    };
    const source = {
      id: "chart-manual-override",
      block_type: "chart" as const,
      title: "收入趋势",
      order_index: 0,
      source_kind: "artifact" as const,
      analysis_run_id: "run-1",
      artifact_id: "artifact-1",
      source_ref: sourceRef,
      content: { rows: [{ 月份: "七月", 收入: 128 }] },
      config: { chart_type: "bar", x_key: "月份", y_keys: ["收入"] },
      layout: { x: 0, y: 0, w: 6, h: 4 },
    };

    const renamed = applyReportBlockUpdates(source, { title: "手工调整后的收入趋势" });
    expect(renamed).toMatchObject({
      title: "手工调整后的收入趋势",
      analysis_run_id: "run-1",
      artifact_id: "artifact-1",
      config: { manual_override: true },
    });
    expect(renamed.source_ref).toBe(sourceRef);

    const restyled = applyReportBlockUpdates(source, {
      config: { ...source.config, stack: "normal", show_labels: true },
      source_ref: { source_kind: "manual" },
      artifact_id: "replacement-artifact",
    });
    expect(restyled).toMatchObject({
      artifact_id: "artifact-1",
      config: {
        chart_type: "bar",
        stack: "normal",
        show_labels: true,
        manual_override: true,
      },
    });
    expect(restyled.source_ref).toBe(sourceRef);
  });
});
