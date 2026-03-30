"use client";

import { useTranslations } from "next-intl";
import { Gauge, History, Settings, Sparkles } from "lucide-react";
import Link from "next/link";
import type { ConnectionSummary, ModelSummary } from "@/lib/types/api";
import { ConnectionDropdown } from "./ConnectionDropdown";
import { ModelDropdown } from "./ModelDropdown";
import { StatusChip } from "./StatusChip";

interface ChatHeaderProps {
  onToggleSidebar: () => void;
  connections?: ConnectionSummary[];
  models?: ModelSummary[];
  selectedConnectionId?: string | null;
  selectedModelId?: string | null;
  showConnectionDropdown: boolean;
  showModelDropdown: boolean;
  onToggleConnectionDropdown: () => void;
  onToggleModelDropdown: () => void;
  onSelectConnection: (id: string) => void;
  onSelectModel: (id: string) => void;
  modelReady: boolean;
  selectedModel?: ModelSummary;
  contextRounds: number;
}

export function ChatHeader({
  onToggleSidebar,
  connections,
  models,
  selectedConnectionId,
  selectedModelId,
  showConnectionDropdown,
  showModelDropdown,
  onToggleConnectionDropdown,
  onToggleModelDropdown,
  onSelectConnection,
  onSelectModel,
  modelReady,
  selectedModel,
  contextRounds,
}: ChatHeaderProps) {
  const t = useTranslations("chat");

  return (
    <header className="sticky top-0 z-10 border-b border-border bg-background/90 backdrop-blur">
      <div className="flex h-16 items-center justify-between px-4">
        <div className="flex items-center gap-4">
          <button
            onClick={onToggleSidebar}
            className="rounded-lg p-2 text-muted-foreground hover:bg-muted"
          >
            <History size={20} />
          </button>
          <div>
            <div className="text-sm font-medium text-foreground">QueryGPT</div>
            <div className="text-xs text-muted-foreground">{t("subtitle")}</div>
          </div>
        </div>

        <Link
          href="/settings"
          className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted"
        >
          <Settings size={18} />
        </Link>
      </div>

      <div className="flex flex-wrap items-center gap-3 px-4 pb-4">
        <ConnectionDropdown
          connections={connections}
          selectedId={selectedConnectionId}
          isOpen={showConnectionDropdown}
          onToggle={() => {
            onToggleConnectionDropdown();
            if (!showConnectionDropdown && showModelDropdown) {
              onToggleModelDropdown();
            }
          }}
          onSelect={(id) => {
            onSelectConnection(id);
          }}
        />

        <ModelDropdown
          models={models}
          selectedId={selectedModelId}
          isOpen={showModelDropdown}
          onToggle={() => {
            onToggleModelDropdown();
            if (!showModelDropdown && showConnectionDropdown) {
              onToggleConnectionDropdown();
            }
          }}
          onSelect={(id) => {
            onSelectModel(id);
          }}
        />

        <StatusChip tone={modelReady ? "success" : "warning"}>
          <Sparkles size={12} />
          {modelReady ? t("modelReady") : t("modelNoAuth")}
        </StatusChip>
        <StatusChip>
          <Gauge size={12} />
          {t("contextRounds", { count: contextRounds })}
        </StatusChip>
        {selectedModel?.extra_options?.api_format && (
          <StatusChip>{selectedModel.extra_options.api_format}</StatusChip>
        )}
      </div>
    </header>
  );
}
