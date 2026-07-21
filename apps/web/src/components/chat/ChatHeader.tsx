"use client";

import { useEffect, useState } from "react";
import { Check, Database, History, Loader2, Pencil, Settings2, X } from "lucide-react";
import Link from "next/link";
import type { Project } from "@/lib/types/api";

interface ChatHeaderProps {
  onToggleSidebar: () => void;
  onToggleData: () => void;
  onOpenUnderstanding?: () => void;
  project?: Project;
  readySources: number;
  totalSources: number;
  pendingUnderstandingCount?: number;
  onRenameProject?: (name: string) => Promise<void>;
}

function renameErrorMessage(error: unknown): string {
  if (typeof error === "object" && error && "response" in error) {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response;
    if (typeof response?.data?.detail === "string" && response.data.detail.trim()) {
      return response.data.detail.trim();
    }
  }
  return "项目名称保存失败，请重试";
}

export function ChatHeader({
  onToggleSidebar,
  onToggleData,
  onOpenUnderstanding,
  project,
  readySources,
  totalSources,
  pendingUnderstandingCount = 0,
  onRenameProject,
}: ChatHeaderProps) {
  const dataReady = readySources > 0;
  const hasPendingUnderstanding = pendingUnderstandingCount > 0;
  const [isEditingName, setIsEditingName] = useState(false);
  const [isSavingName, setIsSavingName] = useState(false);
  const [draftName, setDraftName] = useState(project?.name || "");
  const [renameError, setRenameError] = useState<string | null>(null);

  useEffect(() => {
    setDraftName(project?.name || "");
    setIsEditingName(false);
    setIsSavingName(false);
    setRenameError(null);
  }, [project?.id, project?.name]);

  const beginRename = () => {
    if (!project || !onRenameProject) return;
    setDraftName(project.name);
    setRenameError(null);
    setIsEditingName(true);
  };

  const cancelRename = () => {
    if (isSavingName) return;
    setDraftName(project?.name || "");
    setRenameError(null);
    setIsEditingName(false);
  };

  const saveRename = async () => {
    if (!project || !onRenameProject || isSavingName) return;
    const normalizedName = draftName.trim();
    if (!normalizedName) {
      setRenameError("项目名称不能为空");
      return;
    }
    if (normalizedName === project.name) {
      setDraftName(project.name);
      setRenameError(null);
      setIsEditingName(false);
      return;
    }

    setIsSavingName(true);
    setRenameError(null);
    try {
      await onRenameProject(normalizedName);
      setDraftName(normalizedName);
      setIsEditingName(false);
    } catch (error) {
      setRenameError(renameErrorMessage(error));
    } finally {
      setIsSavingName(false);
    }
  };

  return (
    <header className="sticky top-0 z-10 border-b border-border bg-background/95 backdrop-blur-md">
      <div className="flex h-14 items-center justify-between px-3 sm:h-[68px] sm:px-5">
        <div className="flex min-w-0 items-center gap-2 sm:gap-4">
          <button
            onClick={onToggleSidebar}
            className="p-2 text-muted-foreground hover:bg-muted hover:text-foreground md:hidden"
            aria-label="打开项目导航"
          >
            <History size={20} />
          </button>
          <div className="hidden h-8 w-px bg-border sm:block md:hidden" />
          <div className="min-w-0">
            {isEditingName ? (
              <div className="flex min-w-0 items-center gap-1">
                <input
                  autoFocus
                  aria-label="项目名称"
                  value={draftName}
                  maxLength={120}
                  disabled={isSavingName}
                  onChange={(event) => {
                    setDraftName(event.target.value);
                    setRenameError(null);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void saveRename();
                    }
                    if (event.key === "Escape") {
                      event.preventDefault();
                      cancelRename();
                    }
                  }}
                  className="h-7 min-w-0 max-w-[320px] border border-primary/40 bg-background px-2 text-sm font-semibold text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                />
                <button
                  type="button"
                  onClick={() => void saveRename()}
                  disabled={isSavingName}
                  className="p-1 text-primary hover:bg-primary/10 disabled:opacity-50"
                  aria-label="保存项目名称"
                >
                  {isSavingName ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Check size={14} />
                  )}
                </button>
                <button
                  type="button"
                  onClick={cancelRename}
                  disabled={isSavingName}
                  className="p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                  aria-label="取消重命名"
                >
                  <X size={14} />
                </button>
              </div>
            ) : project && onRenameProject ? (
              <button
                type="button"
                onClick={beginRename}
                className="group flex max-w-full items-center gap-1.5 text-left text-[13px] font-semibold text-foreground"
                aria-label={`重命名项目：${project.name}`}
              >
                <span className="truncate">{project.name}</span>
                <Pencil
                  size={12}
                  className="shrink-0 text-muted-foreground opacity-70 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
                />
              </button>
            ) : project ? (
              <div className="truncate text-sm font-semibold text-foreground">
                {project.name}
              </div>
            ) : null}
            {renameError ? (
              <div role="alert" className="mt-0.5 text-[11px] text-destructive">
                {renameError}
              </div>
            ) : dataReady ? (
              <div className="mt-0.5 hidden items-center gap-2 text-xs text-muted-foreground sm:flex">
                <span className="h-1.5 w-1.5 bg-success" />
                {readySources} 项数据可用
              </div>
            ) : null}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={
              hasPendingUnderstanding
                ? onOpenUnderstanding || onToggleData
                : onToggleData
            }
            aria-label={
              hasPendingUnderstanding
                ? `数据，待核对 ${pendingUnderstandingCount}`
                : `数据${totalSources > 0 ? ` ${totalSources}` : ""}`
            }
            className="inline-flex items-center gap-2 border border-border bg-card px-2.5 py-2 text-sm font-medium text-foreground transition-colors hover:border-primary/50 hover:bg-primary/[0.04] sm:px-3"
          >
            <Database size={16} className="text-primary" />
            <span>数据</span>
            {(hasPendingUnderstanding || totalSources > 0) && (
              <span
                className={
                  hasPendingUnderstanding
                    ? "bg-warning/10 px-1.5 py-0.5 text-[11px] text-warning"
                    : "bg-primary/10 px-1.5 py-0.5 text-[11px] text-primary"
                }
              >
                {hasPendingUnderstanding
                  ? `待核对 ${pendingUnderstandingCount}`
                  : totalSources}
              </span>
            )}
          </button>
          <Link
            href="/settings"
            className="p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground md:hidden"
            aria-label="设置"
          >
            <Settings2 size={18} />
          </Link>
        </div>
      </div>
    </header>
  );
}
