"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Loader2,
  LockKeyhole,
  Settings2,
} from "lucide-react";
import type { ModelSummary } from "@/lib/types/api";
import { cn } from "@/lib/utils";

export type AnalysisServiceState =
  | "available"
  | "unchecked"
  | "reconnect"
  | "temporarily_unavailable"
  | "needs_attention";

export interface AnalysisServicePresentation {
  state: AnalysisServiceState;
  label: string;
  selectable: boolean;
}

export function getAnalysisServicePresentation(
  model: ModelSummary
): AnalysisServicePresentation {
  const credentialState =
    model.credential_state ||
    (model.extra_options?.api_key_optional
      ? "not_required"
      : model.api_key_configured
        ? "readable"
        : "missing");

  if (credentialState === "missing") {
    return { state: "reconnect", label: "尚未连接", selectable: false };
  }
  if (credentialState === "unreadable") {
    return { state: "reconnect", label: "需要重新连接", selectable: false };
  }

  if (model.health_status === "healthy") {
    return { state: "available", label: "可用", selectable: true };
  }

  if (model.health_status === "unhealthy") {
    if (model.last_error_category === "auth") {
      return { state: "reconnect", label: "需要重新连接", selectable: false };
    }
    if (
      model.last_error_category === "timeout" ||
      model.last_error_category === "connection" ||
      model.last_error_category === "rate_limited"
    ) {
      return {
        state: "temporarily_unavailable",
        label: "暂时不可用",
        selectable: false,
      };
    }
    return { state: "needs_attention", label: "需要处理", selectable: false };
  }

  return { state: "unchecked", label: "未检查", selectable: true };
}

interface AnalysisServiceSelectorProps {
  models: ModelSummary[];
  selectedModelId: string | null;
  onSelect: (modelId: string) => void | Promise<void>;
  onManage: () => void;
  locked?: boolean;
  saving?: boolean;
  error?: string | null;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

export function AnalysisServiceSelector({
  models,
  selectedModelId,
  onSelect,
  onManage,
  locked = false,
  saving = false,
  error,
  open,
  onOpenChange,
  className,
}: AnalysisServiceSelectorProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();
  const isOpen = open ?? internalOpen;
  const activeModels = models.filter((model) => model.is_active !== false);
  const selectedModel = activeModels.find((model) => model.id === selectedModelId);
  const selectedPresentation = selectedModel
    ? getAnalysisServicePresentation(selectedModel)
    : null;

  const setOpen = useCallback(
    (nextOpen: boolean) => {
      if (open === undefined) setInternalOpen(nextOpen);
      onOpenChange?.(nextOpen);
    },
    [onOpenChange, open]
  );

  useEffect(() => {
    if (!isOpen) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, setOpen]);

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        type="button"
        data-analysis-service-selector-trigger
        data-testid="analysis-service-selector"
        aria-controls={listboxId}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-label={
          locked
            ? `本次调查使用分析服务：${selectedModel?.name || "未选择"}`
            : `选择分析服务，当前：${selectedModel?.name || "未选择"}`
        }
        onClick={() => {
          if (!locked && !saving) setOpen(!isOpen);
        }}
        className={cn(
          "inline-flex max-w-[220px] items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
          locked
            ? "cursor-default text-muted-foreground"
            : "text-muted-foreground hover:bg-muted hover:text-foreground"
        )}
      >
        {saving ? (
          <Loader2 size={14} className="shrink-0 animate-spin" />
        ) : locked ? (
          <LockKeyhole size={13} className="shrink-0" />
        ) : selectedPresentation?.state === "available" ? (
          <CircleCheck size={14} className="shrink-0 text-success" />
        ) : selectedPresentation && selectedPresentation.state !== "unchecked" ? (
          <CircleAlert size={14} className="shrink-0 text-warning" />
        ) : (
          <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground/40" />
        )}
        <span className="shrink-0">分析服务</span>
        <span aria-hidden="true">·</span>
        <span className="truncate text-foreground">{selectedModel?.name || "未选择"}</span>
        {!locked && <ChevronDown size={13} className="shrink-0" />}
      </button>

      {isOpen && !locked && (
        <div
          id={listboxId}
          role="listbox"
          aria-label="分析服务"
          className="absolute bottom-full left-0 z-50 mb-2 w-72 overflow-hidden border border-border bg-card"
        >
          <div className="border-b border-border px-3 py-2.5">
            <div className="text-xs font-semibold text-foreground">用于下一次调查</div>
            <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
              调查开始后会固定使用所选服务。
            </p>
          </div>

          <div className="max-h-64 overflow-y-auto py-1">
            {activeModels.length ? (
              activeModels.map((model) => {
                const presentation = getAnalysisServicePresentation(model);
                const selected = model.id === selectedModelId;
                return (
                  <button
                    key={model.id}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    disabled={!presentation.selectable || saving}
                    onClick={() => {
                      setOpen(false);
                      void onSelect(model.id);
                    }}
                    className={cn(
                      "flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors",
                      selected ? "bg-primary/[0.07]" : "hover:bg-muted",
                      (!presentation.selectable || saving) &&
                        "cursor-not-allowed opacity-60 hover:bg-transparent"
                    )}
                  >
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center">
                      {selected ? <Check size={15} className="text-primary" /> : null}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-foreground">
                        {model.name}
                      </span>
                      <span
                        className={cn(
                          "mt-0.5 block text-[11px]",
                          presentation.state === "available"
                            ? "text-success"
                            : presentation.state === "unchecked"
                              ? "text-muted-foreground"
                              : "text-warning"
                        )}
                      >
                        {presentation.label}
                      </span>
                    </span>
                  </button>
                );
              })
            ) : (
              <p className="px-4 py-5 text-center text-xs text-muted-foreground">
                还没有可选择的分析服务
              </p>
            )}
          </div>

          {error && (
            <p role="alert" className="border-t border-destructive/30 bg-destructive/[0.06] px-3 py-2 text-xs text-destructive">
              {error}
            </p>
          )}

          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onManage();
            }}
            className="flex w-full items-center gap-2 border-t border-border px-3 py-2.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Settings2 size={14} />
            管理分析服务
          </button>
        </div>
      )}
    </div>
  );
}
