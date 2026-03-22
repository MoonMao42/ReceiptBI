"use client";

import type { FormEvent } from "react";
import { Loader2, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  MODEL_PRESETS,
  type ModelFormData,
  type ModelPreset,
} from "@/lib/settings/models";
import { useTranslations } from "next-intl";

interface ModelSettingsFormProps {
  editingId: string | null;
  formData: ModelFormData;
  activePreset: ModelPreset;
  isSubmitting: boolean;
  onChange: (next: ModelFormData) => void;
  onPresetSelect: (presetKey: string) => void;
  onReset: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

export function ModelSettingsForm({
  editingId,
  formData,
  activePreset,
  isSubmitting,
  onChange,
  onPresetSelect,
  onReset,
  onSubmit,
}: ModelSettingsFormProps) {
  const t = useTranslations("modelSettings");
  const tc = useTranslations("common");

  return (
    <form
      onSubmit={onSubmit}
      data-testid="model-form"
      className="rounded-2xl border border-border bg-secondary p-5 space-y-5"
    >
      <div className="grid gap-3 md:grid-cols-3">
        {Object.entries(MODEL_PRESETS).map(([key, preset]) => (
          <button
            key={key}
            type="button"
            onClick={() => onPresetSelect(key)}
            data-testid={`model-preset-${key}`}
            className={cn(
              "rounded-xl border p-4 text-left transition-colors",
              formData.provider === preset.provider
                ? "border-primary bg-primary/5"
                : "border-border bg-background hover:border-primary/40"
            )}
          >
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Sparkles size={14} className="text-primary" />
              {key === "openai" && t("presetOpenai")}
              {key === "deepseek" && t("presetDeepseek")}
              {key === "anthropic" && t("presetAnthropic")}
              {key === "ollama" && t("presetOllama")}
              {key === "custom" && t("presetCustom")}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {preset.api_format === "anthropic_native" && t("descAnthropic")}
              {preset.api_format === "ollama_local" && t("descOllama")}
              {preset.api_format === "openai_compatible" && t("descOpenai")}
            </p>
          </button>
        ))}
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-foreground">{editingId ? t("editModel") : t("addModel")}</h3>
          <p className="text-sm text-muted-foreground mt-1">
            {t("currentFormat")}{activePreset.api_format}
          </p>
        </div>
        <button type="button" onClick={onReset} className="text-muted-foreground hover:text-foreground">
          <X size={18} />
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">{t("name")}</label>
          <input
            type="text"
            value={formData.name}
            onChange={(event) => onChange({ ...formData, name: event.target.value })}
            data-testid="model-name-input"
            className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground"
            placeholder={t("namePlaceholder")}
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">{t("providerTag")}</label>
          <select
            value={formData.provider}
            onChange={(event) => onPresetSelect(event.target.value)}
            data-testid="model-provider-select"
            className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground"
          >
            {Object.keys(MODEL_PRESETS).map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">{t("modelId")}</label>
          <input
            type="text"
            value={formData.model_id}
            onChange={(event) => onChange({ ...formData, model_id: event.target.value })}
            data-testid="model-id-input"
            className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground"
            placeholder={t("modelIdPlaceholder")}
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">{t("adaptFormat")}</label>
          <select
            value={formData.api_format}
            onChange={(event) =>
              onChange({
                ...formData,
                api_format: event.target.value as ModelFormData["api_format"],
              })
            }
            data-testid="model-api-format-select"
            className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground"
          >
            <option value="openai_compatible">openai_compatible</option>
            <option value="anthropic_native">anthropic_native</option>
            <option value="ollama_local">ollama_local</option>
            <option value="custom">custom</option>
          </select>
        </div>
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-foreground mb-1">Base URL</label>
          <input
            type="url"
            value={formData.base_url}
            onChange={(event) => onChange({ ...formData, base_url: event.target.value })}
            data-testid="model-base-url-input"
            className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground"
            placeholder="https://api.openai.com/v1"
          />
        </div>
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-foreground mb-1">
            API Key {editingId && <span className="text-muted-foreground font-normal">{t("apiKeyEditHint")}</span>}
          </label>
          <input
            type="password"
            value={formData.api_key}
            onChange={(event) => onChange({ ...formData, api_key: event.target.value })}
            data-testid="model-api-key-input"
            className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground"
            placeholder={formData.api_key_optional ? t("apiKeyLocalHint") : "sk-..."}
          />
        </div>
        <div>
          <label className="flex items-center gap-2 cursor-pointer text-sm text-foreground">
            <input
              type="checkbox"
              checked={formData.api_key_optional}
              onChange={(event) =>
                onChange({ ...formData, api_key_optional: event.target.checked })
              }
              data-testid="model-api-key-optional-checkbox"
              className="w-4 h-4 text-primary rounded"
            />
            {t("allowNoApiKey")}
          </label>
        </div>
        <div>
          <label className="flex items-center gap-2 cursor-pointer text-sm text-foreground">
            <input
              type="checkbox"
              checked={formData.is_default}
              onChange={(event) => onChange({ ...formData, is_default: event.target.checked })}
              data-testid="model-default-checkbox"
              className="w-4 h-4 text-primary rounded"
            />
            {t("setDefault")}
          </label>
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">{t("healthcheckMode")}</label>
          <select
            value={formData.healthcheck_mode}
            onChange={(event) =>
              onChange({
                ...formData,
                healthcheck_mode: event.target.value as ModelFormData["healthcheck_mode"],
              })
            }
            data-testid="model-healthcheck-mode-select"
            className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground"
          >
            <option value="chat_completion">chat_completion</option>
            <option value="models_list">models_list</option>
          </select>
        </div>
        <div className="grid gap-4 md:col-span-2 md:grid-cols-2">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">{t("extraHeaders")}</label>
            <textarea
              value={formData.headersText}
              onChange={(event) => onChange({ ...formData, headersText: event.target.value })}
              data-testid="model-headers-textarea"
              className="h-32 w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground font-mono text-xs"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">{t("extraQueryParams")}</label>
            <textarea
              value={formData.queryParamsText}
              onChange={(event) =>
                onChange({ ...formData, queryParamsText: event.target.value })
              }
              data-testid="model-query-params-textarea"
              className="h-32 w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground font-mono text-xs"
            />
          </div>
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onReset}
          className="px-4 py-2 text-muted-foreground hover:bg-muted rounded-lg transition-colors text-sm"
        >
          {tc("cancel")}
        </button>
        <button
          type="submit"
          disabled={isSubmitting}
          data-testid="model-submit-button"
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors text-sm"
        >
          {isSubmitting && <Loader2 size={16} className="animate-spin" />}
          {editingId ? tc("update") : tc("save")}
        </button>
      </div>
    </form>
  );
}
