"use client";

import { useRef } from "react";
import { useTranslations } from "next-intl";
import { Brain, ChevronDown } from "lucide-react";
import type { ModelSummary } from "@/lib/types/api";
import { cn } from "@/lib/utils";
import { StatusChip } from "./StatusChip";

interface ModelDropdownProps {
  models?: ModelSummary[];
  selectedId?: string | null;
  isOpen: boolean;
  onToggle: () => void;
  onSelect: (id: string) => void;
}

export function ModelDropdown({
  models,
  selectedId,
  isOpen,
  onToggle,
  onSelect,
}: ModelDropdownProps) {
  const t = useTranslations("chat");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const selectedModel = models?.find((item) => item.id === selectedId);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={onToggle}
        data-testid="chat-model-select"
        className="flex items-center gap-2 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
      >
        <Brain size={14} className="text-muted-foreground" />
        <span className="max-w-[180px] truncate">{selectedModel?.name || t("selectModel")}</span>
        <ChevronDown size={14} className="text-muted-foreground" />
      </button>
      {isOpen && (
        <div className="absolute left-0 top-full z-50 mt-1 w-80 rounded-xl border border-border bg-background py-1 shadow-lg">
          {models?.length ? (
            models.map((model) => (
              <button
                key={model.id}
                onClick={() => {
                  onSelect(model.id);
                }}
                data-testid={`chat-model-option-${model.id}`}
                className={cn(
                  "flex w-full items-center justify-between px-3 py-2 text-left text-sm text-foreground hover:bg-muted",
                  model.id === selectedId && "bg-primary/10 text-primary"
                )}
              >
                <div>
                  <div className="font-medium">{model.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {model.provider} · {model.model_id}
                  </div>
                </div>
                {model.is_default && <StatusChip>{t("default")}</StatusChip>}
              </button>
            ))
          ) : (
            <div className="px-3 py-4 text-sm text-muted-foreground">
              {t("noModels")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
