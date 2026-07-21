"use client";

import { create } from "zustand";
import { api } from "@/lib/api/client";
import {
  migrateProjectStorage,
  PROJECT_STORAGE_KEY,
} from "@/lib/storage/legacy";
import type {
  PreflightReport,
  Project,
  ProjectDataSource,
  SanitationRecipe,
  SanitationRecipeRevision,
  SanitationTemplatePreview,
  SanitationTemplateSummary,
  SemanticEntry,
  SemanticEntryRevision,
  VisualCleaningApplyResult,
  VisualCleaningOperation,
  VisualCleaningPreview,
} from "@/lib/types/api";

let refreshGeneration = 0;

export function storedProjectId(storage?: Storage): string | null {
  try {
    return migrateProjectStorage(storage || window.localStorage);
  } catch {
    return null;
  }
}

interface ProjectState {
  projects: Project[];
  currentProjectId: string | null;
  sources: ProjectDataSource[];
  preflightReports: PreflightReport[];
  recipes: SanitationRecipe[];
  recipeRevisionsByRecipe: Record<string, SanitationRecipeRevision[]>;
  recipeRevisionLoadingByRecipe: Record<string, boolean>;
  recipeRevisionRestoringByRecipe: Record<string, string | null>;
  recipeRevisionErrorByRecipe: Record<string, string | null>;
  recipeTemplates: SanitationTemplateSummary[];
  recipeTemplatePreviewById: Record<string, SanitationTemplatePreview | undefined>;
  recipeTemplateAction: {
    templateId: string;
    kind: "preview" | "bind";
  } | null;
  cleaningPreviewBySource: Record<string, VisualCleaningPreview | undefined>;
  cleaningAction: {
    sourceId: string;
    kind: "preview" | "apply";
  } | null;
  knowledge: SemanticEntry[];
  knowledgeTotal: number;
  pendingKnowledgeCount: number;
  relationshipKnowledgeCount: number;
  knowledgeRevisionsByEntry: Record<string, SemanticEntryRevision[]>;
  knowledgeRevisionLoadingByEntry: Record<string, boolean>;
  knowledgeRevisionRestoringByEntry: Record<string, string | null>;
  knowledgeRevisionErrorByEntry: Record<string, string | null>;
  suggestedQuestionsRevisionByProject: Record<string, number>;
  isBootstrapping: boolean;
  isUploading: boolean;
  isUpdatingKnowledge: boolean;
  sourceAction: {
    sourceId: string;
    kind: "profile" | "reorganize" | "accept_replacement" | "keep_trusted" | "remove";
  } | null;
  error: string | null;
  bootstrap: () => Promise<void>;
  createProject: (name?: string) => Promise<Project>;
  renameProject: (id: string, name: string) => Promise<Project>;
  selectProject: (id: string) => Promise<void>;
  refreshCurrent: () => Promise<void>;
  loadRecipeRevisions: (id: string) => Promise<SanitationRecipeRevision[]>;
  restoreRecipeRevision: (
    id: string,
    revisionId: string
  ) => Promise<SanitationRecipeRevision>;
  previewRecipeTemplate: (
    templateId: string,
    sourceId: string
  ) => Promise<SanitationTemplatePreview>;
  bindRecipeTemplate: (templateId: string) => Promise<void>;
  previewSourceCleaning: (
    sourceId: string,
    operations: VisualCleaningOperation[]
  ) => Promise<VisualCleaningPreview>;
  clearSourceCleaningPreview: (sourceId: string) => void;
  applySourceCleaning: (
    sourceId: string,
    operations: VisualCleaningOperation[]
  ) => Promise<VisualCleaningApplyResult>;
  loadKnowledgeRevisions: (id: string) => Promise<SemanticEntryRevision[]>;
  restoreKnowledgeRevision: (id: string, revisionId: string) => Promise<SemanticEntry>;
  updateKnowledge: (
    id: string,
    changes: Partial<
      Pick<
        SemanticEntry,
        | "value"
        | "state"
        | "confidence"
        | "definition"
        | "validity"
        | "evidence"
        | "source"
      >
    >
  ) => Promise<SemanticEntry>;
  createKnowledge: (
    entry: Pick<
      SemanticEntry,
      | "key"
      | "value"
      | "entry_type"
      | "state"
      | "confidence"
      | "validity"
      | "evidence"
      | "source"
    >
  ) => Promise<SemanticEntry>;
  uploadFile: (file: File) => Promise<void>;
  attachConnection: (connectionId: string, name?: string) => Promise<void>;
  profileSource: (sourceId: string) => Promise<void>;
  reorganizeSource: (sourceId: string) => Promise<void>;
  acceptReplacement: (sourceId: string) => Promise<void>;
  keepTrustedSource: (sourceId: string) => Promise<void>;
  removeSource: (sourceId: string) => Promise<void>;
}

