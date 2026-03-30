"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { TableNode } from "@/components/schema/TableNode";
import {
  buildRelationshipEdges,
  buildSchemaNodes,
} from "@/lib/settings/schema";
import { useSchemaLayout } from "@/lib/hooks/useSchemaLayout";
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
  _schemaInfo,
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
  const { debouncedSaveLayout } = useSchemaLayout(
    currentLayout,
    visibleTables,
    hiddenTables,
    onSaveLayout
  );
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Memoize nodes — only rebuild when visibleTables or currentLayout change
  // Do NOT rebuild on every node position change (which updates nodes state)
  const memoizedNodes = useMemo(() => {
    if (!visibleTables || visibleTables.length === 0) {
      return [];
    }
    return buildSchemaNodes(visibleTables, currentLayout);
  }, [visibleTables, currentLayout]);

  // Memoize edges — only rebuild when relationships or visibleTables change
  const memoizedEdges = useMemo(() => {
    if (relationships.length === 0 || visibleTables.length === 0) {
      return [];
    }
    return buildRelationshipEdges(visibleTables, relationships);
  }, [relationships, visibleTables]);

  // Update nodes only when memoized version changes (not on every drag)
  useEffect(() => {
    setNodes(memoizedNodes);
  }, [memoizedNodes, setNodes]);

  // Update edges only when memoized version changes
  useEffect(() => {
    setEdges(memoizedEdges);
  }, [memoizedEdges, setEdges]);

  // Handle node changes with debounced save
  const handleNodesChange = useCallback(
    (changes: NodeChange<Node>[]) => {
      onNodesChange(changes);

      // Only save layout if position changed
      const hasPositionChange = changes.some(
        (change) => change.type === "position" && change.dragging === false
      );

      if (hasPositionChange) {
        debouncedSaveLayout(nodes);
      }
    },
    [nodes, onNodesChange, debouncedSaveLayout]
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
