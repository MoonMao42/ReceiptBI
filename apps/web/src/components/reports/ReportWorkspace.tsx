"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  CircleAlert,
  Download,
  Eye,
  FileText,
  FileSpreadsheet,
  LayoutDashboard,
  Loader2,
  PanelLeftClose,
  PanelRightClose,
  PencilLine,
  Plus,
  Printer,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
} from "lucide-react";
import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  exportReportExcel,
  getReport,
  ReportConflictError,
  updateReport,
  type ReportBlock,
  type ReportBlockType,
  type ReportDocument,
  type ReportPage,
} from "@/lib/reports";
import type { AnalysisArtifact, AnalysisRunSummary } from "@/lib/types/api";
import { cn } from "@/lib/utils";
import {
  normalizeConversationId,
  storedConversationIdForProject,
  useChatStore,
} from "@/lib/stores/chat";
import { InvestigationPicker } from "./InvestigationPicker";
import { ReportBlockCard } from "./ReportBlockCard";
import { ReportPrintView } from "./ReportPrintView";
import { ReportPropertyPanel } from "./ReportPropertyPanel";
import { createInvestigationReportDraft } from "./report-draft";
import {
  REPORT_BLOCK_OPTIONS,
  applyReportBlockUpdates,
  applyStaticReportFilters,
  blockTypeLabel,
  createLocalId,
  createManualBlock,
  createReportPage,
  reflowBlocks,
  type ActiveReportFilter,
  type ReportFilterOperator,
} from "./report-blocks";

type SaveState = "idle" | "saving" | "saved" | "error" | "conflict";

const WIDTH_STEPS = [3, 4, 6, 8, 12];
const FILTER_OPERATORS = new Set<ReportFilterOperator>([
  "contains",
  "equals",
  "not_equals",
  "greater_than",
  "greater_or_equal",
  "less_than",
  "less_or_equal",
]);

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : "报告没有打开，请重试。";
}

function savedTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "已保存";
  return `保存于 ${new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date)}`;
}

function orderedPages(report: ReportDocument): ReportPage[] {
  return [...report.pages].sort((left, right) => left.order_index - right.order_index);
}

function totalBlocks(report: ReportDocument): number {
  return report.pages.reduce((total, page) => total + page.blocks.length, 0);
}

