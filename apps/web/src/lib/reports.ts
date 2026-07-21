import { api } from "@/lib/api/client";
import type { AnalysisArtifact, AnalysisRunSummary } from "@/lib/types/api";

export type ReportStatus = "draft" | "published" | "archived";
export type ReportBlockType =
  | "metric"
  | "chart"
  | "table"
  | "text"
  | "evidence"
  | "filter";
export type ReportBlockSource = "manual" | "analysis_run" | "artifact";

export interface ReportBlockLayout {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ReportBlock {
  id: string;
  block_type: ReportBlockType;
  title: string;
  order_index: number;
  source_kind: ReportBlockSource;
  analysis_run_id?: string | null;
  artifact_id?: string | null;
  source_ref?: Record<string, unknown>;
  source_available?: boolean;
  content: Record<string, unknown>;
  layout: ReportBlockLayout;
  config: Record<string, unknown>;
  version?: number;
  created_at?: string;
  updated_at?: string;
}

export interface ReportPage {
  id: string;
  title: string;
  order_index: number;
  config: Record<string, unknown>;
  version?: number;
  created_at?: string;
  updated_at?: string;
  blocks: ReportBlock[];
}

export interface ReportDocument {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: ReportStatus;
  version: number;
  extra_data?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  pages: ReportPage[];
}

export interface ReportListItem {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: ReportStatus;
  version: number;
  page_count: number;
  block_count: number;
  created_at: string;
  updated_at: string;
}

export interface ReportCreateInput {
  title: string;
  description?: string;
  status?: ReportStatus;
  pages?: ReportPage[];
}

export interface ReportUpdateInput {
  title: string;
  description: string;
  status: ReportStatus;
  expected_version: number;
  pages: ReportPage[];
}

export class ReportConflictError extends Error {
  constructor(message = "这份报告已经在别处更新，请重新载入后再保存。") {
    super(message);
    this.name = "ReportConflictError";
  }
}

function responseData<T>(response: { data: unknown }): T {
  const body = response.data;
  if (
    typeof body === "object" &&
    body !== null &&
    "data" in body
  ) {
    return (body as { data: T }).data;
  }
  return body as T;
}

function normalizeError(error: unknown, fallback: string): Error {
  const candidate = error as {
    response?: { status?: number; data?: { detail?: string; message?: string } };
    message?: string;
  };
  if (candidate.response?.status === 409) {
    return new ReportConflictError();
  }
  const detail = candidate.response?.data?.detail;
  const visibleDetail =
    typeof detail === "string" && detail.trim().toLowerCase() !== "not found"
      ? detail
      : undefined;
  const message =
    visibleDetail ||
    candidate.response?.data?.message ||
    candidate.message;
  return new Error(typeof message === "string" && message.trim() ? message : fallback);
}

function persistedId(id: string): string | undefined {
  return id.startsWith("local-") ? undefined : id;
}

function serializeBlock(block: ReportBlock, orderIndex: number) {
  return {
    ...(persistedId(block.id) ? { id: block.id } : {}),
    block_type: block.block_type,
    title: block.title.trim() || "未命名区块",
    order_index: orderIndex,
    source_kind: block.source_kind,
    analysis_run_id: block.analysis_run_id || null,
    artifact_id: block.artifact_id || null,
    ...(block.source_ref ? { source_ref: block.source_ref } : {}),
    content: block.content,
    layout: block.layout,
    config: block.config,
  };
}

function serializePage(page: ReportPage) {
  return {
    ...(persistedId(page.id) ? { id: page.id } : {}),
    title: page.title.trim() || "未命名页面",
    order_index: page.order_index,
    config: page.config,
    blocks: page.blocks.map(serializeBlock),
  };
}

function normalizeDocument(document: ReportDocument): ReportDocument {
  return {
    ...document,
    description: (document.description as string | null) || "",
    pages: [...(document.pages || [])]
      .sort((left, right) => left.order_index - right.order_index)
      .map((page) => ({
        ...page,
        blocks: [...(page.blocks || [])]
          .sort((left, right) => left.order_index - right.order_index)
          .map((block) => ({
            ...block,
            title:
              (block.title as string | null) ||
              (block.block_type === "text" ? "文字" : "未命名区块"),
            order_index: Number.isFinite(block.order_index) ? block.order_index : 0,
            content: block.content || {},
            config: block.config || {},
            layout: {
              x: Number(block.layout?.x) || 0,
              y: Number(block.layout?.y) || 0,
              w: Number(block.layout?.w) || 6,
              h: Number(block.layout?.h) || 3,
            },
          })),
      })),
  };
}

function normalizeSummary(summary: ReportListItem): ReportListItem {
  return {
    ...summary,
    description: (summary.description as string | null) || "",
  };
}

export async function listReports(projectId: string): Promise<ReportListItem[]> {
  try {
    const response = await api.get(`/api/v1/projects/${projectId}/reports`);
    return responseData<ReportListItem[]>(response).map(normalizeSummary);
  } catch (error) {
    throw normalizeError(error, "报告没有加载完成，请重试。");
  }
}

export async function createReport(
  projectId: string,
  input: ReportCreateInput
): Promise<ReportDocument> {
  try {
    const response = await api.post(`/api/v1/projects/${projectId}/reports`, {
      title: input.title.trim() || "未命名报告",
      description: input.description?.trim() || "",
      status: input.status || "draft",
      pages: input.pages?.map(serializePage),
    });
    return normalizeDocument(responseData<ReportDocument>(response));
  } catch (error) {
    throw normalizeError(error, "报告没有创建成功，请重试。");
  }
}

export async function getReport(
  projectId: string,
  reportId: string
): Promise<ReportDocument> {
  try {
    const response = await api.get(
      `/api/v1/projects/${projectId}/reports/${reportId}`
    );
    return normalizeDocument(responseData<ReportDocument>(response));
  } catch (error) {
    throw normalizeError(error, "报告没有加载完成，请重试。");
  }
}

export async function updateReport(
  projectId: string,
  reportId: string,
  input: ReportUpdateInput
): Promise<ReportDocument> {
  try {
    const response = await api.patch(
      `/api/v1/projects/${projectId}/reports/${reportId}`,
      {
        title: input.title.trim() || "未命名报告",
        description: input.description.trim(),
        status: input.status,
        expected_version: input.expected_version,
        pages: input.pages.map(serializePage),
      }
    );
    return normalizeDocument(responseData<ReportDocument>(response));
  } catch (error) {
    throw normalizeError(error, "报告没有保存成功，请重试。");
  }
}

export async function deleteReport(
  projectId: string,
  reportId: string
): Promise<void> {
  try {
    await api.delete(`/api/v1/projects/${projectId}/reports/${reportId}`);
  } catch (error) {
    throw normalizeError(error, "报告没有删除成功，请重试。");
  }
}

export async function exportReportExcel(
  projectId: string,
  reportId: string
): Promise<Blob> {
  try {
    const response = await api.get(
      `/api/v1/projects/${projectId}/reports/${reportId}/export.xlsx`,
      { responseType: "blob" }
    );
    return response.data instanceof Blob
      ? response.data
      : new Blob([response.data], {
          type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
  } catch (error) {
    throw normalizeError(error, "Excel 没有导出，请重试。");
  }
}

export async function listReportAnalysisRuns(
  projectId: string
): Promise<AnalysisRunSummary[]> {
  try {
    const response = await api.get(`/api/v1/projects/${projectId}/analysis-runs`);
    return responseData<AnalysisRunSummary[]>(response);
  } catch (error) {
    throw normalizeError(error, "调查没有加载完成，请重试。");
  }
}

export async function listRunArtifacts(
  projectId: string,
  runId: string,
  signal?: AbortSignal
): Promise<AnalysisArtifact[]> {
  try {
    const response = await api.get(
      `/api/v1/projects/${projectId}/analysis-runs/${runId}/artifacts`,
      { signal }
    );
    return responseData<AnalysisArtifact[]>(response);
  } catch (error) {
    throw normalizeError(error, "调查内容没有加载完成，请重试。");
  }
}
