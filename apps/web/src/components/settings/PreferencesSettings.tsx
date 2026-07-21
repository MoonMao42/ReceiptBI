"use client";

import { useEffect, useState, useTransition } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Save } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api/client";
import type { AppSettings, SystemCapabilities } from "@/lib/types/api";
import { useThemeStore, THEMES, ThemeId } from "@/lib/stores/theme";
import { cn } from "@/lib/utils";
import { useLocale, useTranslations } from "next-intl";
import { setLocale } from "@/lib/actions/locale";

export type PreferencesSection = "appearance" | "execution" | "diagnostics";

interface PreferencesSettingsProps {
  section?: PreferencesSection;
}

const defaultSettings: AppSettings = {
  context_rounds: 5,
  default_model_id: null,
  default_connection_id: null,
  python_enabled: true,
  diagnostics_enabled: true,
  auto_repair_enabled: true,
};

function ToggleRow({
  title,
  description,
  checked,
  onChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-5 border-b border-border bg-card px-4 py-4 first:border-t">
      <div className="max-w-2xl">
        <div className="text-sm font-medium text-foreground">{title}</div>
        <div className="mt-1 text-sm leading-6 text-muted-foreground">{description}</div>
      </div>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 h-4 w-4 rounded border-input text-primary focus:ring-primary"
      />
    </label>
  );
}

