"use client";

import { useEffect, useRef } from "react";
import { useTranslations } from "next-intl";
import { Brain, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "@/lib/types/chat";
import type { AppSettings } from "@/lib/types/api";
import { cn } from "@/lib/utils";
import { AssistantMessageCard } from "./AssistantMessageCard";
import { ChatEmptyState } from "./ChatEmptyState";

interface MessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
  selectedConnection?: { id: string; name: string };
  selectedModel?: { id: string; name: string };
  readyToQuery: boolean;
  appSettings?: AppSettings;
  onRetry: (index: number) => void;
  onRerun: (index: number) => void;
  onOpenSettings: () => void;
  onUsePrompt: (text: string) => void;
}

export function MessageList({
  messages,
  isLoading,
  selectedConnection,
  selectedModel,
  readyToQuery,
  appSettings,
  onRetry,
  onRerun,
  onOpenSettings,
  onUsePrompt,
}: MessageListProps) {
  const t = useTranslations("chat");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isLoading]);

  if (messages.length === 0) {
    return (
      <ChatEmptyState
        selectedConnection={selectedConnection}
        selectedModel={selectedModel}
        readyToQuery={readyToQuery}
        appSettings={appSettings}
        onOpenSettings={onOpenSettings}
        onUsePrompt={onUsePrompt}
      />
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-5xl space-y-6">
        {messages.map((message, index) => (
          <div
            key={index}
            className={cn(
              "flex gap-4",
              message.role === "user" ? "justify-end" : "justify-start"
            )}
          >
            {message.role === "assistant" && (
              <div className="mt-1 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl bg-primary/10">
                <Brain size={18} className="text-primary" />
              </div>
            )}

            {message.role === "assistant" ? (
              message.isLoading ? (
                <div
                  data-testid="assistant-loading-message"
                  className="rounded-[24px] border border-border bg-background px-5 py-4 text-sm text-muted-foreground shadow-sm"
                >
                  <div className="flex items-center gap-2">
                    <Loader2 size={16} className="animate-spin" />
                    {message.thinkingStage || message.status || t("analyzing")}
                  </div>
                </div>
              ) : (
                <AssistantMessageCard
                  message={message}
                  index={index}
                  onRetry={(messageIndex) => void onRetry(messageIndex)}
                  onRerun={(messageIndex) => void onRerun(messageIndex)}
                />
              )
            ) : (
              <div className="max-w-3xl rounded-[24px] bg-primary px-5 py-4 text-primary-foreground shadow-sm">
                <ReactMarkdown className="prose prose-sm max-w-none prose-invert">
                  {message.content}
                </ReactMarkdown>
              </div>
            )}
          </div>
        ))}
      </div>
      <div ref={messagesEndRef} />
    </div>
  );
}
