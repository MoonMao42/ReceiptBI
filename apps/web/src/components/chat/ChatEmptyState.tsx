"use client";

import { Brain } from "lucide-react";
import { useTranslations } from "next-intl";
import type { AppSettings } from "@/lib/types/api";
import { StatusChip } from "./StatusChip";

interface EmptyStateConnection {
  id: string;
  name: string;
}

interface EmptyStateModel {
  id: string;
  name: string;
}

interface ChatEmptyStateProps {
  selectedConnection: EmptyStateConnection | undefined;
  selectedModel: EmptyStateModel | undefined;
  readyToQuery: boolean;
  appSettings?: AppSettings;
  onOpenSettings: () => void;
  onUsePrompt: (prompt: string) => void;
}

const SAMPLE_PROMPTS_KEYS = ["sample1", "sample2", "sample3", "sample4"] as const;

export function ChatEmptyState({
  selectedConnection,
  selectedModel,
  readyToQuery,
  appSettings: _appSettings,
  onOpenSettings,
  onUsePrompt,
}: ChatEmptyStateProps) {
  const t = useTranslations("chatEmpty");
  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col items-center justify-center text-center">
      <div className="rounded-[28px] border border-border bg-secondary px-8 py-10">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-border bg-background">
          <Brain size={28} className="text-primary" />
        </div>
        <h2 className="mt-5 text-2xl font-semibold text-foreground">{t("title")}</h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          {t("description")}
        </p>

        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <StatusChip tone={selectedConnection ? "success" : "warning"}>
            {t("database")}: {selectedConnection?.name || t("notSelected")}
          </StatusChip>
          <StatusChip tone={selectedModel ? "success" : "warning"}>
            {t("model")}: {selectedModel?.name || t("notSelected")}
          </StatusChip>
        </div>

        {!readyToQuery && (
          <div className="mt-6 rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-left text-sm text-amber-800">
            {t("notReadyMessage")}
            <button onClick={onOpenSettings} className="ml-2 font-medium text-primary underline">
              {t("goSettings")}
            </button>
          </div>
        )}

        <div className="mt-8 grid gap-3 text-left md:grid-cols-2">
          {SAMPLE_PROMPTS_KEYS.map((sample) => (
            <button
              key={sample}
              onClick={() => onUsePrompt(t(sample))}
              className="rounded-2xl border border-border bg-background px-4 py-4 text-sm text-foreground transition-all hover:border-primary/40 hover:shadow-sm"
            >
              {t(sample)}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
