"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import { CircleAlert } from "lucide-react";
import type {
  AnalysisRunSummary,
  AppSettings,
  ConnectionSummary,
  ModelSummary,
  StandingAnalysis,
  StandingPrepareResponse,
  SuggestedQuestionsResponse,
} from "@/lib/types/api";
import { getErrorMessage } from "@/lib/types/api";
import { api } from "@/lib/api/client";
import {
  migratePendingTaskStorage,
  PENDING_TASK_STORAGE_KEY,
} from "@/lib/storage/legacy";
import {
  useChatStore,
  type SemanticValidationSelection,
} from "@/lib/stores/chat";
import { useProjectStore } from "@/lib/stores/project";
import { MessageList } from "./MessageList";
import { InputBar } from "./InputBar";
import { ChatHeader } from "./ChatHeader";
import { DataWorkspacePanel } from "./DataWorkspacePanel";
import { useChatAreaState } from "./useChatAreaState";

interface ChatAreaProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  recentRuns: AnalysisRunSummary[];
  recentRunsLoading?: boolean;
  onOpenReport: (conversationId: string, analysisRunId: string) => void;
  focusAnalysisRunId?: string | null;
  onReportFocused?: () => void;
}

interface PendingTask {
  query: string;
  projectId: string | null;
  validationSelection?: SemanticValidationSelection[];
}

function parsePendingTask(value: unknown): PendingTask | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  if (typeof candidate.query !== "string" || !candidate.query.trim()) return null;
  if (candidate.projectId !== null && typeof candidate.projectId !== "string") return null;

  let validationSelection: SemanticValidationSelection[] | undefined;
  if (candidate.validationSelection !== undefined) {
    if (
      !Array.isArray(candidate.validationSelection) ||
      candidate.validationSelection.length > 100
    ) {
      return null;
    }
    validationSelection = [];
    for (const item of candidate.validationSelection) {
      if (!item || typeof item !== "object") return null;
      const selection = item as Record<string, unknown>;
      if (
        typeof selection.entry_id !== "string" ||
        !selection.entry_id ||
        typeof selection.expected_active_revision_id !== "string" ||
        !selection.expected_active_revision_id
      ) {
        return null;
      }
      validationSelection.push({
        entry_id: selection.entry_id,
        expected_active_revision_id: selection.expected_active_revision_id,
      });
    }
  }
  return {
    query: candidate.query,
    projectId: candidate.projectId as string | null,
    ...(validationSelection ? { validationSelection } : {}),
  };
}

interface RunPromptOptions {
  correctionId?: string;
}

