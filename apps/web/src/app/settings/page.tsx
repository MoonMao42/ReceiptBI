"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  BookOpen,
  Brain,
  Database,
  GitBranch,
  Info,
  MessageSquare,
  Settings as SettingsIcon,
  SlidersHorizontal,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { ModelSettings } from "@/components/settings/ModelSettings";
import { ConnectionSettings } from "@/components/settings/ConnectionSettings";
import { PreferencesSettings } from "@/components/settings/PreferencesSettings";
import { SemanticSettings } from "@/components/settings/SemanticSettings";
import { SchemaSettings } from "@/components/settings/SchemaSettings";
import { PromptSettings } from "@/components/settings/PromptSettings";
import { cn } from "@/lib/utils";
import { useTranslations } from "next-intl";

interface Connection {
  id: string;
  name: string;
  is_default: boolean;
}

type TabType = "models" | "connections" | "schema" | "semantic" | "prompts" | "preferences";

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabType>("models");
  const [selectedConnectionId, setSelectedConnectionId] = useState<string | null>(null);
  const router = useRouter();
  const t = useTranslations("settings");

  const { data: connections } = useQuery({
    queryKey: ["connections"],
    queryFn: async () => {
      const response = await api.get("/api/v1/config/connections");
      return response.data.data as Connection[];
    },
  });

  useEffect(() => {
    if (connections && connections.length > 0 && !selectedConnectionId) {
      const defaultConn = connections.find((c) => c.is_default);
      setSelectedConnectionId(defaultConn?.id || connections[0].id);
    }
  }, [connections, selectedConnectionId]);

  const tabs = [
    { id: "models" as TabType, label: t("models"), icon: Brain },
    { id: "connections" as TabType, label: t("connections"), icon: Database },
    { id: "schema" as TabType, label: t("schema"), icon: GitBranch },
    { id: "semantic" as TabType, label: t("semantic"), icon: BookOpen },
    { id: "prompts" as TabType, label: t("prompts"), icon: MessageSquare },
    { id: "preferences" as TabType, label: t("preferences"), icon: SlidersHorizontal },
  ];

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 border-b border-border bg-background">
        <div className="mx-auto flex h-16 max-w-5xl items-center gap-4 px-4">
          <button
            onClick={() => router.push("/")}
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted"
          >
            <ArrowLeft size={20} />
          </button>
          <div className="flex items-center gap-2">
            <SettingsIcon size={20} className="text-muted-foreground" />
            <h1 className="text-lg font-semibold text-foreground">{t("title")}</h1>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-6">
        <div className="flex gap-6">
          <nav className="w-52 flex-shrink-0">
            <ul className="space-y-1">
              {tabs.map((tab) => (
                <li key={tab.id}>
                  <button
                    onClick={() => setActiveTab(tab.id)}
                    data-testid={`settings-tab-${tab.id}`}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                      activeTab === tab.id
                        ? "bg-primary/10 font-medium text-primary"
                        : "text-muted-foreground hover:bg-muted"
                    )}
                  >
                    <tab.icon size={18} />
                    {tab.label}
                  </button>
                </li>
              ))}
            </ul>

            <div className="mt-6 border-t border-border pt-6">
              <button
                onClick={() => router.push("/about")}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted"
              >
                <Info size={18} />
                {t("about")}
              </button>
            </div>
          </nav>

          <main className="flex-1 rounded-xl border border-border bg-background p-6">
            {activeTab === "models" && <ModelSettings />}
            {activeTab === "connections" && <ConnectionSettings onSelectConnection={setSelectedConnectionId} />}
            {activeTab === "schema" && <SchemaSettings connectionId={selectedConnectionId} />}
            {activeTab === "semantic" && <SemanticSettings />}
            {activeTab === "prompts" && <PromptSettings />}
            {activeTab === "preferences" && <PreferencesSettings />}
          </main>
        </div>
      </div>
    </div>
  );
}
