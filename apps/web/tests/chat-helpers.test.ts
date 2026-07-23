import { describe, expect, it } from "vitest";
import type { ChatMessage } from "@/lib/types/chat";
import {
  applyStreamErrorEvent,
  applyStreamEvent,
  buildPendingAssistantMessage,
  finalizeStreamMessage,
  getInvestigationErrorRecovery,
  mapApiMessage,
  mergeDiagnostics,
} from "@/lib/stores/chat-helpers";

function buildMessages(): ChatMessage[] {
  return [{ role: "user", content: "show sales" }, buildPendingAssistantMessage()];
}

describe("chat helpers", () => {
  it("dedupes diagnostics by attempt, phase, status, and message", () => {
    const diagnostics = mergeDiagnostics(
      [{ attempt: 1, phase: "sql", status: "error", message: "broken" }],
      [
        { attempt: 1, phase: "sql", status: "error", message: "broken" },
        { attempt: 2, phase: "sql", status: "repaired", message: "fixed" },
      ]
    );

    expect(diagnostics).toEqual([
      { attempt: 1, phase: "sql", status: "error", message: "broken" },
      { attempt: 2, phase: "sql", status: "repaired", message: "fixed" },
    ]);
  });

  it("applies progress and result events to the pending assistant message", () => {
    const progressMessages = applyStreamEvent(buildMessages(), {
      type: "progress",
      data: {
        stage: "investigating",
        step: "read_files",
        message: "SQL ready",
        analysis_run_id: "run-a",
        project_id: "project-a",
        analysis_state: "investigating",
        resumable: false,
        execution_context: { connection_name: "Analytics DB" },
        diagnostic_entry: {
          attempt: 1,
          phase: "sql",
          status: "success",
          message: "ok",
        },
      },
    });
    const resultMessages = applyStreamEvent(progressMessages, {
      type: "result",
      data: {
        content: "分析完成",
        sql: "SELECT 1",
        data: [{ value: 1 }],
        rows_count: 1,
        execution_time: 0.25,
        execution_context: { model_id: "model-a" },
        diagnostics: [
          { attempt: 1, phase: "sql", status: "success", message: "ok" },
        ],
        correction_application: {
          correction_id: "correction-a",
          source_run_id: "run-before",
          status: "verified",
          summary: "退款已经从本次收入中排除。",
          checks: ["收入已按修正后的口径重新计算"],
        },
      },
    });

    expect(resultMessages[1]).toMatchObject({
      content: "分析完成",
      sql: "SELECT 1",
      rowsCount: 1,
      executionTime: 0.25,
      isLoading: true,
      status: "正在保存调查结果",
      executionContext: {
        connection_name: "Analytics DB",
        model_id: "model-a",
      },
      analysisRunId: "run-a",
      projectId: "project-a",
      analysisState: "investigating",
      thinkingStage: "read_files",
      correctionApplication: {
        correction_id: "correction-a",
        status: "verified",
      },
    });
    expect(resultMessages[1].diagnostics).toHaveLength(1);
    expect(finalizeStreamMessage(resultMessages)[1]).toMatchObject({
      isLoading: false,
      status: undefined,
    });
  });

  it("routes late events to their own stream instead of overwriting a newer task", () => {
    const messages: ChatMessage[] = [
      { role: "user", content: "old" },
      buildPendingAssistantMessage(undefined, "old-stream"),
      { role: "user", content: "new" },
      buildPendingAssistantMessage(undefined, "new-stream"),
    ];

    const updated = applyStreamEvent(
      messages,
      { type: "progress", data: { message: "old task stopped" } },
      "old-stream"
    );

    expect(updated[1].status).toBe("old task stopped");
    expect(updated[3].status).toBeUndefined();
  });

  it("applies python and visualization payloads incrementally", () => {
    const withVisualization = applyStreamEvent(buildMessages(), {
      type: "visualization",
      data: {
        chart: {
          type: "bar",
          data: [{ name: "A", value: 1 }],
        },
      },
    });
    const withOutput = applyStreamEvent(withVisualization, {
      type: "python_output",
      data: {
        output: "hello",
        stream: "stdout",
      },
    });
    const withImage = applyStreamEvent(withOutput, {
      type: "python_image",
      data: {
        image: "base64-data",
        format: "png",
      },
    });

    expect(withImage[1].visualization?.type).toBe("bar");
    expect(withImage[1].pythonOutput).toBe("hello");
    expect(withImage[1].pythonImages).toEqual(["base64-data"]);
  });

  it("marks the assistant message as failed on SSE error", () => {
    const nextMessages = applyStreamErrorEvent(
      buildMessages(),
      {
        type: "error",
        data: {
          code: "SQL_EXECUTION_FAILED",
          message: "syntax error",
          error_category: "sql",
          failed_stage: "execution",
          diagnostics: [
            {
              phase: "execution",
              status: "error",
              message: "OperationalError: syntax error",
            },
          ],
          execution_context: { connection_name: "Analytics DB" },
        },
      },
      "show sales"
    );

    expect(nextMessages[1]).toMatchObject({
      hasError: true,
      errorMessage: "syntax error",
      errorCode: "SQL_EXECUTION_FAILED",
      errorCategory: "sql",
      failedStage: "execution",
      canRetry: false,
      originalQuery: "show sales",
      executionContext: { connection_name: "Analytics DB" },
      isLoading: false,
    });
    expect(nextMessages[1].diagnostics?.[0].message).toBe(
      "OperationalError: syntax error"
    );
  });

  it("does not retry an invalid credential with the same analysis service", () => {
    const nextMessages = applyStreamErrorEvent(
      buildMessages(),
      {
        type: "error",
        data: {
          code: "MODEL_AUTH_ERROR",
          message: "credential rejected",
          error_category: "model_provider",
          analysis_state: "needs_attention",
        },
      },
      "show sales"
    );

    expect(nextMessages[1]).toMatchObject({
      hasError: true,
      canRetry: false,
      originalQuery: "show sales",
    });
    expect(getInvestigationErrorRecovery("MODEL_AUTH_ERROR", "model_provider")).toBe(
      "change_analysis_service"
    );
    expect(
      getInvestigationErrorRecovery(
        "MODEL_SELECTION_CONFLICT",
        "model_selection_conflict"
      )
    ).toBe("change_analysis_service");
  });

  it("allows one truthful retry for a transient provider failure", () => {
    const nextMessages = applyStreamErrorEvent(
      buildMessages(),
      {
        type: "error",
        data: {
          code: "MODEL_TIMEOUT",
          message: "timed out",
          error_category: "timeout",
          analysis_state: "needs_attention",
        },
      },
      "show sales"
    );

    expect(nextMessages[1]).toMatchObject({
      hasError: true,
      canRetry: true,
      originalQuery: "show sales",
    });
  });

  it("keeps a cancelled run resumable without presenting it as a technical failure", () => {
    const nextMessages = applyStreamErrorEvent(
      buildMessages(),
      {
        type: "error",
        data: {
          code: "CANCELLED",
          message: "分析已停止",
          error_category: "cancelled",
          analysis_run_id: "run-a",
          project_id: "project-a",
          analysis_state: "needs_attention",
          resumable: true,
        },
      },
      "show sales"
    );

    expect(nextMessages[1]).toMatchObject({
      hasError: false,
      canRetry: true,
      analysisState: "needs_attention",
      analysisRunId: "run-a",
      projectId: "project-a",
      resumable: true,
      originalQuery: "show sales",
      isLoading: false,
    });
  });

  it("restores an interrupted run from persisted conversation metadata", () => {
    const message = mapApiMessage({
      id: "message-a",
      role: "assistant",
      content: "上次调查因应用关闭而中断。",
      created_at: "2026-07-17T00:00:00Z",
      metadata: {
        error_code: "PROCESS_INTERRUPTED",
        error_category: "interrupted",
        original_query: "show sales",
        analysis_state: "needs_attention",
        analysis_run_id: "run-a",
        project_id: "project-a",
        resumable: true,
      },
    });

    expect(message).toMatchObject({
      hasError: false,
      canRetry: true,
      analysisRunId: "run-a",
      resumable: true,
      originalQuery: "show sales",
    });
  });

  it("restores a correction application receipt from persisted message metadata", () => {
    const message = mapApiMessage({
      id: "message-correction",
      role: "assistant",
      content: "已重新核对",
      created_at: "2026-07-18T00:00:00Z",
      metadata: {
        correction_application: {
          correction_id: "correction-a",
          source_run_id: "run-before",
          rule_key: "revenue_refund_policy",
          status: "definition_only",
          summary: "已经记住退款口径。",
          checks: [],
        },
      },
    });

    expect(message.correctionApplication).toEqual({
      correction_id: "correction-a",
      source_run_id: "run-before",
      rule_key: "revenue_refund_policy",
      status: "definition_only",
      summary: "已经记住退款口径。",
      checks: [],
    });
  });
});
