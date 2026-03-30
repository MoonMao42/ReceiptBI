"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import type { AppSettings, ConnectionSummary, ModelSummary } from "@/lib/types/api";
import { api } from "@/lib/api/client";
import { useChatStore } from "@/lib/stores/chat";
import { MessageList } from "./MessageList";
import { InputBar } from "./InputBar";
import { ChatHeader } from "./ChatHeader";
import { useChatAreaState } from "./useChatAreaState";

interface ChatAreaProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
}

export function ChatArea({ sidebarOpen: _sidebarOpen, onToggleSidebar }: ChatAreaProps) {
  const router = useRouter();
  const locale = useLocale();
  const { messages, isLoading, sendMessage, stopGeneration, retryMessage, rerunMessage } =
    useChatStore();

  const { data: connections } = useQuery({
    queryKey: ["connections"],
    queryFn: async () => {
      const response = await api.get("/api/v1/config/connections");
      return response.data.data as ConnectionSummary[];
    },
  });

  const { data: models } = useQuery({
    queryKey: ["models"],
    queryFn: async () => {
      const response = await api.get("/api/v1/config/models");
      return response.data.data as ModelSummary[];
    },
  });

  const { data: appSettings } = useQuery({
    queryKey: ["app-settings"],
    queryFn: async () => {
      const response = await api.get("/api/v1/settings");
      return response.data.data as AppSettings;
    },
  });

  const {
    selectedConnectionId,
    selectedModelId,
    showConnectionDropdown,
    showModelDropdown,
    input,
    selectedConnection,
    selectedModel,
    readyToQuery,
    modelReady,
    handleSelectConnection,
    handleSelectModel,
    setShowConnectionDropdown,
    setShowModelDropdown,
    setInput,
  } = useChatAreaState(connections, models, appSettings, isLoading);

  const effectiveContextRounds = appSettings?.context_rounds || 5;

  const handleInputSubmit = async (query: string) => {
    await sendMessage(query, selectedConnectionId, selectedModelId, effectiveContextRounds, locale);
  };

  return (
    <div className="flex h-full flex-1 flex-col bg-background">
      <ChatHeader
        onToggleSidebar={onToggleSidebar}
        connections={connections}
        models={models}
        selectedConnectionId={selectedConnectionId}
        selectedModelId={selectedModelId}
        showConnectionDropdown={showConnectionDropdown}
        showModelDropdown={showModelDropdown}
        onToggleConnectionDropdown={() => {
          setShowConnectionDropdown((prev) => {
            if (!prev) setShowModelDropdown(false);
            return !prev;
          });
        }}
        onToggleModelDropdown={() => {
          setShowModelDropdown((prev) => {
            if (!prev) setShowConnectionDropdown(false);
            return !prev;
          });
        }}
        onSelectConnection={(id) => {
          handleSelectConnection(id);
          setShowConnectionDropdown(false);
        }}
        onSelectModel={(id) => {
          handleSelectModel(id);
          setShowModelDropdown(false);
        }}
        modelReady={modelReady}
        selectedModel={selectedModel}
        contextRounds={effectiveContextRounds}
      />

      <MessageList
        messages={messages}
        isLoading={isLoading}
        selectedConnection={selectedConnection}
        selectedModel={selectedModel}
        readyToQuery={readyToQuery}
        appSettings={appSettings}
        onRetry={(index) => void retryMessage(index)}
        onRerun={(index) => void rerunMessage(index)}
        onOpenSettings={() => router.push("/settings")}
        onUsePrompt={setInput}
      />

      <InputBar
        onSubmit={handleInputSubmit}
        onStop={stopGeneration}
        isLoading={isLoading}
        readyToQuery={readyToQuery}
        modelReady={modelReady}
        selectedModel={selectedModel}
        input={input}
        onInputChange={setInput}
      />
    </div>
  );
}
