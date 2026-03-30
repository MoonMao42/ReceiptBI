import { useRef, useEffect, useCallback } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { ChatMessage } from "@/lib/types/chat";

/**
 * Hook for virtual scrolling messages with dynamic heights.
 * Handles messages of varying heights (user text, SQL results, charts) smoothly.
 * Preserves scroll position when messages prepend at top (loading older messages).
 *
 * Configuration details:
 * - estimateSize=100: Most messages ~80-120px. SQL results ~200-400px. Conservative estimate.
 * - measureElement: After render, captures actual height including multi-line text, code blocks, charts.
 * - overscan=10: Render 10 items beyond viewport for smooth rapid scrolling.
 * - shouldAdjustScrollPositionOnItemSizeChange=true: Handles scroll math when items prepend.
 */
export function useMessageVirtualizer(messages: ChatMessage[]) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    // Estimate initial height for message items
    // User messages ~60px, text responses ~80px, SQL results ~200-400px
    // Conservative estimate prevents layout shift when actual height differs
    estimateSize: () => 100,
    // Measure actual element height after render (handles SQL, charts, code blocks)
    measureElement:
      typeof window !== "undefined"
        ? (element) => element?.getBoundingClientRect().height
        : undefined,
    // Render 10 items beyond viewport for smooth rapid scrolling
    overscan: 10,
    // Automatically adjust scroll position when item sizes change (prevents jump when loading older messages)
    shouldAdjustScrollPositionOnItemSizeChange: true,
  });

  // Scroll-to-top trigger: detect when user scrolls to top to load earlier messages
  const handleScroll = useCallback(() => {
    if (parentRef.current) {
      const { scrollTop } = parentRef.current;
      // Trigger loading when at top
      if (scrollTop === 0) {
        return true;
      }
    }
    return false;
  }, []);

  // Re-measure after new messages added (for proper scroll offset calculation)
  useEffect(() => {
    virtualizer.measure();
  }, [messages.length, virtualizer]);

  return {
    parentRef,
    virtualizer,
    virtualItems: virtualizer.getVirtualItems(),
    handleScroll,
    getTotalSize: () => virtualizer.getTotalSize(),
  };
}
