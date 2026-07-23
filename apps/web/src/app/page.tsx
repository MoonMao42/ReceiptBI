"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Sidebar } from "@/components/chat/Sidebar";
import { ChatArea } from "@/components/chat/ChatArea";
import { api } from "@/lib/api/client";
import {
  normalizeConversationId,
  storedConversationIdForProject,
  useChatStore,
} from "@/lib/stores/chat";
import { useProjectStore } from "@/lib/stores/project";
import type { AnalysisRunSummary } from "@/lib/types/api";

export default function Home() {
  const router = useRouter();
  const tSidebar = useTranslations("sidebar");
  const tProjectDefaults = useTranslations("projectDefaults");
  const initialProjectName = tProjectDefaults("initialName");
  const initialProjectDescription = tProjectDefaults("initialDescription");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [selectedReport, setSelectedReport] = useState<{
    conversationId: string;
    analysisRunId: string;
  } | null>(null);
  const [focusAnalysisRunId, setFocusAnalysisRunId] = useState<string | null>(null);
  const attemptedRestoreRef = useRef<string | null>(null);
  const [returnConversationId, setReturnConversationId] = useState<string | null>(
    () => {
      if (typeof window === "undefined") return null;
      return normalizeConversationId(
        new URLSearchParams(window.location.search).get("conversation")
      );
    }
  );
  const { bootstrap, currentProjectId } = useProjectStore();
  const {
    messages,
    currentConversationId,
    isLoading,
    activeStreamId,
    setCurrentConversation,
  } = useChatStore();

  const { data: reportRuns = [], isLoading: reportsLoading } =
    useQuery<AnalysisRunSummary[]>({
      queryKey: ["analysis-runs", currentProjectId],
      queryFn: async () => {
        const response = await api.get(
          `/api/v1/projects/${currentProjectId}/analysis-runs`
        );
        return response.data.data as AnalysisRunSummary[];
      },
      enabled: Boolean(currentProjectId),
    });

  const handleOpenReport = useCallback(
    (conversationId: string, analysisRunId: string) => {
      if (isLoading || activeStreamId) return;
      setSelectedReport({ conversationId, analysisRunId });
      setFocusAnalysisRunId(analysisRunId);
      setCurrentConversation(conversationId, currentProjectId);
    },
    [activeStreamId, currentProjectId, isLoading, setCurrentConversation]
  );

  const latestMessageRunId = [...messages]
    .reverse()
    .find((message) => message.analysisRunId)?.analysisRunId;
  const currentAnalysisRunId =
    (selectedReport?.conversationId === currentConversationId
      ? selectedReport.analysisRunId
      : null) ||
    latestMessageRunId ||
    reportRuns.find((run) => run.conversation_id === currentConversationId)?.id ||
    null;

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 768px)");
    const syncSidebar = (event: MediaQueryList | MediaQueryListEvent) => {
      setSidebarOpen(event.matches);
    };
    syncSidebar(desktop);
    desktop.addEventListener("change", syncSidebar);
    void bootstrap({
      name: initialProjectName,
      description: initialProjectDescription,
    });
    return () => desktop.removeEventListener("change", syncSidebar);
  }, [bootstrap, initialProjectDescription, initialProjectName]);

  useEffect(() => {
    if (!currentProjectId || isLoading || activeStreamId) return;
    const restoreKey = `${currentProjectId}:${returnConversationId || "stored"}`;
    if (returnConversationId) {
      if (attemptedRestoreRef.current !== restoreKey) {
        attemptedRestoreRef.current = restoreKey;
        if (currentConversationId !== returnConversationId) {
          setCurrentConversation(returnConversationId, currentProjectId);
        }
      }
      router.replace("/", { scroll: false });
      setReturnConversationId(null);
      return;
    }
    if (currentConversationId) return;
    if (attemptedRestoreRef.current === restoreKey) return;
    attemptedRestoreRef.current = restoreKey;
    const conversationId = storedConversationIdForProject(currentProjectId);
    if (!conversationId) return;
    setCurrentConversation(conversationId, currentProjectId);
  }, [
    activeStreamId,
    currentConversationId,
    currentProjectId,
    isLoading,
    returnConversationId,
    router,
    setCurrentConversation,
  ]);

  useEffect(() => {
    if (
      !currentConversationId ||
      (selectedReport && selectedReport.conversationId !== currentConversationId)
    ) {
      setSelectedReport(null);
      setFocusAnalysisRunId(null);
    }
  }, [currentConversationId, selectedReport]);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        reportRuns={reportRuns}
        reportsLoading={reportsLoading}
        reportSwitchDisabled={isLoading || Boolean(activeStreamId)}
        currentConversationId={currentConversationId}
        currentAnalysisRunId={currentAnalysisRunId}
        onOpenReport={handleOpenReport}
      />
      {sidebarOpen && (
        <button
          type="button"
          aria-label={tSidebar("closeNav")}
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-slate-950/25 md:hidden"
        />
      )}
      <ChatArea
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        recentRuns={reportRuns}
        recentRunsLoading={reportsLoading}
        onOpenReport={handleOpenReport}
        focusAnalysisRunId={focusAnalysisRunId}
        onReportFocused={() => setFocusAnalysisRunId(null)}
      />
    </div>
  );
}
