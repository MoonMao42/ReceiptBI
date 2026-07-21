import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ProjectUnderstandingWorkspace,
  relationshipDefinition,
  semanticSignalLabel,
  semanticTypeLabel,
} from "@/components/semantic/ProjectUnderstandingWorkspace";
import { api } from "@/lib/api/client";
import { useProjectStore } from "@/lib/stores/project";
import type { ProjectDataSource, SemanticEntry } from "@/lib/types/api";

const candidate = (id: string, leftTable: string, rightTable: string): SemanticEntry => ({
  id,
  project_id: "project-1",
  key: `relationship_candidate:store_id:${id}`,
  value: `${leftTable}.store_id ↔ ${rightTable}.store_id`,
  entry_type: "relationship",
  state: "candidate",
  confidence: 0.55,
  active_revision_id: `revision-${id}`,
  revision_number: 1,
  definition: {
    version: 1,
    left: {
      source_logical_name: "财务库",
      source_kind: "connection",
      table_or_view: leftTable,
      column: "store_id",
      data_type: "integer",
      schema_signature: "a".repeat(64),
    },
    right: {
      source_logical_name: "财务库",
      source_kind: "connection",
      table_or_view: rightTable,
      column: "store_id",
      data_type: "integer",
      schema_signature: "b".repeat(64),
    },
  },
  execution_state: "needs_validation",
  allowed_actions: ["queue_validation", "ignore"],
  validity: "unverified",
  evidence: [{ kind: "matching_column_names" }],
  source_refs: [
    {
      source_id: "source-finance",
      logical_name: "财务库",
      name: "财务库",
      kind: "connection",
      format: "sqlite",
    },
  ],
  source_scope: "local_database",
  source: "inferred",
  created_at: "2026-07-19T00:00:00Z",
  updated_at: "2026-07-19T00:00:00Z",
});

const projectSource = (
  id: string,
  name: string,
  kind: ProjectDataSource["kind"],
  format: string
): ProjectDataSource => ({
  id,
  project_id: "project-1",
  kind,
  name,
  format,
  status: "ready",
  fingerprint: null,
  profile_data: { logical_name: name },
  created_at: "2026-07-19T00:00:00Z",
  updated_at: "2026-07-19T00:00:00Z",
});

