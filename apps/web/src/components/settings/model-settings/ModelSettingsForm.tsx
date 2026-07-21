"use client";

import type { FormEvent } from "react";
import { ChevronDown, Loader2, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  MODEL_PRESETS,
  type ModelFormData,
  type ModelPreset,
} from "@/lib/settings/models";
import { useLocale, useTranslations } from "next-intl";

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

const fieldClassName =
  "w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/15";

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
  const isChinese = useLocale() === "zh";
  const copy = isChinese
    ? {
        chooseService: "选择服务",
        chooseServiceHint: "先选常用服务；地址或协议不同的服务可选“其他兼容服务”。",
        serviceName: "显示名称",
        serviceNameHint: "例如：日常分析服务",
        model: "使用的模型",
        serviceAddress: "服务地址",
        serviceAddressHint: "官方服务可留空；兼容服务填写完整接口地址。",
        accessKey: "访问密钥",
        defaultService: "作为默认分析服务",
        compatibility: "高级连接选项",
        compatibilityHint: "仅在服务商要求特殊协议、请求头或连接测试方式时调整。",
        serviceType: "服务类型",
        protocol: "接口协议",
        healthcheck: "连接测试方式",
        noKey: "这个服务不需要访问密钥",
        headers: "附加请求头（JSON）",
        params: "附加请求参数（JSON）",
        close: "关闭表单",
      }
    : {
        chooseService: "Choose a service",
        chooseServiceHint:
          "Start with a common service. Choose Custom gateway when its address or protocol differs.",
        serviceName: "Display name",
        serviceNameHint: "e.g. Everyday analysis service",
        model: "Model to use",
        serviceAddress: "Service address",
        serviceAddressHint:
          "Leave blank for an official endpoint; enter the full endpoint for a compatible service.",
        accessKey: "Access key",
        defaultService: "Use as the default analysis service",
        compatibility: "Advanced connection options",
        compatibilityHint:
          "Adjust these only when the service needs a special protocol, request headers, or connection check.",
        serviceType: "Service type",
        protocol: "Interface protocol",
        healthcheck: "Connection check",
        noKey: "This service does not require an access key",
        headers: "Additional request headers (JSON)",
        params: "Additional query parameters (JSON)",
        close: "Close form",
      };

  return (
    <form
      onSubmit={onSubmit}
      data-testid="model-form"
      className="border-y border-border bg-card px-4 py-5 sm:px-5"
    >
      <div className="flex items-start justify-between gap-5">
        <div>
          <h3 className="text-base font-semibold text-foreground">
            {editingId ? t("editModel") : t("addModel")}
          </h3>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">{copy.chooseServiceHint}</p>
        </div>
        <button
          type="button"
          onClick={onReset}
          aria-label={copy.close}
          className="p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X size={18} />
        </button>
      </div>

      <fieldset className="mt-5">
        <legend className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          {copy.chooseService}
        </legend>
        <div className="grid border-l border-t border-border sm:grid-cols-2 lg:grid-cols-5">
          {Object.entries(MODEL_PRESETS).map(([key, preset]) => (
            <button
              key={key}
              type="button"
              onClick={() => onPresetSelect(key)}
              data-testid={`model-preset-${key}`}
              className={cn(
                "min-h-20 border-b border-r border-border px-3 py-3 text-left transition-colors",
                formData.provider === preset.provider
                  ? "bg-primary/10 shadow-[inset_3px_0_0_hsl(var(--primary))]"
                  : "bg-background hover:bg-muted"
              )}
            >
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Sparkles size={13} className="text-primary" />
                {key === "openai" && t("presetOpenai")}
                {key === "deepseek" && t("presetDeepseek")}
                {key === "anthropic" && t("presetAnthropic")}
                {key === "ollama" && t("presetOllama")}
                {key === "custom" && t("presetCustom")}
              </div>
              <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
                {preset.api_format === "anthropic_native" && t("descAnthropic")}
                {preset.api_format === "ollama_local" && t("descOllama")}
                {preset.api_format === "openai_compatible" && t("descOpenai")}
              </p>
            </button>
          ))}
        </div>
      </fieldset>

      <div className="mt-6 grid gap-5 md:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-foreground">
            {copy.serviceName}
          </label>
          <input
            type="text"
            value={formData.name}
            onChange={(event) => onChange({ ...formData, name: event.target.value })}
            data-testid="model-name-input"
            className={fieldClassName}
            placeholder={copy.serviceNameHint}
            required
          />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-foreground">
            {copy.model}
          </label>
          <input
            type="text"
            value={formData.model_id}
            onChange={(event) => onChange({ ...formData, model_id: event.target.value })}
            data-testid="model-id-input"
            className={fieldClassName}
            placeholder={t("modelIdPlaceholder")}
            required
          />
        </div>
        <div className="md:col-span-2">
          <label className="mb-1.5 block text-sm font-medium text-foreground">
            {copy.serviceAddress}
          </label>
          <input
            type="url"
            value={formData.base_url}
            onChange={(event) => onChange({ ...formData, base_url: event.target.value })}
            data-testid="model-base-url-input"
            className={fieldClassName}
            placeholder="https://api.example.com/v1"
          />
          <p className="mt-1.5 text-xs text-muted-foreground">{copy.serviceAddressHint}</p>
        </div>
        <div className="md:col-span-2">
          <label className="mb-1.5 block text-sm font-medium text-foreground">
            {copy.accessKey}{" "}
            {editingId && (
              <span className="font-normal text-muted-foreground">{t("apiKeyEditHint")}</span>
            )}
          </label>
          <input
            type="password"
            value={formData.api_key}
            onChange={(event) => onChange({ ...formData, api_key: event.target.value })}
            data-testid="model-api-key-input"
            className={fieldClassName}
            placeholder={formData.api_key_optional ? t("apiKeyLocalHint") : "sk-..."}
          />
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground md:col-span-2">
          <input
            type="checkbox"
            checked={formData.is_default}
            onChange={(event) => onChange({ ...formData, is_default: event.target.checked })}
            data-testid="model-default-checkbox"
            className="h-4 w-4 rounded text-primary"
          />
          {copy.defaultService}
        </label>
      </div>

      <details
        data-testid="model-compatibility-settings"
        className="group mt-6 border-t border-border pt-1"
      >
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-3 text-sm text-muted-foreground marker:content-none">
          <span>
            <span className="font-medium text-foreground">{copy.compatibility}</span>
            <span className="ml-2 hidden text-xs text-muted-foreground sm:inline">
              {copy.compatibilityHint}
            </span>
          </span>
          <ChevronDown size={16} className="transition-transform group-open:rotate-180" />
        </summary>

        <div className="grid gap-5 border-t border-border bg-muted/40 px-4 py-5 md:grid-cols-2">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              {copy.serviceType}
            </label>
            <select
              value={formData.provider}
              onChange={(event) => onPresetSelect(event.target.value)}
              data-testid="model-provider-select"
              className={fieldClassName}
            >
              {Object.keys(MODEL_PRESETS).map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              {copy.protocol}
            </label>
            <select
              value={formData.api_format}
              onChange={(event) =>
                onChange({
                  ...formData,
                  api_format: event.target.value as ModelFormData["api_format"],
                })
              }
              data-testid="model-api-format-select"
              className={fieldClassName}
            >
              <option value="openai_compatible">openai_compatible</option>
              <option value="anthropic_native">anthropic_native</option>
              <option value="ollama_local">ollama_local</option>
              <option value="custom">custom</option>
            </select>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("currentFormat")}: {activePreset.api_format}
            </p>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              {copy.healthcheck}
            </label>
            <select
              value={formData.healthcheck_mode}
              onChange={(event) =>
                onChange({
                  ...formData,
                  healthcheck_mode: event.target.value as ModelFormData["healthcheck_mode"],
                })
              }
              data-testid="model-healthcheck-mode-select"
              className={fieldClassName}
            >
              <option value="chat_completion">chat_completion</option>
              <option value="models_list">models_list</option>
            </select>
          </div>
          <label className="flex cursor-pointer items-center gap-2 self-end pb-2 text-sm text-foreground">
            <input
              type="checkbox"
              checked={formData.api_key_optional}
              onChange={(event) =>
                onChange({ ...formData, api_key_optional: event.target.checked })
              }
              data-testid="model-api-key-optional-checkbox"
              className="h-4 w-4 rounded text-primary"
            />
            {copy.noKey}
          </label>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              {copy.headers}
            </label>
            <textarea
              value={formData.headersText}
              onChange={(event) => onChange({ ...formData, headersText: event.target.value })}
              data-testid="model-headers-textarea"
              className={`${fieldClassName} h-32 font-mono text-xs`}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              {copy.params}
            </label>
            <textarea
              value={formData.queryParamsText}
              onChange={(event) =>
                onChange({ ...formData, queryParamsText: event.target.value })
              }
              data-testid="model-query-params-textarea"
              className={`${fieldClassName} h-32 font-mono text-xs`}
            />
          </div>
        </div>
      </details>

      <div className="mt-6 flex justify-end gap-2 border-t border-border pt-5">
        <button
          type="button"
          onClick={onReset}
          className="px-4 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          {tc("cancel")}
        </button>
        <button
          type="submit"
          disabled={isSubmitting}
          data-testid="model-submit-button"
          className="flex items-center gap-2 bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          {isSubmitting && <Loader2 size={16} className="animate-spin" />}
          {editingId ? tc("update") : tc("save")}
        </button>
      </div>
    </form>
  );
}
