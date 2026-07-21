"use client";

import { useMemo, useState } from "react";
import { CheckCircle, ChevronDown, Plus, X, XCircle } from "lucide-react";
import { ModelSettingsForm } from "@/components/settings/model-settings/ModelSettingsForm";
import { ModelSettingsList } from "@/components/settings/model-settings/ModelSettingsList";
import { useModelSettingsResource } from "@/components/settings/hooks/useModelSettingsResource";
import {
  MODEL_PRESETS,
  buildModelFormData,
  buildModelPayload,
  initialModelFormData,
  type ModelFormData,
} from "@/lib/settings/models";
import type { ConfiguredModel } from "@/lib/types/api";
import { useLocale, useTranslations } from "next-intl";

export function ModelSettings() {
  const {
    models,
    isLoading,
    error,
    testResult,
    isSubmitting,
    testingModelId,
    deletePending,
    clearError,
    addModel,
    updateModel,
    deleteModel,
    testModel,
  } = useModelSettingsResource();
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState<ModelFormData>(initialModelFormData);
  const [validationError, setValidationError] = useState<string | null>(null);
  const activePreset = useMemo(
    () => MODEL_PRESETS[formData.provider] || MODEL_PRESETS.custom,
    [formData.provider]
  );
  const displayError = validationError ?? error;
  const t = useTranslations("modelSettings");
  const isChinese = useLocale() === "zh";
  const copy = isChinese
    ? {
        title: "分析服务",
        description: "添加一个可用的模型服务，ReceiptBI 会在调查中自动使用默认项。",
        add: "添加服务",
        lastCheck: "最近一次连接检查",
        advancedResult: "高级连接详情",
        advancedResultHint: "排查兼容服务或网关问题时再查看。",
      }
    : {
        title: "Analysis services",
        description:
          "Add a model service. ReceiptBI automatically uses the default one during investigations.",
        add: "Add service",
        lastCheck: "Latest connection check",
        advancedResult: "Advanced connection details",
        advancedResultHint: "Review only when troubleshooting a compatible service or gateway.",
      };

  const resetForm = () => {
    setShowForm(false);
    setEditingId(null);
    setFormData(initialModelFormData);
    setValidationError(null);
    clearError();
  };

  const applyPreset = (presetKey: string) => {
    const preset = MODEL_PRESETS[presetKey] || MODEL_PRESETS.custom;
    setShowForm(true);
    setValidationError(null);
    setFormData((current) => ({
      ...current,
      provider: preset.provider,
      api_format: preset.api_format,
      base_url: preset.base_url,
      api_key_optional: preset.api_key_optional,
      healthcheck_mode: preset.healthcheck_mode,
    }));
  };

  const handleEdit = (model: ConfiguredModel) => {
    setEditingId(model.id);
    setFormData(buildModelFormData(model));
    setShowForm(true);
    setValidationError(null);
    clearError();
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    try {
      buildModelPayload(formData);
    } catch (error) {
      setValidationError(error instanceof Error ? error.message : t("validationError"));
      return;
    }

    setValidationError(null);
    try {
      if (editingId) {
        await updateModel(editingId, formData);
        resetForm();
        return;
      }
      await addModel(formData);
      resetForm();
    } catch {
      // Error state is already handled by the resource hook.
    }
  };

  const handleDelete = (id: string) => {
    deleteModel(id);
  };

  return (
    <div className="space-y-7">
      <div className="flex items-center justify-end">
        <button
          onClick={() => {
            if (showForm) {
              resetForm();
              return;
            }
            setShowForm(true);
          }}
          data-testid="model-add-button"
          className="flex items-center gap-2 bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <Plus size={16} />
          {copy.add}
        </button>
      </div>

      {displayError && (
        <div className="flex items-center justify-between border-l-2 border-destructive bg-destructive/10 px-4 py-3">
          <span className="text-sm text-destructive">{displayError}</span>
          <button
            onClick={() => {
              setValidationError(null);
              clearError();
            }}
            className="text-destructive/60 hover:text-destructive"
          >
            <X size={16} />
          </button>
        </div>
      )}

      {showForm && (
        <ModelSettingsForm
          editingId={editingId}
          formData={formData}
          activePreset={activePreset}
          isSubmitting={isSubmitting}
          onChange={setFormData}
          onPresetSelect={applyPreset}
          onReset={resetForm}
          onSubmit={handleSubmit}
        />
      )}

      {testResult && (
        <div data-testid="model-test-summary" className="border-y border-border bg-card px-4 py-4">
          <div className="flex items-center gap-2 text-sm font-medium text-foreground">
            {testResult.success ? (
              <CheckCircle size={16} className="text-primary" />
            ) : (
              <XCircle size={16} className="text-destructive" />
            )}
            {copy.lastCheck}
          </div>
          <div className="mt-3 grid gap-2 text-sm text-muted-foreground md:grid-cols-2">
            <div>
              {t("result") + ":"} <span className="text-foreground">{testResult.message}</span>
            </div>
            <div>
              {t("latency") + ":"} <span className="text-foreground">{testResult.response_time_ms || "-"} ms</span>
            </div>
          </div>
          <details
            data-testid="model-test-advanced"
            className="group mt-4 border-t border-border pt-3"
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-xs text-muted-foreground marker:content-none">
              <span>
                <span className="font-semibold text-foreground">{copy.advancedResult}</span>
                <span className="ml-2 hidden text-muted-foreground sm:inline">
                  {copy.advancedResultHint}
                </span>
              </span>
              <ChevronDown size={14} className="transition-transform group-open:rotate-180" />
            </summary>
            <div className="mt-3 grid gap-2 border-l-2 border-border bg-muted/40 px-3 py-3 text-xs text-muted-foreground md:grid-cols-2">
              <div>
                {t("resolvedProvider") + ":"}{" "}
                <span className="text-foreground">{testResult.resolved_provider || "-"}</span>
              </div>
              <div>
                {t("apiFormat") + ":"}{" "}
                <span className="text-foreground">{testResult.api_format || "-"}</span>
              </div>
              <div className="md:col-span-2">
                {t("baseUrl") + ":"}{" "}
                <span className="text-foreground">{testResult.resolved_base_url || "-"}</span>
              </div>
              {!testResult.success && (
                <div className="md:col-span-2">
                  {t("errorCategoryLabel") + ":"}{" "}
                  <span className="text-foreground">{testResult.error_category || "unknown"}</span>
                </div>
              )}
            </div>
          </details>
        </div>
      )}

      <ModelSettingsList
        models={models}
        isLoading={isLoading}
        testResult={testResult}
        testingModelId={testingModelId ?? undefined}
        deletePending={deletePending}
        onTest={testModel}
        onEdit={handleEdit}
        onDelete={handleDelete}
      />
    </div>
  );
}