function exportFileName(title: string, extension: "xlsx"): string {
  const safeTitle = title.trim().replace(/[\\/:*?"<>|]/g, "-") || "报告";
  return `${safeTitle}.${extension}`;
}

function uniquePageTitle(title: string, usedTitles: Set<string>): string {
  const normalized = title.trim() || "页面";
  let candidate = normalized;
  let suffix = 2;
  while (usedTitles.has(candidate.toLocaleLowerCase())) {
    const suffixText = ` ${suffix}`;
    candidate = `${normalized.slice(0, 160 - suffixText.length)}${suffixText}`;
    suffix += 1;
  }
  usedTitles.add(candidate.toLocaleLowerCase());
  return candidate;
}

function downloadBlob(blob: Blob, fileName: string): void {
  if (typeof URL.createObjectURL !== "function") return;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

async function waitForPrintLayout(): Promise<void> {
  await document.fonts?.ready;
  if (typeof window.requestAnimationFrame !== "function") return;
  await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
  const images = Array.from(
    document.querySelectorAll<HTMLImageElement>(".report-print-view img")
  );
  await Promise.all(
    images.map(async (image) => {
      if (typeof image.decode === "function") {
        await image.decode().catch(() => undefined);
        return;
      }
      if (image.complete) return;
      await new Promise<void>((resolve) => {
        image.addEventListener("load", () => resolve(), { once: true });
        image.addEventListener("error", () => resolve(), { once: true });
      });
    })
  );
  await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
}

function gridStyle(block: ReportBlock): CSSProperties {
  return {
    "--report-column": `${block.layout.x + 1} / span ${block.layout.w}`,
    "--report-row": `${block.layout.y + 1} / span ${block.layout.h}`,
  } as CSSProperties;
}

function remapValues(
  values: Record<string, string>,
  ids: Map<string, string>
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(values).map(([id, value]) => [ids.get(id) || id, value])
  );
}

interface SaveReconciliation {
  report: ReportDocument;
  pageIds: Map<string, string>;
  blockIds: Map<string, string>;
}

export function reconcileReportAfterSave(
  current: ReportDocument,
  sent: ReportDocument,
  saved: ReportDocument
): SaveReconciliation {
  const pageIds = new Map<string, string>();
  const blockIds = new Map<string, string>();

  const pages = current.pages.map((currentPage) => {
    const sentPageIndex = sent.pages.findIndex((page) => page.id === currentPage.id);
    if (sentPageIndex < 0) return currentPage;
    const sentPage = sent.pages[sentPageIndex];
    const savedPage = sentPage.id.startsWith("local-")
      ? saved.pages.find((page) => page.order_index === sentPage.order_index) ||
        saved.pages[sentPageIndex]
      : saved.pages.find((page) => page.id === sentPage.id);
    if (!savedPage) return currentPage;
    pageIds.set(currentPage.id, savedPage.id);

    const blocks = currentPage.blocks.map((currentBlock) => {
      const sentBlockIndex = sentPage.blocks.findIndex(
        (block) => block.id === currentBlock.id
      );
      if (sentBlockIndex < 0) return currentBlock;
      const sentBlock = sentPage.blocks[sentBlockIndex];
      const savedBlock = sentBlock.id.startsWith("local-")
        ? savedPage.blocks.find(
            (block) => block.order_index === sentBlock.order_index
          ) || savedPage.blocks[sentBlockIndex]
        : savedPage.blocks.find((block) => block.id === sentBlock.id);
      if (!savedBlock) return currentBlock;
      blockIds.set(currentBlock.id, savedBlock.id);
      return {
        ...currentBlock,
        id: savedBlock.id,
        version: savedBlock.version,
        created_at: savedBlock.created_at,
        updated_at: savedBlock.updated_at,
      };
    });

    return {
      ...currentPage,
      id: savedPage.id,
      version: savedPage.version,
      created_at: savedPage.created_at,
      updated_at: savedPage.updated_at,
      blocks,
    };
  });

  return {
    report: {
      ...current,
      version: saved.version,
      updated_at: saved.updated_at,
      extra_data: saved.extra_data,
      pages,
    },
    pageIds,
    blockIds,
  };
}

export function ReportWorkspace({
  projectId,
  reportId,
  initialRunId,
}: {
  projectId: string;
  reportId: string;
  initialRunId?: string;
}) {
  const searchParams = useSearchParams();
  const requestedConversationId = normalizeConversationId(
    searchParams.get("fromConversation")
  );
  const {
    currentConversationId,
    currentConversationMeta,
    lastProjectId,
  } = useChatStore();
  const [report, setReport] = useState<ReportDocument | null>(null);
  const [activePageId, setActivePageId] = useState<string | null>(null);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const [propertiesOpen, setPropertiesOpen] = useState(false);
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [investigationOpen, setInvestigationOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<"pdf" | "excel" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [printViewOpen, setPrintViewOpen] = useState(false);
  const [filterValues, setFilterValues] = useState<Record<string, string>>({});
  const [storedConversationId, setStoredConversationId] = useState<string | null>(null);
  const reportRef = useRef<ReportDocument | null>(null);
  const editRevisionRef = useRef(0);
  const liveConversationId =
    currentConversationId &&
    (currentConversationMeta?.project_id === projectId || lastProjectId === projectId)
      ? currentConversationId
      : null;
  const sourceConversationId =
    requestedConversationId || liveConversationId || storedConversationId;
  const reportListParams = new URLSearchParams();
  if (initialRunId) reportListParams.set("fromRun", initialRunId);
  if (sourceConversationId) {
    reportListParams.set("fromConversation", sourceConversationId);
  }
  const reportListQuery = reportListParams.toString();
  const reportListHref = `/projects/${projectId}/reports${
    reportListQuery ? `?${reportListQuery}` : ""
  }`;

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const next = await getReport(projectId, reportId);
      const pages = next.pages.length ? orderedPages(next) : [createReportPage("概览", 0)];
      const normalized = { ...next, pages };
      reportRef.current = normalized;
      editRevisionRef.current = 0;
      setReport(normalized);
      setActivePageId(pages[0]?.id || null);
      setSelectedBlockId(null);
      setEditing(Boolean(initialRunId) || totalBlocks(normalized) === 0);
      setInvestigationOpen(Boolean(initialRunId));
      setDirty(false);
      setSaveState("idle");
      setExportError(null);
      setExportMenuOpen(false);
    } catch (error) {
      setLoadError(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [initialRunId, projectId, reportId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setStoredConversationId(storedConversationIdForProject(projectId));
  }, [projectId]);

  useEffect(() => {
    setOutlineOpen(window.matchMedia("(min-width: 768px)").matches);
    setPropertiesOpen(window.matchMedia("(min-width: 1280px)").matches);
  }, []);

  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);

  const activePage = useMemo(
    () => report?.pages.find((page) => page.id === activePageId) || report?.pages[0] || null,
    [activePageId, report]
  );
  const selectedBlock = useMemo(
    () => activePage?.blocks.find((block) => block.id === selectedBlockId) || null,
    [activePage, selectedBlockId]
  );
  const activeFilters = useMemo<ActiveReportFilter[]>(() => {
    if (!activePage) return [];
    return activePage.blocks.flatMap((block) => {
      if (block.block_type !== "filter") return [];
      const field = typeof block.config.field === "string" ? block.config.field.trim() : "";
      const operatorValue =
        typeof block.config.operator === "string" ? block.config.operator : "contains";
      const operator = FILTER_OPERATORS.has(operatorValue as ReportFilterOperator)
        ? (operatorValue as ReportFilterOperator)
        : "contains";
      const value = filterValues[block.id] || "";
      return field && value.trim() ? [{ field, operator, value }] : [];
    });
  }, [activePage, filterValues]);

  const mutateReport = useCallback((updater: (current: ReportDocument) => ReportDocument) => {
    editRevisionRef.current += 1;
    setReport((current) => {
      if (!current) return current;
      const next = updater(current);
      reportRef.current = next;
      return next;
    });
    setDirty(true);
    setSaveState((current) => (current === "saving" ? current : "idle"));
    setSaveError(null);
  }, []);

  const replacePage = useCallback(
    (pageId: string, updater: (page: ReportPage) => ReportPage) => {
      mutateReport((current) => ({
        ...current,
        pages: current.pages.map((page) => (page.id === pageId ? updater(page) : page)),
      }));
    },
    [mutateReport]
  );

  const changePage = (updates: Partial<ReportPage>) => {
    if (!activePage) return;
    replacePage(activePage.id, (page) => ({ ...page, ...updates }));
  };

  const changeBlock = (updates: Partial<ReportBlock>) => {
    if (!activePage || !selectedBlock) return;
    replacePage(activePage.id, (page) => {
      const blocks = page.blocks.map((block) =>
        block.id === selectedBlock.id
          ? applyReportBlockUpdates(block, updates)
          : block
      );
      return {
        ...page,
        blocks: updates.layout ? reflowBlocks(blocks) : blocks,
      };
    });
  };

  const addBlock = (type: ReportBlockType) => {
    if (!activePage) return;
    const block = createManualBlock(type);
    replacePage(activePage.id, (page) => ({
      ...page,
      blocks: reflowBlocks([...page.blocks, block]),
    }));
    setSelectedBlockId(block.id);
    setPropertiesOpen(true);
    if (window.matchMedia("(max-width: 767px)").matches) setOutlineOpen(false);
    setAddMenuOpen(false);
  };

  const addImportedBlocks = (blocks: ReportBlock[]) => {
    if (!activePage || !blocks.length) return;
    replacePage(activePage.id, (page) => ({
      ...page,
      blocks: reflowBlocks([...page.blocks, ...blocks]),
    }));
    setSelectedBlockId(blocks[0].id);
    setPropertiesOpen(true);
    if (window.matchMedia("(max-width: 767px)").matches) setOutlineOpen(false);
  };

  const addGeneratedDraft = (
    run: AnalysisRunSummary,
    artifacts: AnalysisArtifact[]
  ) => {
    const currentReport = reportRef.current || report;
    if (!currentReport) return;
    const emptyReport = totalBlocks(currentReport) === 0;
    const retainedPages = emptyReport ? [] : currentReport.pages;
    const draft = createInvestigationReportDraft(
      run,
      artifacts,
      retainedPages.length
    );
    const usedTitles = new Set(
      retainedPages.map((page) => page.title.trim().toLocaleLowerCase())
    );
    const draftPages = draft.pages.map((page) => ({
      ...page,
      title: uniquePageTitle(page.title, usedTitles),
    }));
    const pages = [...retainedPages, ...draftPages].map((page, index) => ({
      ...page,
      order_index: index,
    }));

    mutateReport((current) => ({
      ...current,
      title: emptyReport ? draft.title : current.title,
      description: emptyReport ? draft.description : current.description,
      pages,
    }));
    setActivePageId(draftPages[0]?.id || pages[0]?.id || null);
    setSelectedBlockId(null);
    setEditing(true);
    setOutlineOpen(true);
    setPropertiesOpen(false);
    setExportError(null);
  };

  const moveBlock = (blockId: string, direction: -1 | 1) => {
    if (!activePage) return;
    replacePage(activePage.id, (page) => {
      const index = page.blocks.findIndex((block) => block.id === blockId);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= page.blocks.length) return page;
      const blocks = [...page.blocks];
      [blocks[index], blocks[target]] = [blocks[target], blocks[index]];
      return { ...page, blocks: reflowBlocks(blocks) };
    });
  };

  const resizeBlock = (blockId: string, direction: -1 | 1) => {
    if (!activePage) return;
    replacePage(activePage.id, (page) => {
      const blocks = page.blocks.map((block) => {
        if (block.id !== blockId) return block;
        const currentIndex = Math.max(0, WIDTH_STEPS.indexOf(block.layout.w));
        const nextIndex = Math.max(0, Math.min(WIDTH_STEPS.length - 1, currentIndex + direction));
        return { ...block, layout: { ...block.layout, w: WIDTH_STEPS[nextIndex] } };
      });
      return { ...page, blocks: reflowBlocks(blocks) };
    });
  };

  const duplicateBlock = (blockId: string) => {
    if (!activePage) return;
    const duplicateId = createLocalId("block");
    replacePage(activePage.id, (page) => {
      const index = page.blocks.findIndex((block) => block.id === blockId);
      if (index < 0) return page;
      const source = page.blocks[index];
      const copiedConfig = structuredClone(source.config);
      delete copiedConfig.manual_override;
      const copy: ReportBlock = {
        ...source,
        id: duplicateId,
        title: `${source.title} 副本`,
        source_kind: "manual",
        analysis_run_id: null,
        artifact_id: null,
        content: structuredClone(source.content),
        config: copiedConfig,
        layout: { ...source.layout },
      };
      delete copy.source_ref;
      delete copy.source_available;
      delete copy.version;
      delete copy.created_at;
      delete copy.updated_at;
      const blocks = [...page.blocks];
      blocks.splice(index + 1, 0, copy);
      return { ...page, blocks: reflowBlocks(blocks) };
    });
    setSelectedBlockId(duplicateId);
  };

  const deleteBlock = (blockId: string) => {
    if (!activePage) return;
    replacePage(activePage.id, (page) => ({
      ...page,
      blocks: reflowBlocks(page.blocks.filter((block) => block.id !== blockId)),
    }));
    if (selectedBlockId === blockId) setSelectedBlockId(null);
  };

  const addPage = () => {
    if (!report) return;
    const page = createReportPage(`页面 ${report.pages.length + 1}`, report.pages.length);
    mutateReport((current) => ({ ...current, pages: [...current.pages, page] }));
    setActivePageId(page.id);
    setSelectedBlockId(null);
  };

  const deletePage = (pageId: string) => {
    if (!report || report.pages.length <= 1) return;
    const nextPages = report.pages
      .filter((page) => page.id !== pageId)
      .map((page, index) => ({ ...page, order_index: index }));
    mutateReport((current) => ({ ...current, pages: nextPages }));
    if (activePageId === pageId) setActivePageId(nextPages[0].id);
    setSelectedBlockId(null);
  };

  const save = useCallback(async (): Promise<boolean> => {
    const currentReport = reportRef.current || report;
    if (!currentReport || saveState === "saving") return false;
    if (!dirty) return true;
    const sentRevision = editRevisionRef.current;
    const sentSnapshot = structuredClone(currentReport);
    setSaveState("saving");
    setSaveError(null);
    try {
      const saved = await updateReport(projectId, sentSnapshot.id, {
        title: sentSnapshot.title,
        description: sentSnapshot.description,
        status: sentSnapshot.status,
        expected_version: sentSnapshot.version,
        pages: sentSnapshot.pages,
      });
      if (editRevisionRef.current === sentRevision) {
        const identity = reconcileReportAfterSave(sentSnapshot, sentSnapshot, saved);
        reportRef.current = saved;
        setReport(saved);
        setActivePageId((current) =>
          current
            ? identity.pageIds.get(current) ||
              (saved.pages.some((page) => page.id === current)
                ? current
                : saved.pages[0]?.id || null)
            : saved.pages[0]?.id || null
        );
        setSelectedBlockId((current) =>
          current ? identity.blockIds.get(current) || current : current
        );
        setFilterValues((current) => remapValues(current, identity.blockIds));
        setDirty(false);
        setSaveState("saved");
        return true;
      } else {
        const latest = reportRef.current || currentReport;
        const reconciled = reconcileReportAfterSave(latest, sentSnapshot, saved);
        reportRef.current = reconciled.report;
        setReport(reconciled.report);
        setActivePageId((current) =>
          current ? reconciled.pageIds.get(current) || current : current
        );
        setSelectedBlockId((current) =>
          current ? reconciled.blockIds.get(current) || current : current
        );
        setFilterValues((current) => remapValues(current, reconciled.blockIds));
        setDirty(true);
        setSaveState("idle");
        return false;
      }
    } catch (error) {
      setSaveState(error instanceof ReportConflictError ? "conflict" : "error");
      setSaveError(errorMessage(error));
      return false;
    }
  }, [dirty, projectId, report, saveState]);

  const handleExportPdf = useCallback(async () => {
    if (exporting) return;
    setExportMenuOpen(false);
    setExportError(null);
    setExporting("pdf");
    try {
      if (!(await save())) {
        setExportError("请先保存最新修改后再导出。");
        return;
      }
      setPrintViewOpen(true);
      await waitForPrintLayout();
      window.print();
    } catch {
      setExportError("PDF 没有导出，请重试。");
    } finally {
      setPrintViewOpen(false);
      setExporting(null);
    }
  }, [exporting, save]);

  const handleExportExcel = useCallback(async () => {
    if (exporting) return;
    setExportMenuOpen(false);
    setExportError(null);
    setExporting("excel");
    try {
      if (!(await save())) {
        setExportError("请先保存最新修改后再导出。");
        return;
      }
      const currentReport = reportRef.current;
      if (!currentReport) return;
      const file = await exportReportExcel(projectId, currentReport.id);
      downloadBlob(file, exportFileName(currentReport.title, "xlsx"));
    } catch {
      setExportError("Excel 没有导出，请重试。");
    } finally {
      setExporting(null);
    }
  }, [exporting, projectId, save]);

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "s") {
        event.preventDefault();
        void save();
      }
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [save]);

  if (loading) {
    return (
      <main className="flex h-screen items-center justify-center bg-background text-sm text-muted-foreground">
        <Loader2 size={18} className="mr-2 animate-spin" />
        正在打开报告
      </main>
    );
  }

  if (loadError || !report || !activePage) {
    return (
      <main className="flex h-screen flex-col items-center justify-center bg-background px-6 text-center">
        <CircleAlert size={24} className="text-destructive" />
        <h1 className="mt-4 text-lg font-semibold">报告没有打开</h1>
        <p className="mt-2 text-sm text-muted-foreground">{loadError || "这份报告暂时不可用。"}</p>
        <button type="button" onClick={() => void load()} className="mt-5 inline-flex h-9 items-center gap-2 bg-primary px-4 text-xs font-semibold text-primary-foreground">
          <RefreshCw size={14} />
          重新打开
        </button>
      </main>
    );
  }

  return (
    <>
    <main className="report-screen-view flex h-screen min-h-0 flex-col overflow-hidden bg-background text-foreground">
      <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-border bg-card px-4 md:px-5">
        <div className="flex min-w-0 items-center gap-2">
          <Link href={reportListHref} aria-label="返回报告列表" className="inline-flex h-9 w-9 shrink-0 items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground">
            <ArrowLeft size={17} />
          </Link>
          {editing && (
            <button type="button" aria-label={outlineOpen ? "收起页面目录" : "展开页面目录"} onClick={() => {
              setOutlineOpen((current) => {
                if (!current && window.matchMedia("(max-width: 767px)").matches) {
                  setPropertiesOpen(false);
                }
                return !current;
              });
            }} className="inline-flex h-9 w-9 items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground">
              <PanelLeftClose size={16} className={!outlineOpen ? "rotate-180" : ""} />
            </button>
          )}
          <div className="min-w-0">
            {editing ? (
              <input
                value={report.title}
                aria-label="报告标题"
                maxLength={200}
                onChange={(event) => mutateReport((current) => ({ ...current, title: event.target.value }))}
                className="h-8 w-[min(42vw,420px)] min-w-36 truncate border-0 bg-transparent px-1 text-sm font-semibold outline-none focus:bg-muted/50"
              />
            ) : (
              <h1 className="max-w-[46vw] truncate text-sm font-semibold">{report.title}</h1>
            )}
            <p className="px-1 text-[10px] text-muted-foreground">
              {dirty ? "有尚未保存的修改" : savedTime(report.updated_at)}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {editing && (
            <>
              <div className="relative hidden sm:block">
                <button type="button" onClick={() => setAddMenuOpen((current) => !current)} className="inline-flex h-9 items-center gap-2 px-3 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground">
                  <Plus size={15} />
                  添加内容
                  <ChevronDown size={12} />
                </button>
                {addMenuOpen && (
                  <div className="absolute right-0 top-11 z-30 grid w-[360px] grid-cols-2 border border-border bg-popover p-2">
                    {REPORT_BLOCK_OPTIONS.map((option) => (
                      <button key={option.type} type="button" onClick={() => addBlock(option.type)} className="p-3 text-left hover:bg-muted">
                        <span className="block text-xs font-semibold">{option.label}</span>
                        <span className="mt-1 block text-[10px] leading-4 text-muted-foreground">{option.description}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <button type="button" onClick={() => setInvestigationOpen(true)} className="hidden h-9 items-center gap-2 px-3 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground sm:inline-flex">
                <Sparkles size={15} />
                智能整理
              </button>
              <button type="button" aria-label={propertiesOpen ? "收起设置" : "展开设置"} onClick={() => {
                setPropertiesOpen((current) => {
                  if (!current && window.matchMedia("(max-width: 767px)").matches) {
                    setOutlineOpen(false);
                  }
                  return !current;
                });
              }} className="inline-flex h-9 w-9 items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground">
                <PanelRightClose size={16} className={!propertiesOpen ? "rotate-180" : ""} />
              </button>
            </>
          )}

          <div className="relative">
            <button
              type="button"
              aria-label="导出报告"
              aria-expanded={exportMenuOpen}
              onClick={() => {
                setExportMenuOpen((current) => !current);
                setAddMenuOpen(false);
                setExportError(null);
              }}
              disabled={Boolean(exporting) || saveState === "saving"}
              className="inline-flex h-9 items-center gap-1.5 px-2.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-45"
            >
              {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
              <span className="hidden lg:inline">导出</span>
              <ChevronDown size={11} />
            </button>
            {exportMenuOpen && (
              <div className="absolute right-0 top-11 z-30 w-44 border border-border bg-popover p-1.5">
                <button
                  type="button"
                  onClick={() => void handleExportPdf()}
                  className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs font-medium hover:bg-muted"
                >
                  <Printer size={14} className="text-primary" />
                  导出 PDF
                </button>
                <button
                  type="button"
                  onClick={() => void handleExportExcel()}
                  className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs font-medium hover:bg-muted"
                >
                  <FileSpreadsheet size={14} className="text-primary" />
                  导出 Excel
                </button>
              </div>
            )}
          </div>

          <div className="flex h-9 items-center border border-border bg-background p-0.5">
            <button type="button" aria-pressed={!editing} aria-label="阅读报告" onClick={() => { setEditing(false); setAddMenuOpen(false); }} className={cn("inline-flex h-7 items-center gap-1.5 px-2.5 text-[11px] font-medium", !editing ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>
              <Eye size={13} />
              <span className="hidden md:inline">阅读</span>
            </button>
            <button type="button" aria-pressed={editing} aria-label="编辑报告" onClick={() => setEditing(true)} className={cn("inline-flex h-7 items-center gap-1.5 px-2.5 text-[11px] font-medium", editing ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>
              <PencilLine size={13} />
              <span className="hidden md:inline">编辑</span>
            </button>
          </div>

          {editing && (
            <button type="button" onClick={() => void save()} disabled={!dirty || saveState === "saving"} className="inline-flex h-9 min-w-20 items-center justify-center gap-2 bg-primary px-3 text-xs font-semibold text-primary-foreground disabled:opacity-45">
              {saveState === "saving" ? <Loader2 size={14} className="animate-spin" /> : saveState === "saved" ? <Check size={14} /> : <Save size={14} />}
              {saveState === "saving" ? "保存中" : saveState === "saved" ? "已保存" : "保存"}
            </button>
          )}
        </div>
      </header>

      {(saveState === "error" || saveState === "conflict" || exportError) && (
        <div role="alert" className="flex shrink-0 items-center justify-between gap-4 border-b border-destructive/25 bg-destructive/5 px-5 py-2.5 text-xs text-destructive">
          <span>{exportError || saveError}</span>
          {saveState === "conflict" && <button type="button" onClick={() => void load()} className="font-semibold hover:underline">重新载入</button>}
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {editing && outlineOpen && (
          <button
            type="button"
            aria-label="关闭页面目录"
            onClick={() => setOutlineOpen(false)}
            className="fixed inset-0 top-16 z-30 bg-slate-950/20 md:hidden"
          />
        )}
        {editing && outlineOpen && (
          <aside className="fixed bottom-0 left-0 top-16 z-40 flex h-auto min-h-0 w-[232px] shrink-0 flex-col border-r border-border bg-card shadow-xl md:relative md:inset-auto md:z-auto md:h-full md:shadow-none">
            <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
              <h2 className="text-xs font-semibold">页面与区块</h2>
              <button type="button" aria-label="添加页面" onClick={addPage} className="inline-flex h-7 w-7 items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground">
                <Plus size={14} />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto py-2">
              {orderedPages(report).map((page, pageIndex) => {
                const active = page.id === activePage.id;
                return (
                  <div key={page.id} className="mb-1">
                    <div className={cn("group flex items-center border-l-2 pr-2", active ? "border-primary bg-primary/[0.05]" : "border-transparent")}>
                      <button type="button" onClick={() => { setActivePageId(page.id); setSelectedBlockId(null); }} className="flex min-w-0 flex-1 items-center gap-2.5 px-3 py-2.5 text-left">
                        <span className="text-[10px] tabular-nums text-muted-foreground">{String(pageIndex + 1).padStart(2, "0")}</span>
                        <span className="truncate text-xs font-medium">{page.title}</span>
                      </button>
                      {report.pages.length > 1 && (
                        <button type="button" aria-label={`删除页面：${page.title}`} onClick={() => deletePage(page.id)} className="inline-flex h-7 w-7 items-center justify-center text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100 focus:opacity-100">
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                    {active && (
                      <ol className="ml-8 border-l border-border py-1">
                        {page.blocks.map((block) => (
                          <li key={block.id}>
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedBlockId(block.id);
                                setPropertiesOpen(true);
                                if (window.matchMedia("(max-width: 767px)").matches) {
                                  setOutlineOpen(false);
                                }
                                document.querySelector(`[data-report-block=\"${block.id}\"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
                              }}
                              className={cn("flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px]", selectedBlockId === block.id ? "font-medium text-primary" : "text-muted-foreground hover:text-foreground")}
                            >
                              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-60" />
                              <span className="truncate">{block.title || blockTypeLabel(block.block_type)}</span>
                            </button>
                          </li>
                        ))}
                        {!page.blocks.length && <li className="px-3 py-2 text-[10px] text-muted-foreground">还没有内容</li>}
                      </ol>
                    )}
                  </div>
                );
              })}
            </div>
          </aside>
        )}

        <section className="min-w-0 flex-1 overflow-y-auto bg-background">
          <div className={cn("mx-auto min-h-full px-5 pb-20 pt-8 md:px-8", editing ? "max-w-[1320px]" : "max-w-[1240px]")}>
            <div className="mb-8 border-b border-border pb-7">
              <div className="flex flex-wrap items-center justify-between gap-3 border-t-[3px] border-double border-foreground/45 pt-4">
                <div className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
                  <LayoutDashboard size={14} />
                  {activePage.title}
                </div>
                {!editing && (
                  <div className="font-mono text-[11px] tabular-nums tracking-[0.08em] text-muted-foreground">
                    凭证 {report.id.slice(0, 8).toUpperCase()} · v{report.version} · {report.updated_at.slice(0, 10)}
                  </div>
                )}
              </div>
              {!editing && <h2 className="mt-3 text-3xl font-semibold tracking-[-0.045em] md:text-4xl">{report.title}</h2>}
              {editing ? (
                <textarea
                  aria-label="报告说明"
                  value={report.description}
                  maxLength={4000}
                  onChange={(event) => mutateReport((current) => ({ ...current, description: event.target.value }))}
                  placeholder="为这份报告写一句说明"
                  rows={2}
                  className="mt-3 w-full resize-none bg-transparent text-sm leading-6 text-muted-foreground outline-none placeholder:text-muted-foreground/65"
                />
              ) : report.description ? (
                <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">{report.description}</p>
              ) : null}
              {!editing && report.pages.length > 1 && (
                <nav className="mt-6 flex flex-wrap gap-1" aria-label="报告页面">
                  {orderedPages(report).map((page) => (
                    <button key={page.id} type="button" aria-current={page.id === activePage.id ? "page" : undefined} onClick={() => setActivePageId(page.id)} className={cn("h-8 px-3 text-xs font-medium", page.id === activePage.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>{page.title}</button>
                  ))}
                </nav>
              )}
            </div>

            {activePage.blocks.length === 0 ? (
              <div className="flex min-h-[420px] flex-col items-center justify-center border border-dashed border-border bg-card/40 px-6 text-center">
                <FileText size={25} strokeWidth={1.5} className="text-primary" />
                <h3 className="mt-4 text-base font-semibold">这个页面还是空的</h3>
                <p className="mt-2 max-w-md text-xs leading-5 text-muted-foreground">自己添加指标、图表或文字，也可以直接使用已有调查里的内容。</p>
                {editing && (
                  <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
                    <button type="button" onClick={() => addBlock("text")} className="inline-flex h-9 items-center gap-2 border border-border bg-card px-4 text-xs font-medium hover:border-primary/50"><Plus size={14} />添加内容</button>
                    <button type="button" onClick={() => setInvestigationOpen(true)} className="inline-flex h-9 items-center gap-2 bg-primary px-4 text-xs font-semibold text-primary-foreground"><Sparkles size={14} />从调查添加</button>
                  </div>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 xl:grid-cols-12 xl:auto-rows-[72px]">
                {activePage.blocks.map((block) => {
                  const displayedBlock = applyStaticReportFilters(block, activeFilters);
                  return (
                  <div key={block.id} style={gridStyle(block)} className="min-h-0 xl:[grid-column:var(--report-column)] xl:[grid-row:var(--report-row)]">
                    <ReportBlockCard
                      block={displayedBlock}
                      editing={editing}
                      selected={selectedBlockId === block.id}
                      onSelect={() => { setSelectedBlockId(block.id); setPropertiesOpen(true); }}
                      onMove={(direction) => moveBlock(block.id, direction)}
                      onResize={(direction) => resizeBlock(block.id, direction)}
                      onDuplicate={() => duplicateBlock(block.id)}
                      onDelete={() => deleteBlock(block.id)}
                      filterValue={filterValues[block.id] || ""}
                      onFilterValueChange={(value) =>
                        setFilterValues((current) => ({ ...current, [block.id]: value }))
                      }
                    />
                  </div>
                  );
                })}
              </div>
            )}
          </div>
        </section>

        {editing && propertiesOpen && (
          <button
            type="button"
            aria-label="关闭区块设置"
            onClick={() => setPropertiesOpen(false)}
            className="fixed inset-0 top-16 z-30 bg-slate-950/20 xl:hidden"
          />
        )}
        {editing && propertiesOpen && (
          <div className="fixed bottom-0 right-0 top-16 z-40 h-auto min-h-0 shadow-xl xl:relative xl:inset-auto xl:z-auto xl:h-full xl:shadow-none">
            <ReportPropertyPanel page={activePage} block={selectedBlock} onChangePage={changePage} onChangeBlock={changeBlock} />
          </div>
        )}
      </div>

      <InvestigationPicker
        open={investigationOpen}
        projectId={projectId}
        initialRunId={initialRunId}
        onClose={() => setInvestigationOpen(false)}
        onAdd={addImportedBlocks}
        onGenerateDraft={addGeneratedDraft}
      />
    </main>
    {printViewOpen && (
      <ReportPrintView report={report} filterValues={filterValues} />
    )}
    </>
  );
}
