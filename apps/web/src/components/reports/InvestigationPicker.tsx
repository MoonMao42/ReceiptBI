"use client";

import {
  ArrowLeft,
  BarChart3,
  Check,
  FileText,
  Loader2,
  Plus,
  Search,
  Sparkles,
  Table2,
  Target,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AnalysisArtifact, AnalysisRunSummary } from "@/lib/types/api";
import type { ReportBlock } from "@/lib/reports";
import { listReportAnalysisRuns, listRunArtifacts } from "@/lib/reports";
import {
  analysisSummaryToReportBlock,
  artifactToReportBlock,
  reflowBlocks,
} from "./report-blocks";

interface InvestigationPickerProps {
  open: boolean;
  projectId: string;
  initialRunId?: string;
  onClose: () => void;
  onAdd: (blocks: ReportBlock[]) => void;
  onGenerateDraft: (
    run: AnalysisRunSummary,
    artifacts: AnalysisArtifact[]
  ) => void;
}

function runTitle(run: AnalysisRunSummary): string {
  return run.report.title?.trim() || run.query.trim() || "未命名调查";
}

function dateLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "最近";
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(date);
}

function artifactIcon(kind: AnalysisArtifact["kind"]) {
  if (kind === "metric") return <Target size={14} />;
  if (kind === "chart") return <BarChart3 size={14} />;
  if (kind === "table" || kind === "result_snapshot") return <Table2 size={14} />;
  return <FileText size={14} />;
}

