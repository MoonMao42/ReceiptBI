"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  CircleDot,
  ClipboardCheck,
  FilePlus2,
  FolderCheck,
  LayoutDashboard,
  ExternalLink,
  MessageSquareWarning,
  RefreshCw,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "@/lib/types/chat";
import type {
  AnalysisArtifact,
  AnalysisCorrection,
  AnalysisCorrectionSelection,
  AnalysisCorrectionTarget,
  AnalysisCorrectionTargetOption,
  CorrectionApplication,
} from "@/lib/types/api";
import { getErrorMessage } from "@/lib/types/api";
import { api } from "@/lib/api/client";
import { normalizeChartSpec } from "@/lib/charts";
import { useProjectStore } from "@/lib/stores/project";
import { getInvestigationErrorRecovery } from "@/lib/stores/chat-helpers";
import { ChartDisplay } from "./ChartDisplay";
import { DataTable } from "./DataTable";
import { SavedAnalysisArtifacts } from "./SavedAnalysisArtifacts";

interface AssistantMessageCardProps {
  message: ChatMessage;
  index: number;
  onRetry: (index: number) => void;
  onRerun: (index: number) => void;
  onUsePrompt: (prompt: string) => void;
  onRunPrompt?: (prompt: string, options?: { correctionId?: string }) => void;
  onConfirm: (
    analysisRunId: string,
    key: string,
    selectedOption: string,
  ) => Promise<void>;
  onOpenData: () => void;
  onOpenUnderstanding?: () => void;
  onChangeAnalysisService?: (messageIndex: number) => void;
  onManageAnalysisServices?: (messageIndex: number) => void;
}

interface SavedPlaybookSummary {
  name?: string;
  validation?: {
    numeric_columns?: string[];
  };
}

function getStandingErrorMessage(error: unknown): string {
  const status = (
    error as { response?: { status?: unknown } } | null | undefined
  )?.response?.status;
  if (status === 409 || status === 422) {
    return "暂时无法开始关注，请重新保存这项分析后再试。";
  }
  return "暂时无法开始关注，请稍后再试。";
}

type CorrectionState = "idle" | "saving" | "saved" | "deleting";
type CorrectionKind = AnalysisCorrection["correction_type"];

const CORRECTION_KINDS: Array<{
  value: CorrectionKind;
  label: string;
  description: string;
  placeholder: string;
}> = [
  {
    value: "business_rule",
    label: "业务判断",
    description: "结论或业务规则理解错了",
    placeholder: "例如：折扣只是促销，不代表亏损。",
  },
  {
    value: "metric_definition",
    label: "指标口径",
    description: "收入、利润等指标算错了",
    placeholder: "例如：利润应按实付金额减去单位成本计算。",
  },
  {
    value: "filter_rule",
    label: "筛选范围",
    description: "哪些记录该算或不该算",
    placeholder: "例如：已退款订单不计入收入。",
  },
  {
    value: "relationship_rule",
    label: "数据关联",
    description: "表或文件之间连错了",
    placeholder: "例如：订单和门店要通过门店编号关联，不要用门店名称。",
  },
  {
    value: "interpretation",
    label: "解释偏差",
    description: "数字没错，但原因判断不对",
    placeholder: "例如：增长来自新店开业，不能归因于折扣活动。",
  },
];

function correctionKindLabel(kind?: CorrectionKind): string {
  return (
    CORRECTION_KINDS.find((item) => item.value === kind)?.label || "业务判断"
  );
}

function ordinaryReceiptText(value?: string | null): string | null {
  if (!value) return null;
  if (/\b(sql|python|schema|json|tool|agent|token|api)\b/i.test(value))
    return null;
  return value;
}

const RECEIPT_CHECK_LABELS: Record<string, string> = {
  business_definition_recorded: "已保存这条业务定义",
  current_definition_applied: "使用的是当前确认的定义",
  application_reaches_final_result: "这条修正已进入最终结果",
  final_result_revalidated: "最终结果已经重新核对",
  required_metric_used_by_final_aggregate: "修正后的指标已用于最终汇总",
  current_relationship_definition_tested: "使用的是当前修正的关联方式",
  relationship_validation_passed: "关联覆盖率和重复扩张已经核对",
  join_reaches_final_result: "关联后的数据已经进入最终结论",
  final_result_revalidated_after_join: "关联后的最终结果已经重新核对",
};

function ordinaryReceiptCheck(value: string): string | null {
  const mapped = RECEIPT_CHECK_LABELS[value];
  if (mapped) return mapped;
  // Unknown machine check identifiers belong in advanced evidence, not in the
  // ordinary report. Chinese business-facing messages can still pass through.
  if (!/[\u3400-\u9fff]/u.test(value)) return null;
  return ordinaryReceiptText(value);
}

