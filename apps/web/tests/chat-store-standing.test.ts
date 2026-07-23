import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  stream: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  api: { get: mocks.get, post: mocks.post },
  createSecureEventStream: mocks.stream,
}));

import {
  CONVERSATION_CONTINUITY_STORAGE_KEY,
  forgetConversationForProject,
  rememberConversationForProject,
  storedConversationIdForProject,
  useChatStore,
} from "@/lib/stores/chat";

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
}

describe("standing analysis resume", () => {
  beforeEach(() => {
    mocks.stream.mockReset();
    mocks.get.mockReset();
    mocks.post.mockReset();
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.getItem).mockReturnValue(null);
    vi.mocked(localStorage.setItem).mockReset();
    vi.mocked(localStorage.removeItem).mockReset();
    useChatStore.setState({
      messages: [],
      currentConversationId: "old-conversation",
      currentConversationMeta: null,
      isLoading: false,
      isConversationLoading: false,
      conversationLoadError: null,
      abortController: null,
      activeStreamId: null,
      stopRequestedStreamId: null,
      lastConnectionId: null,
      lastModelId: null,
      lastContextRounds: null,
      lastProjectId: null,
      lastLanguage: null,
      pendingAnalysisSettlements: [],
    });
  });

  it("keeps one recoverable conversation pointer per project", () => {
    const storage = memoryStorage();

    rememberConversationForProject("project-A", "conversation-A", storage);
    rememberConversationForProject("project-B", "conversation-B", storage);

    expect(storedConversationIdForProject("project-A", storage)).toBe(
      "conversation-A"
    );
    expect(storedConversationIdForProject("project-B", storage)).toBe(
      "conversation-B"
    );

    forgetConversationForProject("project-A", storage);
    expect(storedConversationIdForProject("project-A", storage)).toBeNull();
    expect(storedConversationIdForProject("project-B", storage)).toBe(
      "conversation-B"
    );
  });

  it("does not let malformed continuity storage escape its project boundary", () => {
    const storage = memoryStorage();
    storage.setItem(CONVERSATION_CONTINUITY_STORAGE_KEY, "not-json");

    expect(storedConversationIdForProject("project-A", storage)).toBeNull();
    rememberConversationForProject("project-A", "conversation/unsafe", storage);
    expect(storedConversationIdForProject("project-A", storage)).toBeNull();
  });

  it("retains project pointers for navigation but forgets only the explicit new investigation", () => {
    vi.mocked(localStorage.getItem).mockReturnValue(
      JSON.stringify({
        version: 1,
        conversations: {
          "project-A": "conversation-A",
          "project-B": "conversation-B",
        },
      })
    );
    useChatStore.setState({
      currentConversationId: "conversation-A",
      lastProjectId: "project-A",
    });

    useChatStore.getState().clearConversation({ forget: false });
    expect(localStorage.setItem).not.toHaveBeenCalled();
    expect(localStorage.removeItem).not.toHaveBeenCalled();

    useChatStore.getState().clearConversation({
      forget: true,
      projectId: "project-A",
    });
    expect(localStorage.setItem).toHaveBeenCalledWith(
      CONVERSATION_CONTINUITY_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        conversations: { "project-B": "conversation-B" },
      })
    );
  });

  it("reuses a restored conversation for an ordinary follow-up", async () => {
    mocks.stream.mockImplementation(() =>
      (async function* () {
        yield {
          type: "done",
          data: { conversation_id: "conversation-1", message_id: "message-2" },
        };
      })()
    );
    useChatStore.setState({
      currentConversationId: "conversation-1",
      lastProjectId: "project-1",
      messages: [{ role: "user", content: "先看本月收入" }],
    });

    await useChatStore
      .getState()
      .sendMessage("继续比较上月", null, "model-1", 5, "zh", "project-1");

    expect(mocks.stream).toHaveBeenCalledWith(
      "/api/v1/chat/stream",
      expect.objectContaining({
        conversation_id: "conversation-1",
        query: "继续比较上月",
      }),
      expect.any(AbortSignal)
    );
  });

  it("uses the prepared conversation instead of the conversation currently on screen", async () => {
    mocks.stream.mockImplementation(() =>
      (async function* () {
        yield {
          type: "done",
          data: { conversation_id: "standing-conversation", message_id: "message-1" },
        };
      })()
    );

    await useChatStore.getState().resumePreparedRun(
      {
        query: "重新核对门店收入变化",
        projectId: "project-1",
        runId: "run-1",
        conversationId: "standing-conversation",
      },
      "model-1",
      5,
      "zh"
    );

    expect(mocks.stream).toHaveBeenCalledWith(
      "/api/v1/chat/stream",
      expect.objectContaining({
        conversation_id: "standing-conversation",
        resume_run_id: "run-1",
        project_id: "project-1",
      }),
      expect.any(AbortSignal)
    );
    expect(useChatStore.getState().currentConversationId).toBe("standing-conversation");
    expect(useChatStore.getState().isLoading).toBe(false);
  });

  it("rejects a second investigation while the first stream is active", async () => {
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    mocks.stream.mockImplementation(() =>
      (async function* () {
        await pending;
        yield {
          type: "done",
          data: { conversation_id: "conversation-1", message_id: "message-1" },
        };
      })()
    );

    const first = useChatStore.getState().sendMessage("第一项调查", null, "model-1");

    await expect(
      useChatStore.getState().sendMessage("第二项调查", null, "model-1")
    ).rejects.toThrow("已有一项调查正在进行");
    expect(mocks.stream).toHaveBeenCalledTimes(1);
    expect(useChatStore.getState().messages.filter((message) => message.role === "user"))
      .toEqual([{ role: "user", content: "第一项调查" }]);

    release();
    await first;
  });

  it("treats an active stream id as busy even if the loading flag is stale", async () => {
    useChatStore.setState({ isLoading: false, activeStreamId: "stream-still-active" });

    await expect(useChatStore.getState().sendMessage("不要并发开启"))
      .rejects.toThrow("已有一项调查正在进行");
    expect(mocks.stream).not.toHaveBeenCalled();
    expect(useChatStore.getState().messages).toEqual([]);
  });

  it("keeps the homepage busy until a stop reaches a terminal event", async () => {
    let releaseStream!: () => void;
    const streamGate = new Promise<void>((resolve) => {
      releaseStream = resolve;
    });
    mocks.post.mockResolvedValue({ data: { data: { stopped: true } } });
    mocks.stream.mockImplementation(() =>
      (async function* () {
        await streamGate;
        yield {
          type: "error",
          data: {
            code: "CANCELLED",
            message: "分析已停止",
            error_category: "cancelled",
            analysis_state: "needs_attention",
            conversation_id: "active-conversation",
          },
        };
      })()
    );
    useChatStore.setState({
      currentConversationId: "active-conversation",
      lastProjectId: "project-1",
    });

    const investigation = useChatStore
      .getState()
      .sendMessage("检查订单变化", null, "model-1", 5, "zh", "project-1");
    const activeStreamId = useChatStore.getState().activeStreamId;
    expect(activeStreamId).toBeTruthy();

    useChatStore.getState().stopGeneration();

    expect(mocks.post).toHaveBeenCalledWith("/api/v1/chat/stop", {
      conversation_id: "active-conversation",
      client_stream_id: activeStreamId,
    });
    expect(mocks.stream).toHaveBeenCalledWith(
      "/api/v1/chat/stream",
      expect.objectContaining({ client_stream_id: activeStreamId }),
      expect.any(AbortSignal)
    );
    expect(useChatStore.getState()).toMatchObject({
      isLoading: true,
      activeStreamId,
      stopRequestedStreamId: activeStreamId,
      pendingAnalysisSettlements: [],
    });

    releaseStream();
    await investigation;

    expect(useChatStore.getState()).toMatchObject({
      isLoading: false,
      activeStreamId: null,
      stopRequestedStreamId: null,
    });
    expect(useChatStore.getState().pendingAnalysisSettlements).toEqual([
      expect.objectContaining({ outcome: "stopped" }),
    ]);
  });

  it("lets a completion that wins the stop race remain completed", async () => {
    let releaseStream!: () => void;
    const streamGate = new Promise<void>((resolve) => {
      releaseStream = resolve;
    });
    mocks.post.mockResolvedValue({ data: { data: { stopped: true } } });
    mocks.stream.mockImplementation(() =>
      (async function* () {
        await streamGate;
        yield {
          type: "done",
          data: {
            conversation_id: "active-conversation",
            message_id: "message-1",
          },
        };
      })()
    );
    useChatStore.setState({
      currentConversationId: "active-conversation",
      lastProjectId: "project-1",
    });

    const investigation = useChatStore
      .getState()
      .sendMessage("检查订单变化", null, "model-1", 5, "zh", "project-1");
    useChatStore.getState().stopGeneration();
    releaseStream();
    await investigation;

    expect(useChatStore.getState().pendingAnalysisSettlements).toEqual([
      expect.objectContaining({ outcome: "completed" }),
    ]);
    expect(useChatStore.getState().stopRequestedStreamId).toBeNull();
  });

  it("does not let a late stop response from an old stream abort the new stream", async () => {
    vi.useFakeTimers();
    let releaseFirst!: () => void;
    let releaseSecond!: () => void;
    let resolveOldStop!: (value: { data: { data: { stopped: boolean } } }) => void;
    const firstGate = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });
    const secondGate = new Promise<void>((resolve) => {
      releaseSecond = resolve;
    });
    const oldStop = new Promise<{ data: { data: { stopped: boolean } } }>(
      (resolve) => {
        resolveOldStop = resolve;
      }
    );
    mocks.post.mockReturnValue(oldStop);
    mocks.stream
      .mockImplementationOnce(() =>
        (async function* () {
          await firstGate;
          yield {
            type: "done",
            data: {
              conversation_id: "active-conversation",
              message_id: "message-a",
            },
          };
        })()
      )
      .mockImplementationOnce(() =>
        (async function* () {
          await secondGate;
          yield {
            type: "done",
            data: {
              conversation_id: "active-conversation",
              message_id: "message-b",
            },
          };
        })()
      );
    useChatStore.setState({
      currentConversationId: "active-conversation",
      lastProjectId: "project-1",
    });

    const first = useChatStore
      .getState()
      .sendMessage("第一项调查", null, "model-1", 5, "zh", "project-1");
    const firstStreamId = useChatStore.getState().activeStreamId;
    useChatStore.getState().stopGeneration();
    releaseFirst();
    await first;

    const second = useChatStore
      .getState()
      .sendMessage("第二项调查", null, "model-1", 5, "zh", "project-1");
    const secondStreamId = useChatStore.getState().activeStreamId;
    const secondController = useChatStore.getState().abortController;
    expect(secondStreamId).toBeTruthy();
    expect(secondStreamId).not.toBe(firstStreamId);
    expect(secondController).not.toBeNull();
    const abortSecond = vi.spyOn(secondController!, "abort");

    try {
      resolveOldStop({ data: { data: { stopped: true } } });
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(3_000);

      expect(useChatStore.getState().activeStreamId).toBe(secondStreamId);
      expect(useChatStore.getState().isLoading).toBe(true);
      expect(abortSecond).not.toHaveBeenCalled();
    } finally {
      releaseSecond();
      await second;
      vi.useRealTimers();
    }
  });

  it("does not replace or abort the active report when history is clicked", () => {
    const abort = vi.fn();
    useChatStore.setState({
      currentConversationId: "active-conversation",
      isLoading: true,
      activeStreamId: "active-stream",
      abortController: { abort } as unknown as AbortController,
      messages: [{ role: "user", content: "正在调查" }],
    });

    useChatStore.getState().setCurrentConversation("history-conversation");

    expect(useChatStore.getState().currentConversationId).toBe("active-conversation");
    expect(useChatStore.getState().messages).toEqual([
      { role: "user", content: "正在调查" },
    ]);
    expect(abort).not.toHaveBeenCalled();
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.get).not.toHaveBeenCalled();
  });

  it("passes a correction id through when rerunning a corrected investigation", async () => {
    mocks.stream.mockImplementation(() =>
      (async function* () {
        yield {
          type: "done",
          data: { conversation_id: "conversation-1", message_id: "message-1" },
        };
      })()
    );

    await useChatStore.getState().sendMessage(
      "按修正后的口径重跑",
      null,
      "model-1",
      5,
      "zh",
      "project-1",
      null,
      null,
      null,
      "correction-1"
    );

    expect(mocks.stream).toHaveBeenCalledWith(
      "/api/v1/chat/stream",
      expect.objectContaining({ correction_id: "correction-1" }),
      expect.any(AbortSignal)
    );
    expect(useChatStore.getState().pendingAnalysisSettlements).toEqual([
      expect.objectContaining({
        projectId: "project-1",
        outcome: "completed",
      }),
    ]);
  });

  it("posts every selected semantic revision without appending identities to the visible query", async () => {
    mocks.stream.mockImplementation(() =>
      (async function* () {
        yield {
          type: "done",
          data: { conversation_id: "conversation-1", message_id: "message-1" },
        };
      })()
    );
    const selection = Array.from({ length: 25 }, (_, index) => ({
      entry_id: `entry-${index}`,
      expected_active_revision_id: `revision-${index}`,
    }));

    await useChatStore.getState().sendMessage(
      "逐条验证所选关联",
      null,
      "model-1",
      5,
      "zh",
      "project-1",
      null,
      null,
      null,
      null,
      selection
    );

    expect(mocks.stream).toHaveBeenCalledWith(
      "/api/v1/chat/stream",
      expect.objectContaining({
        query: "逐条验证所选关联",
        semantic_validation_selection: selection,
      }),
      expect.any(AbortSignal)
    );
    expect(
      useChatStore.getState().messages.find((message) => message.role === "user")
        ?.content
    ).toBe("逐条验证所选关联");
    expect(
      useChatStore.getState().messages.find((message) => message.role === "assistant")
        ?.semanticValidationSelection
    ).toEqual(selection);
  });

  it("keeps every selected revision when a client failure is retried", async () => {
    const selection = Array.from({ length: 25 }, (_, index) => ({
      entry_id: `entry-${index}`,
      expected_active_revision_id: `revision-${index}`,
    }));
    mocks.stream
      .mockImplementationOnce(() =>
        (async function* () {
          throw new Error("connection interrupted");
        })()
      )
      .mockImplementationOnce(() =>
        (async function* () {
          yield {
            type: "done",
            data: { conversation_id: "conversation-2", message_id: "message-2" },
          };
        })()
      );

    await useChatStore.getState().sendMessage(
      "验证所选关联",
      null,
      "model-1",
      5,
      "zh",
      "project-1",
      null,
      null,
      null,
      null,
      selection
    );

    const failedIndex = useChatStore
      .getState()
      .messages.findIndex((message) => message.role === "assistant");
    expect(failedIndex).toBeGreaterThanOrEqual(0);
    expect(
      useChatStore.getState().messages[failedIndex].semanticValidationSelection
    ).toEqual(selection);

    await useChatStore.getState().retryMessage(failedIndex, "zh");

    expect(mocks.stream).toHaveBeenLastCalledWith(
      "/api/v1/chat/stream",
      expect.objectContaining({
        query: "验证所选关联",
        project_id: "project-1",
        semantic_validation_selection: selection,
      }),
      expect.any(AbortSignal)
    );
  });

  it("publishes one failed settlement so project understanding can refresh", async () => {
    mocks.stream.mockImplementation(() =>
      (async function* () {
        yield {
          type: "error",
          data: {
            code: "EXECUTION_FAILED",
            message: "执行失败",
            project_id: "project-from-runtime",
            analysis_state: "needs_attention",
          },
        };
      })()
    );

    await useChatStore.getState().sendMessage(
      "检查异常",
      null,
      "model-1",
      5,
      "zh",
      "project-1"
    );

    const settlements = useChatStore.getState().pendingAnalysisSettlements;
    expect(settlements).toEqual([
      expect.objectContaining({
        projectId: "project-from-runtime",
        outcome: "failed",
      }),
    ]);

    useChatStore.getState().acknowledgeAnalysisSettlement(settlements[0].id);
    expect(useChatStore.getState().pendingAnalysisSettlements).toEqual([]);
  });

  it("replays the preserved question with an explicitly chosen replacement service", async () => {
    mocks.stream.mockImplementation(() =>
      (async function* () {
        yield {
          type: "done",
          data: { conversation_id: "replacement-conversation", message_id: "message-2" },
        };
      })()
    );
    useChatStore.setState({
      currentConversationId: "expired-conversation",
      lastProjectId: "project-1",
      lastModelId: "expired-service",
      lastContextRounds: 5,
      messages: [
        { role: "user", content: "检查本月收入" },
        {
          role: "assistant",
          content: "",
          hasError: true,
          errorCode: "MODEL_AUTH_ERROR",
          errorCategory: "auth",
          originalQuery: "检查本月收入",
          projectId: "project-1",
          executionContext: { connection_id: "connection-1" },
          semanticValidationSelection: [
            {
              entry_id: "entry-1",
              expected_active_revision_id: "revision-1",
            },
          ],
        },
      ],
    });

    await useChatStore.getState().retryMessageWithModel(1, "healthy-service", "zh");

    expect(mocks.stream).toHaveBeenCalledWith(
      "/api/v1/chat/stream",
      expect.objectContaining({
        query: "检查本月收入",
        model: "healthy-service",
        project_id: "project-1",
        connection_id: "connection-1",
        semantic_validation_selection: [
          {
            entry_id: "entry-1",
            expected_active_revision_id: "revision-1",
          },
        ],
      }),
      expect.any(AbortSignal)
    );
    expect(mocks.stream.mock.calls[0][1]).not.toHaveProperty("resume_run_id");
    expect(mocks.stream.mock.calls[0][1]).not.toHaveProperty("conversation_id");
    expect(useChatStore.getState().currentConversationId).toBe(
      "replacement-conversation"
    );
    expect(useChatStore.getState().lastModelId).toBe("healthy-service");
  });

  it("exposes loading and failure state while restoring conversation history", async () => {
    let rejectLoad!: (error: Error) => void;
    mocks.get.mockReturnValue(
      new Promise((_, reject) => {
        rejectLoad = reject;
      })
    );
    useChatStore.setState({ currentConversationId: "conversation-1" });

    const load = useChatStore.getState().loadConversation("conversation-1");
    expect(useChatStore.getState().isConversationLoading).toBe(true);
    expect(useChatStore.getState().conversationLoadError).toBeNull();

    rejectLoad(new Error("network unavailable"));
    await load;

    expect(useChatStore.getState().isConversationLoading).toBe(false);
    expect(useChatStore.getState().conversationLoadError).toContain("无法打开");
  });

  it("restores a conversation and clears its loading error", async () => {
    mocks.get.mockResolvedValue({
      data: {
        data: {
          id: "conversation-1",
          title: "七月复盘",
          model_id: "model-1",
          connection_id: null,
          context_rounds: 5,
          project_id: "project-1",
          status: "active",
          messages: [
            {
              id: "message-1",
              role: "user",
              content: "收入为什么下降？",
              created_at: "2026-07-18T00:00:00Z",
            },
          ],
          created_at: "2026-07-18T00:00:00Z",
          updated_at: "2026-07-18T00:00:00Z",
        },
      },
    });
    useChatStore.setState({
      currentConversationId: "conversation-1",
      conversationLoadError: "旧错误",
    });

    await useChatStore.getState().loadConversation("conversation-1");

    expect(useChatStore.getState().isConversationLoading).toBe(false);
    expect(useChatStore.getState().conversationLoadError).toBeNull();
    expect(useChatStore.getState().messages).toEqual([
      expect.objectContaining({ role: "user", content: "收入为什么下降？" }),
    ]);
    expect(useChatStore.getState().currentConversationMeta?.title).toBe("七月复盘");
  });

  it("rejects a persisted conversation that belongs to another project", async () => {
    mocks.get.mockResolvedValue({
      data: {
        data: {
          id: "conversation-1",
          title: "其他项目的调查",
          project_id: "project-2",
          status: "active",
          messages: [],
          created_at: "2026-07-18T00:00:00Z",
          updated_at: "2026-07-18T00:00:00Z",
        },
      },
    });
    useChatStore.setState({ currentConversationId: "conversation-1" });

    await useChatStore
      .getState()
      .loadConversation("conversation-1", "project-1");

    expect(useChatStore.getState().currentConversationId).toBeNull();
    expect(useChatStore.getState().messages).toEqual([]);
    expect(useChatStore.getState().conversationLoadError).toContain("不属于当前项目");
  });

  it("saves a late confirmation but does not pull the user back from another investigation", async () => {
    let resolveConfirmation!: (value: unknown) => void;
    mocks.post.mockReturnValue(
      new Promise((resolve) => {
        resolveConfirmation = resolve;
      })
    );
    useChatStore.setState({
      currentConversationId: "origin-conversation",
      lastProjectId: "project-1",
      messages: [
        {
          role: "assistant",
          content: "请选择收入口径",
          analysisRunId: "run-1",
          projectId: "project-1",
          originalQuery: "比较门店收入",
        },
      ],
    });

    const confirmation = useChatStore
      .getState()
      .confirmBusinessDefinition("run-1", "revenue_rule", "扣除退款", "zh");
    useChatStore.setState({ currentConversationId: "other-conversation" });
    resolveConfirmation({
      data: {
        data: {
          analysis_run_id: "run-1",
          resume_run_id: "run-1",
          project_id: "project-1",
          conversation_id: "origin-conversation",
          key: "revenue_rule",
          selected_option: "扣除退款",
          ready_to_continue: true,
        },
      },
    });

    await expect(confirmation).rejects.toThrow("你已切换到其他调查");
    expect(mocks.stream).not.toHaveBeenCalled();
    expect(useChatStore.getState().currentConversationId).toBe("other-conversation");
  });
});
