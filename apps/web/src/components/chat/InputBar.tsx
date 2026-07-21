"use client";

import { useRef, useState } from "react";
import { ArrowUp, Database, Loader2, Paperclip, Square } from "lucide-react";
import type { ModelSummary } from "@/lib/types/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { AnalysisServiceSelector } from "./AnalysisServiceSelector";

interface InputBarProps {
  onSubmit: (query: string) => Promise<boolean | void>;
  onStop: () => void;
  onOpenData: () => void;
  onUploadFile: (file: File) => void;
  isLoading: boolean;
  isUploading: boolean;
  projectName?: string;
  dataReady: boolean;
  sourceCount: number;
  input: string;
  onInputChange: (value: string) => void;
  placement?: "dock" | "surface";
  analysisServices?: ModelSummary[];
  selectedAnalysisServiceId?: string | null;
  onSelectAnalysisService?: (modelId: string) => void | Promise<void>;
  onManageAnalysisServices?: () => void;
  analysisServiceLocked?: boolean;
  analysisServiceSaving?: boolean;
  analysisServiceError?: string | null;
  analysisServiceSelectorOpen?: boolean;
  onAnalysisServiceSelectorOpenChange?: (open: boolean) => void;
}

export function InputBar({
  onSubmit,
  onStop,
  onOpenData,
  onUploadFile,
  isLoading,
  isUploading,
  sourceCount,
  input,
  onInputChange,
  placement = "dock",
  analysisServices,
  selectedAnalysisServiceId = null,
  onSelectAnalysisService,
  onManageAnalysisServices,
  analysisServiceLocked = false,
  analysisServiceSaving = false,
  analysisServiceError,
  analysisServiceSelectorOpen,
  onAnalysisServiceSelectorOpenChange,
}: InputBarProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const submit = async () => {
    if (isLoading) {
      onStop();
      return;
    }
    if (!input.trim() || isSubmitting) return;
    setIsSubmitting(true);
    try {
      const accepted = await onSubmit(input.trim());
      if (accepted !== false) onInputChange("");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className={cn(
        placement === "dock"
          ? "border-t border-border bg-background px-5 pb-4 pt-2 sm:px-7 sm:pb-5 sm:pt-3"
          : "bg-transparent"
      )}
    >
      <div className={cn(placement === "dock" ? "mx-auto max-w-[1080px]" : "w-full")}>
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
              setIsDragging(false);
            }
          }}
          onDrop={(event) => {
            event.preventDefault();
            setIsDragging(false);
            const file = event.dataTransfer.files?.[0];
            if (file) onUploadFile(file);
          }}
          className={cn(
            "relative overflow-visible border bg-card transition-[border-color,background-color] focus-within:border-primary",
            isDragging ? "border-primary bg-primary/[0.03]" : "border-border"
          )}
        >
          {isDragging && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-card/95 text-sm font-semibold text-primary">
              松开后自动整理并加入当前项目
            </div>
          )}
          <textarea
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
            data-testid="chat-input"
            placeholder="输入问题或分析任务"
            disabled={isLoading}
            rows={2}
            className={cn(
              "max-h-44 w-full resize-none bg-transparent px-3 pb-0 pt-3 text-[15px] leading-6 text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-60 sm:px-4 sm:pb-2 sm:pt-4",
              placement === "surface" ? "min-h-[104px] sm:min-h-[122px]" : "min-h-[52px] sm:min-h-[76px]"
            )}
          />
          <div className="flex items-center justify-between gap-2 px-2 pb-2 sm:gap-3 sm:px-3 sm:pb-3">
            <div className="flex min-w-0 items-center gap-1">
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xls,.xlsx,.parquet,.json"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) onUploadFile(file);
                  event.currentTarget.value = "";
                }}
              />
              <Button
                variant="ghost"
                size="sm"
                disabled={isUploading}
                onClick={() => fileInputRef.current?.click()}
                aria-label={isUploading ? "正在整理文件" : "添加文件"}
                className="gap-1.5 px-2 text-xs"
              >
                {isUploading ? <Loader2 size={14} className="animate-spin" /> : <Paperclip size={14} />}
                <span className="hidden sm:inline">{isUploading ? "正在整理" : "文件"}</span>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={onOpenData}
                className="gap-1.5 px-2 text-xs"
              >
                <Database size={14} />
                <span className="sm:hidden">数据{sourceCount > 0 ? ` · ${sourceCount}` : ""}</span>
                <span className="hidden sm:inline">
                  数据来源{sourceCount > 0 ? ` · ${sourceCount}` : ""}
                </span>
              </Button>
              {analysisServices && onSelectAnalysisService && onManageAnalysisServices && (
                <AnalysisServiceSelector
                  models={analysisServices}
                  selectedModelId={selectedAnalysisServiceId}
                  onSelect={onSelectAnalysisService}
                  onManage={onManageAnalysisServices}
                  locked={analysisServiceLocked}
                  saving={analysisServiceSaving}
                  error={analysisServiceError}
                  open={analysisServiceSelectorOpen}
                  onOpenChange={onAnalysisServiceSelectorOpenChange}
                />
              )}
            </div>
            <Button
              variant={isLoading ? "destructive" : "primary"}
              size="icon"
              onClick={() => void submit()}
              disabled={!input.trim() && !isLoading}
              data-testid="chat-submit"
              aria-label={isLoading ? "停止分析" : "开始分析"}
            >
              {isLoading ? <Square size={15} fill="currentColor" /> : <ArrowUp size={18} />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