function messageFrom(error: unknown): string {
  if (typeof error === "object" && error && "response" in error) {
    const response = error.response;
    if (typeof response === "object" && response && "data" in response) {
      const data = response.data;
      if (typeof data === "object" && data) {
        if ("detail" in data && typeof data.detail === "string") return data.detail;
        if ("message" in data && typeof data.message === "string") return data.message;
      }
    }
  }
  if (typeof error === "object" && error && "message" in error) {
    return String(error.message);
  }
  return "数据准备失败，请稍后重试";
}

function responseStatus(error: unknown): number | null {
  if (typeof error !== "object" || !error || !("response" in error)) return null;
  const response = error.response;
  if (typeof response !== "object" || !response || !("status" in response)) return null;
  return typeof response.status === "number" ? response.status : null;
}

interface SemanticKnowledgeSummary {
  active_total: number;
  pending_total: number;
  relationship_total: number;
  confirmed_total: number;
  locked_total: number;
}

interface SemanticKnowledgePreview {
  items: SemanticEntry[];
  summary: SemanticKnowledgeSummary;
}

const KNOWLEDGE_PREVIEW_LIMIT = 100;

function isUserVisibleKnowledge(entry: SemanticEntry): boolean {
  if (entry.entry_type === "verified_query") return false;
  return !(
    entry.entry_type === "cleaning_rule" && /^[\[{]/.test(entry.value.trim())
  );
}

async function fetchKnowledgePreview(projectId: string): Promise<SemanticKnowledgePreview> {
  const [summaryResponse, pageResponse] = await Promise.all([
    api.get(`/api/v1/projects/${projectId}/knowledge/summary`),
    api.get(`/api/v1/projects/${projectId}/knowledge/page`, {
      params: {
        offset: 0,
        limit: KNOWLEDGE_PREVIEW_LIMIT,
        business_facing_only: true,
      },
    }),
  ]);
  return {
    items: (pageResponse.data.data.items || []) as SemanticEntry[],
    summary: summaryResponse.data.data as SemanticKnowledgeSummary,
  };
}

async function fetchKnowledgeRestoreState(
  projectId: string,
  entryId: string,
  options: { includeEntry: boolean }
) {
  const [previewResult, revisionsResult, entryResult] = await Promise.allSettled([
    fetchKnowledgePreview(projectId),
    api.get(`/api/v1/projects/${projectId}/knowledge/${entryId}/revisions`),
    options.includeEntry
      ? api.get(`/api/v1/projects/${projectId}/knowledge/${entryId}`)
      : Promise.resolve(null),
  ]);
  return {
    preview:
      previewResult.status === "fulfilled" ? previewResult.value : null,
    revisions:
      revisionsResult.status === "fulfilled"
        ? (revisionsResult.value.data.data as SemanticEntryRevision[])
        : null,
    entry:
      options.includeEntry &&
      entryResult.status === "fulfilled" &&
      entryResult.value
        ? (entryResult.value.data.data as SemanticEntry)
        : null,
  };
}

function semanticCountContribution(entry: SemanticEntry | undefined) {
  const active = Boolean(entry && entry.is_active !== false);
  return {
    total: active ? 1 : 0,
    pending:
      active &&
      entry &&
      isUserVisibleKnowledge(entry) &&
      entry.state === "candidate" &&
      entry.validity !== "stale"
        ? 1
        : 0,
    relationship: active && entry?.entry_type === "relationship" ? 1 : 0,
  };
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  currentProjectId: null,
  sources: [],
  preflightReports: [],
  recipes: [],
  recipeRevisionsByRecipe: {},
  recipeRevisionLoadingByRecipe: {},
  recipeRevisionRestoringByRecipe: {},
  recipeRevisionErrorByRecipe: {},
  recipeTemplates: [],
  recipeTemplatePreviewById: {},
  recipeTemplateAction: null,
  cleaningPreviewBySource: {},
  cleaningAction: null,
  knowledge: [],
  knowledgeTotal: 0,
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

  bootstrap: async () => {
    if (get().isBootstrapping) return;
    set({ isBootstrapping: true, error: null });
    try {
      const response = await api.get("/api/v1/projects");
      let projects = response.data.data as Project[];
      if (!projects.length) {
        const created = await api.post("/api/v1/projects", {
          name: "我的分析项目",
          description: "订单、门店和业务口径都保存在这里",
        });
        projects = [created.data.data as Project];
      }
      const saved = storedProjectId();
      const currentProjectId =
        projects.find((project) => project.id === saved)?.id || projects[0].id;
      localStorage.setItem(PROJECT_STORAGE_KEY, currentProjectId);
      set({ projects, currentProjectId });
      await get().refreshCurrent();
    } catch (error) {
      set({ error: messageFrom(error) });
    } finally {
      set({ isBootstrapping: false });
    }
  },

  createProject: async (name = "新的分析项目") => {
    const response = await api.post("/api/v1/projects", { name });
    const project = response.data.data as Project;
    set((state) => ({ projects: [project, ...state.projects] }));
    await get().selectProject(project.id);
    return project;
  },

  renameProject: async (id, name) => {
    const response = await api.patch(`/api/v1/projects/${id}`, {
      name: name.trim(),
    });
    const project = response.data.data as Project;
    set((state) => ({
      projects: state.projects.map((item) => (item.id === id ? project : item)),
    }));
    return project;
  },

  selectProject: async (id) => {
    localStorage.setItem(PROJECT_STORAGE_KEY, id);
    set({
      currentProjectId: id,
      sources: [],
      preflightReports: [],
      recipes: [],
      recipeRevisionsByRecipe: {},
      recipeRevisionLoadingByRecipe: {},
      recipeRevisionRestoringByRecipe: {},
      recipeRevisionErrorByRecipe: {},
      recipeTemplates: [],
      recipeTemplatePreviewById: {},
      recipeTemplateAction: null,
      cleaningPreviewBySource: {},
      cleaningAction: null,
      knowledge: [],
      knowledgeTotal: 0,
      pendingKnowledgeCount: 0,
      relationshipKnowledgeCount: 0,
      knowledgeRevisionsByEntry: {},
      knowledgeRevisionLoadingByEntry: {},
      knowledgeRevisionRestoringByEntry: {},
      knowledgeRevisionErrorByEntry: {},
      sourceAction: null,
      error: null,
    });
    await get().refreshCurrent();
  },

  refreshCurrent: async () => {
    const projectId = get().currentProjectId;
    if (!projectId) return;
    const generation = ++refreshGeneration;
    try {
      const [
        sourcesResponse,
        reportsResponse,
        knowledgePreview,
        recipesResponse,
        templatesResponse,
      ] =
        await Promise.all([
        api.get(`/api/v1/projects/${projectId}/sources`),
        api.get(`/api/v1/projects/${projectId}/preflight`),
        fetchKnowledgePreview(projectId),
        Promise.resolve()
          .then(() => api.get(`/api/v1/projects/${projectId}/recipes`))
          .catch(() => null),
        Promise.resolve()
          .then(() => api.get(`/api/v1/projects/${projectId}/recipe-templates`))
          .catch(() => null),
      ]);
      if (
        get().currentProjectId !== projectId ||
        generation !== refreshGeneration
      ) {
        return;
      }
      set({
        sources: sourcesResponse.data.data as ProjectDataSource[],
        preflightReports: reportsResponse.data.data as PreflightReport[],
        recipes:
          (recipesResponse?.data?.data as SanitationRecipe[] | undefined) ||
          get().recipes,
        recipeTemplates:
          (templatesResponse?.data?.data as SanitationTemplateSummary[] | undefined) ||
          get().recipeTemplates,
        knowledge: knowledgePreview.items,
        knowledgeTotal: knowledgePreview.summary.active_total,
        pendingKnowledgeCount: knowledgePreview.summary.pending_total,
        relationshipKnowledgeCount: knowledgePreview.summary.relationship_total,
        error: null,
      });
    } catch (error) {
      if (
        get().currentProjectId === projectId &&
        generation === refreshGeneration
      ) {
        set({ error: messageFrom(error) });
      }
    }
  },

  loadRecipeRevisions: async (id) => {
    const projectId = get().currentProjectId;
    if (!projectId) throw new Error("当前没有可查看的项目");
    const cached = get().recipeRevisionsByRecipe[id];
    if (cached) return cached;
    if (get().recipeRevisionLoadingByRecipe[id]) return [];

    set((state) => ({
      recipeRevisionLoadingByRecipe: {
        ...state.recipeRevisionLoadingByRecipe,
        [id]: true,
      },
      recipeRevisionErrorByRecipe: {
        ...state.recipeRevisionErrorByRecipe,
        [id]: null,
      },
    }));
    try {
      const response = await api.get(
        `/api/v1/projects/${projectId}/recipes/${id}/revisions`
      );
      const revisions = response.data.data as SanitationRecipeRevision[];
      if (get().currentProjectId === projectId) {
        set((state) => ({
          recipeRevisionsByRecipe: {
            ...state.recipeRevisionsByRecipe,
            [id]: revisions,
          },
        }));
      }
      return revisions;
    } catch (error) {
      if (get().currentProjectId === projectId) {
        set((state) => ({
          recipeRevisionErrorByRecipe: {
            ...state.recipeRevisionErrorByRecipe,
            [id]: "整理方法的修改记录暂时无法加载，请重试。",
          },
        }));
      }
      throw error;
    } finally {
      if (get().currentProjectId === projectId) {
        set((state) => ({
          recipeRevisionLoadingByRecipe: {
            ...state.recipeRevisionLoadingByRecipe,
            [id]: false,
          },
        }));
      }
    }
  },

  restoreRecipeRevision: async (id, revisionId) => {
    const projectId = get().currentProjectId;
    if (!projectId) throw new Error("当前没有可更新的项目");
    const recipe = get().recipes.find((item) => item.id === id);
    if (!recipe?.active_revision_id) {
      throw new Error("这套整理方法的修改记录还没有准备好，请刷新后重试。");
    }
    set((state) => ({
      recipeRevisionRestoringByRecipe: {
        ...state.recipeRevisionRestoringByRecipe,
        [id]: revisionId,
      },
      recipeRevisionErrorByRecipe: {
        ...state.recipeRevisionErrorByRecipe,
        [id]: null,
      },
    }));
    try {
      const response = await api.post(
        `/api/v1/projects/${projectId}/recipes/${id}/revisions/${revisionId}/restore`,
        { expected_active_revision_id: recipe.active_revision_id }
      );
      const restored = response.data.data as SanitationRecipeRevision;
      const [recipesResponse, revisionsResponse] = await Promise.all([
        api.get(`/api/v1/projects/${projectId}/recipes`),
        api.get(`/api/v1/projects/${projectId}/recipes/${id}/revisions`),
      ]);
      if (get().currentProjectId === projectId) {
        set((state) => ({
          recipes: recipesResponse.data.data as SanitationRecipe[],
          recipeRevisionsByRecipe: {
            ...state.recipeRevisionsByRecipe,
            [id]: revisionsResponse.data.data as SanitationRecipeRevision[],
          },
        }));
      }
      return restored;
    } catch (error) {
      const status = responseStatus(error);
      const message =
        status === 409
          ? "整理方法刚刚有了新修改，刷新后再选择要恢复的版本。"
          : status === 404
            ? "这个历史版本已经不可用，请刷新后重新选择。"
            : "这次恢复没有完成，请稍后重试。";
      if (get().currentProjectId === projectId) {
        set((state) => ({
          recipeRevisionErrorByRecipe: {
            ...state.recipeRevisionErrorByRecipe,
            [id]: message,
          },
        }));
      }
      throw new Error(message);
    } finally {
      if (get().currentProjectId === projectId) {
        set((state) => ({
          recipeRevisionRestoringByRecipe: {
            ...state.recipeRevisionRestoringByRecipe,
            [id]: null,
          },
        }));
      }
    }
  },

  previewRecipeTemplate: async (templateId, sourceId) => {
    const projectId = get().currentProjectId;
    if (!projectId) throw new Error("当前没有可整理的项目");
    set({
      recipeTemplateAction: { templateId, kind: "preview" },
      error: null,
    });
    try {
      const response = await api.post(
        `/api/v1/projects/${projectId}/recipe-templates/${templateId}/preview`,
        { source_id: sourceId },
        { timeout: 120000 }
      );
      const preview = response.data.data as SanitationTemplatePreview;
      if (get().currentProjectId === projectId) {
        set((state) => ({
          recipeTemplatePreviewById: {
            ...state.recipeTemplatePreviewById,
            [templateId]: preview,
          },
        }));
      }
      return preview;
    } catch (error) {
      if (get().currentProjectId === projectId) set({ error: messageFrom(error) });
      throw error;
    } finally {
      if (
        get().currentProjectId === projectId &&
        get().recipeTemplateAction?.templateId === templateId
      ) {
        set({ recipeTemplateAction: null });
      }
    }
  },

  bindRecipeTemplate: async (templateId) => {
    const projectId = get().currentProjectId;
    const preview = get().recipeTemplatePreviewById[templateId];
    if (!projectId || !preview) {
      throw new Error("请先查看这套整理方法会带来什么变化");
    }
    set({
      recipeTemplateAction: { templateId, kind: "bind" },
      error: null,
    });
    try {
      await api.post(
        `/api/v1/projects/${projectId}/recipe-templates/${templateId}/bind`,
        {
          source_id: preview.source_id,
          expected_template_active_revision_id:
            preview.template_active_revision_id,
          expected_template_operations_hash: preview.template_operations_hash,
          expected_source_fingerprint: preview.source_fingerprint,
          expected_preview_output_fingerprint:
            preview.preview_output_fingerprint,
          expected_current_working_fingerprint:
            preview.current_working_fingerprint ?? null,
          expected_current_recipe_active_revision_id:
            preview.current_recipe_active_revision_id ?? null,
        },
        { timeout: 120000 }
      );
      if (get().currentProjectId === projectId) {
        set((state) => ({
          recipeTemplatePreviewById: Object.fromEntries(
            Object.entries(state.recipeTemplatePreviewById).filter(
              ([id]) => id !== templateId
            )
          ),
        }));
        await get().refreshCurrent();
      }
    } catch (error) {
      if (get().currentProjectId === projectId) set({ error: messageFrom(error) });
      throw error;
    } finally {
      if (
        get().currentProjectId === projectId &&
        get().recipeTemplateAction?.templateId === templateId
      ) {
        set({ recipeTemplateAction: null });
      }
    }
  },

  previewSourceCleaning: async (sourceId, operations) => {
    const projectId = get().currentProjectId;
    if (!projectId) throw new Error("当前没有可整理的项目");
    set({
      cleaningAction: { sourceId, kind: "preview" },
      error: null,
    });
    try {
      const response = await api.post(
        `/api/v1/projects/${projectId}/sources/${sourceId}/cleaning/preview`,
        { operations },
        { timeout: 120000 }
      );
      const preview = response.data.data as VisualCleaningPreview;
      if (
        get().currentProjectId === projectId &&
        preview.source_id === sourceId
      ) {
        set((state) => ({
          cleaningPreviewBySource: {
            ...state.cleaningPreviewBySource,
            [sourceId]: preview,
          },
        }));
      }
      return preview;
    } catch (error) {
      if (get().currentProjectId === projectId) {
        set({ error: "暂时无法预览整理结果，请重试。" });
      }
      throw error;
    } finally {
      if (
        get().currentProjectId === projectId &&
        get().cleaningAction?.sourceId === sourceId
      ) {
        set({ cleaningAction: null });
      }
    }
  },

  clearSourceCleaningPreview: (sourceId) => {
    set((state) => ({
      cleaningPreviewBySource: Object.fromEntries(
        Object.entries(state.cleaningPreviewBySource).filter(
          ([id]) => id !== sourceId
        )
      ),
    }));
  },

  applySourceCleaning: async (sourceId, operations) => {
    const projectId = get().currentProjectId;
    const preview = get().cleaningPreviewBySource[sourceId];
    if (!projectId || !preview) {
      throw new Error("请先预览整理后的变化");
    }
    set({
      cleaningAction: { sourceId, kind: "apply" },
      error: null,
    });
    try {
      let result: VisualCleaningApplyResult;
      try {
        const response = await api.post(
          `/api/v1/projects/${projectId}/sources/${sourceId}/cleaning/apply`,
          {
            operations,
            expected_operations_hash: preview.operations_hash,
            expected_source_fingerprint: preview.source_fingerprint,
            expected_preview_output_fingerprint:
              preview.preview_output_fingerprint,
            expected_current_working_fingerprint:
              preview.current_working_fingerprint ?? null,
            expected_current_recipe_active_revision_id:
              preview.current_recipe_active_revision_id ?? null,
          },
          { timeout: 120000 }
        );
        result = response.data.data as VisualCleaningApplyResult;
      } catch (error) {
        if (get().currentProjectId === projectId) {
          set({
            error:
              responseStatus(error) === 409 || responseStatus(error) === 422
                ? "数据刚刚发生了变化，请重新预览后再应用。"
                : "暂时无法应用这次整理，请重试。",
          });
        }
        throw error;
      }

      if (get().currentProjectId === projectId) {
        get().clearSourceCleaningPreview(sourceId);
        try {
          await get().refreshCurrent();
        } catch {
          // The mutation is already committed. A follow-up refresh is useful
          // but must never turn a successful apply into a failed apply.
        }
        if (get().currentProjectId === projectId) set({ error: null });
      }
      return result;
    } finally {
      if (
        get().currentProjectId === projectId &&
        get().cleaningAction?.sourceId === sourceId
      ) {
        set({ cleaningAction: null });
      }
    }
  },

  loadKnowledgeRevisions: async (id) => {
    const projectId = get().currentProjectId;
    if (!projectId) throw new Error("当前没有可查看的项目");
    const cached = get().knowledgeRevisionsByEntry[id];
    if (cached) return cached;
    if (get().knowledgeRevisionLoadingByEntry[id]) return [];

    set((state) => ({
      knowledgeRevisionLoadingByEntry: {
        ...state.knowledgeRevisionLoadingByEntry,
        [id]: true,
      },
      knowledgeRevisionErrorByEntry: {
        ...state.knowledgeRevisionErrorByEntry,
        [id]: null,
      },
    }));
    try {
      const response = await api.get(
        `/api/v1/projects/${projectId}/knowledge/${id}/revisions`
      );
      const revisions = response.data.data as SemanticEntryRevision[];
      if (get().currentProjectId === projectId) {
        set((state) => ({
          knowledgeRevisionsByEntry: {
            ...state.knowledgeRevisionsByEntry,
            [id]: revisions,
          },
        }));
      }
      return revisions;
    } catch (error) {
      if (get().currentProjectId === projectId) {
        set((state) => ({
          knowledgeRevisionErrorByEntry: {
            ...state.knowledgeRevisionErrorByEntry,
            [id]: "修改记录暂时无法加载，请重试。",
          },
        }));
      }
      throw error;
    } finally {
      if (get().currentProjectId === projectId) {
        set((state) => ({
          knowledgeRevisionLoadingByEntry: {
            ...state.knowledgeRevisionLoadingByEntry,
            [id]: false,
          },
        }));
      }
    }
  },

  restoreKnowledgeRevision: async (id, revisionId) => {
    const projectId = get().currentProjectId;
    if (!projectId) throw new Error("当前没有可更新的项目");
    const entry = get().knowledge.find((item) => item.id === id);
    const expectedActiveRevisionId = entry?.active_revision_id;
    if (!expectedActiveRevisionId) {
      const message = "这条理解仍在准备修改记录，请刷新后再恢复。";
      set((state) => ({
        knowledgeRevisionErrorByEntry: {
          ...state.knowledgeRevisionErrorByEntry,
          [id]: message,
        },
      }));
      throw new Error(message);
    }

    set((state) => ({
      knowledgeRevisionRestoringByEntry: {
        ...state.knowledgeRevisionRestoringByEntry,
        [id]: revisionId,
      },
      knowledgeRevisionErrorByEntry: {
        ...state.knowledgeRevisionErrorByEntry,
        [id]: null,
      },
    }));
    try {
      const response = await api.post(
        `/api/v1/projects/${projectId}/knowledge/${id}/revisions/${revisionId}/restore`,
        { expected_active_revision_id: expectedActiveRevisionId }
      );
      const restored = response.data.data as SemanticEntry;
      const refreshed = await fetchKnowledgeRestoreState(projectId, id, {
        includeEntry: false,
      });
      if (get().currentProjectId === projectId) {
        set((state) => {
          const previous = state.knowledge.find((item) => item.id === id);
          const before = semanticCountContribution(previous);
          const after = semanticCountContribution(restored);
          return {
            knowledge:
              refreshed.preview?.items ||
              state.knowledge.map((item) => (item.id === id ? restored : item)),
            knowledgeTotal:
              refreshed.preview?.summary.active_total ??
              state.knowledgeTotal + after.total - before.total,
            pendingKnowledgeCount:
              refreshed.preview?.summary.pending_total ??
              state.pendingKnowledgeCount + after.pending - before.pending,
            relationshipKnowledgeCount:
              refreshed.preview?.summary.relationship_total ??
              state.relationshipKnowledgeCount + after.relationship - before.relationship,
            knowledgeRevisionsByEntry: refreshed.revisions
              ? { ...state.knowledgeRevisionsByEntry, [id]: refreshed.revisions }
              : state.knowledgeRevisionsByEntry,
            knowledgeRevisionErrorByEntry: {
              ...state.knowledgeRevisionErrorByEntry,
              [id]: null,
            },
            suggestedQuestionsRevisionByProject: {
              ...state.suggestedQuestionsRevisionByProject,
              [projectId]: (state.suggestedQuestionsRevisionByProject[projectId] || 0) + 1,
            },
          };
        });
      }
      return restored;
    } catch (error) {
      const status = responseStatus(error);
      const refreshed =
        status === 409 || status === 404
          ? await fetchKnowledgeRestoreState(projectId, id, { includeEntry: true })
          : { preview: null, revisions: null, entry: null };
      const refreshCompleted = Boolean(
        (refreshed.preview || refreshed.entry) && refreshed.revisions
      );
      const message =
        status === 409
          ? refreshCompleted
            ? "这条理解刚刚有了新修改，已刷新最新版本；请确认后再恢复。"
            : "这条理解刚刚有了新修改，请刷新后再尝试恢复。"
          : status === 404
            ? refreshCompleted
              ? "这个历史版本已不可用，已刷新修改记录，请重新选择。"
              : "这个历史版本已不可用，请刷新后重新选择。"
            : "历史版本暂时无法恢复，请稍后重试。";
      if (get().currentProjectId === projectId) {
        set((state) => {
          const fallbackKnowledge = refreshed.entry
            ? state.knowledge.map((item) =>
                item.id === id ? refreshed.entry as SemanticEntry : item
              )
            : state.knowledge;
          return {
            knowledge: refreshed.preview?.items || fallbackKnowledge,
            knowledgeTotal:
              refreshed.preview?.summary.active_total ?? state.knowledgeTotal,
            pendingKnowledgeCount:
              refreshed.preview?.summary.pending_total ?? state.pendingKnowledgeCount,
            relationshipKnowledgeCount:
              refreshed.preview?.summary.relationship_total ??
              state.relationshipKnowledgeCount,
            knowledgeRevisionsByEntry: refreshed.revisions
              ? { ...state.knowledgeRevisionsByEntry, [id]: refreshed.revisions }
              : state.knowledgeRevisionsByEntry,
            knowledgeRevisionErrorByEntry: {
              ...state.knowledgeRevisionErrorByEntry,
              [id]: message,
            },
          };
        });
      }
      throw new Error(message);
    } finally {
      if (get().currentProjectId === projectId) {
        set((state) => ({
          knowledgeRevisionRestoringByEntry: {
            ...state.knowledgeRevisionRestoringByEntry,
            [id]: null,
          },
        }));
      }
    }
  },

  updateKnowledge: async (id, changes) => {
    const projectId = get().currentProjectId;
    if (!projectId) throw new Error("当前没有可更新的项目");
    const activeRevisionId = get().knowledge.find((item) => item.id === id)?.active_revision_id;
    set({ isUpdatingKnowledge: true, error: null });
    try {
      const response = await api.put(`/api/v1/projects/${projectId}/knowledge/${id}`, {
        ...changes,
        ...(activeRevisionId ? { expected_active_revision_id: activeRevisionId } : {}),
      });
      const entry = response.data.data as SemanticEntry;
      set((state) => {
        if (state.currentProjectId !== projectId) {
          return {
            suggestedQuestionsRevisionByProject: {
              ...state.suggestedQuestionsRevisionByProject,
              [projectId]:
                (state.suggestedQuestionsRevisionByProject[projectId] || 0) + 1,
            },
          };
        }
        const previous = state.knowledge.find((item) => item.id === id);
        const before = semanticCountContribution(previous);
        const after = semanticCountContribution(entry);
        return {
          knowledge: state.knowledge.map((item) => (item.id === id ? entry : item)),
          knowledgeTotal: state.knowledgeTotal + after.total - before.total,
          pendingKnowledgeCount:
            state.pendingKnowledgeCount + after.pending - before.pending,
          relationshipKnowledgeCount:
            state.relationshipKnowledgeCount + after.relationship - before.relationship,
          knowledgeRevisionsByEntry: Object.fromEntries(
            Object.entries(state.knowledgeRevisionsByEntry).filter(
              ([entryId]) => entryId !== id
            )
          ),
          suggestedQuestionsRevisionByProject: {
            ...state.suggestedQuestionsRevisionByProject,
            [projectId]:
              (state.suggestedQuestionsRevisionByProject[projectId] || 0) + 1,
          },
        };
      });
      return entry;
    } catch (error) {
      set({ error: messageFrom(error) });
      throw error;
    } finally {
      set({ isUpdatingKnowledge: false });
    }
  },

  createKnowledge: async (entry) => {
    const projectId = get().currentProjectId;
    if (!projectId) throw new Error("当前没有可更新的项目");
    set({ isUpdatingKnowledge: true, error: null });
    try {
      const response = await api.post(`/api/v1/projects/${projectId}/knowledge`, entry);
      const created = response.data.data as SemanticEntry;
      set((state) => {
        if (state.currentProjectId !== projectId) {
          return {
            suggestedQuestionsRevisionByProject: {
              ...state.suggestedQuestionsRevisionByProject,
              [projectId]:
                (state.suggestedQuestionsRevisionByProject[projectId] || 0) + 1,
            },
          };
        }
        const previous = state.knowledge.find((item) => item.id === created.id);
        const before = semanticCountContribution(previous);
        const after = semanticCountContribution(created);
        return {
          knowledge: [
            created,
            ...state.knowledge.filter((item) => item.id !== created.id),
          ].slice(0, KNOWLEDGE_PREVIEW_LIMIT),
          knowledgeTotal: state.knowledgeTotal + after.total - before.total,
          pendingKnowledgeCount:
            state.pendingKnowledgeCount + after.pending - before.pending,
          relationshipKnowledgeCount:
            state.relationshipKnowledgeCount + after.relationship - before.relationship,
          suggestedQuestionsRevisionByProject: {
            ...state.suggestedQuestionsRevisionByProject,
            [projectId]:
              (state.suggestedQuestionsRevisionByProject[projectId] || 0) + 1,
          },
        };
      });
      return created;
    } catch (error) {
      set({ error: messageFrom(error) });
      throw error;
    } finally {
      set({ isUpdatingKnowledge: false });
    }
  },

  uploadFile: async (file) => {
    const projectId = get().currentProjectId;
    if (!projectId) return;
    set({ isUploading: true, error: null });
    try {
      const form = new FormData();
      form.append("file", file);
      const uploaded = await api.post(
        `/api/v1/projects/${projectId}/sources/files`,
        form,
        { headers: { "Content-Type": "multipart/form-data" }, timeout: 120000 }
      );
      const source = uploaded.data.data as ProjectDataSource;
      await api.post(
        `/api/v1/projects/${projectId}/sources/${source.id}/preflight`,
        undefined,
        { timeout: 120000 }
      );
      await get().refreshCurrent();
    } catch (error) {
      const message = messageFrom(error);
      if (get().currentProjectId === projectId) await get().refreshCurrent();
      if (get().currentProjectId === projectId) set({ error: message });
    } finally {
      set({ isUploading: false });
    }
  },

  attachConnection: async (connectionId, name) => {
    const projectId = get().currentProjectId;
    if (!projectId) return;
    set({ isUploading: true, error: null });
    try {
      const attached = await api.post(
        `/api/v1/projects/${projectId}/sources/connections`,
        { connection_id: connectionId, name }
      );
      const source = attached.data.data as ProjectDataSource;
      await api.post(`/api/v1/projects/${projectId}/sources/${source.id}/preflight`);
      await get().refreshCurrent();
    } catch (error) {
      const message = messageFrom(error);
      if (get().currentProjectId === projectId) await get().refreshCurrent();
      if (get().currentProjectId === projectId) set({ error: message });
    } finally {
      set({ isUploading: false });
    }
  },

  profileSource: async (sourceId) => {
    const projectId = get().currentProjectId;
    if (!projectId) return;
    set({ sourceAction: { sourceId, kind: "profile" }, error: null });
    try {
      await api.post(
        `/api/v1/projects/${projectId}/sources/${sourceId}/preflight`,
        undefined,
        { timeout: 120000 }
      );
      await get().refreshCurrent();
    } catch (error) {
      const message = messageFrom(error);
      if (get().currentProjectId === projectId) await get().refreshCurrent();
      if (get().currentProjectId === projectId) set({ error: message });
      throw error;
    } finally {
      set({ sourceAction: null });
    }
  },

  reorganizeSource: async (sourceId) => {
    const projectId = get().currentProjectId;
    if (!projectId) throw new Error("当前没有可整理的项目");
    set({ sourceAction: { sourceId, kind: "reorganize" }, error: null });
    try {
      const recipesResponse = await api.get(`/api/v1/projects/${projectId}/recipes`);
      const recipe = (recipesResponse.data.data as Array<{ id: string; data_source_id: string }>).find(
        (item) => item.data_source_id === sourceId
      );
      if (recipe) {
        await api.post(
          `/api/v1/projects/${projectId}/recipes/${recipe.id}/reapply`,
          undefined,
          { timeout: 120000 }
        );
      } else {
        await api.post(
          `/api/v1/projects/${projectId}/sources/${sourceId}/preflight`,
          undefined,
          { timeout: 120000 }
        );
      }
      if (get().currentProjectId === projectId) await get().refreshCurrent();
    } catch (error) {
      if (get().currentProjectId === projectId) set({ error: messageFrom(error) });
      throw error;
    } finally {
      if (
        get().currentProjectId === projectId &&
        get().sourceAction?.sourceId === sourceId
      ) {
        set({ sourceAction: null });
      }
    }
  },

  acceptReplacement: async (sourceId) => {
    const projectId = get().currentProjectId;
    if (!projectId) throw new Error("当前没有可处理的项目");
    set({ sourceAction: { sourceId, kind: "accept_replacement" }, error: null });
    try {
      const response = await api.post(
        `/api/v1/projects/${projectId}/sources/${sourceId}/accept-replacement`
      );
      const accepted = response.data?.data as ProjectDataSource | undefined;
      if (
        get().currentProjectId === projectId &&
        accepted?.id === sourceId
      ) {
        set((state) => ({
          sources: state.sources.map((source) =>
            source.id === sourceId ? accepted : source
          ),
          preflightReports: state.preflightReports.map((report) =>
            report.data_source_id === sourceId
              ? {
                  ...report,
                  status: accepted.status,
                  summary:
                    accepted.profile_data.summary ||
                    "这版数据已确认启用，上个可信版本保留在历史中",
                  source_snapshot: {
                    ...report.source_snapshot,
                    replacement: {
                      status: "accepted",
                      active_source_id: sourceId,
                    },
                  },
                }
              : report
          ),
        }));
      }
      if (get().currentProjectId === projectId) await get().refreshCurrent();
    } catch (error) {
      if (get().currentProjectId === projectId) set({ error: messageFrom(error) });
      throw error;
    } finally {
      if (
        get().currentProjectId === projectId &&
        get().sourceAction?.sourceId === sourceId
      ) {
        set({ sourceAction: null });
      }
    }
  },

  keepTrustedSource: async (sourceId) => {
    const projectId = get().currentProjectId;
    if (!projectId) throw new Error("当前没有可处理的项目");
    set({ sourceAction: { sourceId, kind: "keep_trusted" }, error: null });
    try {
      const recipesResponse = await api.get(`/api/v1/projects/${projectId}/recipes`);
      const recipe = (recipesResponse.data.data as Array<{ id: string; data_source_id: string }>).find(
        (item) => item.data_source_id === sourceId
      );
      if (!recipe) throw new Error("没有可撤销的本次整理记录");
      await api.post(`/api/v1/projects/${projectId}/recipes/${recipe.id}/undo`);
      if (get().currentProjectId === projectId) await get().refreshCurrent();
    } catch (error) {
      if (get().currentProjectId === projectId) set({ error: messageFrom(error) });
      throw error;
    } finally {
      if (
        get().currentProjectId === projectId &&
        get().sourceAction?.sourceId === sourceId
      ) {
        set({ sourceAction: null });
      }
    }
  },

  removeSource: async (sourceId) => {
    const projectId = get().currentProjectId;
    if (!projectId) throw new Error("当前没有可处理的项目");
    set({ sourceAction: { sourceId, kind: "remove" }, error: null });
    try {
      await api.delete(`/api/v1/projects/${projectId}/sources/${sourceId}`);
      if (get().currentProjectId === projectId) await get().refreshCurrent();
    } catch (error) {
      if (get().currentProjectId === projectId) set({ error: messageFrom(error) });
      throw error;
    } finally {
      if (
        get().currentProjectId === projectId &&
        get().sourceAction?.sourceId === sourceId
      ) {
        set({ sourceAction: null });
      }
    }
  },
}));