export function PreferencesSettings({ section = "appearance" }: PreferencesSettingsProps) {
  const [formData, setFormData] = useState<AppSettings>(defaultSettings);
  const [hasChanges, setHasChanges] = useState(false);
  const queryClient = useQueryClient();
  const { theme: currentTheme, setTheme } = useThemeStore();
  const t = useTranslations("preferences");
  const tTheme = useTranslations("theme");
  const locale = useLocale();
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const isChinese = locale === "zh";
  const needsPersistedSettings = section !== "appearance";

  const sectionCopy = isChinese
    ? {
        execution: {
          title: "执行",
          description: "设置分析过程的自动处理方式。",
          behavior: "执行方式",
          environment: "分析环境",
          libraries: "可用工具",
          unavailable: "尚未安装",
          codeAnalysis: "允许本机计算与绘图",
          codeAnalysisDescription: "需要复杂计算或图表时，允许调查使用隔离的本机分析环境。",
          autoRepair: "自动修复执行问题",
          autoRepairDescription: "查询、计算或绘图失败时，在同一次调查中修正后继续。",
        },
        diagnostics: {
          title: "调查诊断",
          description: "诊断只用于解释失败和核对依据，普通报告仍保持业务语言。",
          keepDiagnostics: "保留技术诊断",
          keepDiagnosticsDescription:
            "保存服务响应、执行尝试和错误分类，供需要时展开查看；不会默认显示在报告里。",
          environmentDetails: "本机环境详情",
          environmentDescription: "仅在排查依赖或执行问题时查看安装档位和可用工具。",
        },
      }
    : {
        execution: {
          title: "Execution",
          description: "Configure automatic analysis behavior.",
          behavior: "Execution behavior",
          environment: "Analysis environment",
          libraries: "Available tools",
          unavailable: "Not installed",
          codeAnalysis: "Allow local computation and charts",
          codeAnalysisDescription:
            "Use the isolated local analysis environment when a task needs complex calculations or charts.",
          autoRepair: "Repair execution problems automatically",
          autoRepairDescription:
            "When a query, calculation, or chart fails, correct it and continue the same investigation.",
        },
        diagnostics: {
          title: "Investigation diagnostics",
          description:
            "Diagnostics explain failures and support evidence review while ordinary reports stay in business language.",
          keepDiagnostics: "Keep technical diagnostics",
          keepDiagnosticsDescription:
            "Save service responses, execution attempts, and error categories for optional review without showing them in reports by default.",
          environmentDetails: "Local environment details",
          environmentDescription:
            "Review the install profile and available tools only when diagnosing execution or dependency problems.",
        },
      };

  const handleLocaleChange = (newLocale: string) => {
    startTransition(() => {
      setLocale(newLocale);
      router.refresh();
    });
  };

  const { data: settings, isLoading } = useQuery({
    queryKey: ["app-settings"],
    queryFn: async () => {
      const response = await api.get("/api/v1/settings");
      return response.data.data as AppSettings;
    },
    enabled: needsPersistedSettings,
  });

  const { data: capabilities } = useQuery({
    queryKey: ["system-capabilities"],
    queryFn: async () => {
      const response = await api.get("/api/v1/system/capabilities");
      return response.data.data as SystemCapabilities;
    },
    enabled: section === "diagnostics",
  });

  const updateMutation = useMutation({
    mutationFn: async (data: AppSettings) => {
      const response = await api.put("/api/v1/settings", data);
      return response.data.data as AppSettings;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["app-settings"] });
      queryClient.invalidateQueries({ queryKey: ["system-capabilities"] });
      setHasChanges(false);
    },
  });

  useEffect(() => {
    if (!settings) return;
    setFormData({ ...defaultSettings, ...settings });
  }, [settings]);

  const handleChange = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
    setFormData((previous) => ({ ...previous, [key]: value }));
    setHasChanges(true);
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    updateMutation.mutate(formData);
  };

  if (needsPersistedSettings && isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin text-muted-foreground" size={24} />
      </div>
    );
  }

  return (
    <div>
      <form onSubmit={handleSubmit} className="space-y-9">
        {section === "appearance" && (
          <>
            <section>
              <label className="mb-3 block text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                {t("language")}
              </label>
              <div className="flex border-l border-t border-border sm:w-fit">
                {[
                  { id: "zh", label: t("languageChinese") },
                  { id: "en", label: t("languageEnglish") },
                ].map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => handleLocaleChange(option.id)}
                    disabled={isPending}
                    className={cn(
                      "flex min-w-28 items-center justify-center gap-2 border-b border-r border-border px-4 py-2.5 text-sm transition-colors",
                      locale === option.id
                        ? "bg-primary/10 font-medium text-primary"
                        : "bg-card text-muted-foreground hover:bg-muted",
                      isPending && "opacity-50"
                    )}
                  >
                    {locale === option.id && <Check size={14} />}
                    {option.label}
                  </button>
                ))}
              </div>
            </section>

            <section>
              <label className="mb-3 block text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                {t("uiTheme")}
              </label>
              <div className="grid border-l border-t border-border sm:grid-cols-2 lg:grid-cols-4">
                {Object.entries(THEMES).map(([id]) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setTheme(id as ThemeId)}
                    className={cn(
                      "relative min-h-24 border-b border-r border-border px-4 py-4 text-left transition-colors",
                      currentTheme === id
                        ? "bg-primary/10 shadow-[inset_3px_0_0_hsl(var(--primary))]"
                        : "bg-card hover:bg-muted"
                    )}
                  >
                    {currentTheme === id && (
                      <Check size={15} className="absolute right-3 top-3 text-primary" />
                    )}
                    <div className="pr-5 text-sm font-medium text-foreground">
                      {tTheme(`${id}.name`)}
                    </div>
                    <div className="mt-1 text-xs leading-5 text-muted-foreground">
                      {tTheme(`${id}.description`)}
                    </div>
                  </button>
                ))}
              </div>
            </section>
          </>
        )}

        {section === "execution" && (
          <>
            <section>
              <div className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                {sectionCopy.execution.behavior}
              </div>
              <ToggleRow
                title={sectionCopy.execution.codeAnalysis}
                description={sectionCopy.execution.codeAnalysisDescription}
                checked={formData.python_enabled}
                onChange={(value) => handleChange("python_enabled", value)}
              />
              <ToggleRow
                title={sectionCopy.execution.autoRepair}
                description={sectionCopy.execution.autoRepairDescription}
                checked={formData.auto_repair_enabled}
                onChange={(value) => handleChange("auto_repair_enabled", value)}
              />
            </section>
          </>
        )}

        {section === "diagnostics" && (
          <>
            <section>
              <ToggleRow
                title={sectionCopy.diagnostics.keepDiagnostics}
                description={sectionCopy.diagnostics.keepDiagnosticsDescription}
                checked={formData.diagnostics_enabled}
                onChange={(value) => handleChange("diagnostics_enabled", value)}
              />
            </section>
            <details className="group border-t border-border pt-5">
              <summary className="cursor-pointer list-none text-sm font-medium text-foreground marker:content-none">
                {sectionCopy.diagnostics.environmentDetails}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  {sectionCopy.diagnostics.environmentDescription}
                </span>
              </summary>
              <div className="mt-4 grid border-l border-t border-border md:grid-cols-2">
                <div className="border-b border-r border-border bg-card px-4 py-4">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.11em] text-muted-foreground">
                    {sectionCopy.execution.environment}
                  </div>
                  <div className="mt-2 text-sm font-medium text-foreground">
                    {capabilities?.install_profile || "core"}
                  </div>
                </div>
                <div className="border-b border-r border-border bg-card px-4 py-4">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.11em] text-muted-foreground">
                    {sectionCopy.execution.libraries}
                  </div>
                  <div className="mt-2 text-sm leading-6 text-foreground">
                    {capabilities?.available_python_libraries?.join(", ") || "—"}
                  </div>
                  {capabilities?.missing_optional_libraries?.length ? (
                    <div className="mt-2 text-xs text-warning">
                      {sectionCopy.execution.unavailable}: {capabilities.missing_optional_libraries.join(", ")}
                    </div>
                  ) : null}
                </div>
              </div>
            </details>
          </>
        )}

        {needsPersistedSettings && (
          <div className="border-t border-border pt-5">
            <button
              type="submit"
              disabled={!hasChanges || updateMutation.isPending}
              className="flex items-center gap-2 bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {updateMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Save size={16} />
              )}
              {t("saveSettings")}
            </button>
            {updateMutation.isSuccess && (
              <p className="mt-2 text-sm text-success">{t("saved")}</p>
            )}
            {updateMutation.isError && (
              <p className="mt-2 text-sm text-destructive">{t("saveFailed")}</p>
            )}
          </div>
        )}
      </form>
    </div>
  );
}
