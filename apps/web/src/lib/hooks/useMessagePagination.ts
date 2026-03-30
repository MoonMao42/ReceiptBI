import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { APIMessage } from "@/lib/types/api";
import { mapApiMessage } from "@/lib/stores/chat-helpers";
import type { ChatMessage } from "@/lib/types/chat";

interface PaginatedMessagesResponse {
  items: APIMessage[];
  total: number;
  next_cursor: string | null;
}

/**
 * Hook for infinite scrolling through message history.
 * Fetches messages in reverse chronological order (newest first).
 * When user scrolls to top, call fetchPreviousPage() to load older messages.
 *
 * Data flow:
 * 1. Initial load: cursor=null → fetch 50 most recent messages
 * 2. User scrolls to top → calls fetchPreviousPage()
 * 3. Next query: cursor=oldest_timestamp → fetch 50 older messages
 * 4. Messages prepended to list (appear at top due to reverse ordering)
 * 5. hasMoreMessages=false when next_cursor=null (no more history)
 */
export function useMessagePagination(conversationId: string | null) {
  const {
    data,
    fetchPreviousPage,
    isFetchingPreviousPage,
    hasNextPage,
    isLoading,
    error,
  } = useInfiniteQuery({
    queryKey: ["messages", conversationId],
    queryFn: async ({ pageParam }) => {
      if (!conversationId) {
        return { items: [], total: 0, next_cursor: null };
      }

      const response = await api.get<{ data: PaginatedMessagesResponse }>(
        `/api/v1/conversations/${conversationId}/messages`,
        {
          params: {
            cursor: pageParam || null,
            limit: 50,
          },
        }
      );

      return response.data.data;
    },
    initialPageParam: null, // Start with no cursor (most recent messages first)
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    enabled: !!conversationId,
    // Flatten pages into single array for rendering
    select: (data) => {
      const allMessages = data.pages.flatMap((page) => page.items);
      return allMessages;
    },
  });

  return {
    messages: data || [],
    isFetchingPreviousPage,
    hasMoreMessages: hasNextPage,
    loadEarlierMessages: fetchPreviousPage,
    isLoading,
    error,
  };
}
