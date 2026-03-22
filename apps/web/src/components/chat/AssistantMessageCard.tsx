"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { AlertTriangle, PlayCircle, RefreshCw, Sparkles } from "lucide-react";
import Image from "next/image";
import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "@/lib/types/chat";
import { ChartDisplay } from "./ChartDisplay";
import { DataTable } from "./DataTable";
import { SqlHighlight } from "./SqlHighlight";
import { StatusChip } from "./StatusChip";

type AssistantTab = "summary" | "sql" | "data" | "chart" | "python" | "diagnostics";

interface AssistantMessageCardProps {
  message: ChatMessage;
  index: number;
  onRetry: (index: number) => void;
  onRerun: (index: number) => void;
}

export function AssistantMessageCard({
  message,
  index,
  onRetry,
  onRerun,
}: AssistantMessageCardProps) {
  const t = useTranslations("assistant");
  const [activeTab, setActiveTab] = useState<AssistantTab>("summary");
  const executionContext = message.executionContext;
  const diagnostics = message.diagnostics || [];
  const autoRepairCount = diagnostics.filter((entry) => entry.status === "repaired").length;

  const tabs = useMemo(
    () =>
      [
        { id: "summary", label: t("summary"), visible: true },
        { id: "sql", label: "SQL", visible: Boolean(message.sql) },
        { id: "data", label: t("data"), visible: Boolean(message.data?.length) },
        {
          id: "chart",
          label: t("chart"),
          visible: Boolean(message.visualization || message.pythonImages?.length),
        },
        { id: "python", label: "Python", visible: Boolean(message.pythonCode || message.pythonOutput) },
        { id: "diagnostics", label: t("diagnostics"), visible: true },
      ].filter((tab) => tab.visible) as Array<{ id: AssistantTab; label: string }>,
    [
      t,
      message.data?.length,
      message.pythonCode,
      message.pythonImages?.length,
      message.pythonOutput,
      message.sql,
      message.visualization,
    ]
  );

  return (
    <div
      data-testid={`assistant-message-card-${index}`}
      className="w-full max-w-4xl rounded-[24px] border border-border bg-background shadow-sm"
    >
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              data-testid={`assistant-tab-${tab.id}`}
              className={
                activeTab === tab.id
                  ? "rounded-full bg-primary px-3 py-1.5 text-xs text-primary-foreground transition-colors"
                  : "rounded-full bg-secondary px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
              }
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onRerun(index)}
            className="inline-flex items-center gap-1 rounded-full bg-secondary px-3 py-1.5 text-xs text-foreground transition-colors hover:bg-muted"
          >
            <PlayCircle size={14} />
            {t("rerun")}
          </button>
          {message.hasError && (
            <button
              onClick={() => onRetry(index)}
              className="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1.5 text-xs text-primary-foreground transition-colors hover:bg-primary/90"
            >
              <RefreshCw size={14} />
              {t("retry")}
            </button>
          )}
        </div>
      </div>

      <div className="space-y-4 px-5 py-4">
        {message.hasError && (
          <div className="rounded-xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {message.errorMessage || t("executionError")}
          </div>
        )}

        {activeTab === "summary" && (
          <ReactMarkdown className="prose prose-sm max-w-none dark:prose-invert">
            {message.content || t("noSummary")}
          </ReactMarkdown>
        )}

        {activeTab === "sql" && message.sql && <SqlHighlight code={message.sql} />}

        {activeTab === "data" && message.data && message.data.length > 0 && (
          <DataTable data={message.data} title={`${t("queryResult")} (${message.data.length})`} />
        )}

        {activeTab === "chart" && (
          <div className="space-y-4">
            {message.visualization && (
              <ChartDisplay
                type={message.visualization.type || "bar"}
                data={message.visualization.data || []}
                title={message.visualization.title}
              />
            )}
            {message.pythonImages?.map((img, imageIndex) => (
              <Image
                key={imageIndex}
                src={`data:image/png;base64,${img}`}
                alt={t("chartAlt", { index: imageIndex + 1 })}
                width={1280}
                height={720}
                unoptimized
                className="h-auto max-w-full rounded-xl border border-border"
              />
            ))}
            {!message.visualization && !message.pythonImages?.length && (
              <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                {t("noChart")}
              </div>
            )}
          </div>
        )}

        {activeTab === "python" && (
          <div className="space-y-3">
            {message.pythonCode && (
              <div>
                <div className="mb-1 text-xs font-medium text-muted-foreground">{t("pythonCode")}</div>
                <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl bg-secondary p-4 text-xs text-foreground">
                  {message.pythonCode}
                </pre>
              </div>
            )}
            {message.pythonOutput && (
              <div>
                <div className="mb-1 text-xs font-medium text-muted-foreground">{t("pythonOutputLabel")}</div>
                <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl bg-secondary p-4 text-xs text-foreground">
                  {message.pythonOutput}
                </pre>
              </div>
            )}
            {!message.pythonCode && !message.pythonOutput && (
              <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl bg-secondary p-4 text-xs text-foreground">
                {t("noPython")}
              </pre>
            )}
          </div>
        )}

        {activeTab === "diagnostics" && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="min-w-0 rounded-xl border border-border bg-secondary p-4">
                <div className="text-xs text-muted-foreground">{t("modelLabel")}</div>
                <div className="mt-1 text-sm text-foreground">
                  {executionContext?.model_name || executionContext?.model_identifier || "-"}
                </div>
              </div>
              <div className="min-w-0 rounded-xl border border-border bg-secondary p-4">
                <div className="text-xs text-muted-foreground">{t("connectionLabel")}</div>
                <div className="mt-1 text-sm text-foreground">
                  {executionContext?.connection_name || "-"}
                </div>
                {(executionContext?.database_name || executionContext?.connection_host) && (
                  <div className="mt-1 truncate text-xs text-muted-foreground" title={[executionContext.database_name, executionContext.connection_host].filter(Boolean).join(" · ")}>
                    {[executionContext.database_name, executionContext.connection_host]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                )}
              </div>
              <div className="min-w-0 rounded-xl border border-border bg-secondary p-4">
                <div className="text-xs text-muted-foreground">Provider</div>
                <div className="mt-1 text-sm text-foreground">
                  {executionContext?.provider_summary || "-"}
                </div>
                {(executionContext?.source_provider || executionContext?.resolved_provider) && (
                  <div className="mt-1 text-xs text-muted-foreground">
                    {t("sourceProvider")}: {executionContext?.source_provider || "-"} · {t("runtimeProvider")}:{" "}
                    {executionContext?.resolved_provider || "-"}
                  </div>
                )}
              </div>
              <div className="min-w-0 rounded-xl border border-border bg-secondary p-4">
                <div className="text-xs text-muted-foreground">{t("contextRoundsLabel")}</div>
                <div className="mt-1 text-sm text-foreground">
                  {executionContext?.context_rounds || "-"}
                </div>
              </div>
              <div className="min-w-0 rounded-xl border border-border bg-secondary p-4">
                <div className="text-xs text-muted-foreground">{t("execTime")}</div>
                <div className="mt-1 text-sm text-foreground">
                  {message.executionTime ? `${message.executionTime.toFixed(2)}s` : "-"}
                </div>
              </div>
              <div className="min-w-0 rounded-xl border border-border bg-secondary p-4">
                <div className="text-xs text-muted-foreground">{t("rowCount")}</div>
                <div className="mt-1 text-sm text-foreground">{message.rowsCount ?? "-"}</div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <StatusChip>
                <Sparkles size={12} />
                {t("autoRepair", { count: autoRepairCount })}
              </StatusChip>
              {message.errorCategory && (
                <StatusChip tone="warning">{t("errorCategory")}: {message.errorCategory}</StatusChip>
              )}
              {message.errorCode && (
                <StatusChip tone="warning">{t("errorCode")}: {message.errorCode}</StatusChip>
              )}
            </div>

            <div className="rounded-2xl border border-border bg-secondary/50 p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-medium text-foreground">
                <AlertTriangle size={14} />
                {t("attemptLog")}
              </div>
              {diagnostics.length ? (
                <div className="space-y-3">
                  {diagnostics.map((entry, diagIndex) => (
                    <div
                      key={`${entry.attempt}-${entry.phase}-${diagIndex}`}
                      className="rounded-xl border border-border bg-background px-4 py-3"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusChip>{t("attemptLabel", { attempt: entry.attempt || 1, phase: entry.phase || "unknown" })}</StatusChip>
                        {entry.status === "success" && <StatusChip tone="success">{t("success")}</StatusChip>}
                        {entry.status === "repaired" && (
                          <StatusChip tone="success">{t("repaired")}</StatusChip>
                        )}
                        {entry.status === "error" && <StatusChip tone="warning">{t("failed")}</StatusChip>}
                        {entry.error_category && (
                          <StatusChip tone="warning">{entry.error_category}</StatusChip>
                        )}
                        {entry.recoverable && <StatusChip>{t("recoverable")}</StatusChip>}
                      </div>
                      <div className="mt-2 text-sm text-foreground">{entry.message || "-"}</div>
                      {entry.sql && (
                        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-xl bg-secondary p-3 text-xs text-foreground">
                          {entry.sql}
                        </pre>
                      )}
                      {!entry.sql && entry.python && (
                        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-xl bg-secondary p-3 text-xs text-foreground">
                          {entry.python}
                        </pre>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">{t("noDiagnostics")}</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
