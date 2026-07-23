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
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  createReport,
  deleteReport,
  listReports,
  type ReportSerializationCopy,
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

function updatedLabel(value: string, locale: string, recent: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return recent;
  return new Intl.DateTimeFormat(locale, {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function ReportIndexPage({ projectId }: { projectId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const locale = useLocale();
  const t = useTranslations("reportIndex");
  const tBlocks = useTranslations("reportBlocks");
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
  const serializationCopy = useMemo<ReportSerializationCopy>(
    () => ({
      unnamedBlock: tBlocks("unnamedBlock"),
      textBlock: tBlocks("labelText"),
      unnamedPage: tBlocks("unnamedPage"),
      unnamedReport: tBlocks("unnamedReport"),
    }),
    [tBlocks]
  );
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
    } catch {
      setError(t("loadError"));
    } finally {
      setLoading(false);
    }
  }, [projectId, t]);

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
        title: t("newReportTitle"),
        pages: [
          {
            id: `local-page-${Date.now()}`,
            title: t("overviewPage"),
            order_index: 0,
            config: {},
            blocks: [],
          },
        ],
      }, serializationCopy);
      router.push(`/projects/${projectId}/reports/${report.id}${contextQuery}`);
    } catch {
      setError(t("createError"));
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
    } catch {
      setError(t("deleteError"));
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
              aria-label={t("backToProject")}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <ArrowLeft size={17} />
            </Link>
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold tracking-[-0.02em]">{t("title")}</h1>
              <p className="mt-0.5 text-[11px] text-muted-foreground">{t("subtitle")}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href={`/projects/${projectId}/understanding`}
              className="hidden h-9 items-center gap-2 px-3 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:inline-flex"
            >
              <BookOpenText size={15} />
              {t("projectUnderstanding")}
            </Link>
            <button
              type="button"
              onClick={handleCreate}
              disabled={creating}
              className="inline-flex h-9 items-center gap-2 bg-primary px-4 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {creating ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
              {t("newReport")}
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1440px] px-5 py-10 md:px-10 md:py-14">
        {fromRun && (
          <div className="mb-7 flex items-center gap-3 border border-primary/25 bg-primary/[0.045] px-4 py-3 text-xs text-foreground">
            <FilePlus2 size={15} className="shrink-0 text-primary" />
            <span>{t("selectReportHint")}</span>
          </div>
        )}
        <div className="mb-8 flex items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-primary">
              <BarChart3 size={15} />
              {t("workspaceLabel")}
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.035em] md:text-3xl">
              {t("workspaceTitle")}
            </h2>
          </div>
          {!loading && reports.length > 0 && (
            <span className="text-xs tabular-nums text-muted-foreground">{t("reportCount", { count: reports.length })}</span>
          )}
        </div>

        {error && reports.length > 0 && (
          <div role="alert" className="mb-6 flex items-center justify-between gap-4 border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            <span>{error}</span>
            <button type="button" onClick={() => void load()} className="inline-flex shrink-0 items-center gap-1.5 font-medium hover:underline">
              <RefreshCw size={13} />
              {t("retry")}
            </button>
          </div>
        )}

        {loading ? (
          <div className="flex min-h-72 items-center justify-center text-sm text-muted-foreground">
            <Loader2 size={18} className="mr-2 animate-spin" />
            {t("loading")}
          </div>
        ) : error ? (
          <section
            role="alert"
            className="flex min-h-[360px] flex-col items-center justify-center border border-destructive/25 bg-card px-6 text-center"
          >
            <CircleAlert size={28} strokeWidth={1.5} className="text-destructive" />
            <h3 className="mt-5 text-lg font-semibold">{t("unavailableTitle")}</h3>
            <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{error}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="mt-6 inline-flex h-10 items-center gap-2 border border-border px-5 text-sm font-semibold text-foreground transition-colors hover:bg-muted"
            >
              <RefreshCw size={14} />
              {t("retry")}
            </button>
          </section>
        ) : reports.length === 0 ? (
          <section className="flex min-h-[420px] flex-col items-center justify-center border border-border bg-card px-6 text-center">
            <FilePlus2 size={28} strokeWidth={1.5} className="text-primary" />
            <h3 className="mt-5 text-lg font-semibold">{t("emptyTitle")}</h3>
            <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
              {t("emptyDescription")}
            </p>
            <button
              type="button"
              onClick={handleCreate}
              disabled={creating}
              className="mt-6 inline-flex h-10 items-center gap-2 bg-primary px-5 text-sm font-semibold text-primary-foreground disabled:opacity-50"
            >
              {creating ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
              {t("newReport")}
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
                    {report.description || t("defaultDescription")}
                  </p>
                  <div className="mt-auto flex items-center justify-between gap-3 pt-7 text-[11px] text-muted-foreground">
                    <span>{t("reportStats", { pages: report.page_count, blocks: report.block_count })}</span>
                    <span>{updatedLabel(report.updated_at, locale, t("recent"))}</span>
                  </div>
                </Link>
                <button
                  type="button"
                  aria-label={
                    armedDeleteId === report.id
                      ? t("confirmDelete")
                      : t("deleteReport", { title: report.title })
                  }
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
                    t("confirmDelete")
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
