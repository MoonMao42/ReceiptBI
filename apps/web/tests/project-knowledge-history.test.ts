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
import type { SemanticEntry, SemanticEntryRevision } from "@/lib/types/api";

function semanticEntry(overrides: Partial<SemanticEntry> = {}): SemanticEntry {
  return {
    id: "knowledge-1",
    project_id: "project-A",
    key: "revenue",
    value: "收入按实付金额计算",
    entry_type: "metric",
    state: "confirmed",
    confidence: 1,
    active_revision_id: "revision-2",
    revision_number: 2,
    definition: null,
    execution_state: "definition_only",
    execution_details: {},
    validity: "active",
    evidence: [],
    source: "user",
    created_at: "2026-07-18T00:00:00Z",
    updated_at: "2026-07-18T00:00:00Z",
    ...overrides,
    allowed_actions: overrides.allowed_actions ?? [],
  };
}

function revision(
  id: string,
  revisionNumber: number,
  overrides: Partial<SemanticEntryRevision> = {}
): SemanticEntryRevision {
  return {
    id,
    project_id: "project-A",
    semantic_entry_id: "knowledge-1",
    revision_number: revisionNumber,
    parent_revision_id: revisionNumber > 1 ? `revision-${revisionNumber - 1}` : null,
    restored_from_revision_id: null,
    mutation_kind: "user_updated",
    actor_source: "user",
    reason: null,
    source_correction_id: null,
    snapshot: {
      key: "revenue",
      value: revisionNumber === 1 ? "收入按开票金额计算" : "收入按实付金额计算",
      entry_type: "metric",
      state: "confirmed",
      confidence: 1,
      definition: null,
      validity: "active",
      execution_state: "definition_only",
      execution_details: {},
      evidence: [],
      source: "user",
      is_active: true,
    },
    created_at: `2026-07-1${revisionNumber}T08:00:00Z`,
    ...overrides,
  };
}

describe("project knowledge history", () => {
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
      knowledgeRevisionsByEntry: {},
      knowledgeRevisionLoadingByEntry: {},
      knowledgeRevisionRestoringByEntry: {},
      knowledgeRevisionErrorByEntry: {},
      suggestedQuestionsRevisionByProject: {},
      isBootstrapping: false,
      isUploading: false,
      isUpdatingKnowledge: false,
      sourceAction: null,
      error: null,
    });
  });

  it("loads one entry's revisions only when requested and reuses the result", async () => {
    const revisions = [revision("revision-2", 2), revision("revision-1", 1)];
    mocks.get.mockResolvedValue({ data: { data: revisions } });

    await useProjectStore.getState().loadKnowledgeRevisions("knowledge-1");
    await useProjectStore.getState().loadKnowledgeRevisions("knowledge-1");

    expect(mocks.get).toHaveBeenCalledTimes(1);
    expect(mocks.get).toHaveBeenCalledWith(
      "/api/v1/projects/project-A/knowledge/knowledge-1/revisions"
    );
    expect(useProjectStore.getState().knowledgeRevisionsByEntry["knowledge-1"])
      .toEqual(revisions);
    expect(useProjectStore.getState().knowledgeRevisionLoadingByEntry["knowledge-1"])
      .toBe(false);
  });

  it("restores against the current head and refreshes knowledge plus history", async () => {
    const restored = semanticEntry({
      value: "收入按开票金额计算",
      active_revision_id: "revision-3",
      revision_number: 3,
    });
    const refreshedRevisions = [
      revision("revision-3", 3, {
        mutation_kind: "restored",
        restored_from_revision_id: "revision-1",
      }),
      revision("revision-2", 2),
      revision("revision-1", 1),
    ];
    mocks.post.mockResolvedValue({ data: { data: restored } });
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith("/revisions")) {
        return Promise.resolve({ data: { data: refreshedRevisions } });
      }
      if (url.endsWith("/knowledge/summary")) {
        return Promise.resolve({
          data: {
            data: {
              active_total: 1,
              pending_total: 0,
              relationship_total: 0,
              confirmed_total: 1,
              locked_total: 0,
            },
          },
        });
      }
      if (url.endsWith("/knowledge/page")) {
        return Promise.resolve({ data: { data: { items: [restored] } } });
      }
      throw new Error(`unexpected URL ${url}`);
    });

    await useProjectStore
      .getState()
      .restoreKnowledgeRevision("knowledge-1", "revision-1");

    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/projects/project-A/knowledge/knowledge-1/revisions/revision-1/restore",
      { expected_active_revision_id: "revision-2" }
    );
    expect(mocks.get).toHaveBeenCalledWith(
      "/api/v1/projects/project-A/knowledge/summary"
    );
    expect(mocks.get).toHaveBeenCalledWith(
      "/api/v1/projects/project-A/knowledge/page",
      { params: { offset: 0, limit: 100, business_facing_only: true } }
    );
    expect(mocks.get).toHaveBeenCalledWith(
      "/api/v1/projects/project-A/knowledge/knowledge-1/revisions"
    );
    expect(
      mocks.get.mock.calls.some(
        ([url]) => url === "/api/v1/projects/project-A/knowledge"
      )
    ).toBe(false);
    expect(useProjectStore.getState().knowledge).toEqual([restored]);
    expect(useProjectStore.getState().knowledgeRevisionsByEntry["knowledge-1"])
      .toEqual(refreshedRevisions);
    expect(useProjectStore.getState().suggestedQuestionsRevisionByProject)
      .toEqual({ "project-A": 1 });
  });

  it("refreshes a concurrent head and returns a plain-language conflict", async () => {
    const latest = semanticEntry({
      value: "收入按财务最终入账金额计算",
      active_revision_id: "revision-3",
      revision_number: 3,
    });
    const latestRevisions = [revision("revision-3", 3), revision("revision-2", 2)];
    mocks.post.mockRejectedValue({
      response: { status: 409, data: { detail: "internal revision conflict" } },
    });
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith("/revisions")) {
        return Promise.resolve({ data: { data: latestRevisions } });
      }
      if (url.endsWith("/knowledge/summary")) {
        return Promise.resolve({
          data: {
            data: {
              active_total: 1,
              pending_total: 0,
              relationship_total: 0,
              confirmed_total: 1,
              locked_total: 0,
            },
          },
        });
      }
      if (url.endsWith("/knowledge/page")) {
        return Promise.resolve({ data: { data: { items: [latest] } } });
      }
      if (url.endsWith("/knowledge/knowledge-1")) {
        return Promise.resolve({ data: { data: latest } });
      }
      throw new Error(`unexpected URL ${url}`);
    });

    await expect(
      useProjectStore
        .getState()
        .restoreKnowledgeRevision("knowledge-1", "revision-1")
    ).rejects.toThrow("这条理解刚刚有了新修改，已刷新最新版本；请确认后再恢复。");

    expect(useProjectStore.getState().knowledge).toEqual([latest]);
    expect(useProjectStore.getState().knowledgeRevisionErrorByEntry["knowledge-1"])
      .toBe("这条理解刚刚有了新修改，已刷新最新版本；请确认后再恢复。");
    expect(useProjectStore.getState().knowledgeRevisionErrorByEntry["knowledge-1"])
      .not.toContain("internal");
    expect(mocks.get).toHaveBeenCalledWith(
      "/api/v1/projects/project-A/knowledge/knowledge-1"
    );
    expect(
      mocks.get.mock.calls.some(
        ([url]) => url === "/api/v1/projects/project-A/knowledge"
      )
    ).toBe(false);
  });
});