function CorrectionApplicationReceipt({
  receipt,
}: {
  receipt: CorrectionApplication;
}) {
  const verified = receipt.status === "verified";
  const failed = receipt.status === "failed";
  const title = verified
    ? "本次修正已用于当前数据并重新核对"
    : failed
      ? "本次修正没有完成核对"
      : "已记住定义，执行方式尚未验证";
  const fallback = verified
    ? "这份报告使用了修正后的判断，并重新检查了当前数据。"
    : failed
      ? "调查没有足够依据证明这条修正已经正确作用，请处理后再继续。"
      : "这条理解会保留在项目中；在形成可复用的处理方式前，每次仍需重新核对。";
  const summary = ordinaryReceiptText(receipt.summary) || fallback;
  const checks = (Array.isArray(receipt.checks) ? receipt.checks : [])
    .map(ordinaryReceiptCheck)
    .filter((item): item is string => Boolean(item));

  return (
    <section
      aria-label="本次修正核对结果"
      role={failed ? "alert" : "status"}
      className={`relative mt-5 border-y px-5 py-4 pl-6 ${
        verified
          ? "border-success/30 bg-success/[0.04]"
          : failed
            ? "border-destructive/30 bg-destructive/[0.05]"
            : "border-warning/30 bg-warning/[0.05]"
      }`}
    >
      <span
        aria-hidden="true"
        className={`absolute bottom-3 left-0 top-3 w-[3px] ${
          verified ? "bg-success" : failed ? "bg-destructive" : "bg-warning"
        }`}
      />
      <div className="flex items-start gap-3">
        {verified ? (
          <CheckCircle2
            size={17}
            className="mt-0.5 shrink-0 text-success"
          />
        ) : (
          <AlertCircle
            size={17}
            className={`mt-0.5 shrink-0 ${failed ? "text-destructive" : "text-warning"}`}
          />
        )}
        <div className="min-w-0">
          <h3
            className={`text-sm font-semibold ${
              verified
                ? "text-success"
                : failed
                  ? "text-destructive"
                  : "text-warning"
            }`}
          >
            {title}
          </h3>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {summary}
          </p>
          {checks.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs leading-5 text-foreground/85">
              {checks.map((check, checkIndex) => (
                <li key={`${check}-${checkIndex}`} className="flex gap-2">
                  <span
                    className={verified ? "text-success" : "text-destructive"}
                  >
                    ·
                  </span>
                  <span>{check}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}

export function AssistantMessageCard({
  message,
  index,
  onRetry,
  onRerun,
  onUsePrompt,
  onRunPrompt,
  onConfirm,
  onOpenData,
  onOpenUnderstanding,
  onChangeAnalysisService,
  onManageAnalysisServices,
}: AssistantMessageCardProps) {
  const queryClient = useQueryClient();
  const refreshProject = useProjectStore((state) => state.refreshCurrent);
  const projectKnowledge = useProjectStore((state) => state.knowledge);
  const [confirmingOption, setConfirmingOption] = useState<string | null>(null);
  const [confirmationError, setConfirmationError] = useState<string | null>(
    null,
  );
  const [playbookState, setPlaybookState] = useState<
    "idle" | "saving" | "saved"
  >("idle");
  const [playbookError, setPlaybookError] = useState<string | null>(null);
  const [savedPlaybook, setSavedPlaybook] =
    useState<SavedPlaybookSummary | null>(null);
  const [standingState, setStandingState] = useState<
    "idle" | "saving" | "saved"
  >("idle");
  const [standingError, setStandingError] = useState<string | null>(null);
  const [savedArtifactsOpen, setSavedArtifactsOpen] = useState(false);
  const [correctionOpen, setCorrectionOpen] = useState(false);
  const [correctionText, setCorrectionText] = useState("");
  const [correctionKind, setCorrectionKind] =
    useState<CorrectionKind>("business_rule");
  const [correctionTargetRef, setCorrectionTargetRef] = useState<string | null>(
    null,
  );
  const [correctionSelection, setCorrectionSelection] =
    useState<AnalysisCorrectionSelection | null>(null);
  const [correctionReusable, setCorrectionReusable] = useState(false);
  const [correctionState, setCorrectionState] =
    useState<CorrectionState>("idle");
  const [correctionError, setCorrectionError] = useState<string | null>(null);
  const correctionIdentityRef = useRef("");
  const correctionIdentity = `${message.projectId || ""}:${message.analysisRunId || ""}`;
  correctionIdentityRef.current = correctionIdentity;
  const report = message.report;
  const correctionApplicationFailed =
    message.correctionApplication?.status === "failed";
  const hasError = Boolean(message.hasError || correctionApplicationFailed);
  const errorRecovery = getInvestigationErrorRecovery(
    message.errorCode,
    message.errorCategory,
  );
  const needsAnalysisServiceChange =
    hasError && errorRecovery === "change_analysis_service";
  const analysisServiceFailureReason = (() => {
    switch (message.errorCode) {
      case "MODEL_AUTH_ERROR":
        return "访问凭证已失效。";
      case "MODEL_ENDPOINT_ERROR":
        return "连接设置不可用。";
      case "MODEL_NOT_FOUND":
      case "MODEL_NOT_FOUND_ERROR":
        return "当前服务不支持所选模型。";
      case "MODEL_FORMAT_ERROR":
        return "服务返回的内容无法使用。";
      case "MODEL_SELECTION_CONFLICT":
        return "这份调查已固定使用原服务。";
      default:
        return "当前服务暂时无法完成调查。";
    }
  })();
  const failureTitle = correctionApplicationFailed
    ? "本次修正未完成"
    : needsAnalysisServiceChange
      ? "分析服务不可用"
      : message.resumable
        ? "调查已暂停"
        : "调查未完成";
  const failureReason = (() => {
    if (correctionApplicationFailed) {
      return (
        ordinaryReceiptText(message.correctionApplication?.summary) ||
        "当前数据不足以完成核对。"
      );
    }
    if (needsAnalysisServiceChange) return analysisServiceFailureReason;

    const code = (message.errorCode || "").toUpperCase();
    const category = (message.errorCategory || "").toLowerCase();
    if (code.includes("TIMEOUT") || category === "timeout") {
      return "分析服务暂时没有响应。";
    }
    if (code.includes("RATE_LIMIT") || category === "rate_limited") {
      return "分析服务当前繁忙。";
    }
    if (code.includes("CONNECTION") || category === "connection") {
      return "暂时无法连接分析服务。";
    }
    return message.resumable
      ? "进度已保留，可以继续。"
      : "处理过程中出现问题。";
  })();
  const needsData = report?.status === "needs_data";
  const wasStopped =
    message.analysisState === "needs_attention" &&
    !message.hasError &&
    !needsData;
  const canResume =
    wasStopped && Boolean(message.canRetry && message.resumable);
  const nextActions = report?.next_actions || [];
  const canCorrectReport = Boolean(
    message.projectId &&
    message.analysisRunId &&
    !hasError &&
    !needsData &&
    (report?.status === "completed" || message.analysisState === "completed"),
  );
  const {
    data: artifacts = [],
    isError: artifactsFailed,
    refetch: refetchArtifacts,
  } = useQuery<AnalysisArtifact[]>({
    queryKey: ["artifacts", message.projectId, message.analysisRunId],
    queryFn: async () => {
      const response = await api.get(
        `/api/v1/projects/${message.projectId}/analysis-runs/${message.analysisRunId}/artifacts`,
      );
      return response.data.data as AnalysisArtifact[];
    },
    enabled: Boolean(message.projectId && message.analysisRunId),
    staleTime: 30_000,
  });
  const correctionQueryKey = [
    "analysis-corrections",
    message.projectId,
  ] as const;
  const { data: projectCorrections = [], isPending: correctionsPending } =
    useQuery<AnalysisCorrection[]>({
      queryKey: correctionQueryKey,
      queryFn: async () => {
        const response = await api.get(
          `/api/v1/projects/${message.projectId}/corrections`,
        );
        return response.data.data as AnalysisCorrection[];
      },
      enabled: Boolean(message.projectId),
      staleTime: 30_000,
    });
  const {
    data: correctionTargets = [],
    isFetching: correctionTargetsFetching,
    isError: correctionTargetsFailed,
  } = useQuery<AnalysisCorrectionTarget[]>({
    queryKey: [
      "analysis-correction-targets",
      message.projectId,
      message.analysisRunId,
    ],
    queryFn: async () => {
      const response = await api.get(
        `/api/v1/projects/${message.projectId}/analysis-runs/${message.analysisRunId}/correction-targets`,
      );
      return response.data.data as AnalysisCorrectionTarget[];
    },
    enabled: canCorrectReport && correctionOpen,
    retry: false,
    staleTime: 30_000,
  });
  const persistedCorrection = projectCorrections.find(
    (item) => item.analysis_run_id === message.analysisRunId,
  );
  const selectedCorrectionTarget = correctionTargets.find(
    (target) => target.target_ref === correctionTargetRef,
  );
  const ownsPersistedCorrectionTarget = Boolean(
    correctionTargetRef &&
    persistedCorrection?.target_ref === correctionTargetRef,
  );
  const hasBoundCorrectionTarget = Boolean(
    selectedCorrectionTarget || ownsPersistedCorrectionTarget,
  );
  const boundCorrectionType =
    selectedCorrectionTarget?.correction_type ||
    (ownsPersistedCorrectionTarget
      ? persistedCorrection?.correction_type
      : undefined);
  const {
    data: correctionTargetOptions = [],
    isFetching: correctionTargetOptionsFetching,
    isError: correctionTargetOptionsFailed,
  } = useQuery<AnalysisCorrectionTargetOption[]>({
    queryKey: [
      "analysis-correction-target-options",
      message.projectId,
      message.analysisRunId,
      correctionTargetRef,
    ],
    queryFn: async () => {
      const response = await api.get(
        `/api/v1/projects/${message.projectId}/analysis-runs/${message.analysisRunId}/correction-targets/${encodeURIComponent(
          correctionTargetRef || "",
        )}/options`,
      );
      return response.data.data as AnalysisCorrectionTargetOption[];
    },
    enabled: Boolean(
      canCorrectReport &&
      correctionOpen &&
      correctionTargetRef &&
      boundCorrectionType === "metric_definition",
    ),
    retry: false,
    staleTime: 30_000,
  });
  const validMetricSelection: AnalysisCorrectionSelection | null =
    !correctionTargetOptionsFailed &&
    correctionSelection?.kind === "metric_column" &&
    correctionTargetOptions.some(
      (option) => option.field_ref === correctionSelection.field_ref,
    )
      ? correctionSelection
      : null;
  const soleMetricSelection: AnalysisCorrectionSelection | null =
    !correctionTargetOptionsFailed && correctionTargetOptions.length === 1
      ? {
          kind: "metric_column",
          field_ref: correctionTargetOptions[0].field_ref,
        }
      : null;
  const effectiveMetricSelection = validMetricSelection || soleMetricSelection;
  const metricSelectionRequired = Boolean(
    correctionReusable &&
    boundCorrectionType === "metric_definition" &&
    !correctionTargetOptionsFailed &&
    correctionTargetOptions.length > 1 &&
    !effectiveMetricSelection,
  );
  const metricSelectionPending = Boolean(
    correctionReusable &&
    boundCorrectionType === "metric_definition" &&
    correctionTargetOptionsFetching,
  );
  const linkedProjectKnowledge = persistedCorrection?.semantic_entry_id
    ? projectKnowledge.find(
        (entry) => entry.id === persistedCorrection.semantic_entry_id,
      )
    : undefined;
  const currentCorrectionText =
    linkedProjectKnowledge?.value ||
    persistedCorrection?.text ||
    correctionText;
  const correctionPromoted = Boolean(
    persistedCorrection?.state === "promoted" &&
    persistedCorrection.semantic_entry_id,
  );
  const projectCorrectionInactive =
    linkedProjectKnowledge?.validity === "stale";
  const correctionExecutionState =
    linkedProjectKnowledge?.execution_state ||
    (projectCorrectionInactive ? "blocked" : "definition_only");
  const correctionExecutionVerified = correctionExecutionState === "verified";
  const correctionExecutionBlocked = correctionExecutionState === "blocked";

  useEffect(() => {
    setSavedArtifactsOpen(false);
    setCorrectionOpen(false);
    setCorrectionText("");
    setCorrectionKind("business_rule");
    setCorrectionTargetRef(null);
    setCorrectionSelection(null);
    setCorrectionReusable(false);
    setCorrectionState("idle");
    setCorrectionError(null);
  }, [message.analysisRunId, message.projectId]);

  useEffect(() => {
    if (correctionState === "saving" || correctionState === "deleting") return;
    if (!persistedCorrection) return;
    setCorrectionText(
      linkedProjectKnowledge?.value || persistedCorrection.text,
    );
    setCorrectionKind(persistedCorrection.correction_type);
    setCorrectionTargetRef(persistedCorrection.target_ref || null);
    setCorrectionSelection(persistedCorrection.selection || null);
    setCorrectionReusable(persistedCorrection.scope === "project");
    setCorrectionState("saved");
  }, [linkedProjectKnowledge?.value, persistedCorrection, correctionState]);

  const savedFiles = artifacts.filter(
    (artifact) => typeof artifact.payload.relative_path === "string",
  );
  const visualization =
    message.visualization || report?.visualization || undefined;
  const pythonImages = (message.pythonImages || []).filter(
    (image) => image.trim().length > 0,
  );
  const structuredVisualization =
    pythonImages.length === 0 ? normalizeChartSpec(visualization) : null;
  const hasValidatedResult = Boolean(
    message.toolHistory?.some((item) => item.kind === "validation"),
  );
  const canSavePlaybook = Boolean(
    !hasError &&
    report?.status === "completed" &&
    message.projectId &&
    message.analysisRunId &&
    hasValidatedResult,
  );
  const partialSummary =
    report?.summary ||
    (message.content && message.content !== message.errorMessage
      ? message.content
      : "");
  const runPrompt = onRunPrompt || onUsePrompt;

  const correctedInvestigationPrompt = () => {
    const originalQuestion =
      message.originalQuery || report?.title || "刚才这项调查";
    return [
      `请根据我的修正重新调查：${originalQuestion}`,
      `我的修正：${correctionText.trim()}`,
      "请重新检查数据和依据，不要直接沿用上一份结论。",
    ].join("\n");
  };

  const handleLatestDataRerun = () => {
    if (canResume) {
      onRetry(index);
      return;
    }

    const reusableCorrection =
      persistedCorrection?.scope === "project" ? persistedCorrection : null;
    const originalQuestion = message.originalQuery?.trim();
    if (reusableCorrection && originalQuestion) {
      runPrompt(originalQuestion, { correctionId: reusableCorrection.id });
      return;
    }

    onRerun(index);
  };

  const handleConfirmation = async (key: string, option: string) => {
    if (!message.analysisRunId) {
      setConfirmationError("这次调查缺少可继续的记录，请重新调查。");
      return;
    }
    setConfirmingOption(option);
    setConfirmationError(null);
    try {
      await onConfirm(message.analysisRunId, key, option);
    } catch (error) {
      setConfirmationError(getErrorMessage(error));
    } finally {
      setConfirmingOption(null);
    }
  };

  const handleSavePlaybook = async () => {
    if (
      !message.projectId ||
      !message.analysisRunId ||
      playbookState === "saving"
    )
      return;
    setPlaybookState("saving");
    setPlaybookError(null);
    try {
      const response = await api.post(
        `/api/v1/projects/${message.projectId}/analysis-playbooks`,
        {
          analysis_run_id: message.analysisRunId,
        },
      );
      setSavedPlaybook(response.data.data as SavedPlaybookSummary);
      setPlaybookState("saved");
    } catch (error) {
      setPlaybookState("idle");
      setPlaybookError(getErrorMessage(error));
    }
  };

  const handleCreateStanding = async () => {
    if (
      !message.projectId ||
      !message.analysisRunId ||
      standingState === "saving" ||
      !savedPlaybook
    ) {
      return;
    }
    const numericColumns = (savedPlaybook.validation?.numeric_columns || [])
      .filter((column) => column.trim())
      .slice(0, 10);
    if (!numericColumns.length) {
      setStandingError("这份结果没有可稳定比较的数值指标，暂时不能持续关注。");
      return;
    }

    setStandingState("saving");
    setStandingError(null);
    try {
      await api.post(
        `/api/v1/projects/${message.projectId}/standing-analyses`,
        {
          analysis_run_id: message.analysisRunId,
          name: report?.title || savedPlaybook.name || "持续关注这项分析",
          overdue_after_seconds: 86400,
          materiality: {
            version: 1,
            match: "any",
            percent_unit: "ratio",
            top_driver_limit: 10,
            rules: numericColumns.map((metric, index) => ({
              id: `rule_metric_${index + 1}`,
              metric,
              scope: "either",
              direction: "any",
              change_kind: "percent",
              threshold: 0.1,
            })),
          },
        },
      );
      setStandingState("saved");
      await queryClient.invalidateQueries({
        queryKey: ["standing-analyses", message.projectId],
      });
    } catch (error) {
      setStandingState("idle");
      setStandingError(getStandingErrorMessage(error));
    }
  };

  const handleSaveCorrection = async () => {
    const correction = correctionText.trim();
    const requestProjectId = message.projectId;
    const requestAnalysisRunId = message.analysisRunId;
    const requestIdentity = correctionIdentity;
    if (
      !requestProjectId ||
      !requestAnalysisRunId ||
      !correction ||
      correctionState === "saving" ||
      (correctionReusable && !hasBoundCorrectionTarget) ||
      metricSelectionPending ||
      metricSelectionRequired
    ) {
      return;
    }
    setCorrectionState("saving");
    setCorrectionError(null);
    const requestCorrectionQueryKey = [
      "analysis-corrections",
      requestProjectId,
    ] as const;
    try {
      await queryClient.cancelQueries({ queryKey: requestCorrectionQueryKey });
      const payload = {
        analysis_run_id: requestAnalysisRunId,
        text: correction,
        correction_type: correctionKind,
        target_ref: correctionTargetRef,
        selection:
          correctionReusable && boundCorrectionType === "metric_definition"
            ? effectiveMetricSelection
            : null,
        scope: correctionReusable ? "project" : "run",
        report_title: report?.title,
      };
      const response = persistedCorrection
        ? await api.put(
            `/api/v1/projects/${requestProjectId}/corrections/${persistedCorrection.id}`,
            payload,
          )
        : await api.post(
            `/api/v1/projects/${requestProjectId}/corrections`,
            payload,
          );
      const savedCorrection = response.data.data as AnalysisCorrection;
      queryClient.setQueryData<AnalysisCorrection[]>(
        requestCorrectionQueryKey,
        (current = []) => [
          savedCorrection,
          ...current.filter((item) => item.id !== savedCorrection.id),
        ],
      );
      await queryClient.invalidateQueries({
        queryKey: requestCorrectionQueryKey,
        refetchType: "none",
      });
      if (correctionIdentityRef.current !== requestIdentity) return;
      setCorrectionText(savedCorrection.text);
      setCorrectionKind(savedCorrection.correction_type);
      setCorrectionTargetRef(savedCorrection.target_ref || correctionTargetRef);
      setCorrectionSelection(savedCorrection.selection || null);
      setCorrectionReusable(savedCorrection.scope === "project");
      setCorrectionState("saved");
      setCorrectionOpen(false);

      if (savedCorrection.scope === "project") {
        await Promise.allSettled([
          refreshProject(),
          queryClient.invalidateQueries({
            queryKey: ["suggested-questions", requestProjectId],
          }),
        ]);
      }
    } catch (error) {
      if (correctionIdentityRef.current !== requestIdentity) return;
      setCorrectionState("idle");
      setCorrectionError(getErrorMessage(error));
    }
  };

  const handleDeleteCorrection = async () => {
    const requestProjectId = message.projectId;
    const requestIdentity = correctionIdentity;
    const requestCorrection = persistedCorrection;
    if (
      !requestProjectId ||
      !requestCorrection ||
      correctionState === "saving" ||
      correctionState === "deleting"
    ) {
      return;
    }
    setCorrectionState("deleting");
    setCorrectionError(null);
    const requestCorrectionQueryKey = [
      "analysis-corrections",
      requestProjectId,
    ] as const;
    try {
      await queryClient.cancelQueries({ queryKey: requestCorrectionQueryKey });
      await api.delete(
        `/api/v1/projects/${requestProjectId}/corrections/${requestCorrection.id}`,
      );
      queryClient.setQueryData<AnalysisCorrection[]>(
        requestCorrectionQueryKey,
        (current = []) =>
          current.filter((item) => item.id !== requestCorrection.id),
      );
      await queryClient.invalidateQueries({
        queryKey: requestCorrectionQueryKey,
        refetchType: "none",
      });
      if (correctionIdentityRef.current !== requestIdentity) return;
      if (requestCorrection.scope === "project") {
        await Promise.allSettled([
          refreshProject(),
          queryClient.invalidateQueries({
            queryKey: ["suggested-questions", requestProjectId],
          }),
        ]);
      }
      setCorrectionText("");
      setCorrectionKind("business_rule");
      setCorrectionTargetRef(null);
      setCorrectionSelection(null);
      setCorrectionReusable(false);
      setCorrectionOpen(false);
      setCorrectionState("idle");
    } catch (error) {
      if (correctionIdentityRef.current !== requestIdentity) return;
      setCorrectionState("saved");
      setCorrectionError(getErrorMessage(error));
    }
  };

  return (
    <article
      data-testid={`assistant-message-card-${index}`}
      className="relative w-full max-w-[920px] overflow-hidden border border-border bg-card"
    >
      {!hasError && (
        <div className="absolute bottom-0 left-0 top-0 w-[3px] bg-primary" />
      )}
      <div
        className={hasError ? "px-6 py-6 md:px-8" : "px-6 py-7 md:px-9 md:py-8"}
      >
        {hasError ? (
          <div
            role="alert"
            aria-labelledby={`investigation-error-title-${index}`}
            aria-describedby={`investigation-error-reason-${index}`}
            className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between"
          >
            <div className="flex min-w-0 items-start gap-3">
              <AlertCircle
                aria-hidden="true"
                size={18}
                className="mt-0.5 shrink-0 text-destructive"
              />
              <div className="min-w-0">
                <h2
                  id={`investigation-error-title-${index}`}
                  className="text-lg font-semibold leading-6 tracking-[-0.015em] text-foreground"
                >
                  {failureTitle}
                </h2>
                <p
                  id={`investigation-error-reason-${index}`}
                  className="mt-1 text-sm leading-6 text-muted-foreground"
                >
                  {failureReason}
                </p>
              </div>
            </div>
            {needsAnalysisServiceChange &&
              (onChangeAnalysisService || onManageAnalysisServices) && (
                <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
                  {onChangeAnalysisService && (
                    <button
                      type="button"
                      onClick={() => onChangeAnalysisService(index)}
                      className="rounded-md bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                    >
                      更换服务
                    </button>
                  )}
                  {onManageAnalysisServices && (
                    <button
                      type="button"
                      onClick={() => onManageAnalysisServices(index)}
                      className="rounded-md border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                    >
                      设置
                    </button>
                  )}
                </div>
              )}
            {!needsAnalysisServiceChange && message.canRetry && (
              <button
                type="button"
                onClick={() => onRetry(index)}
                className="shrink-0 self-start rounded-md bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
              >
                {message.resumable ? "继续" : "重试"}
              </button>
            )}
          </div>
        ) : (
          <div className="flex items-start justify-between gap-5">
            <div className="min-w-0">
              <div
                className={`flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.15em] ${
                  needsData ? "text-warning" : "text-success"
                }`}
              >
                {needsData ? (
                  <FilePlus2 size={14} />
                ) : (
                  <CheckCircle2 size={14} />
                )}
                {needsData
                  ? "等待补充数据"
                  : message.analysisState === "waiting_confirmation"
                    ? "等待你的判断"
                    : wasStopped
                      ? "调查已停止"
                      : "调查报告"}
              </div>
              <h2 className="mt-2 max-w-2xl text-[26px] font-semibold leading-tight tracking-[-0.035em] text-foreground">
                {report?.title || (wasStopped ? "这次调查已停止" : "分析结果")}
              </h2>
            </div>
            {!needsData && (
              <div className="flex shrink-0 items-center gap-1">
                {message.projectId && message.analysisRunId && canCorrectReport && (
                  <Link
                    href={`/projects/${message.projectId}/reports?fromRun=${message.analysisRunId}`}
                    className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-2 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
                  >
                    <LayoutDashboard size={13} />
                    加入报表
                  </Link>
                )}
                <button
                  onClick={handleLatestDataRerun}
                  disabled={Boolean(message.projectId && correctionsPending)}
                  className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-2 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-wait disabled:opacity-60"
                >
                  <RefreshCw size={13} />
                  {canResume ? "继续上次调查" : "用最新数据重跑"}
                </button>
              </div>
            )}
          </div>
        )}

        {message.correctionApplication && !correctionApplicationFailed && (
          <CorrectionApplicationReceipt
            receipt={message.correctionApplication}
          />
        )}

        {!hasError && partialSummary ? (
          <ReactMarkdown className="prose prose-sm mt-5 max-w-none dark:prose-invert">
            {partialSummary}
          </ReactMarkdown>
        ) : !hasError ? (
          <p className="mt-5 text-sm text-muted-foreground">还没有形成结论。</p>
        ) : null}

        {needsData && report.action?.kind === "add_data" && (
          <section className="mt-7 rounded-lg border border-primary/25 bg-primary/[0.04] px-5 py-5">
            <div className="flex items-start gap-3">
              <FilePlus2 size={18} className="mt-0.5 shrink-0 text-primary" />
              <div className="min-w-0 flex-1">
                <h3 className="text-base font-semibold text-foreground">
                  {report.action.label}
                </h3>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  {report.action.reason}
                </p>
                <ul className="mt-3 space-y-1.5 text-sm text-foreground/85">
                  {report.action.requested_data.map((item) => (
                    <li key={item} className="flex gap-2">
                      <span className="text-primary">·</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={onOpenData}
                    className="inline-flex items-center gap-2 bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
                  >
                    补充文件或数据库
                    <ArrowRight size={14} />
                  </button>
                  {message.resumable && (
                    <button
                      type="button"
                      onClick={() => onRetry(index)}
                      className="border border-border bg-background px-4 py-2.5 text-sm font-semibold text-foreground hover:border-primary/50 hover:text-primary"
                    >
                      数据已补好，继续调查
                    </button>
                  )}
                </div>
              </div>
            </div>
          </section>
        )}

        {report?.metrics?.length ? (
          <div className="mt-7 grid overflow-hidden rounded-lg border border-border bg-background/45 sm:grid-cols-2 lg:grid-cols-3">
            {report.metrics.map((metric, metricIndex) => (
              <div
                key={`${metric.label}-${metricIndex}`}
                className="border-b border-border px-4 py-4 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0"
              >
                <div className="text-xs text-muted-foreground">
                  {metric.label}
                </div>
                <div className="mt-1 text-2xl font-semibold tracking-[-0.025em] text-foreground tabular-nums">
                  {metric.value}
                </div>
                {metric.context && (
                  <div className="mt-1 text-xs leading-5 text-muted-foreground">
                    {metric.context}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : null}

        {report?.confirmation && (
          <section className="mt-7 rounded-lg border border-warning/40 bg-warning/[0.06] px-5 py-5">
            <div className="flex items-start gap-3">
              <CircleDot size={18} className="mt-0.5 shrink-0 text-warning" />
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.12em] text-warning">
                  {message.confirmationResolved
                    ? "已按这个口径继续调查"
                    : "这会改变结论，需要你决定"}
                </div>
                <h3 className="mt-2 text-base font-semibold text-foreground">
                  {report.confirmation.question}
                </h3>
                <p className="mt-1 text-xs leading-5 text-warning/80">
                  {report.confirmation.reason}
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {report.confirmation.options.map((option) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() =>
                        void handleConfirmation(
                          report.confirmation!.key,
                          option,
                        )
                      }
                      disabled={
                        confirmingOption !== null ||
                        Boolean(message.confirmationResolved)
                      }
                      className="border border-warning/50 bg-card px-3 py-2 text-sm font-medium text-foreground hover:bg-warning/15 disabled:cursor-wait disabled:opacity-60"
                    >
                      {confirmingOption === option
                        ? "正在按这个口径继续…"
                        : message.confirmationResolved === option
                          ? `${option}（已选择）`
                          : option}
                    </button>
                  ))}
                </div>
                {confirmationError && (
                  <p className="mt-3 text-xs leading-5 text-destructive">
                    {confirmationError}
                  </p>
                )}
              </div>
            </div>
          </section>
        )}

        {report?.findings?.length ? (
          <section className="mt-7">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              关键发现
            </h3>
            <div className="mt-3 divide-y divide-border border-y border-border">
              {report.findings.map((finding, findingIndex) => (
                <div
                  key={`${finding}-${findingIndex}`}
                  className="grid grid-cols-[28px_1fr] gap-3 py-3.5"
                >
                  <span className="font-mono text-xs text-primary">
                    {String(findingIndex + 1).padStart(2, "0")}
                  </span>
                  <p className="text-sm leading-6 text-foreground">{finding}</p>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {(structuredVisualization || pythonImages.length > 0) && (
          <section className="mt-7">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              结果图
            </h3>
            {structuredVisualization ? (
              <ChartDisplay spec={structuredVisualization} />
            ) : null}
            {pythonImages.map((image, imageIndex) => (
              <Image
                key={imageIndex}
                src={`data:image/png;base64,${image}`}
                alt={`分析结果图 ${imageIndex + 1}`}
                width={1280}
                height={720}
                unoptimized
                className="mt-4 h-auto max-w-full rounded-lg border border-border bg-white"
              />
            ))}
          </section>
        )}

        {!hasError && message.data?.length ? (
          <section className="mt-7" aria-label="结果明细">
            <DataTable data={message.data} title="结果明细" />
          </section>
        ) : null}

        {!needsData && artifactsFailed && (
          <section className="mt-7 flex flex-wrap items-center justify-between gap-3 border-y border-border py-3">
            <span className="text-xs text-muted-foreground">
              本次调查内容暂时没有载入。
            </span>
            <button
              type="button"
              onClick={() => void refetchArtifacts()}
              className="text-xs font-semibold text-primary hover:underline"
            >
              重试
            </button>
          </section>
        )}

        {!needsData && !artifactsFailed && artifacts.length > 0 && (
          <section className="mt-7 flex flex-wrap items-center justify-between gap-3 border-y border-border py-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <FolderCheck size={15} className="text-success" />
              本次调查已保存 {artifacts.length} 项内容
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => setSavedArtifactsOpen(true)}
                className="text-xs font-semibold text-primary hover:underline"
              >
                查看 {artifacts.length} 项
              </button>
              {savedFiles.map((artifact) => (
                <a
                  key={artifact.id}
                  href={`/api/v1/projects/${artifact.project_id}/analysis-runs/${artifact.analysis_run_id}/artifacts/${artifact.id}/file`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
                >
                  打开{artifact.title}
                  <ExternalLink size={12} />
                </a>
              ))}
            </div>
          </section>
        )}

        <SavedAnalysisArtifacts
          artifacts={artifacts}
          open={savedArtifactsOpen}
          onClose={() => setSavedArtifactsOpen(false)}
        />

        {canSavePlaybook && (
          <section className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-muted/30 px-4 py-3">
            <div className="flex items-start gap-2.5">
              <ClipboardCheck
                size={16}
                className="mt-0.5 shrink-0 text-primary"
              />
              <div>
                <div className="text-sm font-medium text-foreground">
                  {playbookState === "saved"
                    ? "已保存为可复用分析"
                    : "这次方法验证通过"}
                </div>
                <div className="mt-0.5 text-xs leading-5 text-muted-foreground">
                  下次遇到同类数据时会沿用这套思路，并重新检查数据和结果。
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void handleSavePlaybook()}
                disabled={playbookState !== "idle"}
                className="border border-primary/40 bg-background px-3 py-2 text-xs font-semibold text-primary hover:bg-primary/5 disabled:cursor-default disabled:opacity-60"
              >
                {playbookState === "saving"
                  ? "正在保存…"
                  : playbookState === "saved"
                    ? "方法已保存"
                    : "下次继续这样分析"}
              </button>
              {playbookState === "saved" && (
                <button
                  type="button"
                  onClick={() => void handleCreateStanding()}
                  disabled={standingState !== "idle"}
                  className="bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:cursor-default disabled:opacity-60"
                >
                  {standingState === "saving"
                    ? "正在开始关注…"
                    : standingState === "saved"
                      ? "已持续关注"
                      : "持续关注变化"}
                </button>
              )}
            </div>
            {playbookError && (
              <p className="w-full text-xs leading-5 text-destructive">
                {playbookError}
              </p>
            )}
            {playbookState === "saved" &&
              standingState !== "saved" &&
              !standingError && (
                <p className="w-full text-xs leading-5 text-muted-foreground">
                  持续关注会在数据变化或间隔一天后重新核对；关键指标变化超过 10%
                  才提醒你。
                </p>
              )}
            {standingError && (
              <p className="w-full text-xs leading-5 text-destructive">
                {standingError}
              </p>
            )}
          </section>
        )}

        {nextActions.length ? (
          <section className="mt-7">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              下一步建议
            </h3>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {nextActions.map((action) => (
                <button
                  key={action.prompt}
                  onClick={() => onUsePrompt(action.prompt)}
                  className="group border border-border bg-background px-4 py-3 text-left transition-colors hover:border-primary/50"
                >
                  <span className="flex items-center justify-between gap-3 text-sm font-semibold text-foreground group-hover:text-primary">
                    <span>{action.label}</span>
                    {action.recommended ? (
                      <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-primary">
                        建议先做
                      </span>
                    ) : (
                      <ArrowRight
                        size={13}
                        className="text-muted-foreground group-hover:text-primary"
                      />
                    )}
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                    {action.reason}
                  </span>
                </button>
              ))}
            </div>
          </section>
        ) : report?.follow_ups?.length ? (
          <section className="mt-7">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              可以继续问
            </h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {report.follow_ups.map((question) => (
                <button
                  key={question}
                  onClick={() => onUsePrompt(question)}
                  className="group inline-flex items-center gap-2 border border-border bg-background px-3 py-2 text-left text-xs leading-5 text-foreground transition-colors hover:border-primary/50 hover:text-primary"
                >
                  {question}
                  <ArrowRight
                    size={13}
                    className="text-muted-foreground group-hover:text-primary"
                  />
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {canCorrectReport && (
          <section className="mt-7 border-t border-border pt-5">
            {(correctionState === "saved" || correctionState === "deleting") &&
            !correctionOpen ? (
              <div
                className={`flex flex-wrap items-start justify-between gap-3 border px-4 py-4 text-sm ${
                  projectCorrectionInactive || correctionExecutionBlocked
                    ? "border-border bg-muted/40 text-foreground"
                    : correctionReusable && !correctionExecutionVerified
                      ? "border-warning/30 bg-warning/[0.05] text-warning"
                      : "border-success/30 bg-success/[0.05] text-success"
                }`}
              >
                <div className="flex items-start gap-2.5">
                  {projectCorrectionInactive || correctionExecutionBlocked ? (
                    <AlertCircle size={16} className="mt-0.5 shrink-0" />
                  ) : (
                    <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
                  )}
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">
                        {projectCorrectionInactive
                          ? "这条项目口径已停用"
                          : correctionExecutionBlocked
                            ? "这条定义暂时不能用于调查"
                            : correctionReusable && !correctionPromoted
                              ? "已记录，尚未形成可复用定义"
                              : correctionReusable &&
                                  !correctionExecutionVerified
                                ? "已记住定义，执行方式尚未验证"
                                : correctionReusable
                                  ? "已记住定义"
                                  : "已记录这次修正"}
                      </span>
                      <span className="rounded-full border border-current/15 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                        {correctionKindLabel(
                          persistedCorrection?.correction_type,
                        )}
                      </span>
                    </div>
                    <div className="mt-0.5 text-xs leading-5 text-muted-foreground">
                      {projectCorrectionInactive
                        ? "它不会进入后续调查；可以在“数据”中重新启用。"
                        : correctionExecutionBlocked
                          ? "当前处理方式需要重新核对；在确认前不会自动使用。"
                          : correctionReusable && !correctionPromoted
                            ? "本次重新调查会带上这条修正；还不能明确绑定到数据，所以以后不会自动套用。"
                            : correctionReusable && correctionExecutionVerified
                              ? "这条定义和对应处理方式都已经核对；数据变化时仍会重新验证。"
                              : correctionReusable
                                ? "后续调查会带上这条定义，但不会仅因为记住了它就自动修改数据。"
                                : "它只用于重新检查这份报告，不会自动变成长期规则。"}
                    </div>
                    <blockquote className="mt-2 border-l border-current/25 pl-3 text-sm leading-6 text-foreground">
                      {currentCorrectionText}
                    </blockquote>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {correctionExecutionVerified ? (
                    <button
                      type="button"
                      disabled={correctionState === "deleting"}
                      onClick={onOpenUnderstanding || onOpenData}
                      className="px-2 py-2 text-xs font-medium text-muted-foreground hover:text-foreground disabled:cursor-wait disabled:opacity-60"
                    >
                      在数据中管理
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={correctionState === "deleting"}
                      onClick={() => {
                        setCorrectionText(currentCorrectionText);
                        setCorrectionKind(
                          persistedCorrection?.correction_type ||
                            "business_rule",
                        );
                        setCorrectionTargetRef(
                          persistedCorrection?.target_ref || null,
                        );
                        setCorrectionSelection(
                          persistedCorrection?.selection || null,
                        );
                        setCorrectionReusable(
                          persistedCorrection?.scope === "project",
                        );
                        setCorrectionError(null);
                        setCorrectionState("idle");
                        setCorrectionOpen(true);
                      }}
                      className="px-2 py-2 text-xs font-medium text-muted-foreground hover:text-foreground disabled:cursor-wait disabled:opacity-60"
                    >
                      修改
                    </button>
                  )}
                  {persistedCorrection && (
                    <button
                      type="button"
                      disabled={correctionState === "deleting"}
                      onClick={() => void handleDeleteCorrection()}
                      className="px-2 py-2 text-xs font-medium text-muted-foreground hover:text-foreground disabled:cursor-wait disabled:opacity-60"
                    >
                      {correctionState === "deleting"
                        ? "正在撤销…"
                        : "撤销记录"}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={correctionState === "deleting"}
                    onClick={() =>
                      runPrompt(correctedInvestigationPrompt(), {
                        correctionId: persistedCorrection?.id,
                      })
                    }
                    className="rounded-md bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:cursor-wait disabled:opacity-60"
                  >
                    按修正重新调查
                  </button>
                </div>
                {correctionError && (
                  <p
                    className="basis-full text-xs leading-5 text-destructive"
                    role="alert"
                  >
                    {correctionError}
                  </p>
                )}
              </div>
            ) : !correctionOpen ? (
              <button
                type="button"
                onClick={() => setCorrectionOpen(true)}
                className="inline-flex items-center gap-2 rounded-md px-1 py-1.5 text-sm text-muted-foreground transition-colors hover:text-primary"
              >
                <MessageSquareWarning size={16} />
                结论有偏差或口径不对？纠正这次理解
              </button>
            ) : (
              <div className="rounded-lg border border-warning/30 bg-warning/[0.05] px-4 py-4">
                {correctionTargets.length > 0 && (
                  <fieldset>
                    <legend className="text-sm font-semibold text-foreground">
                      你要修正哪一项？
                    </legend>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      <label
                        className={`cursor-pointer rounded-md border px-3 py-2.5 transition-colors ${
                          correctionTargetRef === null
                            ? "border-primary bg-card text-foreground"
                            : "border-warning/30 bg-card/60 text-muted-foreground hover:border-primary/40"
                        }`}
                      >
                        <input
                          type="radio"
                          name={`report-correction-target-${index}`}
                          checked={correctionTargetRef === null}
                          onChange={() => {
                            setCorrectionTargetRef(null);
                            setCorrectionSelection(null);
                            setCorrectionReusable(false);
                          }}
                          disabled={correctionState === "saving"}
                          className="sr-only"
                        />
                        <span className="block text-xs font-semibold">
                          整体结论 / 其他
                        </span>
                        <span className="mt-0.5 block text-[11px] leading-4">
                          修正报告整体判断，或列表里没有的内容
                        </span>
                      </label>
                      {correctionTargets.map((target) => {
                        const selected =
                          correctionTargetRef === target.target_ref;
                        return (
                          <label
                            key={target.target_ref}
                            className={`cursor-pointer rounded-md border px-3 py-2.5 transition-colors ${
                              selected
                                ? "border-primary bg-card text-foreground"
                                : "border-warning/30 bg-card/60 text-muted-foreground hover:border-primary/40"
                            }`}
                          >
                            <input
                              type="radio"
                              name={`report-correction-target-${index}`}
                              value={target.target_ref}
                              checked={selected}
                              onChange={() => {
                                if (correctionTargetRef !== target.target_ref) {
                                  setCorrectionSelection(null);
                                }
                                setCorrectionTargetRef(target.target_ref);
                                setCorrectionKind(target.correction_type);
                              }}
                              disabled={correctionState === "saving"}
                              className="sr-only"
                            />
                            <span className="block text-xs font-semibold">
                              {target.label}
                            </span>
                            {target.description && (
                              <span className="mt-0.5 block text-[11px] leading-4">
                                {target.description}
                              </span>
                            )}
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>
                )}
                {!hasBoundCorrectionTarget && (
                  <fieldset
                    className={
                      correctionTargets.length > 0 ? "mt-4" : undefined
                    }
                  >
                    <legend className="text-sm font-semibold text-foreground">
                      这次问题出在哪里？
                    </legend>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {CORRECTION_KINDS.map((kind) => {
                        const selected = correctionKind === kind.value;
                        return (
                          <label
                            key={kind.value}
                            className={`cursor-pointer rounded-md border px-3 py-2.5 transition-colors ${
                              selected
                                ? "border-primary bg-card text-foreground"
                                : "border-warning/30 bg-card/60 text-muted-foreground hover:border-primary/40"
                            }`}
                          >
                            <input
                              type="radio"
                              name={`report-correction-kind-${index}`}
                              value={kind.value}
                              checked={selected}
                              onChange={() => {
                                setCorrectionKind(kind.value);
                                setCorrectionSelection(null);
                              }}
                              disabled={correctionState === "saving"}
                              className="sr-only"
                            />
                            <span className="block text-xs font-semibold">
                              {kind.label}
                            </span>
                            <span className="mt-0.5 block text-[11px] leading-4">
                              {kind.description}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>
                )}
                {correctionTargetsFetching && (
                  <p
                    className="mt-3 text-xs leading-5 text-muted-foreground"
                    role="status"
                  >
                    正在确认这份报告里哪些口径可以安全复用…
                  </p>
                )}
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {hasBoundCorrectionTarget
                    ? "先保存这次修正；需要时可以让这个明确口径在以后继续使用。"
                    : correctionTargetsFailed
                      ? "目标暂时无法核对，这次修正仍可保存，但只作用于当前报告。"
                      : "没有选择具体口径时，这次修正只作用于当前报告。"}
                </p>
                <label
                  htmlFor={`report-correction-${index}`}
                  className="mt-3 block text-xs font-medium text-foreground"
                >
                  正确的理解是什么？
                </label>
                <textarea
                  id={`report-correction-${index}`}
                  value={correctionText}
                  onChange={(event) => setCorrectionText(event.target.value)}
                  disabled={correctionState === "saving"}
                  rows={3}
                  autoFocus
                  placeholder={
                    CORRECTION_KINDS.find(
                      (kind) => kind.value === correctionKind,
                    )?.placeholder
                  }
                  className="mt-2 w-full resize-y rounded-md border border-warning/30 bg-card px-3 py-2.5 text-sm leading-6 text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-primary"
                />
                <label className="mt-3 flex cursor-pointer items-start gap-2.5 text-xs leading-5 text-foreground">
                  <input
                    type="checkbox"
                    checked={correctionReusable}
                    onChange={(event) => {
                      if (event.target.checked && !hasBoundCorrectionTarget)
                        return;
                      setCorrectionReusable(event.target.checked);
                    }}
                    aria-disabled={!hasBoundCorrectionTarget}
                    disabled={
                      correctionState === "saving" ||
                      (!hasBoundCorrectionTarget && !correctionReusable)
                    }
                    className="mt-1 h-3.5 w-3.5 accent-[hsl(var(--primary))]"
                  />
                  <span>
                    <span className="font-medium">
                      以后遇到同类问题也按这个口径
                    </span>
                    <span className="block text-muted-foreground">
                      {hasBoundCorrectionTarget
                        ? "不勾选时只重做当前报告；长期使用前仍会重新核对真实数据。"
                        : "先选择上方一个明确的业务项，才能用于以后的调查。"}
                    </span>
                  </span>
                </label>
                {correctionReusable &&
                  boundCorrectionType === "metric_definition" && (
                    <fieldset className="mt-3 border-t border-warning/30 pt-3">
                      <legend className="text-xs font-semibold text-foreground">
                        这个指标应该读取哪个数值字段？
                      </legend>
                      <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
                        这里只列出本次调查中可重新绑定的数据字段；保存后仍会用真实数据重跑并验证。
                      </p>
                      {correctionTargetOptionsFetching ? (
                        <p
                          className="mt-2 text-xs text-muted-foreground"
                          role="status"
                        >
                          正在核对可用字段…
                        </p>
                      ) : correctionTargetOptionsFailed ? (
                        <p
                          className="mt-2 text-xs leading-5 text-warning"
                          role="alert"
                        >
                          暂时无法读取字段选项；可以稍后重试，或先只保存文字口径。
                        </p>
                      ) : correctionTargetOptions.length > 0 ? (
                        <div className="mt-2 grid gap-2 sm:grid-cols-2">
                          {correctionTargetOptions.map((option) => {
                            const selected =
                              effectiveMetricSelection?.kind ===
                                "metric_column" &&
                              effectiveMetricSelection.field_ref ===
                                option.field_ref;
                            return (
                              <label
                                key={option.field_ref}
                                className={`cursor-pointer rounded-md border px-3 py-2.5 transition-colors ${
                                  selected
                                    ? "border-primary bg-card text-foreground"
                                    : "border-warning/30 bg-card/60 text-muted-foreground hover:border-primary/40"
                                }`}
                              >
                                <input
                                  type="radio"
                                  name={`report-correction-metric-field-${index}`}
                                  value={option.field_ref}
                                  checked={selected}
                                  onChange={() =>
                                    setCorrectionSelection({
                                      kind: "metric_column",
                                      field_ref: option.field_ref,
                                    })
                                  }
                                  disabled={correctionState === "saving"}
                                  className="sr-only"
                                />
                                <span className="block text-xs font-semibold">
                                  {option.label}
                                </span>
                                <span className="mt-0.5 block text-[11px] leading-4">
                                  {option.description}
                                </span>
                              </label>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">
                          当前报告里没有可安全绑定的数值字段；文字口径仍可保存，但不会假装已经能自动执行。
                        </p>
                      )}
                    </fieldset>
                  )}
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled={
                      !correctionText.trim() ||
                      correctionState === "saving" ||
                      (correctionReusable && !hasBoundCorrectionTarget) ||
                      metricSelectionPending ||
                      metricSelectionRequired
                    }
                    onClick={() => void handleSaveCorrection()}
                    className="rounded-md bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {correctionState === "saving" ? "正在保存…" : "保存修正"}
                  </button>
                  <button
                    type="button"
                    disabled={correctionState === "saving"}
                    onClick={() => {
                      setCorrectionText(currentCorrectionText);
                      setCorrectionKind(
                        persistedCorrection?.correction_type || "business_rule",
                      );
                      setCorrectionTargetRef(
                        persistedCorrection?.target_ref || null,
                      );
                      setCorrectionSelection(
                        persistedCorrection?.selection || null,
                      );
                      setCorrectionReusable(
                        persistedCorrection?.scope === "project",
                      );
                      setCorrectionOpen(false);
                      setCorrectionError(null);
                    }}
                    className="px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
                  >
                    取消
                  </button>
                </div>
                {correctionError && (
                  <p
                    className="mt-2 text-xs leading-5 text-destructive"
                    role="alert"
                  >
                    {correctionError}
                  </p>
                )}
              </div>
            )}
          </section>
        )}

      </div>
    </article>
  );
}
