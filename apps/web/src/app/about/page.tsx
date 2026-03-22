"use client";

import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Bot,
  Database,
  Gauge,
  GitBranch,
  Layers,
  Palette,
  Shield,
} from "lucide-react";
import { useTranslations } from "next-intl";

const VERSION = "2.0.0";

export default function AboutPage() {
  const router = useRouter();
  const t = useTranslations("about");

  const providers = [
    ["OpenAI-compatible", t("providerOpenaiDesc")],
    ["Anthropic", t("providerAnthropicDesc")],
    ["Ollama", t("providerOllamaDesc")],
    ["Custom", t("providerCustomDesc")],
  ];

  const capabilities = [
    [t("capNl2sql"), t("capNl2sqlDesc")],
    [t("capTraceable"), t("capTraceableDesc")],
    [t("capAutoRepair"), t("capAutoRepairDesc")],
    [t("capWorkspace"), t("capWorkspaceDesc")],
  ];

  const currentLimits = [
    t("limitSingleUser"),
    t("limitQueryStop"),
    t("limitReadOnly"),
  ];

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-50 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center px-6">
          <button
            onClick={() => router.back()}
            className="flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft size={18} />
            {t("back")}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-12">
        <section className="rounded-[28px] border border-border bg-secondary p-8">
          <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-border bg-background px-3 py-1 text-xs text-muted-foreground">
                <Gauge size={12} />
                Single-User Workspace
              </div>
              <h1 className="mt-4 text-4xl font-semibold text-foreground">QueryGPT</h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
                {t("description")}
              </p>
            </div>
            <div className="rounded-2xl border border-border bg-background px-5 py-4 text-sm">
              <div className="text-muted-foreground">Version</div>
              <div className="mt-1 font-medium text-foreground">{VERSION}</div>
            </div>
          </div>
        </section>

        <section className="mt-8 grid gap-6 md:grid-cols-2">
          <div className="rounded-2xl border border-border bg-background p-6">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Bot size={16} className="text-primary" />
              {t("supportedAdapters")}
            </div>
            <div className="mt-4 space-y-3">
              {providers.map(([name, desc]) => (
                <div key={name} className="rounded-xl border border-border bg-secondary px-4 py-3">
                  <div className="text-sm font-medium text-foreground">{name}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-background p-6">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Layers size={16} className="text-primary" />
              {t("coreCapabilities")}
            </div>
            <div className="mt-4 space-y-3">
              {capabilities.map(([name, desc]) => (
                <div key={name} className="rounded-xl border border-border bg-secondary px-4 py-3">
                  <div className="text-sm font-medium text-foreground">{name}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{desc}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mt-8 grid gap-6 md:grid-cols-3">
          <div className="rounded-2xl border border-border bg-background p-6">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Database size={16} className="text-primary" />
              {t("dataSources")}
            </div>
            <div className="mt-3 text-sm text-muted-foreground">MySQL / PostgreSQL / SQLite</div>
          </div>
          <div className="rounded-2xl border border-border bg-background p-6">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <GitBranch size={16} className="text-primary" />
              {t("relationsAndSemantic")}
            </div>
            <div className="mt-3 text-sm text-muted-foreground">{t("relationsAndSemanticDesc")}</div>
          </div>
          <div className="rounded-2xl border border-border bg-background p-6">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Palette size={16} className="text-primary" />
              {t("ui")}
            </div>
            <div className="mt-3 text-sm text-muted-foreground">{t("uiDesc")}</div>
          </div>
        </section>

        <section className="mt-8 rounded-2xl border border-border bg-background p-6">
          <div className="flex items-center gap-2 text-sm font-medium text-foreground">
            <Shield size={16} className="text-primary" />
            {t("knownLimitations")}
          </div>
          <ul className="mt-4 space-y-3 text-sm text-muted-foreground">
            {currentLimits.map((item) => (
              <li key={item} className="rounded-xl border border-border bg-secondary px-4 py-3">
                {item}
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
