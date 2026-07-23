import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  api: {
    get: mocks.get,
    post: mocks.post,
    patch: mocks.patch,
  },
}));

import { useProjectStore } from "@/lib/stores/project";

const originalRefreshCurrent = useProjectStore.getState().refreshCurrent;
const originalSelectProject = useProjectStore.getState().selectProject;

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("project workspace refresh", () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.patch.mockReset();
    useProjectStore.setState({
      projects: [],
      currentProjectId: null,
      sources: [],
      preflightReports: [],
      knowledge: [],
      knowledgeTotal: 0,
      pendingKnowledgeCount: 0,
      relationshipKnowledgeCount: 0,
      isBootstrapping: false,
      isUploading: false,
      isUpdatingKnowledge: false,
      error: null,
      refreshCurrent: originalRefreshCurrent,
      selectProject: originalSelectProject,
    });
  });

  it("posts the localized project name supplied by the UI", async () => {
    const project = {
      id: "project-en",
      name: "New analysis project",
      status: "active",
      extra_data: {},
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-01T00:00:00Z",
    };
    const selectProject = vi.fn().mockResolvedValue(undefined);
    useProjectStore.setState({ selectProject });
    mocks.post.mockResolvedValue({ data: { data: project } });

    await useProjectStore.getState().createProject("New analysis project");

    expect(mocks.post).toHaveBeenCalledWith("/api/v1/projects", {
      name: "New analysis project",
    });
    expect(selectProject).toHaveBeenCalledWith("project-en");
  });

  it("posts localized defaults when bootstrapping an empty workspace", async () => {
    const project = {
      id: "project-initial-en",
      name: "My analysis project",
      status: "active",
      extra_data: {},
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-01T00:00:00Z",
    };
    const refreshCurrent = vi.fn().mockResolvedValue(undefined);
    useProjectStore.setState({ refreshCurrent });
    mocks.get.mockResolvedValue({ data: { data: [] } });
    mocks.post.mockResolvedValue({ data: { data: project } });

    await useProjectStore.getState().bootstrap({
      name: "My analysis project",
      description: "Keep orders, stores, and confirmed business definitions here",
    });

    expect(mocks.post).toHaveBeenCalledWith("/api/v1/projects", {
      name: "My analysis project",
      description: "Keep orders, stores, and confirmed business definitions here",
    });
    expect(refreshCurrent).toHaveBeenCalledTimes(1);
  });

  it("does not let a slow previous project overwrite the current project", async () => {
    const aSources = deferred<{ data: { data: Array<{ id: string }> } }>();
    const aReports = deferred<{ data: { data: Array<{ id: string }> } }>();
    const aKnowledge = deferred<{
      data: { data: { items: Array<{ id: string }> } };
    }>();
    const aSummary = deferred<{
      data: {
        data: {
          active_total: number;
          pending_total: number;
          relationship_total: number;
        };
      };
    }>();
    const bSources = deferred<{ data: { data: Array<{ id: string }> } }>();
    const bReports = deferred<{ data: { data: Array<{ id: string }> } }>();
    const bKnowledge = deferred<{
      data: { data: { items: Array<{ id: string }> } };
    }>();
    const bSummary = deferred<{
      data: {
        data: {
          active_total: number;
          pending_total: number;
          relationship_total: number;
        };
      };
    }>();

    mocks.get.mockImplementation((url: string) => {
      if (url === "/api/v1/projects/A/sources") return aSources.promise;
      if (url === "/api/v1/projects/A/preflight") return aReports.promise;
      if (url === "/api/v1/projects/A/knowledge/page") return aKnowledge.promise;
      if (url === "/api/v1/projects/A/knowledge/summary") return aSummary.promise;
      if (url === "/api/v1/projects/B/sources") return bSources.promise;
      if (url === "/api/v1/projects/B/preflight") return bReports.promise;
      if (url === "/api/v1/projects/B/knowledge/page") return bKnowledge.promise;
      if (url === "/api/v1/projects/B/knowledge/summary") return bSummary.promise;
      throw new Error(`unexpected URL ${url}`);
    });

    useProjectStore.setState({ currentProjectId: "A" });
    const refreshA = useProjectStore.getState().refreshCurrent();
    useProjectStore.setState({ currentProjectId: "B" });
    const refreshB = useProjectStore.getState().refreshCurrent();

    bSources.resolve({ data: { data: [{ id: "source-B" }] } });
    bReports.resolve({ data: { data: [{ id: "report-B" }] } });
    bKnowledge.resolve({ data: { data: { items: [{ id: "knowledge-B" }] } } });
    bSummary.resolve({
      data: {
        data: { active_total: 802, pending_total: 792, relationship_total: 792 },
      },
    });
    await refreshB;

    aSources.resolve({ data: { data: [{ id: "source-A" }] } });
    aReports.resolve({ data: { data: [{ id: "report-A" }] } });
    aKnowledge.resolve({ data: { data: { items: [{ id: "knowledge-A" }] } } });
    aSummary.resolve({
      data: {
        data: { active_total: 4, pending_total: 1, relationship_total: 2 },
      },
    });
    await refreshA;

    expect(useProjectStore.getState().currentProjectId).toBe("B");
    expect(useProjectStore.getState().sources).toEqual([{ id: "source-B" }]);
    expect(useProjectStore.getState().preflightReports).toEqual([{ id: "report-B" }]);
    expect(useProjectStore.getState().knowledge).toEqual([{ id: "knowledge-B" }]);
    expect(useProjectStore.getState().knowledgeTotal).toBe(802);
    expect(useProjectStore.getState().pendingKnowledgeCount).toBe(792);
    expect(useProjectStore.getState().relationshipKnowledgeCount).toBe(792);
    expect(mocks.get).toHaveBeenCalledWith(
      "/api/v1/projects/B/knowledge/page",
      { params: { offset: 0, limit: 100, business_facing_only: true } }
    );
    expect(
      mocks.get.mock.calls.some(([url]) => url === "/api/v1/projects/B/knowledge")
    ).toBe(false);
  });

  it("replaces the renamed project without disturbing the current workspace", async () => {
    const original = {
      id: "A",
      name: "新的分析项目",
      status: "active",
      extra_data: {},
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-01T00:00:00Z",
    };
    const renamed = {
      ...original,
      name: "七月门店复盘",
      updated_at: "2026-07-02T00:00:00Z",
    };
    useProjectStore.setState({
      projects: [original],
      currentProjectId: "A",
      sources: [{ id: "source-A" }] as never,
      preflightReports: [{ id: "report-A" }] as never,
      knowledge: [{ id: "knowledge-A" }] as never,
    });
    mocks.patch.mockResolvedValue({ data: { data: renamed } });

    await useProjectStore.getState().renameProject("A", "  七月门店复盘  ");

    expect(mocks.patch).toHaveBeenCalledWith("/api/v1/projects/A", {
      name: "七月门店复盘",
    });
    expect(useProjectStore.getState().projects).toEqual([renamed]);
    expect(useProjectStore.getState().sources).toEqual([{ id: "source-A" }]);
    expect(useProjectStore.getState().preflightReports).toEqual([{ id: "report-A" }]);
    expect(useProjectStore.getState().knowledge).toEqual([{ id: "knowledge-A" }]);
  });
});
