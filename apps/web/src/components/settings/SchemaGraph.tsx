"use client";

import { useCallback, useEffect, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { TableNode } from "@/components/schema/TableNode";
import {
  buildLayoutSnapshot,
  buildRelationshipEdges,
  buildSchemaNodes,
} from "@/lib/settings/schema";
import type {
  SchemaInfo,
  TableRelationship,
  SchemaLayout,
  TableInfo,
  SchemaLayoutUpdate,
} from "@/lib/types/schema";

interface SchemaGraphProps {
  schemaInfo: SchemaInfo | null;
  relationships: TableRelationship[];
  visibleTables: TableInfo[];
  currentLayout: SchemaLayout | null;
  hiddenTables: Set<string>;
  onSaveLayout: (snapshot: SchemaLayoutUpdate) => void;
  onConnect: (connection: Connection) => void;
  onEdgeClick: (_: React.MouseEvent, edge: Edge) => void;
  onNodeContextMenu: (
    event: React.MouseEvent,
    node: Node
  ) => void;
}

export function SchemaGraph({
  schemaInfo,
  relationships,
  visibleTables,
  currentLayout,
  hiddenTables,
  onSaveLayout,
  onConnect,
  onEdgeClick,
  onNodeContextMenu,
}: SchemaGraphProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChangeInternal] = useEdgesState<Edge>([]);
  const { getViewport } = useReactFlow();
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastSavedRef = useRef<string>("");

  // Initialize nodes from visible tables
  useEffect(() => {
    if (!visibleTables || visibleTables.length === 0) {
      setNodes([]);
      return;
    }
    setNodes(buildSchemaNodes(visibleTables, currentLayout));
  }, [visibleTables, currentLayout, setNodes]);

  // Initialize edges from relationships
  useEffect(() => {
    if (relationships.length === 0 || visibleTables.length === 0) {
      setEdges([]);
      return;
    }
    setEdges(buildRelationshipEdges(visibleTables, relationships));
  }, [relationships, visibleTables, setEdges]);

  // Auto-save layout on node position change
  const saveLayout = useCallback(() => {
    if (!currentLayout?.id) return;

    const snapshot = buildLayoutSnapshot(nodes, getViewport(), schemaInfo?.tables, hiddenTables);

    if (snapshot.signature === lastSavedRef.current) return;
    lastSavedRef.current = snapshot.signature;

    onSaveLayout(snapshot.payload);
  }, [nodes, getViewport, currentLayout, schemaInfo, hiddenTables, onSaveLayout]);

  const handleNodesChange = useCallback(
    (changes: NodeChange<Node>[]) => {
      onNodesChange(changes);

      const hasPositionChange = changes.some(
        (change) => change.type === "position" && change.dragging === false
      );

      if (hasPositionChange) {
        if (saveTimeoutRef.current) {
          clearTimeout(saveTimeoutRef.current);
        }
        saveTimeoutRef.current = setTimeout(saveLayout, 500);
      }
    },
    [onNodesChange, saveLayout]
  );

  const nodeTypes = {
    tableNode: TableNode,
  };

  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, []);

  return (
    <div
      className="border border-border rounded-lg overflow-hidden bg-muted/20"
      style={{ width: "100%", height: "500px", minHeight: "500px" }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={onEdgesChangeInternal}
        onConnect={onConnect}
        onEdgeClick={onEdgeClick}
        nodeTypes={nodeTypes}
        fitView
        snapToGrid
        snapGrid={[15, 15]}
        onNodeContextMenu={onNodeContextMenu}
      >
        <Background gap={15} size={1} />
        <Controls />
        <MiniMap nodeColor="hsl(var(--primary))" maskColor="hsl(var(--background) / 0.8)" />
      </ReactFlow>
    </div>
  );
}
