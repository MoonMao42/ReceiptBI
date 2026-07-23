"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Database,
  FileSearch,
  Info,
  Layers3,
  Loader2,
  Palette,
  Play,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { ModelSettings } from "@/components/settings/ModelSettings";
import { cn } from "@/lib/utils";
import { RECEIPTBI_BRAND_ICON_SRC } from "@/lib/brand";

function SettingsPanelPending() {
  const t = useTranslations("settings");
  return (
    <div
      role="status"
      aria-label={t("openingAria")}
      className="flex min-h-40 items-center justify-center text-muted-foreground"
    >
      <Loader2 size={16} className="animate-spin" />
    </div>
  );
}

const loadConnectionSettings = () =>
  import("@/components/settings/ConnectionSettings").then(
    (module) => module.ConnectionSettings
  );

const loadPreferencesSettings = () =>
  import("@/components/settings/PreferencesSettings").then(
    (module) => module.PreferencesSettings
  );

const ConnectionSettings = dynamic(loadConnectionSettings, {
  loading: SettingsPanelPending,
});

const PreferencesSettings = dynamic(loadPreferencesSettings, {
  loading: SettingsPanelPending,
});

type TabType =
  | "models"
  | "connections"
  | "execution"
  | "appearance"
  | "advanced";

interface NavigationItem {
  id: TabType;
  label: string;
  description: string;
  icon: typeof Layers3;
  testId: string;
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabType>("models");
  const [routeReady, setRouteReady] = useState(false);
  const router = useRouter();
  const t = useTranslations("settings");

  useEffect(() => {
    const requestedTab = new URLSearchParams(window.location.search).get("tab");
    const destinations: Record<string, TabType> = {
      models: "models",
      connections: "connections",
      preferences: "appearance",
      appearance: "appearance",
      runtime: "execution",
      execution: "execution",
      diagnostics: "advanced",
      advanced: "advanced",
    };
    const destination = requestedTab ? destinations[requestedTab] : null;
    if (destination) setActiveTab(destination);
    setRouteReady(true);
  }, []);

  useEffect(() => {
    if (!routeReady) return;
    router.prefetch("/about");
    const warmPanels = () => {
      void Promise.allSettled([loadConnectionSettings(), loadPreferencesSettings()]);
    };
    if ("requestIdleCallback" in window) {
      const idleId = window.requestIdleCallback(warmPanels, { timeout: 1200 });
      return () => window.cancelIdleCallback(idleId);
    }
    const timeoutId = globalThis.setTimeout(warmPanels, 250);
    return () => globalThis.clearTimeout(timeoutId);
  }, [routeReady, router]);

  const primaryTabs: NavigationItem[] = [
    {
      id: "models",
      label: t("analysisService"),
      description: t("analysisServiceDesc"),
      icon: Layers3,
      testId: "settings-tab-models",
    },
    {
      id: "connections",
      label: t("dataConnections"),
      description: t("dataConnectionsDesc"),
      icon: Database,
      testId: "settings-tab-connections",
    },
    {
      id: "execution",
      label: t("execution"),
      description: t("executionDesc"),
      icon: Play,
      testId: "settings-tab-execution",
    },
    {
      id: "appearance",
      label: t("appearance"),
      description: t("appearanceDesc"),
      icon: Palette,
      testId: "settings-tab-appearance",
    },
    {
      id: "advanced",
      label: t("diagnostics"),
      description: t("diagnosticsDesc"),
      icon: FileSearch,
      testId: "settings-tab-advanced",
    },
  ];

  const activeItem = primaryTabs.find((tab) => tab.id === activeTab);
  const activeLabel = activeItem?.label;

  const renderNavigation = (items: NavigationItem[]) => (
    <div className="space-y-1">
      {items.map((item) => {
        const selected = item.id === activeTab;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => {
              setActiveTab(item.id);
            }}
            data-testid={item.testId}
            aria-current={selected ? "page" : undefined}
            className={cn(
              "group flex w-full items-center gap-3 border-l-2 px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary",
              selected
                ? "border-primary bg-primary/10 text-foreground"
                : "border-transparent text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <item.icon
              size={16}
              className={selected ? "text-primary" : "text-muted-foreground group-hover:text-foreground"}
            />
            <span className="text-sm">{item.label}</span>
          </button>
        );
      })}
    </div>
  );

  return (
    <div className="min-h-screen bg-background text-foreground lg:flex">
      <aside className="border-r border-border bg-card text-card-foreground lg:sticky lg:top-0 lg:flex lg:h-screen lg:w-[252px] lg:flex-col">
        <div className="flex h-[72px] items-center border-b border-border px-5">
          <Image
            src={RECEIPTBI_BRAND_ICON_SRC}
            alt=""
            width={32}
            height={32}
            unoptimized
            className="h-8 w-8 object-contain"
            aria-hidden="true"
          />
          <div className="ml-3">
            <div className="text-sm font-semibold tracking-wide">ReceiptBI</div>
            <div className="text-[10px] tracking-[0.14em] text-muted-foreground">{t("workbench")}</div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => router.push("/")}
          className="mx-4 mt-4 flex items-center gap-2 border border-border px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <ArrowLeft size={16} />
          {t("backToProject")}
        </button>

        <nav className="grid gap-4 px-3 py-5 sm:grid-cols-2 lg:block lg:flex-1 lg:overflow-y-auto">
          <div>
            <div className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              {t("globalSettings")}
            </div>
            {renderNavigation(primaryTabs)}
          </div>
        </nav>

        <Link
          href="/about"
          prefetch
          className="flex w-full items-center gap-3 border-t border-border px-6 py-4 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
        >
          <Info size={16} />
          {t("about")}
        </Link>
      </aside>

      <section className="min-w-0 flex-1">
        <header className="sticky top-0 z-10 border-b border-border bg-background/95 backdrop-blur">
          <div className="flex min-h-[64px] items-center px-5 sm:px-8 lg:px-10">
            <h1 className="truncate text-xl font-semibold tracking-[-0.02em] text-foreground">
              {activeLabel || t("title")}
            </h1>
          </div>
        </header>

        <main className="w-full max-w-[1180px] px-5 py-6 sm:px-8 lg:px-10 lg:py-7">
          {!routeReady ? (
            <SettingsPanelPending />
          ) : (
            <>
              {activeTab === "models" && <ModelSettings />}
              {activeTab === "connections" && <ConnectionSettings />}
              {activeTab === "execution" && <PreferencesSettings section="execution" />}
              {activeTab === "appearance" && <PreferencesSettings section="appearance" />}
              {activeTab === "advanced" && <PreferencesSettings section="diagnostics" />}
            </>
          )}
        </main>
      </section>
    </div>
  );
}
