"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { AlertTriangle, Send, Square } from "lucide-react";
import { cn } from "@/lib/utils";

interface InputBarProps {
  onSubmit: (query: string) => Promise<void>;
  onStop: () => void;
  isLoading: boolean;
  readyToQuery: boolean;
  modelReady: boolean;
  selectedModel?: { name: string };
  input: string;
  onInputChange: (value: string) => void;
}

export function InputBar({
  onSubmit,
  onStop,
  isLoading,
  readyToQuery,
  modelReady,
  selectedModel,
  input,
  onInputChange,
}: InputBarProps) {
  const t = useTranslations("chat");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (isLoading) {
      onStop();
      return;
    }
    if (!input.trim() || !readyToQuery || isSubmitting) return;

    setIsSubmitting(true);
    try {
      await onSubmit(input);
      onInputChange("");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="border-t border-border bg-background p-4">
      <form onSubmit={handleSubmit} className="mx-auto max-w-5xl">
        {!modelReady && selectedModel && (
          <div className="mb-3 flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-800">
            <AlertTriangle size={16} />
            {t("modelWarning")}
          </div>
        )}
        <div className="relative flex items-center">
          <input
            type="text"
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            data-testid="chat-input"
            placeholder={t("inputPlaceholder")}
            disabled={isLoading}
            className="w-full rounded-[24px] border border-input bg-background px-5 py-4 pr-16 text-foreground shadow-sm outline-none transition-all focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={(!input.trim() && !isLoading) || !readyToQuery}
            data-testid="chat-submit"
            className={cn(
              "absolute right-2 rounded-2xl p-3 text-white shadow-sm transition-all",
              isLoading
                ? "bg-red-500 hover:bg-red-600"
                : "bg-primary hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
            )}
          >
            {isLoading ? <Square size={18} fill="currentColor" /> : <Send size={18} />}
          </button>
        </div>
        <div className="mt-2 text-center text-xs text-muted-foreground">
          {t("disclaimer")}
        </div>
      </form>
    </div>
  );
}
