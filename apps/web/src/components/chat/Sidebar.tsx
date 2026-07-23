"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  Archive,
  BookOpenText,
  Check,
  ChevronDown,
  LayoutDashboard,
  Loader2,
  Pencil,
  Plus,
  Settings,
  X,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useChatStore } from "@/lib/stores/chat";
import { useProjectStore } from "@/lib/stores/project";
import type { AnalysisRunSummary } from "@/lib/types/api";
import { cn } from "@/lib/utils";
import { RECEIPTBI_BRAND_ICON_SRC } from "@/lib/brand";
import { ProjectReportIndex } from "./ProjectReportIndex";

export interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  reportRuns?: AnalysisRunSummary[];
  currentConversationId?: string | null;
  currentAnalysisRunId?: string | null;
  reportsLoading?: boolean;
  reportSwitchDisabled?: boolean;
  onOpenReport?: (conversationId: string, analysisRunId: string) => void;
}

export function Sidebar({
  isOpen,
  onToggle,
  reportRuns = [],
  currentConversationId,
  currentAnalysisRunId,
  reportsLoading = false,
  reportSwitchDisabled = false,
  onOpenReport,
}: SidebarProps) {
  const { clearConversation } = useChatStore();
  const { projects, currentProjectId, selectProject, createProject, renameProject } =
    useProjectStore();
  const t = useTranslations("sidebar");
  const tProjectDefaults = useTranslations("projectDefaults");
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const currentProject = projects.find((project) => project.id === currentProjectId);
  const [isRenamingProject, setIsRenamingProject] = useState(false);
  const [isSavingProjectName, setIsSavingProjectName] = useState(false);
  const [projectNameDraft, setProjectNameDraft] = useState(currentProject?.name || "");
  const [projectRenameError, setProjectRenameError] = useState<string | null>(null);

  useEffect(() => {
    setProjectNameDraft(currentProject?.name || "");
    setIsRenamingProject(false);
    setIsSavingProjectName(false);
    setProjectRenameError(null);
  }, [currentProject?.id, currentProject?.name]);

  const beginProjectRename = () => {
    if (!currentProject) return;
    setProjectNameDraft(currentProject.name);
    setProjectRenameError(null);
    setIsRenamingProject(true);
    setProjectMenuOpen(true);
  };

  const cancelProjectRename = () => {
    if (isSavingProjectName) return;
    setProjectNameDraft(currentProject?.name || "");
    setProjectRenameError(null);
    setIsRenamingProject(false);
  };

  const saveProjectRename = async () => {
    if (!currentProject || isSavingProjectName) return;
    const normalizedName = projectNameDraft.trim();
    if (!normalizedName) {
      setProjectRenameError(t("projectNameEmpty"));
      return;
    }
    if (normalizedName === currentProject.name) {
      setIsRenamingProject(false);
      return;
    }

    setIsSavingProjectName(true);
    setProjectRenameError(null);
    try {
      await renameProject(currentProject.id, normalizedName);
      setIsRenamingProject(false);
    } catch {
      setProjectRenameError(t("projectNameSaveFailed"));
    } finally {
      setIsSavingProjectName(false);
    }
  };

  const closeOnMobile = () => {
    if (!window.matchMedia("(max-width: 767px)").matches) return;
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
    onToggle();
  };

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 flex w-[260px] flex-shrink-0 flex-col overflow-hidden border-r border-border bg-card text-card-foreground shadow-2xl transition-transform duration-200 md:relative md:inset-auto md:z-auto md:w-[260px] md:translate-x-0 md:pointer-events-auto md:shadow-none",
        isOpen
          ? "translate-x-0"
          : "pointer-events-none -translate-x-full"
      )}
      aria-hidden={!isOpen}
      inert={!isOpen}
    >
      <div className="w-[260px]">
        <div className="flex h-[68px] items-center border-b border-border px-[18px]">
          <Image
            src={RECEIPTBI_BRAND_ICON_SRC}
            alt=""
            width={32}
            height={32}
            unoptimized
            className="h-8 w-8 shrink-0 object-contain"
            aria-hidden="true"
          />
          <div className="ml-3 min-w-0">
            <div className="text-[13px] font-semibold tracking-[0.04em]">ReceiptBI</div>
            <div className="mt-0.5 text-[9px] font-medium tracking-[0.18em] text-muted-foreground">
              {t("brandSubtitle")}
            </div>
          </div>
        </div>

        <div className="border-b border-border px-[18px] pb-4 pt-5">
          <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            {t("currentProject")}
          </div>
          <button
            onClick={() => setProjectMenuOpen((value) => !value)}
            className="group flex w-full items-center gap-2.5 py-2 text-left text-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-card"
            aria-expanded={projectMenuOpen}
          >
            <Archive size={15} className="shrink-0 text-primary" strokeWidth={1.8} />
            <span className="min-w-0 flex-1 truncate text-[13px] font-medium tracking-[0.01em]">
              {currentProject?.name || t("preparing")}
            </span>
            <ChevronDown
              size={13}
              className={cn(
                "shrink-0 text-muted-foreground transition-transform duration-200 group-hover:text-foreground",
                projectMenuOpen && "rotate-180"
              )}
            />
          </button>

          {projectMenuOpen && (
            <div className="mt-1.5 border-l border-border bg-muted/40 py-1 pl-2">
              {isRenamingProject && (
                <form
                  className="border-b border-border px-2 pb-3 pt-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void saveProjectRename();
                  }}
                >
                  <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                    {t("projectNameLabel")}
                  </label>
                  <input
                    autoFocus
                    aria-label={t("projectNameInputAria")}
                    value={projectNameDraft}
                    maxLength={120}
                    disabled={isSavingProjectName}
                    onChange={(event) => {
                      setProjectNameDraft(event.target.value);
                      setProjectRenameError(null);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Escape") {
                        event.preventDefault();
                        cancelProjectRename();
                      }
                    }}
                    className="mt-1.5 h-8 w-full border border-border bg-background px-2 text-xs text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                  />
                  <div className="mt-2 flex items-center gap-1.5">
                    <button
                      type="submit"
                      disabled={isSavingProjectName}
                      aria-label={t("saveProjectNameAria")}
                      className="inline-flex h-7 items-center gap-1 bg-primary px-2 text-[11px] font-semibold text-primary-foreground disabled:opacity-50"
                    >
                      {isSavingProjectName ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Check size={12} />
                      )}
                      {t("save")}
                    </button>
                    <button
                      type="button"
                      onClick={cancelProjectRename}
                      disabled={isSavingProjectName}
                      className="inline-flex h-7 items-center gap-1 px-2 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                    >
                        <X size={12} />
                        {t("cancel")}
                      </button>
                  </div>
                  {projectRenameError && (
                    <p role="alert" className="mt-2 text-[11px] leading-4 text-destructive">
                      {projectRenameError}
                    </p>
                  )}
                </form>
              )}
              {projects.map((project) => (
                <button
                  key={project.id}
                  onClick={() => {
                    if (project.id === currentProjectId) {
                      setProjectMenuOpen(false);
                      closeOnMobile();
                      return;
                    }
                    clearConversation({ forget: false });
                    void selectProject(project.id);
                    setProjectMenuOpen(false);
                    closeOnMobile();
                  }}
                  className={cn(
                    "w-full truncate px-2 py-2 text-left text-xs transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary",
                    project.id === currentProjectId ? "text-primary" : "text-muted-foreground"
                  )}
                >
                  {project.name}
                </button>
              ))}
              <button
                type="button"
                onClick={beginProjectRename}
                disabled={!currentProject || isRenamingProject}
                className="mt-1 flex w-full items-center gap-2 border-t border-border px-2 py-2.5 text-left text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary disabled:opacity-50"
              >
                <Pencil size={13} strokeWidth={1.8} /> {t("renameCurrent")}
              </button>
              <button
                onClick={() => {
                  clearConversation({ forget: false });
                  void createProject(tProjectDefaults("newName"));
                  setProjectMenuOpen(false);
                  closeOnMobile();
                }}
                className="mt-1 flex w-full items-center gap-2 border-t border-border px-2 py-2.5 text-left text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
              >
                <Plus size={13} strokeWidth={1.8} /> {t("newProject")}
              </button>
            </div>
          )}
        </div>

        <div className="px-[18px] py-3">
          <button
            onClick={() => {
              clearConversation({ forget: true, projectId: currentProjectId });
              closeOnMobile();
            }}
            className="group flex w-full items-center gap-2.5 py-2 text-left text-[13px] font-medium text-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-card"
          >
            <span className="flex h-6 w-6 shrink-0 items-center justify-center border border-primary/40 bg-primary/10 text-primary transition-colors group-hover:border-primary/70 group-hover:bg-primary/20">
              <Plus size={14} strokeWidth={2} />
            </span>
            <span>{t("startNewInvestigation")}</span>
          </button>
          {currentProjectId && (
            <>
              <Link
                href={`/projects/${currentProjectId}/reports`}
                prefetch
                onClick={closeOnMobile}
                className="group mt-1 flex w-full items-center gap-2.5 py-2 text-left text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-card"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center text-primary">
                  <LayoutDashboard size={15} strokeWidth={1.8} />
                </span>
                <span>{t("reports")}</span>
              </Link>
              <Link
                href={`/projects/${currentProjectId}/understanding`}
                prefetch
                onClick={closeOnMobile}
                className="group mt-1 flex w-full items-center gap-2.5 py-2 text-left text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-card"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center text-primary">
                  <BookOpenText size={15} strokeWidth={1.8} />
                </span>
                <span>{t("projectUnderstanding")}</span>
              </Link>
            </>
          )}
        </div>
      </div>

      <div className="min-h-0 w-[260px] flex-1 border-t border-border">
        <ProjectReportIndex
          runs={reportRuns}
          isLoading={reportsLoading}
          disabled={reportSwitchDisabled || !onOpenReport}
          currentConversationId={currentConversationId}
          currentAnalysisRunId={currentAnalysisRunId}
          onOpenReport={(conversationId, analysisRunId) => {
            if (!onOpenReport) return;
            onOpenReport(conversationId, analysisRunId);
            closeOnMobile();
          }}
        />
      </div>

      <div className="w-[260px] border-t border-border px-[18px] py-3.5">
        <Link
          href="/settings"
          prefetch
          onClick={closeOnMobile}
          className="flex w-full items-center gap-2.5 py-2 text-[13px] text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-card"
        >
          <Settings size={15} strokeWidth={1.8} /> {t("settings")}
        </Link>
      </div>
    </aside>
  );
}