export function InvestigationPicker({
  open,
  projectId,
  initialRunId,
  onClose,
  onAdd,
  onGenerateDraft,
}: InvestigationPickerProps) {
  const [runs, setRuns] = useState<AnalysisRunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState<AnalysisRunSummary | null>(null);
  const [artifacts, setArtifacts] = useState<AnalysisArtifact[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [includeSummary, setIncludeSummary] = useState(false);
  const [search, setSearch] = useState("");
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [loadingArtifacts, setLoadingArtifacts] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const artifactRequestRef = useRef(0);
  const artifactAbortRef = useRef<AbortController | null>(null);

  const loadRunArtifacts = useCallback(
    async (run: AnalysisRunSummary) => {
      artifactRequestRef.current += 1;
      const requestId = artifactRequestRef.current;
      artifactAbortRef.current?.abort();
      const controller = new AbortController();
      artifactAbortRef.current = controller;
      setSelectedRun(run);
      setArtifacts([]);
      setSelectedIds(new Set());
      setIncludeSummary(Boolean(run.report.summary));
      setError(null);
      setLoadingArtifacts(true);
      try {
        const items = await listRunArtifacts(projectId, run.id, controller.signal);
        if (requestId !== artifactRequestRef.current || controller.signal.aborted) return;
        setArtifacts(items);
      } catch (nextError) {
        if (requestId !== artifactRequestRef.current || controller.signal.aborted) return;
        setError(
          nextError instanceof Error
            ? nextError.message
            : "调查内容没有加载完成，请重试。"
        );
      } finally {
        if (requestId === artifactRequestRef.current) setLoadingArtifacts(false);
      }
    },
    [projectId]
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setSelectedRun(null);
    setArtifacts([]);
    setSelectedIds(new Set());
    setIncludeSummary(false);
    setSearch("");
    setError(null);
    setLoadingRuns(true);
    void listReportAnalysisRuns(projectId)
      .then((items) => {
        if (cancelled) return;
        const completed = items.filter((item) => item.state === "completed");
        setRuns(completed);
        const initialRun = initialRunId
          ? completed.find((item) => item.id === initialRunId)
          : undefined;
        if (!initialRun) return;
        void loadRunArtifacts(initialRun);
      })
      .catch((nextError: unknown) =>
        !cancelled &&
        setError(nextError instanceof Error ? nextError.message : "调查没有加载完成，请重试。")
      )
      .finally(() => !cancelled && setLoadingRuns(false));
    return () => {
      cancelled = true;
      artifactRequestRef.current += 1;
      artifactAbortRef.current?.abort();
    };
  }, [initialRunId, loadRunArtifacts, open, projectId]);

  const filteredRuns = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    if (!query) return runs;
    return runs.filter((run) =>
      `${runTitle(run)} ${run.query}`.toLocaleLowerCase().includes(query)
    );
  }, [runs, search]);

  const addSelected = () => {
    if (!selectedRun) return;
    const blocks = artifacts
      .filter((artifact) => selectedIds.has(artifact.id))
      .map(artifactToReportBlock);
    if (includeSummary) blocks.unshift(analysisSummaryToReportBlock(selectedRun));
    if (!blocks.length) return;
    onAdd(reflowBlocks(blocks));
    onClose();
  };

  const generateDraft = () => {
    if (!selectedRun) return;
    onGenerateDraft(selectedRun, artifacts);
    onClose();
  };

  if (!open) return null;

  const selectionCount = selectedIds.size + (includeSummary ? 1 : 0);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/25" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="flex h-full w-full max-w-[520px] flex-col bg-card shadow-2xl" aria-label="从调查添加">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-border px-5">
          <div className="flex items-center gap-3">
            {selectedRun && (
              <button type="button" aria-label="返回调查列表" onClick={() => {
                artifactRequestRef.current += 1;
                artifactAbortRef.current?.abort();
                setLoadingArtifacts(false);
                setSelectedRun(null);
                setArtifacts([]);
              }} className="inline-flex h-8 w-8 items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground">
                <ArrowLeft size={16} />
              </button>
            )}
            <div>
              <h2 className="text-sm font-semibold">{selectedRun ? "选择内容" : "从调查添加"}</h2>
              <p className="mt-0.5 max-w-80 truncate text-[11px] text-muted-foreground">
                {selectedRun ? runTitle(selectedRun) : "选中后仍可自由编辑"}
              </p>
            </div>
          </div>
          <button type="button" aria-label="关闭" onClick={onClose} className="inline-flex h-8 w-8 items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground">
            <X size={17} />
          </button>
        </header>

        {!selectedRun && (
          <div className="shrink-0 border-b border-border px-5 py-4">
            <label className="flex h-9 items-center gap-2 border border-input bg-background px-3 focus-within:border-primary">
              <Search size={14} className="text-muted-foreground" />
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="查找调查" className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" />
            </label>
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto">
          {error && <p role="alert" className="m-5 border border-destructive/30 bg-destructive/5 px-4 py-3 text-xs text-destructive">{error}</p>}
          {(loadingRuns || loadingArtifacts) && (
            <div className="flex min-h-44 items-center justify-center text-sm text-muted-foreground">
              <Loader2 size={17} className="mr-2 animate-spin" />
              正在打开
            </div>
          )}

          {!selectedRun && !loadingRuns && filteredRuns.length === 0 && (
            <div className="px-8 py-20 text-center">
              <p className="text-sm font-medium">没有可添加的调查</p>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">完成一次调查后，可以把其中的内容加入报告。</p>
            </div>
          )}

          {!selectedRun && !loadingRuns && (
            <ol className="divide-y divide-border">
              {filteredRuns.map((run) => (
                <li key={run.id}>
                  <button type="button" onClick={() => void loadRunArtifacts(run)} className="w-full px-5 py-4 text-left transition-colors hover:bg-primary/[0.035]">
                    <span className="block text-sm font-medium leading-5">{runTitle(run)}</span>
                    <span className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                      <span>{dateLabel(run.updated_at)}</span>
                      <span aria-hidden="true">·</span>
                      <span className="line-clamp-1">{run.query}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}

          {selectedRun && !loadingArtifacts && (
            <div className="divide-y divide-border">
              <section className="flex items-center justify-between gap-5 bg-primary/[0.035] px-5 py-4">
                <div className="min-w-0">
                  <span className="flex items-center gap-2 text-sm font-semibold">
                    <Sparkles size={14} className="text-primary" />
                    生成完整初稿
                  </span>
                  <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
                    自动整理成概览、明细和依据，生成后仍可自由编辑。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={generateDraft}
                  className="inline-flex h-9 shrink-0 items-center gap-2 bg-primary px-4 text-xs font-semibold text-primary-foreground"
                >
                  <Sparkles size={14} />
                  生成初稿
                </button>
              </section>
              <label className="flex cursor-pointer items-start gap-3 px-5 py-4 hover:bg-primary/[0.025]">
                <input type="checkbox" checked={includeSummary} onChange={(event) => setIncludeSummary(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[hsl(var(--primary))]" />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-sm font-medium"><FileText size={14} className="text-primary" />调查摘要</span>
                  <span className="mt-1 block line-clamp-2 text-xs leading-5 text-muted-foreground">{selectedRun.report.summary || selectedRun.query}</span>
                </span>
              </label>
              {artifacts.map((artifact) => (
                <label key={artifact.id} className="flex cursor-pointer items-start gap-3 px-5 py-4 hover:bg-primary/[0.025]">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(artifact.id)}
                    onChange={() => setSelectedIds((current) => {
                      const next = new Set(current);
                      if (next.has(artifact.id)) next.delete(artifact.id);
                      else next.add(artifact.id);
                      return next;
                    })}
                    className="mt-0.5 h-4 w-4 accent-[hsl(var(--primary))]"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2 text-sm font-medium">
                      <span className="text-primary">{artifactIcon(artifact.kind)}</span>
                      {artifact.title}
                    </span>
                    <span className="mt-1 block text-[11px] text-muted-foreground">加入后可修改标题、内容和呈现方式</span>
                  </span>
                </label>
              ))}
              {!artifacts.length && !includeSummary && (
                <p className="px-5 py-10 text-center text-xs text-muted-foreground">这次调查还没有可加入的内容</p>
              )}
            </div>
          )}
        </div>

        {selectedRun && (
          <footer className="flex h-16 shrink-0 items-center justify-between gap-4 border-t border-border px-5">
            <span className="text-xs tabular-nums text-muted-foreground">已选择 {selectionCount} 项</span>
            <button type="button" onClick={addSelected} disabled={selectionCount === 0} className="inline-flex h-9 items-center gap-2 bg-primary px-4 text-xs font-semibold text-primary-foreground disabled:opacity-40">
              {selectionCount > 0 ? <Check size={14} /> : <Plus size={14} />}
              加入当前页面
            </button>
          </footer>
        )}
      </aside>
    </div>
  );
}
