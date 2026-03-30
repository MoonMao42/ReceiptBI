"use client";

import { useRef } from "react";
import { useTranslations } from "next-intl";
import { ChevronDown, Database } from "lucide-react";
import type { ConnectionSummary } from "@/lib/types/api";
import { cn } from "@/lib/utils";
import { StatusChip } from "./StatusChip";

interface ConnectionDropdownProps {
  connections?: ConnectionSummary[];
  selectedId?: string | null;
  isOpen: boolean;
  onToggle: () => void;
  onSelect: (id: string) => void;
}

export function ConnectionDropdown({
  connections,
  selectedId,
  isOpen,
  onToggle,
  onSelect,
}: ConnectionDropdownProps) {
  const t = useTranslations("chat");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const selectedConnection = connections?.find((item) => item.id === selectedId);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={onToggle}
        data-testid="chat-connection-select"
        className="flex items-center gap-2 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
      >
        <Database size={14} className="text-muted-foreground" />
        <span className="max-w-[180px] truncate">{selectedConnection?.name || t("selectDatabase")}</span>
        <ChevronDown size={14} className="text-muted-foreground" />
      </button>
      {isOpen && (
        <div className="absolute left-0 top-full z-50 mt-1 w-72 rounded-xl border border-border bg-background py-1 shadow-lg">
          {connections?.length ? (
            connections.map((connection) => (
              <button
                key={connection.id}
                onClick={() => {
                  onSelect(connection.id);
                }}
                data-testid={`chat-connection-option-${connection.id}`}
                className={cn(
                  "flex w-full items-center justify-between px-3 py-2 text-left text-sm text-foreground hover:bg-muted",
                  connection.id === selectedId && "bg-primary/10 text-primary"
                )}
              >
                <div>
                  <div className="font-medium">{connection.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {connection.driver}
                    {connection.database_name ? ` · ${connection.database_name}` : ""}
                  </div>
                </div>
                {connection.is_default && <StatusChip>{t("default")}</StatusChip>}
              </button>
            ))
          ) : (
            <div className="px-3 py-4 text-sm text-muted-foreground">
              {t("noConnections")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
