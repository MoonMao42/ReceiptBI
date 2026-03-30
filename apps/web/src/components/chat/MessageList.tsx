"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Brain, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "@/lib/types/chat";
import type { AppSettings } from "@/lib/types/api";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/lib/stores/chat";
import { useMessagePagination } from "@/lib/hooks/useMessagePagination";
import { useMessageVirtualizer } from "@/lib/hooks/useMessageVirtualizer";
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
  const { currentConversationId } = useChatStore();
  const [hasPendingScroll, setHasPendingScroll] = useState(false);

  // Load paginated messages from history
  const {
    messages: historyMessages,
    hasMoreMessages,
    isFetchingPreviousPage,
    loadEarlierMessages,
  } = useMessagePagination(currentConversationId);

  // Combine current messages (from store) + history (from pagination)
  // History messages are older, current messages are newer
  const allMessages = [...historyMessages, ...messages];

  // Virtual scrolling with dynamic heights
  const { parentRef, virtualizer, virtualItems, getTotalSize } = useMessageVirtualizer(allMessages);

  // Scroll to top auto-triggers loading earlier messages
  useEffect(() => {
    const handleScroll = () => {
      if (parentRef.current?.scrollTop === 0 && hasMoreMessages && !isFetchingPreviousPage) {
        loadEarlierMessages();
      }
    };

    const container = parentRef.current;
    if (container) {
      container.addEventListener("scroll", handleScroll);
      return () => container.removeEventListener("scroll", handleScroll);
    }
  }, [hasMoreMessages, isFetchingPreviousPage, loadEarlierMessages]);

  // Auto-scroll to bottom when new messages arrive (user was already at bottom)
  const wasAtBottomRef = useRef(true);
  useEffect(() => {
    if (parentRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = parentRef.current;
      wasAtBottomRef.current = scrollTop + clientHeight >= scrollHeight - 100;

      if (isLoading && wasAtBottomRef.current && hasPendingScroll) {
        // Scroll to bottom when new message arrives
        setTimeout(() => {
          if (parentRef.current) {
            parentRef.current.scrollTop = parentRef.current.scrollHeight;
          }
          setHasPendingScroll(false);
        }, 0);
      }
    }
  }, [messages.length, isLoading, hasPendingScroll]);

  if (allMessages.length === 0 && !isFetchingPreviousPage) {
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
    <div className="flex-1 overflow-y-auto bg-white" ref={parentRef}>
      {isFetchingPreviousPage && (
        <div className="flex justify-center items-center p-4">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="ml-2 text-sm text-gray-500">{t("loading_messages") || "Loading earlier messages..."}</span>
        </div>
      )}

      <div style={{ height: `${getTotalSize()}px`, position: "relative" }}>
        {virtualItems.map((virtualItem) => {
          const message = allMessages[virtualItem.index];
          const messageIndex = virtualItem.index;

          return (
            <div
              key={`${message.role}-${messageIndex}`}
              data-index={virtualItem.index}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualItem.start}px)`,
              }}
            >
              <div className="flex gap-4 p-4 mx-auto max-w-5xl" style={{ justifyContent: message.role === "user" ? "flex-end" : "flex-start" }}>
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
                      index={messageIndex}
                      onRetry={(idx) => void onRetry(idx)}
                      onRerun={(idx) => void onRerun(idx)}
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
            </div>
          );
        })}
      </div>

      {isLoading && (
        <div className="flex justify-center p-4">
          <Loader2 className="w-4 h-4 animate-spin" />
        </div>
      )}
    </div>
  );
}
