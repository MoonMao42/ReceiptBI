import { useCallback, useRef } from "react";
import { useReactFlow, type Node } from "@xyflow/react";
import { buildLayoutSnapshot } from "@/lib/settings/schema";
import type { SchemaLayout, SchemaLayoutUpdate, TableInfo } from "@/lib/types/schema";

/**
 * Hook for schema layout save logic with debouncing.
 * Handles position changes, layout snapshots, and throttled saves to backend.
 */
export function useSchemaLayout(
  currentLayout: SchemaLayout | null,
  schemaInfo: TableInfo[] | undefined,
  hiddenTables: Set<string>,
  onSaveLayout: (snapshot: SchemaLayoutUpdate) => void
) {
  const { getViewport } = useReactFlow();
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Save layout snapshot (immediate - for explicit saves)
  const saveLayout = useCallback(
    (nodes: Node[]) => {
      if (!currentLayout?.id) return;

      const snapshot = buildLayoutSnapshot(nodes, getViewport(), schemaInfo, hiddenTables);
      onSaveLayout(snapshot.payload);
    },
    [currentLayout, getViewport, schemaInfo, hiddenTables, onSaveLayout]
  );

  // Debounced save (500ms) — only called on drag completion
  const debouncedSaveLayout = useCallback(
    (nodes: Node[]) => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }

      saveTimeoutRef.current = setTimeout(() => {
        saveLayout(nodes);
      }, 500);
    },
    [saveLayout]
  );

  return { saveLayout, debouncedSaveLayout };
}
