"use client";

import { useState } from "react";
import { ChevronDown, Search, Eye, EyeOff, X, Plus, Copy, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import type { SchemaLayoutListItem } from "@/lib/types/schema";

interface LayoutControlsProps {
  layouts: SchemaLayoutListItem[];
  selectedLayoutId: string | null;
  searchQuery: string;
  hiddenTables: Set<string>;
  showHiddenPanel: boolean;
  visibleTableCount: number;
  totalTableCount: number;
  onSelectLayout: (id: string) => void;
  onCreateLayout: (name: string) => Promise<void>;
  onDeleteLayout: (id: string) => void;
  onDuplicateLayout: (id: string) => void;
  onSearch: (query: string) => void;
  onToggleHiddenPanel: () => void;
  onShowTable: (tableName: string) => void;
}

interface LayoutDropdownProps {
  layouts: SchemaLayoutListItem[];
  selectedLayoutId: string | null;
  onSelectLayout: (id: string) => void;
  onCreateLayout: (name: string) => Promise<void>;
  onDeleteLayout: (id: string) => void;
  onDuplicateLayout: (id: string) => void;
}

function LayoutDropdown({
  layouts,
  selectedLayoutId,
  onSelectLayout,
  onCreateLayout,
  onDeleteLayout,
  onDuplicateLayout,
}: LayoutDropdownProps) {
  const [show, setShow] = useState(false);
  const [newName, setNewName] = useState("");
  const [showNewInput, setShowNewInput] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const t = useTranslations("schema");

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setIsCreating(true);
    try {
      await onCreateLayout(newName.trim());
      setNewName("");
      setShowNewInput(false);
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setShow(!show)}
        className="flex items-center gap-2 px-3 py-2 text-sm border border-border rounded-lg hover:bg-muted min-w-[160px]"
      >
        <span className="flex-1 text-left truncate">
          {layouts.find((l) => l.id === selectedLayoutId)?.name || t("selectView")}
        </span>
        <ChevronDown size={14} />
      </button>

      {show && (
        <div className="absolute top-full left-0 mt-1 w-64 bg-background border border-border rounded-lg shadow-lg z-50">
          <div className="p-2 border-b border-border">
            {showNewInput ? (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder={t("viewNamePlaceholder")}
                  className="flex-1 px-2 py-1 text-sm border border-border rounded"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleCreate();
                    if (e.key === "Escape") setShowNewInput(false);
                  }}
                />
                <button
                  onClick={handleCreate}
                  disabled={!newName.trim() || isCreating}
                  className="px-2 py-1 text-sm bg-primary text-primary-foreground rounded disabled:opacity-50"
                >
                  {t("create")}
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowNewInput(true)}
                className="flex items-center gap-2 w-full px-2 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded"
              >
                <Plus size={14} />
                {t("newView")}
              </button>
            )}
          </div>

          <div className="max-h-48 overflow-y-auto">
            {layouts.map((layout) => (
              <div
                key={layout.id}
                className={`flex items-center justify-between px-3 py-2 hover:bg-muted cursor-pointer ${
                  layout.id === selectedLayoutId ? "bg-primary/10" : ""
                }`}
                onClick={() => {
                  onSelectLayout(layout.id);
                  setShow(false);
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
                      onDuplicateLayout(layout.id);
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
                          onDeleteLayout(layout.id);
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
            {layouts.length === 0 && (
              <div className="px-3 py-4 text-sm text-muted-foreground text-center">
                {t("noViews")}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function LayoutControls({
  layouts,
  selectedLayoutId,
  searchQuery,
  hiddenTables,
  showHiddenPanel,
  visibleTableCount,
  totalTableCount,
  onSelectLayout,
  onCreateLayout,
  onDeleteLayout,
  onDuplicateLayout,
  onSearch,
  onToggleHiddenPanel,
  onShowTable,
}: LayoutControlsProps) {
  const t = useTranslations("schema");

  return (
    <div className="space-y-3 p-4 border-b">
      <div className="flex items-center gap-4">
        <LayoutDropdown
          layouts={layouts}
          selectedLayoutId={selectedLayoutId}
          onSelectLayout={onSelectLayout}
          onCreateLayout={onCreateLayout}
          onDeleteLayout={onDeleteLayout}
          onDuplicateLayout={onDuplicateLayout}
        />

        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearch(e.target.value)}
            placeholder={t("searchTables")}
            className="w-full pl-9 pr-3 py-2 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
          {searchQuery && (
            <button
              onClick={() => onSearch("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X size={14} />
            </button>
          )}
        </div>

        <div className="text-sm text-muted-foreground whitespace-nowrap">
          {t("showCount", { visible: visibleTableCount, total: totalTableCount })}
        </div>

        {hiddenTables.size > 0 && (
          <button
            onClick={onToggleHiddenPanel}
            className="flex items-center gap-2 px-3 py-2 text-sm border border-border rounded-lg hover:bg-muted"
          >
            <EyeOff size={14} />
            {t("hiddenTables")} ({hiddenTables.size})
          </button>
        )}
      </div>

      {showHiddenPanel && hiddenTables.size > 0 && (
        <div className="p-3 bg-muted/50 border border-border rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">{t("hiddenTables")}</span>
            <button onClick={onToggleHiddenPanel} className="text-muted-foreground hover:text-foreground">
              <X size={14} />
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {Array.from(hiddenTables).map((tableName) => (
              <button
                key={tableName}
                onClick={() => onShowTable(tableName)}
                className="flex items-center gap-1 px-2 py-1 text-xs bg-background border border-border rounded hover:border-primary"
              >
                <Eye size={12} />
                {tableName}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
