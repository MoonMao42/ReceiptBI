"use client";

import { useCallback, useEffect, useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Loader2, Database } from "lucide-react";
import { api } from "@/lib/api/client";
import {
  filterVisibleTables,
  deriveHiddenTables,
} from "@/lib/settings/schema";
import { SchemaGraph } from "./SchemaGraph";
import { RelationshipPanel } from "./RelationshipPanel";
import { LayoutControls } from "./LayoutControls";
import type {
  SchemaInfo,
  TableRelationship,
  TableRelationshipCreate,
  RelationshipSuggestion,
  SchemaLayout,
  SchemaLayoutListItem,
  SchemaLayoutCreate,
  SchemaLayoutUpdate,
} from "@/lib/types/schema";
import { useTranslations } from "next-intl";

interface SchemaSettingsProps {
  connectionId: string | null;
}

function SchemaSettingsInner({ connectionId }: SchemaSettingsProps) {
  const queryClient = useQueryClient();
  const { setViewport } = useReactFlow();
  const t = useTranslations("schema");

  // Layout & visibility state
  const [selectedLayoutId, setSelectedLayoutId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [hiddenTables, setHiddenTables] = useState<Set<string>>(new Set());
  const [showHiddenPanel, setShowHiddenPanel] = useState(false);

  // Data queries
  const { data: schemaInfo, isLoading: schemaLoading } = useQuery({
    queryKey: ["schema", connectionId],
    queryFn: async () => {
      if (!connectionId) return null;
      const response = await api.get(`/api/v1/schema/${connectionId}`);
      return response.data.data as SchemaInfo;
    },
    enabled: !!connectionId,
  });

  const { data: relationships, isLoading: relLoading } = useQuery({
    queryKey: ["relationships", connectionId],
    queryFn: async () => {
      if (!connectionId) return [];
      const response = await api.get(`/api/v1/schema/${connectionId}/relationships`);
      return response.data.data as TableRelationship[];
    },
    enabled: !!connectionId,
  });

  const { data: layouts } = useQuery({
    queryKey: ["layouts", connectionId],
    queryFn: async () => {
      if (!connectionId) return [];
      const response = await api.get(`/api/v1/schema/${connectionId}/layouts`);
      return response.data.data as SchemaLayoutListItem[];
    },
    enabled: !!connectionId,
  });

  const { data: currentLayout } = useQuery({
    queryKey: ["layout", connectionId, selectedLayoutId],
    queryFn: async () => {
      if (!connectionId || !selectedLayoutId) return null;
      const response = await api.get(`/api/v1/schema/${connectionId}/layouts/${selectedLayoutId}`);
      return response.data.data as SchemaLayout;
    },
    enabled: !!connectionId && !!selectedLayoutId,
  });

  // Mutations
  const createLayoutMutation = useMutation({
    mutationFn: async (data: SchemaLayoutCreate) => {
      const response = await api.post(`/api/v1/schema/${connectionId}/layouts`, data);
      return response.data.data as SchemaLayout;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["layouts", connectionId] });
      setSelectedLayoutId(data.id);
    },
  });

  const updateLayoutMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: SchemaLayoutUpdate }) => {
      const response = await api.put(`/api/v1/schema/${connectionId}/layouts/${id}`, data);
      return response.data.data as SchemaLayout;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["layout", connectionId, selectedLayoutId] });
    },
  });

  const deleteLayoutMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/schema/${connectionId}/layouts/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["layouts", connectionId] });
      setSelectedLayoutId(null);
    },
  });

  const duplicateLayoutMutation = useMutation({
    mutationFn: async (id: string) => {
      const response = await api.post(`/api/v1/schema/${connectionId}/layouts/${id}/duplicate`);
      return response.data.data as SchemaLayout;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["layouts", connectionId] });
      setSelectedLayoutId(data.id);
    },
  });

  const createRelationshipMutation = useMutation({
    mutationFn: async (data: TableRelationshipCreate) => {
      const response = await api.post(`/api/v1/schema/${connectionId}/relationships`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["relationships", connectionId] });
    },
  });

  const deleteRelationshipMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/schema/relationships/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["relationships", connectionId] });
    },
  });

  // Effects
  useEffect(() => {
    if (layouts && layouts.length > 0 && !selectedLayoutId) {
      const defaultLayout = layouts.find((l) => l.is_default);
      setSelectedLayoutId(defaultLayout?.id || layouts[0].id);
    }
  }, [layouts, selectedLayoutId]);

  useEffect(() => {
    if (currentLayout && schemaInfo) {
      const allTables = schemaInfo.tables.map((t) => t.name);
      setHiddenTables(deriveHiddenTables(currentLayout, allTables));

      if (currentLayout.zoom && currentLayout.viewport_x !== undefined) {
        setViewport({
          x: currentLayout.viewport_x,
          y: currentLayout.viewport_y,
          zoom: currentLayout.zoom,
        });
      }
    }
  }, [currentLayout, schemaInfo, setViewport]);

  // Computed state
  const visibleTables = useMemo(() => {
    return filterVisibleTables(schemaInfo?.tables, hiddenTables, searchQuery);
  }, [schemaInfo, hiddenTables, searchQuery]);

  const suggestions = schemaInfo?.suggestions || [];

  // Event handlers
  const handleSaveLayout = useCallback(
    (snapshot: SchemaLayoutUpdate) => {
      if (!selectedLayoutId || !connectionId) return;
      updateLayoutMutation.mutate({
        id: selectedLayoutId,
        data: snapshot,
      });
    },
    [selectedLayoutId, connectionId, updateLayoutMutation]
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;

      const sourceColumn = connection.sourceHandle?.replace("-left", "") || "";
      const targetColumn = connection.targetHandle?.replace("-right", "") || "";

      createRelationshipMutation.mutate({
        source_table: connection.source,
        source_column: sourceColumn,
        target_table: connection.target,
        target_column: targetColumn,
        relationship_type: "1:N",
        join_type: "LEFT",
      });
    },
    [createRelationshipMutation]
  );

  const handleEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      if (confirm(t("confirmDeleteRelationship"))) {
        deleteRelationshipMutation.mutate(edge.id);
      }
    },
    [deleteRelationshipMutation, t]
  );

  const handleNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: Node) => {
      event.preventDefault();
      if (confirm(t("confirmHideTable", { table: node.id }))) {
        setHiddenTables((prev) => new Set([...prev, node.id]));
      }
    },
    [t]
  );

  const handleApplySuggestion = useCallback(
    (suggestion: RelationshipSuggestion) => {
      createRelationshipMutation.mutate({
        source_table: suggestion.source_table,
        source_column: suggestion.source_column,
        target_table: suggestion.target_table,
        target_column: suggestion.target_column,
        relationship_type: "1:N",
        join_type: "LEFT",
      });
    },
    [createRelationshipMutation]
  );

  const handleDeleteRelationship = useCallback(
    (id: string) => {
      deleteRelationshipMutation.mutate(id);
    },
    [deleteRelationshipMutation]
  );

  const handleShowTable = useCallback((tableName: string) => {
    setHiddenTables((prev) => {
      const next = new Set(prev);
      next.delete(tableName);
      return next;
    });
  }, []);

  const handleRefresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["schema", connectionId] });
  }, [queryClient, connectionId]);

  if (!connectionId) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <Database size={48} className="mb-4 opacity-50" />
        <p>{t("selectConnectionFirst")}</p>
      </div>
    );
  }

  if (schemaLoading || relLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin text-muted-foreground" size={24} />
      </div>
    );
  }

  return (
    <div className="min-h-[600px] flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">{t("title")}</h2>
          <p className="text-sm text-muted-foreground mt-1">
            {t("description")}
          </p>
        </div>
        <button
          onClick={handleRefresh}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
        >
          {/* Refresh icon handled by RefreshCw */}
        </button>
      </div>

      <LayoutControls
        layouts={layouts || []}
        selectedLayoutId={selectedLayoutId}
        searchQuery={searchQuery}
        hiddenTables={hiddenTables}
        showHiddenPanel={showHiddenPanel}
        visibleTableCount={visibleTables.length}
        totalTableCount={schemaInfo?.tables.length || 0}
        onSelectLayout={setSelectedLayoutId}
        onCreateLayout={async (name) => {
          createLayoutMutation.mutate({
            name,
            is_default: !layouts || layouts.length === 0,
          });
        }}
        onDeleteLayout={(id) => deleteLayoutMutation.mutate(id)}
        onDuplicateLayout={(id) => duplicateLayoutMutation.mutate(id)}
        onSearch={setSearchQuery}
        onToggleHiddenPanel={() => setShowHiddenPanel(!showHiddenPanel)}
        onShowTable={handleShowTable}
      />

      <RelationshipPanel
        suggestions={suggestions}
        relationships={relationships || []}
        isLoading={createRelationshipMutation.isPending}
        onApplySuggestion={handleApplySuggestion}
        onDeleteRelationship={handleDeleteRelationship}
      />

      <SchemaGraph
        schemaInfo={schemaInfo || null}
        relationships={relationships || []}
        visibleTables={visibleTables}
        currentLayout={currentLayout || null}
        hiddenTables={hiddenTables}
        onSaveLayout={handleSaveLayout}
        onConnect={handleConnect}
        onEdgeClick={handleEdgeClick}
        onNodeContextMenu={handleNodeContextMenu}
      />

      {updateLayoutMutation.isPending && (
        <div className="mt-2 text-xs text-muted-foreground flex items-center gap-1">
          <Loader2 size={12} className="animate-spin" />
          {t("saving")}
        </div>
      )}
    </div>
  );
}

export function SchemaSettings({ connectionId }: SchemaSettingsProps) {
  return (
    <ReactFlowProvider>
      <SchemaSettingsInner connectionId={connectionId} />
    </ReactFlowProvider>
  );
}
