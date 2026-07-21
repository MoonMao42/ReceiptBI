import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  api: mocks,
}));

import { useProjectStore } from "@/lib/stores/project";
import type { SemanticEntry } from "@/lib/types/api";

function semanticEntry(overrides: Partial<SemanticEntry> = {}): SemanticEntry {
  return {
    id: "knowledge-1",
    project_id: "project-A",
    key: "revenue",
    value: "收入按实付金额计算",
    entry_type: "metric",
    state: "confirmed",
    confidence: 1,
    validity: "active",
    evidence: [],
    source: "user",
    created_at: "2026-07-18T00:00:00Z",
    updated_at: "2026-07-18T00:00:00Z",
    ...overrides,
    allowed_actions: overrides.allowed_actions ?? [],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("project knowledge refresh", () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    useProjectStore.setState({
      projects: [],
      currentProjectId: "project-A",
      sources: [],
      preflightReports: [],
      knowledge: [semanticEntry()],
      knowledgeTotal: 1,
      pendingKnowledgeCount: 0,
      relationshipKnowledgeCount: 0,
      suggestedQuestionsRevisionByProject: {},
      isBootstrapping: false,
      isUploading: false,
      isUpdatingKnowledge: false,
      sourceAction: null,
      error: null,
    });
  });

  it("advances the current project's suggestion revision after update and create", async () => {
    const updated = semanticEntry({ value: "收入按实付金额减退款计算" });
    mocks.put.mockResolvedValue({ data: { data: updated } });

    await useProjectStore.getState().updateKnowledge("knowledge-1", {
      value: updated.value,
    });

    expect(useProjectStore.getState().knowledge).toEqual([updated]);
    expect(useProjectStore.getState().suggestedQuestionsRevisionByProject)
      .toEqual({ "project-A": 1 });

    const created = semanticEntry({ id: "knowledge-2", key: "refund" });
    mocks.post.mockResolvedValue({ data: { data: created } });
    await useProjectStore.getState().createKnowledge({
      key: created.key,
      value: created.value,
      entry_type: created.entry_type,
      state: created.state,
      confidence: created.confidence,
      validity: created.validity,
      evidence: created.evidence,
      source: created.source,
    });

    expect(useProjectStore.getState().knowledge[0]).toEqual(created);
    expect(useProjectStore.getState().suggestedQuestionsRevisionByProject)
      .toEqual({ "project-A": 2 });
  });

  it("forwards an explicit definition reset with the active revision guard", async () => {
    const current = semanticEntry({
      definition: { version: 1, kind: "metric_formula" },
      active_revision_id: "revision-1",
    });
    const updated = semanticEntry({
      value: "收入按实付金额减去已审核退款计算",
      definition: null,
      active_revision_id: "revision-2",
      revision_number: 2,
      execution_state: "definition_only",
    });
    useProjectStore.setState({ knowledge: [current] });
    mocks.put.mockResolvedValue({ data: { data: updated } });

    await useProjectStore.getState().updateKnowledge(current.id, {
      value: updated.value,
      definition: null,
    });

    expect(mocks.put).toHaveBeenCalledWith(
      "/api/v1/projects/project-A/knowledge/knowledge-1",
      {
        value: updated.value,
        definition: null,
        expected_active_revision_id: "revision-1",
      }
    );
    expect(useProjectStore.getState().knowledge).toEqual([updated]);
  });

  it("does not invalidate suggestions when a knowledge mutation fails", async () => {
    mocks.put.mockRejectedValue(new Error("save failed"));

    await expect(
      useProjectStore.getState().updateKnowledge("knowledge-1", { value: "new value" })
    ).rejects.toThrow("save failed");

    expect(useProjectStore.getState().suggestedQuestionsRevisionByProject).toEqual({});
  });

  it("invalidates the original project without overwriting a project selected meanwhile", async () => {
    const request = deferred<{ data: { data: SemanticEntry } }>();
    mocks.put.mockReturnValue(request.promise);
    const update = useProjectStore.getState().updateKnowledge("knowledge-1", {
      value: "更新后的口径",
    });

    const projectBEntry = semanticEntry({
      id: "knowledge-B",
      project_id: "project-B",
      key: "orders",
    });
    useProjectStore.setState({
      currentProjectId: "project-B",
      knowledge: [projectBEntry],
    });
    request.resolve({
      data: { data: semanticEntry({ value: "更新后的口径" }) },
    });
    await update;

    expect(useProjectStore.getState().knowledge).toEqual([projectBEntry]);
    expect(useProjectStore.getState().suggestedQuestionsRevisionByProject)
      .toEqual({ "project-A": 1 });
  });

  it("refreshes a bounded preview and keeps server totals without loading all knowledge", async () => {
    const preview = semanticEntry({
      id: "relationship-preview",
      key: "relationship:orders:stores",
      entry_type: "relationship",
      state: "candidate",
      validity: "unverified",
    });
    mocks.get.mockImplementation((url: string, config?: unknown) => {
      if (url === "/api/v1/projects/project-A/sources") {
        return Promise.resolve({ data: { data: [] } });
      }
      if (url === "/api/v1/projects/project-A/preflight") {
        return Promise.resolve({ data: { data: [] } });
      }
      if (url === "/api/v1/projects/project-A/knowledge/summary") {
        return Promise.resolve({
          data: {
            data: {
              active_total: 802,
              pending_total: 792,
              relationship_total: 792,
              confirmed_total: 10,
              locked_total: 0,
            },
          },
        });
      }
      if (url === "/api/v1/projects/project-A/knowledge/page") {
        expect(config).toEqual({
          params: { offset: 0, limit: 100, business_facing_only: true },
        });
        return Promise.resolve({ data: { data: { items: [preview] } } });
      }
      if (
        url === "/api/v1/projects/project-A/recipes" ||
        url === "/api/v1/projects/project-A/recipe-templates"
      ) {
        return Promise.resolve({ data: { data: [] } });
      }
      throw new Error(`unexpected URL ${url}`);
    });

    await useProjectStore.getState().refreshCurrent();

    expect(useProjectStore.getState().knowledge).toEqual([preview]);
    expect(useProjectStore.getState().knowledgeTotal).toBe(802);
    expect(useProjectStore.getState().pendingKnowledgeCount).toBe(792);
    expect(useProjectStore.getState().relationshipKnowledgeCount).toBe(792);
    expect(
      mocks.get.mock.calls.some(
        ([url]) => url === "/api/v1/projects/project-A/knowledge"
      )
    ).toBe(false);
  });

  it("does not fall back to an unbounded list when the paginated API is unavailable", async () => {
    mocks.get.mockImplementation((url: string) => {
      if (url === "/api/v1/projects/project-A/sources") {
        return Promise.resolve({ data: { data: [] } });
      }
      if (url === "/api/v1/projects/project-A/preflight") {
        return Promise.resolve({ data: { data: [] } });
      }
      if (url === "/api/v1/projects/project-A/knowledge/summary") {
        return Promise.reject({ response: { status: 404 } });
      }
      if (url === "/api/v1/projects/project-A/knowledge/page") {
        return Promise.resolve({ data: { data: { items: [] } } });
      }
      if (
        url === "/api/v1/projects/project-A/recipes" ||
        url === "/api/v1/projects/project-A/recipe-templates"
      ) {
        return Promise.resolve({ data: { data: [] } });
      }
      throw new Error(`unexpected URL ${url}`);
    });

    await useProjectStore.getState().refreshCurrent();

    expect(useProjectStore.getState().error).toBe("数据准备失败，请稍后重试");
    expect(
      mocks.get.mock.calls.some(
        ([url]) => url === "/api/v1/projects/project-A/knowledge"
      )
    ).toBe(false);
  });

  it("does not turn a non-404 pagination failure into a full-list request", async () => {
    mocks.get.mockImplementation((url: string) => {
      if (url === "/api/v1/projects/project-A/sources") {
        return Promise.resolve({ data: { data: [] } });
      }
      if (url === "/api/v1/projects/project-A/preflight") {
        return Promise.resolve({ data: { data: [] } });
      }
      if (url === "/api/v1/projects/project-A/knowledge/summary") {
        return Promise.reject({
          response: { status: 503, data: { detail: "语义摘要暂时不可用" } },
        });
      }
      if (url === "/api/v1/projects/project-A/knowledge/page") {
        return Promise.resolve({ data: { data: { items: [] } } });
      }
      if (
        url === "/api/v1/projects/project-A/recipes" ||
        url === "/api/v1/projects/project-A/recipe-templates"
      ) {
        return Promise.resolve({ data: { data: [] } });
      }
      throw new Error(`unexpected URL ${url}`);
    });

    await useProjectStore.getState().refreshCurrent();

    expect(useProjectStore.getState().error).toBe("语义摘要暂时不可用");
    expect(
      mocks.get.mock.calls.some(
        ([url]) => url === "/api/v1/projects/project-A/knowledge"
      )
    ).toBe(false);
  });
});