describe("ProjectUnderstandingWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.sessionStorage.clear();
    window.localStorage.clear();
    useProjectStore.setState({ currentProjectId: null });
  });

  it("shows the full relationship count with governed paging and filtering", async () => {
    const first = candidate("one", "orders", "stores");
    const second = candidate("two", "refunds", "stores");
    const get = vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      return {
        data: {
          data: {
            items: [first, second],
            total: 792,
            offset: 0,
            limit: 50,
            has_more: true,
            next_offset: 50,
          },
        },
      } as never;
    });

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);

    expect(await screen.findByText("共 792 条")).toBeInTheDocument();
    expect(screen.getAllByText(/财务库 · orders.store_id/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("同名字段").length).toBeGreaterThan(0);
    expect(screen.getByRole("columnheader", { name: "线索强度" })).toBeInTheDocument();
    expect(screen.getAllByText("初步线索").length).toBeGreaterThan(0);
    expect(screen.queryByText("55%")).not.toBeInTheDocument();
    expect(screen.queryByText("只有验证过的规则才会执行")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("内容类型"), {
      target: { value: "business_rule" },
    });
    await waitFor(() =>
      expect(get).toHaveBeenLastCalledWith(
        "/api/v1/projects/project-1/knowledge/page",
        expect.objectContaining({
          params: expect.objectContaining({
            entry_type: "business_rule",
            business_facing_only: true,
          }),
        })
      )
    );
  });

  it("groups project understanding by real source and sends source filters to the page API", async () => {
    const sources = [
      projectSource("local-db", "本地财务库", "connection", "sqlite"),
      projectSource("remote-db", "线上订单库", "connection", "postgresql"),
      projectSource("excel-file", "年度预算.xlsx", "file", "xlsx"),
      projectSource("csv-file", "门店清单.csv", "file", "csv"),
      projectSource("parquet-file", "明细.parquet", "file", "parquet"),
      projectSource("json-file", "渠道.json", "file", "json"),
    ];
    const get = vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: sources } } as never;
      }
      return {
        data: {
          data: {
            items: [],
            total: 0,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);
    await screen.findByRole("option", { name: "本地财务库" });

    const sourceSelect = screen.getByLabelText("适用数据") as HTMLSelectElement;
    expect(sourceSelect.querySelector('option[value="scope:project"]')).toHaveTextContent(
      "项目通用"
    );
    expect(
      sourceSelect.querySelector(
        'optgroup[label="本地数据库"] option[value="source:local-db"]'
      )
    ).toHaveTextContent("本地财务库");
    expect(
      sourceSelect.querySelector(
        'optgroup[label="在线数据库"] option[value="source:remote-db"]'
      )
    ).toHaveTextContent("线上订单库");
    expect(
      sourceSelect.querySelector('optgroup[label="Excel"] option[value="source:excel-file"]')
    ).toHaveTextContent("年度预算.xlsx");
    expect(
      sourceSelect.querySelector('optgroup[label="CSV"] option[value="source:csv-file"]')
    ).toHaveTextContent("门店清单.csv");
    expect(sourceSelect.querySelector('optgroup[label="其他文件"]')).toBeNull();

    fireEvent.change(sourceSelect, { target: { value: "scope:remote_database" } });
    await waitFor(() => {
      const [, config] = get.mock.calls.at(-1) || [];
      const params = (config as { params?: Record<string, unknown> } | undefined)?.params;
      expect(params).toMatchObject({ source_scope: "remote_database", offset: 0 });
      expect(params).not.toHaveProperty("source_id");
    });

    fireEvent.change(sourceSelect, { target: { value: "source:csv-file" } });
    await waitFor(() => {
      const [, config] = get.mock.calls.at(-1) || [];
      const params = (config as { params?: Record<string, unknown> } | undefined)?.params;
      expect(params).toMatchObject({ source_id: "csv-file", offset: 0 });
      expect(params).not.toHaveProperty("source_scope");
    });
  });

  it("shows applicable data separately from how a definition was added", async () => {
    const rule: SemanticEntry = {
      ...candidate("remote-rule", "orders", "stores"),
      key: "rule:recognized_revenue",
      value: "只统计已审核订单",
      entry_type: "business_rule",
      definition: null,
      source_scope: "remote_database",
      source_refs: [
        {
          source_id: "remote-db",
          logical_name: "线上订单库",
          name: "线上订单库",
          kind: "connection",
          format: "postgresql",
        },
      ],
      source: "user",
    };
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      return {
        data: {
          data: {
            items: [rule],
            total: 1,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);

    expect(await screen.findByText(/适用数据 · 线上订单库/)).toBeInTheDocument();
    const details = screen.getByRole("complementary", { name: "项目理解详情" });
    expect(within(details).getByText("适用数据")).toBeInTheDocument();
    expect(within(details).getByText("线上订单库")).toBeInTheDocument();
    expect(within(details).getByText("添加方式")).toBeInTheDocument();
    expect(within(details).getByText("人工维护")).toBeInTheDocument();
  });

  it("offers validation in bulk without offering unsafe candidate approval", async () => {
    const first = candidate("one", "orders", "stores");
    const second = candidate("two", "refunds", "stores");
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      return {
        data: {
          data: {
            items: [first, second],
            total: 792,
            offset: 0,
            limit: 50,
            has_more: true,
            next_offset: 50,
          },
        },
      } as never;
    });
    const post = vi.spyOn(api, "post").mockResolvedValue({
      data: {
        data: {
          action: "queue_validation",
          items: [first, second],
          queued_entry_ids: [first.id, second.id],
          validation_selection: [
            {
              entry_id: first.id,
              expected_active_revision_id: "queued-revision-one",
            },
            {
              entry_id: second.id,
              expected_active_revision_id: "queued-revision-two",
            },
          ],
          validation_prompt: "验证所选数据关联",
        },
      },
    } as never);

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);
    await screen.findByText("共 792 条");

    fireEvent.click(screen.getByLabelText("选择本页"));
    const validate = screen.getByRole("button", { name: "验证所选" });
    const remember = screen.getByRole("button", { name: "记住所选" });
    expect(validate).toBeEnabled();
    expect(remember).toBeDisabled();

    await act(async () => fireEvent.click(validate));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        "/api/v1/projects/project-1/knowledge/batch",
        expect.objectContaining({
          action: "queue_validation",
          items: [
            { entry_id: first.id, expected_active_revision_id: first.active_revision_id },
            { entry_id: second.id, expected_active_revision_id: second.active_revision_id },
          ],
        })
      )
    );
    expect(window.sessionStorage.getItem("receiptbi-pending-task")).toContain(
      "验证所选数据关联"
    );
    expect(window.sessionStorage.getItem("receiptbi-pending-task")).toContain(
      "queued-revision-two"
    );
  });

  it("opens details from the whole row or arrow while checkboxes only batch-select", async () => {
    const first = candidate("one", "orders", "stores");
    const second = candidate("two", "refunds", "stores");
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      return {
        data: {
          data: {
            items: [first, second],
            total: 2,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);
    await screen.findByText("共 2 条");

    const firstRow = screen.getByRole("row", { name: /orders\.store_id/ });
    const secondRow = screen.getByRole("row", { name: /refunds\.store_id/ });
    expect(firstRow).toHaveAttribute("aria-selected", "true");
    expect(secondRow).toHaveAttribute("aria-selected", "false");

    fireEvent.click(screen.getByLabelText(/选择 .*refunds\.store_id/));
    expect(firstRow).toHaveAttribute("aria-selected", "true");
    expect(secondRow).toHaveAttribute("aria-selected", "false");
    expect(screen.getByText("已选 1 条")).toBeInTheDocument();

    fireEvent.click(secondRow);
    expect(secondRow).toHaveAttribute("aria-selected", "true");

    fireEvent.click(within(firstRow).getByRole("button", { name: /查看.*orders\.store_id/ }));
    expect(firstRow).toHaveAttribute("aria-selected", "true");
  });

  it("keeps the list and detail pane as independent viewport scroll regions", async () => {
    const first = candidate("one", "orders", "stores");
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      return {
        data: {
          data: {
            items: [first],
            total: 1,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });

    const { container } = render(
      <ProjectUnderstandingWorkspace projectId="project-1" />
    );
    await screen.findByText("共 1 条");

    expect(container.firstElementChild).toHaveClass("h-dvh", "overflow-hidden");
    expect(screen.getByRole("region", { name: "项目理解列表" })).toHaveClass(
      "overflow-hidden"
    );
    expect(screen.getByRole("complementary", { name: "项目理解详情" })).toHaveClass(
      "overflow-y-auto",
      "overscroll-contain"
    );
  });

  it("uses server-authorized actions for mixed candidate states", async () => {
    const verified: SemanticEntry = {
      ...candidate("verified", "orders", "stores"),
      validity: "active",
      execution_state: "verified",
      allowed_actions: ["ignore", "remember"],
    };
    const definitionMissing: SemanticEntry = {
      ...candidate("missing", "refunds", "stores"),
      definition: null,
      allowed_actions: ["ignore"],
    };
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      return {
        data: {
          data: {
            items: [verified, definitionMissing],
            total: 2,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);
    await screen.findByText("共 2 条");

    expect(screen.getByLabelText("搜索项目理解")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /筛选/ })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
    expect(screen.queryByRole("button", { name: "验证这条关系" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "记住这条内容" })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("选择本页"));
    expect(screen.getByRole("button", { name: "记住所选" })).toBeDisabled();
    const ignoreActions = screen.getAllByRole("button", { name: "不采用" });
    expect(ignoreActions[ignoreActions.length - 1]).toBeEnabled();
  });

  it("restores an ignored candidate against its visible revision", async () => {
    const ignored: SemanticEntry = {
      ...candidate("ignored", "orders", "stores"),
      is_active: false,
      validity: "stale",
      allowed_actions: ["restore"],
    };
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      return {
        data: {
          data: {
            items: [ignored],
            total: 1,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });
    const post = vi.spyOn(api, "post").mockResolvedValue({
      data: {
        data: {
          action: "restore",
          items: [{ ...ignored, is_active: true, validity: "unverified" }],
          queued_entry_ids: [],
          validation_selection: [],
        },
      },
    } as never);

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);
    await screen.findByText("共 1 条");
    expect(screen.getByRole("button", { name: "修改业务定义" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "重新考虑" }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        "/api/v1/projects/project-1/knowledge/batch",
        {
          action: "restore",
          items: [
            {
              entry_id: ignored.id,
              expected_active_revision_id: ignored.active_revision_id,
            },
          ],
        }
      )
    );
  });

  it("edits one business description against the visible revision", async () => {
    const first = candidate("one", "orders", "stores");
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      return {
        data: {
          data: {
            items: [first],
            total: 1,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });
    const put = vi.spyOn(api, "put").mockResolvedValue({
      data: { data: { ...first, value: "订单按门店编号关联" } },
    } as never);

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);
    await screen.findByText("共 1 条");
    fireEvent.click(screen.getByRole("button", { name: "修改业务定义" }));
    fireEvent.change(screen.getByLabelText("业务定义"), {
      target: { value: "订单按门店编号关联" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith(
        `/api/v1/projects/project-1/knowledge/${first.id}`,
        expect.objectContaining({
          expected_active_revision_id: first.active_revision_id,
          key: first.key,
          value: "订单按门店编号关联",
          entry_type: "relationship",
          state: "candidate",
          source: "user",
          confidence: first.confidence,
          definition: expect.objectContaining({
            left: expect.objectContaining({ table_or_view: "orders", column: "store_id" }),
            right: expect.objectContaining({ table_or_view: "stores", column: "store_id" }),
            default_join: "left",
          }),
        })
      )
    );
  });

  it("adds a manual business definition with an explicit governance state", async () => {
    const created: SemanticEntry = {
      ...candidate("created", "orders", "stores"),
      key: "rule:recognized_revenue",
      value: "只统计已审核订单",
      entry_type: "business_rule",
      state: "confirmed",
      confidence: 1,
      definition: null,
      validity: "active",
      source: "user",
      allowed_actions: [],
    };
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      return {
        data: {
          data: {
            items: [],
            total: 0,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });
    const post = vi.spyOn(api, "post").mockResolvedValue({
      data: { data: created },
    } as never);

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);
    await screen.findByText("共 0 条");
    fireEvent.click(screen.getByRole("button", { name: "新增定义" }));
    expect(screen.getByRole("dialog", { name: "新增业务定义" })).toBeInTheDocument();
    expect(screen.getByLabelText("采用状态")).toHaveValue("candidate");

    fireEvent.change(screen.getByLabelText("名称"), {
      target: { value: "rule:recognized_revenue" },
    });
    fireEvent.change(screen.getByLabelText("业务定义"), {
      target: { value: "只统计已审核订单" },
    });
    fireEvent.change(screen.getByLabelText("采用状态"), {
      target: { value: "confirmed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加定义" }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        "/api/v1/projects/project-1/knowledge",
        {
          key: "rule:recognized_revenue",
          value: "只统计已审核订单",
          entry_type: "business_rule",
          state: "confirmed",
          confidence: 1,
          definition: null,
          validity: "active",
          source: "user",
          evidence: [{ kind: "user_declaration" }],
        }
      )
    );
  });

  it("binds a manual definition to one selected data source", async () => {
    const source = projectSource("csv-file", "门店清单.csv", "file", "csv");
    const created: SemanticEntry = {
      ...candidate("created-for-csv", "orders", "stores"),
      key: "dimension:store_region",
      value: "门店所属经营区域",
      entry_type: "dimension",
      definition: null,
      source: "user",
      source_scope: "csv",
      source_refs: [
        {
          source_id: source.id,
          logical_name: source.name,
          name: source.name,
          kind: source.kind,
          format: source.format,
        },
      ],
    };
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [source] } } as never;
      }
      return {
        data: {
          data: {
            items: [],
            total: 0,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { data: created } } as never);

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);
    await screen.findByRole("option", { name: "门店清单.csv" });
    fireEvent.click(screen.getByRole("button", { name: "新增定义" }));
    fireEvent.change(screen.getByLabelText("定义类型"), {
      target: { value: "dimension" },
    });
    fireEvent.change(screen.getByLabelText("名称"), {
      target: { value: "dimension:store_region" },
    });
    fireEvent.change(screen.getByLabelText("业务定义"), {
      target: { value: "门店所属经营区域" },
    });
    fireEvent.change(screen.getByLabelText("适用范围"), {
      target: { value: `source:${source.id}` },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加定义" }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        "/api/v1/projects/project-1/knowledge",
        expect.objectContaining({
          entry_type: "dimension",
          evidence: [{ kind: "user_declaration", source_ids: [source.id] }],
        })
      )
    );
  });

  it("keeps an existing cross-source scope when editing unrelated fields", async () => {
    const crossSourceRule: SemanticEntry = {
      ...candidate("cross-rule", "orders", "stores"),
      key: "rule:cross_source_customer",
      value: "客户口径跨订单库与会员库统一",
      entry_type: "business_rule",
      definition: null,
      source_scope: "cross_source",
      source_refs: [
        {
          source_id: "orders-db",
          logical_name: "订单库",
          name: "订单库",
          kind: "connection",
          format: "postgresql",
        },
        {
          source_id: "members-db",
          logical_name: "会员库",
          name: "会员库",
          kind: "connection",
          format: "mysql",
        },
      ],
      evidence: [
        { kind: "matching_column_names", score: 0.9 },
        { kind: "user_declaration", source_ids: ["orders-db", "members-db"] },
      ],
      source: "user",
    };
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      return {
        data: {
          data: {
            items: [crossSourceRule],
            total: 1,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });
    const put = vi.spyOn(api, "put").mockResolvedValue({
      data: { data: { ...crossSourceRule, value: "统一客户口径" } },
    } as never);

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);
    await screen.findByText(/适用数据 · 跨数据源 · 订单库、会员库/);
    fireEvent.click(screen.getByRole("button", { name: "修改业务定义" }));
    expect(screen.getByLabelText("适用范围")).toHaveValue("preserve");
    fireEvent.change(screen.getByLabelText("业务定义"), {
      target: { value: "统一客户口径" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith(
        `/api/v1/projects/project-1/knowledge/${crossSourceRule.id}`,
        expect.objectContaining({ evidence: crossSourceRule.evidence })
      )
    );
  });

  it("builds a structured relationship from project source metadata", async () => {
    const source = {
      id: "source-1",
      project_id: "project-1",
      kind: "connection",
      name: "财务库",
      format: "sqlite",
      status: "ready",
      fingerprint: null,
      profile_data: {
        logical_name: "财务库",
        tables: [
          {
            name: "orders",
            columns: [
              { name: "id", type: "INTEGER" },
              { name: "store_id", type: "INTEGER" },
            ],
          },
          {
            name: "stores",
            columns: [
              { name: "id", type: "INTEGER" },
              { name: "name", type: "TEXT" },
            ],
          },
        ],
      },
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    };
    const created = candidate("manual-relationship", "orders", "stores");
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [source] } } as never;
      }
      return {
        data: {
          data: {
            items: [],
            total: 0,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { data: created } } as never);

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);
    await screen.findByText("共 0 条");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "新增定义" })).toBeEnabled()
    );
    fireEvent.click(screen.getByRole("button", { name: "新增定义" }));
    fireEvent.change(screen.getByLabelText("定义类型"), {
      target: { value: "relationship" },
    });
    fireEvent.change(screen.getByLabelText("名称"), {
      target: { value: "relationship:orders_to_stores" },
    });
    fireEvent.change(screen.getByLabelText("业务定义"), {
      target: { value: "订单通过门店编号关联门店" },
    });
    fireEvent.change(screen.getByLabelText("左侧数据来源"), {
      target: { value: source.id },
    });
    fireEvent.change(screen.getByLabelText("左侧表或视图"), {
      target: { value: "orders" },
    });
    fireEvent.change(screen.getByLabelText("左侧字段"), {
      target: { value: "store_id" },
    });
    fireEvent.change(screen.getByLabelText("右侧数据来源"), {
      target: { value: source.id },
    });
    fireEvent.change(screen.getByLabelText("右侧表或视图"), {
      target: { value: "stores" },
    });
    fireEvent.change(screen.getByLabelText("右侧字段"), {
      target: { value: "id" },
    });
    fireEvent.change(screen.getByLabelText("连接方式"), {
      target: { value: "inner" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加定义" }));

    await waitFor(() => expect(post).toHaveBeenCalled());
    const payload = post.mock.calls[0]?.[1] as Record<string, unknown>;
    const definition = payload.definition as Record<string, unknown>;
    const left = definition.left as Record<string, unknown>;
    const right = definition.right as Record<string, unknown>;
    expect(definition.default_join).toBe("inner");
    expect(left).toMatchObject({
      source_logical_name: "财务库",
      source_kind: "connection",
      table_or_view: "orders",
      column: "store_id",
      data_type: "INTEGER",
    });
    expect(right).toMatchObject({ table_or_view: "stores", column: "id" });
    expect(left.schema_signature).toBe(
      "e1c990977787c443205b82fc5e6dcc4efe2bea6ecb6bd28000a5b3586ad28d56"
    );
    expect(right.schema_signature).toBe(
      "5571d00d2f7bebe04ebc5c692b865ec86ee672b9e85955cb7ce9afa3ed3385ad"
    );
  });

  it("validates extension JSON and executable definition compatibility before updating", async () => {
    const rule: SemanticEntry = {
      ...candidate("rule", "orders", "stores"),
      key: "rule:refund_scope",
      value: "退款按审核状态计算",
      entry_type: "business_rule",
      definition: null,
    };
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      return {
        data: {
          data: {
            items: [rule],
            total: 1,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });
    const put = vi.spyOn(api, "put");

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);
    await screen.findByText("共 1 条");
    fireEvent.click(screen.getByRole("button", { name: "修改业务定义" }));
    fireEvent.click(screen.getByText("高级定义（可选）"));
    fireEvent.change(screen.getByLabelText("扩展定义"), {
      target: { value: '{"kind":' },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("扩展定义不是有效的 JSON，请检查括号和引号。")).toBeInTheDocument();
    expect(put).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("扩展定义"), {
      target: { value: '{"kind":"aggregate_metric"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("聚合指标定义只能用于指标类型。")).toBeInTheDocument();
    expect(put).not.toHaveBeenCalled();

    const customDefinition = { kind: "custom_display", label: "退款范围说明" };
    put.mockResolvedValue({
      data: { data: { ...rule, definition: customDefinition, source: "user" } },
    } as never);
    fireEvent.change(screen.getByLabelText("扩展定义"), {
      target: { value: JSON.stringify(customDefinition) },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith(
        `/api/v1/projects/project-1/knowledge/${rule.id}`,
        expect.objectContaining({
          entry_type: "business_rule",
          definition: customDefinition,
        })
      )
    );
  });

  it("syncs a deep-linked project without triggering a legacy full refresh", async () => {
    useProjectStore.setState({ currentProjectId: "project-A" });
    window.localStorage.setItem("receiptbi-current-project", "project-A");
    const get = vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-B") {
        return { data: { data: { id: "project-B", name: "项目 B" } } } as never;
      }
      if (url === "/api/v1/projects/project-B/sources") {
        return { data: { data: [] } } as never;
      }
      return {
        data: {
          data: {
            items: [],
            total: 0,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });

    render(<ProjectUnderstandingWorkspace projectId="project-B" />);

    await waitFor(() =>
      expect(useProjectStore.getState().currentProjectId).toBe("project-B")
    );
    expect(window.localStorage.setItem).toHaveBeenCalledWith(
      "receiptbi-current-project",
      "project-B"
    );
    expect(get).not.toHaveBeenCalledWith("/api/v1/projects/project-B/knowledge", expect.anything());
  });

  it("does not fall back to loading the entire semantic layer", async () => {
    const get = vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      if (url === "/api/v1/projects/project-1/knowledge/page") {
        throw { response: { status: 404, data: { detail: "分页接口不可用" } } };
      }
      throw new Error(`unexpected request: ${url}`);
    });

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);

    expect(await screen.findByText("分页接口不可用")).toBeInTheDocument();
    expect(
      get.mock.calls.some(
        ([url]) => url === "/api/v1/projects/project-1/knowledge"
      )
    ).toBe(false);
  });

  it("clears and disables selection while a replacement query is pending", async () => {
    const first = candidate("one", "orders", "stores");
    let resolveReplacement: ((value: unknown) => void) | null = null;
    let pageCallCount = 0;
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      if (url === "/api/v1/projects/project-1/sources") {
        return { data: { data: [] } } as never;
      }
      pageCallCount += 1;
      if (pageCallCount === 1) {
        return {
          data: {
            data: {
              items: [first],
              total: 1,
              offset: 0,
              limit: 50,
              has_more: false,
              next_offset: null,
            },
          },
        } as never;
      }
      return await new Promise((resolve) => {
        resolveReplacement = resolve;
      });
    });

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);
    await screen.findByText("共 1 条");
    fireEvent.click(screen.getByLabelText("选择本页"));
    expect(screen.getByText("已选 1 条")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("内容类型"), {
      target: { value: "business_rule" },
    });

    await waitFor(() => expect(screen.queryByText("已选 1 条")).not.toBeInTheDocument());
    expect(screen.getByLabelText("选择本页")).toBeDisabled();

    await act(async () => {
      resolveReplacement?.({
        data: {
          data: {
            items: [],
            total: 0,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      });
    });
    await waitFor(() => expect(screen.getByText("共 0 条")).toBeInTheDocument());
  });

  it("rejects entries whose server action contract is missing", async () => {
    const unsafe = {
      ...candidate("unsafe", "orders", "stores"),
      allowed_actions: undefined,
    } as unknown as SemanticEntry;
    vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (url.endsWith("/sources")) return { data: { data: [] } } as never;
      if (url === "/api/v1/projects/project-1") {
        return { data: { data: { id: "project-1", name: "财务分析" } } } as never;
      }
      return {
        data: {
          data: {
            items: [unsafe],
            total: 1,
            offset: 0,
            limit: 50,
            has_more: false,
            next_offset: null,
          },
        },
      } as never;
    });

    render(<ProjectUnderstandingWorkspace projectId="project-1" />);

    expect(
      await screen.findByText("项目理解的操作权限没有加载完成，请刷新重试。")
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "验证这条关系" })).not.toBeInTheDocument();
  });

  it("keeps relationship parsing explicit and typed", () => {
    const entry = candidate("one", "orders", "stores");
    expect(relationshipDefinition(entry)?.left?.table_or_view).toBe("orders");
    expect(semanticTypeLabel(entry.entry_type)).toBe("数据关联");
    expect(semanticSignalLabel(entry)).toBe("初步线索");
    expect(
      semanticSignalLabel({
        ...entry,
        validity: "active",
        execution_state: "verified",
      })
    ).toBe("完整数据已验证");
  });
});