export function ChatArea({
  sidebarOpen: _sidebarOpen,
  onToggleSidebar,
  recentRuns,
  recentRunsLoading = false,
  onOpenReport,
  focusAnalysisRunId,
  onReportFocused,
}: ChatAreaProps) {
  const router = useRouter();
  const locale = useLocale();
  const queryClient = useQueryClient();
  const [dataPanelOpen, setDataPanelOpen] = useState(false);
  const [dataPanelView, setDataPanelView] = useState<"sources" | "understanding">(
    "sources"
  );
  const processingSettlementsRef = useRef(new Set<string>());
  const [pendingTask, setPendingTask] = useState<PendingTask | null>(null);
  const [checkingStandingId, setCheckingStandingId] = useState<string | null>(null);
  const [standingFeedback, setStandingFeedback] = useState<Record<string, string>>({});
  const [analysisServiceSelectorOpen, setAnalysisServiceSelectorOpen] = useState(false);
  const [pendingServiceChangeMessageIndex, setPendingServiceChangeMessageIndex] =
    useState<number | null>(null);

  useEffect(() => {
    router.prefetch("/settings");
  }, [router]);
  const closeDataPanel = () => {
    if (typeof document !== "undefined" && document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
    setDataPanelOpen(false);
  };
  const openDataPanel = useCallback((view: "sources" | "understanding") => {
    setDataPanelView(view);
    setDataPanelOpen(true);
  }, []);
  const {
    messages,
    isLoading,
    activeStreamId,
    isConversationLoading,
    conversationLoadError,
    currentConversationId,
    currentConversationMeta,
    lastModelId,
    sendMessage,
    resumePreparedRun,
    confirmBusinessDefinition,
    stopGeneration,
    retryMessage,
    retryMessageWithModel,
    rerunMessage,
    setCurrentConversation,
    loadConversation,
    pendingAnalysisSettlements,
  } = useChatStore();

  // A parked task belongs to the "new investigation" workspace. Once a
  // conversation is open, sidebar navigation must win over the pending card.
  const pendingTaskVisible = Boolean(pendingTask) && !currentConversationId;

  const {
    projects,
    currentProjectId,
    sources,
    pendingKnowledgeCount,
    suggestedQuestionsRevisionByProject,
    isUploading,
    error: projectError,
    bootstrap,
    renameProject,
    uploadFile,
    refreshCurrent,
  } = useProjectStore();
  const currentProject = projects.find((project) => project.id === currentProjectId);
  const suggestedQuestionsRevision = currentProjectId
    ? suggestedQuestionsRevisionByProject[currentProjectId] || 0
    : 0;
  const readySources = sources.filter((source) =>
    ["ready", "needs_confirmation"].includes(source.status)
  );
  const pendingUnderstandingCount = pendingKnowledgeCount;

  useEffect(() => {
    const settlement = pendingAnalysisSettlements.find(
      (item) => !processingSettlementsRef.current.has(item.id)
    );
    if (!settlement) return;

    processingSettlementsRef.current.add(settlement.id);
    const refreshSettledAnalysis = async () => {
      if (!settlement.projectId) return;
      const refreshes: Promise<unknown>[] = [
        queryClient.invalidateQueries({
          queryKey: ["analysis-corrections", settlement.projectId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["analysis-correction-targets", settlement.projectId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["analysis-correction-target-options", settlement.projectId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["analysis-runs", settlement.projectId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["standing-analyses", settlement.projectId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["suggested-questions", settlement.projectId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["artifacts", settlement.projectId],
        }),
        queryClient.invalidateQueries({ queryKey: ["models"] }),
      ];
      if (useProjectStore.getState().currentProjectId === settlement.projectId) {
        refreshes.unshift(useProjectStore.getState().refreshCurrent());
      }
      await Promise.allSettled(refreshes);
    };

    void refreshSettledAnalysis().finally(() => {
      processingSettlementsRef.current.delete(settlement.id);
      useChatStore.getState().acknowledgeAnalysisSettlement(settlement.id);
    });
  }, [pendingAnalysisSettlements, queryClient]);

  const { data: connections } = useQuery({
    queryKey: ["connections"],
    queryFn: async () => {
      const response = await api.get("/api/v1/config/connections");
      return response.data.data as ConnectionSummary[];
    },
  });

  const { data: models } = useQuery({
    queryKey: ["models"],
    queryFn: async () => {
      const response = await api.get("/api/v1/config/models");
      return response.data.data as ModelSummary[];
    },
  });

  const { data: appSettings } = useQuery({
    queryKey: ["app-settings"],
    queryFn: async () => {
      const response = await api.get("/api/v1/settings");
      return response.data.data as AppSettings;
    },
  });

  const {
    data: standingAnalyses = [],
    isLoading: standingLoading,
    refetch: refetchStanding,
  } = useQuery<StandingAnalysis[]>({
    queryKey: ["standing-analyses", currentProjectId],
    queryFn: async () => {
      const response = await api.get(
        `/api/v1/projects/${currentProjectId}/standing-analyses`
      );
      return response.data.data as StandingAnalysis[];
    },
    enabled: Boolean(currentProjectId),
  });

  const recordedMessageModelId = [...messages]
    .reverse()
    .find((message) => message.executionContext?.model_id)?.executionContext?.model_id;
  const modelSelectionLocked = Boolean(
    currentConversationId || messages.length || isLoading || activeStreamId
  );
  const selectorLocked =
    modelSelectionLocked && pendingServiceChangeMessageIndex === null;
  const lockedModelId =
    currentConversationMeta?.model_id ||
    recordedMessageModelId ||
    (modelSelectionLocked ? lastModelId : null);
  const {
    selectedModelId,
    input,
    modelReady,
    setInput,
    selectModel,
    modelSelectionSaving,
    modelSelectionError,
  } = useChatAreaState(models, appSettings, isLoading, {
    selectionLocked: selectorLocked,
    lockedModelId,
  });
  const executionModelId = selectorLocked
    ? lockedModelId || selectedModelId
    : selectedModelId;

  const handleSelectAnalysisService = async (modelId: string) => {
    selectModel(modelId);
    if (pendingServiceChangeMessageIndex === null) return;
    const messageIndex = pendingServiceChangeMessageIndex;
    setAnalysisServiceSelectorOpen(false);
    const retryPromise = retryMessageWithModel(messageIndex, modelId, locale);
    setPendingServiceChangeMessageIndex(null);
    await retryPromise;
  };

  const sourceSuggestionKey = readySources
    .map((source) => `${source.id}:${source.updated_at}`)
    .join("|");
  const { data: suggestedQuestions, isLoading: suggestionsLoading } =
    useQuery<SuggestedQuestionsResponse>({
      queryKey: [
        "suggested-questions",
        currentProjectId,
        selectedModelId,
        sourceSuggestionKey,
        suggestedQuestionsRevision,
      ],
      queryFn: async () => {
        const response = await api.post(
          `/api/v1/projects/${currentProjectId}/suggested-questions`,
          { model_id: selectedModelId || null },
          { timeout: 20_000 }
        );
        return response.data.data as SuggestedQuestionsResponse;
      },
      enabled: Boolean(currentProjectId && readySources.length),
      staleTime: 5 * 60_000,
      retry: false,
    });

  useEffect(() => {
    if (!currentProjectId) return;
    const stored = migratePendingTaskStorage(sessionStorage);
    if (!stored) {
      setPendingTask(null);
      return;
    }
    try {
      const parsed = parsePendingTask(JSON.parse(stored));
      setPendingTask(
        parsed?.projectId === currentProjectId ? parsed : null
      );
    } catch {
      sessionStorage.removeItem(PENDING_TASK_STORAGE_KEY);
      setPendingTask(null);
    }
  }, [currentProjectId]);

  const effectiveContextRounds = appSettings?.context_rounds || 5;

  const clearPendingTask = () => {
    sessionStorage.removeItem(PENDING_TASK_STORAGE_KEY);
    setPendingTask(null);
  };

  const handleInputSubmit = async (query: string, options?: RunPromptOptions) => {
    if (pendingServiceChangeMessageIndex !== null) {
      setAnalysisServiceSelectorOpen(true);
      return false;
    }
    if (!modelReady || !executionModelId) {
      setAnalysisServiceSelectorOpen(true);
      return false;
    }
    if (pendingTaskVisible) clearPendingTask();
    await sendMessage(
      query,
      null,
      executionModelId,
      effectiveContextRounds,
      locale,
      currentProjectId,
      null,
      null,
      null,
      options?.correctionId
    );
    return true;
  };

  const handleContinuePendingTask = async () => {
    if (!pendingTask || !modelReady || !executionModelId) return;
    const task = pendingTask;
    // Hide the prompt while it runs, but keep the durable copy until the
    // backend has returned a run identity. Provider/configuration failures can
    // happen before a server checkpoint exists, so clearing storage first
    // would silently turn a later retry into an unscoped investigation.
    setPendingTask(null);
    try {
      await sendMessage(
        task.query,
        null,
        executionModelId,
        effectiveContextRounds,
        locale,
        task.projectId,
        null,
        null,
        null,
        null,
        task.validationSelection
      );
    } catch {
      setPendingTask(task);
      return;
    }
    const acceptedMessage = [...useChatStore.getState().messages]
      .reverse()
      .find(
        (message) =>
          message.role === "assistant" && message.originalQuery === task.query
      );
    if (acceptedMessage?.analysisRunId) {
      clearPendingTask();
    } else {
      setPendingTask(task);
    }
  };

  const handleEditPendingTask = () => {
    if (!pendingTask) return;
    setInput(pendingTask.query);
    clearPendingTask();
  };

  const handleChangeAnalysisService = (messageIndex: number) => {
    const failedMessage = messages[messageIndex];
    const preservedQuery = failedMessage?.originalQuery;
    if (preservedQuery) setInput(preservedQuery);
    setPendingServiceChangeMessageIndex(messageIndex);
    setAnalysisServiceSelectorOpen(true);
    void queryClient.invalidateQueries({ queryKey: ["models"] });
  };

  const handleManageAnalysisServices = (messageIndex?: number) => {
    const failedMessage =
      typeof messageIndex === "number" ? messages[messageIndex] : null;
    const preservedQuery = failedMessage?.originalQuery;
    if (preservedQuery) {
      const task: PendingTask = {
        query: preservedQuery,
        projectId: failedMessage?.projectId || currentProjectId,
        ...(failedMessage?.semanticValidationSelection?.length
          ? { validationSelection: failedMessage.semanticValidationSelection }
          : {}),
      };
      sessionStorage.setItem(PENDING_TASK_STORAGE_KEY, JSON.stringify(task));
    }
    router.push("/settings?tab=models");
  };

  const handleConfirmation = async (
    analysisRunId: string,
    key: string,
    selectedOption: string
  ) => {
    await confirmBusinessDefinition(analysisRunId, key, selectedOption, locale);
    await refreshCurrent();
  };

  const handleCheckStanding = async (standing: StandingAnalysis) => {
    if (!currentProjectId || checkingStandingId) return;
    const originProjectId = currentProjectId;
    if (!modelReady || !selectedModelId) {
      setStandingFeedback((current) => ({
        ...current,
        [standing.id]: "分析能力尚未就绪，请先在设置中选择后再检查。",
      }));
      router.push("/settings");
      return;
    }
    if (isLoading) {
      setStandingFeedback((current) => ({
        ...current,
        [standing.id]: "当前调查完成后再检查这项变化。",
      }));
      return;
    }

    setCheckingStandingId(standing.id);
    setStandingFeedback((current) => ({ ...current, [standing.id]: "正在核对最新数据…" }));
    try {
      const response = await api.post(
        `/api/v1/projects/${originProjectId}/standing-analyses/${standing.id}/prepare-run`,
        { trigger: "manual", force: false }
      );
      const prepared = response.data.data as StandingPrepareResponse;
      if (useProjectStore.getState().currentProjectId !== originProjectId) {
        return;
      }
      await refetchStanding();

      if (prepared.outcome === "no_change") {
        setStandingFeedback((current) => ({
          ...current,
          [standing.id]: "数据和口径没有变化，当前结论仍然有效。",
        }));
        return;
      }
      if (prepared.outcome === "paused") {
        setStandingFeedback((current) => ({
          ...current,
          [standing.id]: "这项持续关注已经暂停。",
        }));
        return;
      }
      if (prepared.outcome === "already_completed") {
        setStandingFeedback((current) => ({
          ...current,
          [standing.id]: "这次检查已经完成，最新结果已保存在调查记录中。",
        }));
        return;
      }
      if (prepared.outcome === "already_running") {
        const runsResponse = await api.get(
          `/api/v1/projects/${originProjectId}/analysis-runs`
        );
        if (useProjectStore.getState().currentProjectId !== originProjectId) {
          return;
        }
        const claimedRun = (runsResponse.data.data as AnalysisRunSummary[]).find(
          (run) => run.id === prepared.run_id
        );
        if (claimedRun?.stage !== "prepared") {
          if (prepared.conversation_id) {
            setCurrentConversation(prepared.conversation_id);
          }
          setStandingFeedback((current) => ({
            ...current,
            [standing.id]: "这项变化已经在检查，已打开对应调查。",
          }));
          return;
        }
      }
      if (prepared.outcome === "needs_attention") {
        setStandingFeedback((current) => ({
          ...current,
          [standing.id]: prepared.attention_reason || "需要先处理项目中的数据变化。",
        }));
        return;
      }
      if (!prepared.run_id || !prepared.conversation_id) {
        throw new Error("持续检查缺少可继续的调查记录");
      }
      await resumePreparedRun(
        {
          query: standing.query,
          projectId: originProjectId,
          runId: prepared.run_id,
          conversationId: prepared.conversation_id,
        },
        selectedModelId,
        effectiveContextRounds,
        locale
      );
    } catch (error) {
      setStandingFeedback((current) => ({
        ...current,
        [standing.id]: getErrorMessage(error),
      }));
    } finally {
      setCheckingStandingId(null);
      void refetchStanding();
    }
  };

  const showDockComposer = messages.length > 0 && !pendingTaskVisible;

  const taskComposer = (
    <InputBar
      placement="surface"
      onSubmit={handleInputSubmit}
      onStop={stopGeneration}
      isLoading={isLoading}
      projectName={currentProject?.name}
      dataReady={readySources.length > 0}
      sourceCount={sources.length}
      isUploading={isUploading}
      onOpenData={() => openDataPanel("sources")}
      onUploadFile={(file) => void uploadFile(file)}
      input={input}
      onInputChange={setInput}
      analysisServices={models || []}
      selectedAnalysisServiceId={executionModelId}
      onSelectAnalysisService={handleSelectAnalysisService}
      onManageAnalysisServices={() => handleManageAnalysisServices()}
      analysisServiceLocked={selectorLocked}
      analysisServiceSaving={modelSelectionSaving}
      analysisServiceError={modelSelectionError}
      analysisServiceSelectorOpen={analysisServiceSelectorOpen}
      onAnalysisServiceSelectorOpenChange={setAnalysisServiceSelectorOpen}
    />
  );

  return (
    <div className="flex h-full min-w-0 flex-1 bg-background">
      <main className="flex min-w-0 flex-1 flex-col">
        <ChatHeader
          onToggleSidebar={onToggleSidebar}
          onToggleData={() => openDataPanel("sources")}
          onOpenUnderstanding={() => openDataPanel("understanding")}
          project={currentProject}
          readySources={readySources.length}
          totalSources={sources.length}
          pendingUnderstandingCount={pendingUnderstandingCount}
          onRenameProject={
            currentProject
              ? async (name) => {
                  await renameProject(currentProject.id, name);
                }
              : undefined
          }
        />

        {projectError && (
          <div
            role="status"
            className="flex items-start gap-3 border-b border-warning/30 bg-warning/[0.06] px-5 py-3 text-sm text-foreground"
          >
            <CircleAlert size={17} className="mt-0.5 shrink-0 text-warning" />
            <div>
              <div className="font-semibold">
                {currentProjectId ? "数据来源刷新失败" : "本地工作区尚未连接"}
              </div>
              <div className="mt-0.5 text-xs leading-5 text-muted-foreground">
                {currentProjectId
                  ? `${projectError}。当前项目仍保留，可以重新连接后继续。`
                  : "当前可以先整理任务；读取文件、连接数据库和运行调查，需要打开桌面应用或启动本地工作区。"}
              </div>
            </div>
            <button
              type="button"
              onClick={() => void bootstrap()}
              className="ml-auto shrink-0 border border-warning/40 bg-card px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-warning/10"
            >
              重新连接
            </button>
          </div>
        )}

        <MessageList
          key={currentConversationId || currentProjectId || "workspace"}
          messages={messages}
          isLoading={isLoading}
          conversationLoading={isConversationLoading}
          conversationLoadError={conversationLoadError}
          project={currentProject}
          sources={sources}
          standingAnalyses={standingAnalyses}
          recentRuns={recentRuns}
          suggestedQuestions={suggestedQuestions?.items || []}
          suggestionsLoading={Boolean(readySources.length && suggestionsLoading)}
          emptyComposer={taskComposer}
          activityLoading={standingLoading || recentRunsLoading}
          checkingStandingId={checkingStandingId}
          standingFeedback={standingFeedback}
          modelReady={modelReady}
          pendingTask={pendingTaskVisible ? pendingTask?.query : undefined}
          onRetry={(index) => void retryMessage(index, locale)}
          onRerun={(index) => void rerunMessage(index, locale)}
          onChangeAnalysisService={handleChangeAnalysisService}
          onManageAnalysisServices={handleManageAnalysisServices}
          onOpenSettings={() => router.push("/settings")}
          onOpenData={() => openDataPanel("sources")}
          onOpenUnderstanding={() => openDataPanel("understanding")}
          onUsePrompt={setInput}
          onRunPrompt={(prompt, options) => void handleInputSubmit(prompt, options)}
          onOpenReport={onOpenReport}
          focusAnalysisRunId={focusAnalysisRunId}
          onReportFocused={onReportFocused}
          onRetryConversation={() => {
            if (currentConversationId) void loadConversation(currentConversationId);
          }}
          onCheckStanding={(standing) => void handleCheckStanding(standing)}
          onConfirm={handleConfirmation}
          onContinuePending={() => void handleContinuePendingTask()}
          onEditPending={handleEditPendingTask}
        />

        {showDockComposer && (
          <InputBar
            onSubmit={handleInputSubmit}
            onStop={stopGeneration}
            isLoading={isLoading}
            projectName={currentProject?.name}
            dataReady={readySources.length > 0}
            sourceCount={sources.length}
            isUploading={isUploading}
            onOpenData={() => openDataPanel("sources")}
            onUploadFile={(file) => void uploadFile(file)}
            input={input}
            onInputChange={setInput}
            analysisServices={models || []}
            selectedAnalysisServiceId={executionModelId}
            onSelectAnalysisService={handleSelectAnalysisService}
            onManageAnalysisServices={() => handleManageAnalysisServices()}
            analysisServiceLocked={selectorLocked}
            analysisServiceSaving={modelSelectionSaving}
            analysisServiceError={modelSelectionError}
            analysisServiceSelectorOpen={analysisServiceSelectorOpen}
            onAnalysisServiceSelectorOpenChange={setAnalysisServiceSelectorOpen}
          />
        )}
      </main>
      {dataPanelOpen && (
        <button
          type="button"
          aria-label="关闭数据来源"
          onClick={closeDataPanel}
          className="fixed inset-0 z-30 bg-slate-950/25 md:hidden"
        />
      )}
      <DataWorkspacePanel
        open={dataPanelOpen}
        onClose={closeDataPanel}
        onConfigureConnection={() => router.push("/settings?tab=connections")}
        connections={connections}
        view={dataPanelView}
        onViewChange={setDataPanelView}
      />
    </div>
  );
}
