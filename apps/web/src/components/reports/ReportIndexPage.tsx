"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  BarChart3,
  BookOpenText,
  CircleAlert,
  FilePlus2,
  Loader2,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  createReport,
  deleteReport,
  listReports,
  type ReportListItem,
} from "@/lib/reports";
import {
  normalizeConversationId,
  storedConversationIdForProject,
  useChatStore,
} from "@/lib/stores/chat";
import { useArmedAction } from "@/lib/hooks/useArmedAction";

function reportContextQuery(
  fromRun: string,
  fromConversation: string | null
): string {
  const params = new URLSearchParams();
  if (fromRun) params.set("fromRun", fromRun);
  if (fromConversation) params.set("fromConversation", fromConversation);
  const query = params.toString();
  return query ? `?${query}` : "";
}

function updatedLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "最近更新";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : "报告没有加载完成，请重试。";
}

export function ReportIndexPage({ projectId }: { projectId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromRun = searchParams.get("fromRun")?.trim() || "";
  const requestedConversationId = normalizeConversationId(
    searchParams.get("fromConversation")
  );
  const {
    currentConversationId,
    currentConversationMeta,
    lastProjectId,
  } = useChatStore();
  const [storedConversationId, setStoredConversationId] = useState<string | null>(null);
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const { armedId: armedDeleteId, request: requestDelete } = useArmedAction();
  const [error, setError] = useState<string | null>(null);
  const liveConversationId =
    currentConversationId &&
    (currentConversationMeta?.project_id === projectId || lastProjectId === projectId)
      ? currentConversationId
      : null;
  const sourceConversationId =
    requestedConversationId || liveConversationId || storedConversationId;
  const contextQuery = reportContextQuery(fromRun, sourceConversationId);
  const projectHref = sourceConversationId
    ? `/?conversation=${encodeURIComponent(sourceConversationId)}`
    : "/";

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReports(await listReports(projectId));
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setStoredConversationId(storedConversationIdForProject(projectId));
  }, [projectId]);

  const handleCreate = async () => {
    if (creating) return;
    setCreating(true);
    setError(null);
    try {
      const report = await createReport(projectId, {
        title: "新报告",
        pages: [
          {
            id: `local-page-${Date.now()}`,
            title: "概览",
            order_index: 0,
            config: {},
            blocks: [],
          },
        ],
      });
      router.push(`/projects/${projectId}/reports/${report.id}${contextQuery}`);
    } catch (nextError) {
      setError(errorMessage(nextError));
      setCreating(false);
    }
  };

  const handleDelete = async (report: ReportListItem) => {
    if (deletingId) return;
    setDeletingId(report.id);
    setError(null);
    try {
      await deleteReport(projectId, report.id);
      setReports((current) => current.filter((item) => item.id !== report.id));
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-5 px-5 md:px-10">
          <div className="flex min-w-0 items-center gap-4">
            <Link
              href={projectHref}
              aria-label="返回项目"
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <ArrowLeft size={17} />
            </Link>
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold tracking-[-0.02em]">报告</h1>
              <p className="mt-0.5 text-[11px] text-muted-foreground">整理、编辑和交付分析结果</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href={`/projects/${projectId}/understanding`}
              className="hidden h-9 items-center gap-2 px-3 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:inline-flex"
            >
              <BookOpenText size={15} />
              项目理解
            </Link>
            <button
              type="button"
              onClick={handleCreate}
              disabled={creating}
              className="inline-flex h-9 items-center gap-2 bg-primary px-4 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {creating ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
              新建报告
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1440px] px-5 py-10 md:px-10 md:py-14">
        {fromRun && (
          <div className="mb-7 flex items-center gap-3 border border-primary/25 bg-primary/[0.045] px-4 py-3 text-xs text-foreground">
            <FilePlus2 size={15} className="shrink-0 text-primary" />
            <span>选择一份报告，调查内容会在打开后供你挑选。</span>
          </div>
        )}
        <div className="mb-8 flex items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-primary">
              <BarChart3 size={15} />
              报告工作台
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.035em] md:text-3xl">
              把调查结果变成自己的报告
            </h2>
          </div>
          {!loading && reports.length > 0 && (
            <span className="text-xs tabular-nums text-muted-foreground">{reports.length} 份报告</span>
          )}
        </div>

        {error && reports.length > 0 && (
          <div role="alert" className="mb-6 flex items-center justify-between gap-4 border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            <span>{error}</span>
            <button type="button" onClick={() => void load()} className="inline-flex shrink-0 items-center gap-1.5 font-medium hover:underline">
              <RefreshCw size={13} />
              重试
            </button>
          </div>
        )}

        {loading ? (
          <div className="flex min-h-72 items-center justify-center text-sm text-muted-foreground">
            <Loader2 size={18} className="mr-2 animate-spin" />
            正在打开报告
          </div>
        ) : error ? (
          <section
            role="alert"
            className="flex min-h-[360px] flex-col items-center justify-center border border-destructive/25 bg-card px-6 text-center"
          >
            <CircleAlert size={28} strokeWidth={1.5} className="text-destructive" />
            <h3 className="mt-5 text-lg font-semibold">报告暂时没有打开</h3>
            <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{error}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="mt-6 inline-flex h-10 items-center gap-2 border border-border px-5 text-sm font-semibold text-foreground transition-colors hover:bg-muted"
            >
              <RefreshCw size={14} />
              重试
            </button>
          </section>
        ) : reports.length === 0 ? (
          <section className="flex min-h-[420px] flex-col items-center justify-center border border-border bg-card px-6 text-center">
            <FilePlus2 size={28} strokeWidth={1.5} className="text-primary" />
            <h3 className="mt-5 text-lg font-semibold">从一张空白报告开始</h3>
            <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
              你可以自己添加内容，也可以把已有调查中的指标、图表和明细放进来继续编辑。
            </p>
            <button
              type="button"
              onClick={handleCreate}
              disabled={creating}
              className="mt-6 inline-flex h-10 items-center gap-2 bg-primary px-5 text-sm font-semibold text-primary-foreground disabled:opacity-50"
            >
              {creating ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
              新建报告
            </button>
          </section>
        ) : (
          <ol className="grid grid-cols-1 gap-px overflow-hidden border border-border bg-border md:grid-cols-2 xl:grid-cols-3">
            {reports.map((report) => (
              <li key={report.id} className="group relative min-h-56 bg-card">
                <Link
                  href={`/projects/${projectId}/reports/${report.id}${contextQuery}`}
                  className="flex h-full flex-col px-6 py-6 outline-none transition-colors hover:bg-primary/[0.025] focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="inline-flex h-8 w-8 items-center justify-center bg-primary/10 text-primary">
                      <BarChart3 size={16} />
                    </span>
                    <MoreHorizontal size={17} className="text-muted-foreground" />
                  </div>
                  <h3 className="mt-7 line-clamp-2 text-lg font-semibold tracking-[-0.025em] group-hover:text-primary">
                    {report.title}
                  </h3>
                  <p className="mt-2 line-clamp-2 min-h-10 text-xs leading-5 text-muted-foreground">
                    {report.description || "打开后可添加页面、图表、明细和文字。"}
                  </p>
                  <div className="mt-auto flex items-center justify-between gap-3 pt-7 text-[11px] text-muted-foreground">
                    <span>{report.page_count} 页 · {report.block_count} 个区块</span>
                    <span>{updatedLabel(report.updated_at)}</span>
                  </div>
                </Link>
                <button
                  type="button"
                  aria-label={armedDeleteId === report.id ? "确认删除" : `删除报告：${report.title}`}
                  disabled={deletingId === report.id}
                  onClick={() => requestDelete(report.id, () => void handleDelete(report))}
                  className={
                    armedDeleteId === report.id
                      ? "absolute right-4 top-4 inline-flex h-8 items-center justify-center border border-destructive/50 bg-destructive/10 px-2.5 text-[11px] font-semibold text-destructive transition-all"
                      : "absolute right-4 top-4 inline-flex h-8 w-8 items-center justify-center border border-border bg-card text-muted-foreground opacity-0 transition-all hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 focus:opacity-100 disabled:opacity-50"
                  }
                >
                  {deletingId === report.id ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : armedDeleteId === report.id ? (
                    "确认删除"
                  ) : (
                    <Trash2 size={14} />
                  )}
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    </main>
  );
}
