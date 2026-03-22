"use client";

import { useCallback, useEffect, useState, useMemo, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  type Connection,
  type Edge,
  type Node,
  type NodeTypes,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Loader2,
  RefreshCw,
  Lightbulb,
  Trash2,
  Database,
  Plus,
  Copy,
  ChevronDown,
  Search,
  Eye,
  EyeOff,
  X,
} from "lucide-react";
import { api } from "@/lib/api/client";
import { TableNode } from "@/components/schema/TableNode";
import {
  buildLayoutSnapshot,
  buildRelationshipEdges,
  buildSchemaNodes,
  deriveHiddenTables,
  filterVisibleTables,
} from "@/lib/settings/schema";
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

const nodeTypes: NodeTypes = {
  tableNode: TableNode,
};

function SchemaSettingsInner({ connectionId }: SchemaSettingsProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const queryClient = useQueryClient();
  const { getViewport, setViewport } = useReactFlow();
  const t = useTranslations("schema");

  const [selectedLayoutId, setSelectedLayoutId] = useState<string | null>(null);
  const [showLayoutDropdown, setShowLayoutDropdown] = useState(false);
  const [newLayoutName, setNewLayoutName] = useState("");
  const [showNewLayoutInput, setShowNewLayoutInput] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [hiddenTables, setHiddenTables] = useState<Set<string>>(new Set());
  const [showHiddenPanel, setShowHiddenPanel] = useState(false);

  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastSavedRef = useRef<string>("");

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

  const createLayoutMutation = useMutation({
    mutationFn: async (data: SchemaLayoutCreate) => {
      const response = await api.post(`/api/v1/schema/${connectionId}/layouts`, data);
      return response.data.data as SchemaLayout;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["layouts", connectionId] });
      setSelectedLayoutId(data.id);
      setShowNewLayoutInput(false);
      setNewLayoutName("");
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

  const createMutation = useMutation({
    mutationFn: async (data: TableRelationshipCreate) => {
      const response = await api.post(`/api/v1/schema/${connectionId}/relationships`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["relationships", connectionId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/schema/relationships/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["relationships", connectionId] });
    },
  });

  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (layouts && layouts.length > 0 && !selectedLayoutId) {
      const defaultLayout = layouts.find((l) => l.is_default);
      if (defaultLayout) {
        setSelectedLayoutId(defaultLayout.id);
      } else {
        setSelectedLayoutId(layouts[0].id);
      }
    }
  }, [layouts, selectedLayoutId]);

  useEffect(() => {
    if (currentLayout) {
      const allTables = schemaInfo?.tables.map((table) => table.name) || [];
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

  const visibleTables = useMemo(() => {
    return filterVisibleTables(schemaInfo?.tables, hiddenTables, searchQuery);
  }, [schemaInfo, hiddenTables, searchQuery]);

  useEffect(() => {
    if (!visibleTables || visibleTables.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    setNodes(buildSchemaNodes(visibleTables, currentLayout));
    setEdges(buildRelationshipEdges(visibleTables, relationships));
  }, [visibleTables, relationships, currentLayout, setNodes, setEdges]);

  const saveLayout = useCallback(() => {
    if (!selectedLayoutId || !connectionId) return;

    const snapshot = buildLayoutSnapshot(nodes, getViewport(), schemaInfo?.tables, hiddenTables);

    if (snapshot.signature === lastSavedRef.current) return;
    lastSavedRef.current = snapshot.signature;

    updateLayoutMutation.mutate({
      id: selectedLayoutId,
      data: snapshot.payload,
    });
  }, [selectedLayoutId, connectionId, nodes, getViewport, hiddenTables, schemaInfo, updateLayoutMutation]);

  const handleNodesChange = useCallback(
    (changes: NodeChange<Node>[]) => {
      onNodesChange(changes);

      const hasPositionChange = changes.some(
        (change) => change.type === "position" && change.dragging === false
      );

      if (hasPositionChange && selectedLayoutId) {
        if (saveTimeoutRef.current) {
          clearTimeout(saveTimeoutRef.current);
        }
        saveTimeoutRef.current = setTimeout(saveLayout, 500);
      }
    },
    [onNodesChange, selectedLayoutId, saveLayout]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;

      const sourceColumn = connection.sourceHandle?.replace("-left", "") || "";
      const targetColumn = connection.targetHandle?.replace("-right", "") || "";

      createMutation.mutate({
        source_table: connection.source,
        source_column: sourceColumn,
        target_table: connection.target,
        target_column: targetColumn,
        relationship_type: "1:N",
        join_type: "LEFT",
      });
    },
    [createMutation]
  );

  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      if (confirm(t("confirmDeleteRelationship"))) {
        deleteMutation.mutate(edge.id);
      }
    },
    [deleteMutation, t]
  );

  const applySuggestion = (suggestion: RelationshipSuggestion) => {
    createMutation.mutate({
      source_table: suggestion.source_table,
      source_column: suggestion.source_column,
      target_table: suggestion.target_table,
      target_column: suggestion.target_column,
      relationship_type: "1:N",
      join_type: "LEFT",
    });
  };

  const hideTable = (tableName: string) => {
    setHiddenTables((prev) => new Set([...prev, tableName]));
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    saveTimeoutRef.current = setTimeout(saveLayout, 500);
  };

  const showTable = (tableName: string) => {
    setHiddenTables((prev) => {
      const next = new Set(prev);
      next.delete(tableName);
      return next;
    });
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    saveTimeoutRef.current = setTimeout(saveLayout, 500);
  };

  const handleCreateLayout = () => {
    if (!newLayoutName.trim()) return;
    createLayoutMutation.mutate({
      name: newLayoutName.trim(),
      is_default: layouts?.length === 0,
    });
  };

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
          onClick={() => queryClient.invalidateQueries({ queryKey: ["schema", connectionId] })}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
        >
          <RefreshCw size={14} />
          {t("refresh")}
        </button>
      </div>

      <div className="flex items-center gap-4 mb-4">
        <div className="relative">
          <button
            onClick={() => setShowLayoutDropdown(!showLayoutDropdown)}
            className="flex items-center gap-2 px-3 py-2 text-sm border border-border rounded-lg hover:bg-muted transition-colors min-w-[160px]"
          >
            <span className="flex-1 text-left truncate">
              {layouts?.find((l) => l.id === selectedLayoutId)?.name || t("selectView")}
            </span>
            <ChevronDown size={14} />
          </button>

          {showLayoutDropdown && (
            <div className="absolute top-full left-0 mt-1 w-64 bg-background border border-border rounded-lg shadow-lg z-50">
              <div className="p-2 border-b border-border">
                {showNewLayoutInput ? (
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newLayoutName}
                      onChange={(e) => setNewLayoutName(e.target.value)}
                      placeholder={t("viewNamePlaceholder")}
                      className="flex-1 px-2 py-1 text-sm border border-border rounded"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleCreateLayout();
                        if (e.key === "Escape") setShowNewLayoutInput(false);
                      }}
                    />
                    <button
                      onClick={handleCreateLayout}
                      disabled={!newLayoutName.trim() || createLayoutMutation.isPending}
                      className="px-2 py-1 text-sm bg-primary text-primary-foreground rounded disabled:opacity-50"
                    >
                      {t("create")}
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setShowNewLayoutInput(true)}
                    className="flex items-center gap-2 w-full px-2 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded"
                  >
                    <Plus size={14} />
                    {t("newView")}
                  </button>
                )}
              </div>

              <div className="max-h-48 overflow-y-auto">
                {layouts?.map((layout) => (
                  <div
                    key={layout.id}
                    className={`flex items-center justify-between px-3 py-2 hover:bg-muted cursor-pointer ${
                      layout.id === selectedLayoutId ? "bg-primary/10" : ""
                    }`}
                    onClick={() => {
                      setSelectedLayoutId(layout.id);
                      setShowLayoutDropdown(false);
                    }}
                  >
                    <span className="text-sm truncate">
                      {layout.name}
                      {layout.is_default && (
                        <span className="ml-2 text-xs text-muted-foreground">({t("default")})</span>
                      )}
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          duplicateLayoutMutation.mutate(layout.id);
                        }}
                        className="p-1 hover:bg-background rounded"
                        title={t("duplicate")}
                      >
                        <Copy size={12} />
                      </button>
                      {!layout.is_default && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (confirm(t("confirmDeleteView"))) {
                              deleteLayoutMutation.mutate(layout.id);
                            }
                          }}
                          className="p-1 hover:bg-background hover:text-destructive rounded"
                          title={t("deleteView")}
                        >
                          <Trash2 size={12} />
                        </button>
                      )}
                    </div>
                  </div>
                ))}

                {(!layouts || layouts.length === 0) && (
                  <div className="px-3 py-4 text-sm text-muted-foreground text-center">
                    {t("noViews")}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("searchTables")}
            className="w-full pl-9 pr-3 py-2 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X size={14} />
            </button>
          )}
        </div>

        <div className="text-sm text-muted-foreground">
          {t("showCount", { visible: visibleTables.length, total: schemaInfo?.tables.length || 0 })}
        </div>

        {hiddenTables.size > 0 && (
          <button
            onClick={() => setShowHiddenPanel(!showHiddenPanel)}
            className="flex items-center gap-2 px-3 py-2 text-sm border border-border rounded-lg hover:bg-muted transition-colors"
          >
            <EyeOff size={14} />
            {t("hiddenTables")} ({hiddenTables.size})
          </button>
        )}
      </div>

      {showHiddenPanel && hiddenTables.size > 0 && (
        <div className="mb-4 p-3 bg-muted/50 border border-border rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">{t("hiddenTables")}</span>
            <button
              onClick={() => setShowHiddenPanel(false)}
              className="text-muted-foreground hover:text-foreground"
            >
              <X size={14} />
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {Array.from(hiddenTables).map((tableName) => (
              <button
                key={tableName}
                onClick={() => showTable(tableName)}
                className="flex items-center gap-1 px-2 py-1 text-xs bg-background border border-border rounded hover:border-primary transition-colors"
              >
                <Eye size={12} />
                {tableName}
              </button>
            ))}
          </div>
        </div>
      )}

      {schemaInfo?.suggestions && schemaInfo.suggestions.length > 0 && (
        <div className="mb-4 p-3 bg-primary/5 border border-primary/20 rounded-lg">
          <div className="flex items-center gap-2 text-primary text-sm font-medium mb-2">
            <Lightbulb size={14} />
            {t("detectedRelationships")}
          </div>
          <div className="flex flex-wrap gap-2">
            {schemaInfo.suggestions.slice(0, 5).map((suggestion, index) => (
              <button
                key={index}
                onClick={() => applySuggestion(suggestion)}
                disabled={createMutation.isPending}
                className="px-2 py-1 text-xs bg-background border border-border rounded hover:border-primary transition-colors"
              >
                {suggestion.source_table}.{suggestion.source_column} → {suggestion.target_table}.
                {suggestion.target_column}
              </button>
            ))}
          </div>
        </div>
      )}

      {relationships && relationships.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {relationships.map((rel) => (
            <div
              key={rel.id}
              className="flex items-center gap-2 px-2 py-1 text-xs bg-primary/10 text-primary rounded"
            >
              <span>
                {rel.source_table}.{rel.source_column} → {rel.target_table}.{rel.target_column}
              </span>
              <button onClick={() => deleteMutation.mutate(rel.id)} className="hover:text-destructive">
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        className="border border-border rounded-lg overflow-hidden bg-muted/20"
        style={{ width: "100%", height: "500px", minHeight: "500px" }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={handleNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onEdgeClick={onEdgeClick}
          nodeTypes={nodeTypes}
          fitView
          snapToGrid
          snapGrid={[15, 15]}
          onNodeContextMenu={(e, node) => {
            e.preventDefault();
            if (confirm(t("confirmHideTable", { table: node.id }))) {
              hideTable(node.id);
            }
          }}
        >
          <Background gap={15} size={1} />
          <Controls />
          <MiniMap nodeColor="hsl(var(--primary))" maskColor="hsl(var(--background) / 0.8)" />
        </ReactFlow>
      </div>

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
