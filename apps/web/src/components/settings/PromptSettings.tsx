"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { Prompt, PromptCreate, PromptUpdate, PromptVersion } from "@/lib/types/api";
import { useTranslations } from "next-intl";

interface APIResponse<T> {
  success: boolean;
  data: T;
  message?: string;
}

export function PromptSettings() {
  const queryClient = useQueryClient();
  const [editingPrompt, setEditingPrompt] = useState<Prompt | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [showVersions, setShowVersions] = useState<string | null>(null);
  const t = useTranslations("prompts");
  const tc = useTranslations("common");

  const { data: promptsData, isLoading } = useQuery({
    queryKey: ["prompts"],
    queryFn: async () => {
      const res = await api.get<APIResponse<{ items: Prompt[]; total: number }>>(
        "/api/v1/prompts"
      );
      return res.data.data;
    },
  });

  const { data: versions } = useQuery({
    queryKey: ["prompt-versions", showVersions],
    queryFn: async () => {
      if (!showVersions) return [];
      const res = await api.get<APIResponse<PromptVersion[]>>(
        `/api/v1/prompts/${showVersions}/versions`
      );
      return res.data.data;
    },
    enabled: !!showVersions,
  });

  const createMutation = useMutation({
    mutationFn: async (data: PromptCreate) => {
      const res = await api.post<APIResponse<Prompt>>("/api/v1/prompts", data);
      return res.data.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
      setIsCreating(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: PromptUpdate }) => {
      const res = await api.put<APIResponse<Prompt>>(`/api/v1/prompts/${id}`, data);
      return res.data.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
      setEditingPrompt(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/prompts/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
    },
  });

  const setDefaultMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await api.post<APIResponse<Prompt>>(`/api/v1/prompts/${id}/set-default`);
      return res.data.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
    },
  });

  const unsetDefaultMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await api.post<APIResponse<Prompt>>(`/api/v1/prompts/${id}/unset-default`);
      return res.data.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: async ({ id, version }: { id: string; version: number }) => {
      const res = await api.post<APIResponse<Prompt>>(
        `/api/v1/prompts/${id}/rollback/${version}`
      );
      return res.data.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
      queryClient.invalidateQueries({ queryKey: ["prompt-versions"] });
      setShowVersions(null);
    },
  });

  const prompts = promptsData?.items || [];

  if (isLoading) {
    return <div className="p-4 text-center text-gray-500">{t("loading")}</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">{t("title")}</h2>
          <p className="text-sm text-gray-500">{t("description")}</p>
        </div>
        <button
          onClick={() => setIsCreating(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors text-sm"
        >
          {t("createPrompt")}
        </button>
      </div>

      {isCreating && (
        <PromptForm
          onSubmit={(data) => createMutation.mutate(data)}
          onCancel={() => setIsCreating(false)}
          isLoading={createMutation.isPending}
        />
      )}

      {prompts.length === 0 && !isCreating ? (
        <div className="text-center py-12 text-gray-500">
          <p>{t("emptyState")}</p>
          <p className="text-sm mt-2">{t("emptyStateHint")}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {prompts.map((prompt) => (
            <div
              key={prompt.id}
              className="border rounded-lg p-4 bg-white dark:bg-gray-800"
            >
              {editingPrompt?.id === prompt.id ? (
                <PromptForm
                  initialData={prompt}
                  onSubmit={(data) =>
                    updateMutation.mutate({ id: prompt.id, data: { name: data.name, content: data.content, description: data.description } })
                  }
                  onCancel={() => setEditingPrompt(null)}
                  isLoading={updateMutation.isPending}
                />
              ) : (
                <>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium">{prompt.name}</h3>
                        {prompt.is_default && (
                          <span className="px-2 py-0.5 text-xs bg-green-100 text-green-700 rounded">
                            {t("default")}
                          </span>
                        )}
                        <span className="text-xs text-gray-400">
                          v{prompt.version}
                        </span>
                      </div>
                      {prompt.description && (
                        <p className="text-sm text-gray-500 mt-1">
                          {prompt.description}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {prompt.is_default ? (
                        <button
                          onClick={() => unsetDefaultMutation.mutate(prompt.id)}
                          className="text-sm text-orange-600 hover:text-orange-700"
                          disabled={unsetDefaultMutation.isPending}
                        >
                          {t("unsetDefault")}
                        </button>
                      ) : (
                        <button
                          onClick={() => setDefaultMutation.mutate(prompt.id)}
                          className="text-sm text-blue-600 hover:text-blue-700"
                          disabled={setDefaultMutation.isPending}
                        >
                          {t("setDefault")}
                        </button>
                      )}
                      <button
                        onClick={() => setShowVersions(prompt.id)}
                        className="text-sm text-gray-600 hover:text-gray-700"
                      >
                        {t("versionHistory")}
                      </button>
                      <button
                        onClick={() => setEditingPrompt(prompt)}
                        className="text-sm text-gray-600 hover:text-gray-700"
                      >
                        {tc("edit")}
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(t("confirmDelete"))) {
                            deleteMutation.mutate(prompt.id);
                          }
                        }}
                        className="text-sm text-red-600 hover:text-red-700"
                        disabled={deleteMutation.isPending}
                      >
                        {tc("delete")}
                      </button>
                    </div>
                  </div>
                  <div className="mt-3 p-3 bg-gray-50 dark:bg-gray-900 rounded text-sm font-mono whitespace-pre-wrap max-h-40 overflow-y-auto">
                    {prompt.content.slice(0, 500)}
                    {prompt.content.length > 500 && "..."}
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {showVersions && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md max-h-[80vh] overflow-y-auto">
            <h3 className="text-lg font-semibold mb-4">{t("versionHistory")}</h3>
            <div className="space-y-2">
              {versions?.map((v) => (
                <div
                  key={v.id}
                  className="flex items-center justify-between p-3 border rounded"
                >
                  <div>
                    <span className="font-medium">v{v.version}</span>
                    <span className="text-sm text-gray-500 ml-2">
                      {new Date(v.created_at).toLocaleString()}
                    </span>
                    {v.is_active && (
                      <span className="ml-2 text-xs text-green-600">{t("current")}</span>
                    )}
                  </div>
                  {!v.is_active && (
                    <button
                      onClick={() =>
                        rollbackMutation.mutate({
                          id: showVersions,
                          version: v.version,
                        })
                      }
                      className="text-sm text-blue-600 hover:text-blue-700"
                      disabled={rollbackMutation.isPending}
                    >
                      {t("rollback")}
                    </button>
                  )}
                </div>
              ))}
            </div>
            <button
              onClick={() => setShowVersions(null)}
              className="mt-4 w-full py-2 border rounded hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              {tc("close")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function PromptForm({
  initialData,
  onSubmit,
  onCancel,
  isLoading,
}: {
  initialData?: Prompt;
  onSubmit: (data: PromptCreate) => void;
  onCancel: () => void;
  isLoading: boolean;
}) {
  const [name, setName] = useState(initialData?.name || "");
  const [content, setContent] = useState(initialData?.content || "");
  const [description, setDescription] = useState(initialData?.description || "");
  const [isDefault, setIsDefault] = useState(initialData?.is_default || false);
  const t = useTranslations("prompts");
  const tc = useTranslations("common");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !content.trim()) return;

    onSubmit({ name, content, description, is_default: isDefault });
  };

  return (
    <form onSubmit={handleSubmit} className="border rounded-lg p-4 bg-gray-50 dark:bg-gray-900">
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">{t("nameLabel")}</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("namePlaceholder")}
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-800"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">{t("descriptionLabel")}</label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t("descriptionPlaceholder")}
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-800"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">{t("contentLabel")}</label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={t("contentPlaceholder")}
            rows={12}
            className="w-full px-3 py-2 border rounded-lg font-mono text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-800"
            required
          />
        </div>
        {!initialData && (
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="is_default"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
              className="rounded"
            />
            <label htmlFor="is_default" className="text-sm">
              {t("setDefaultPrompt")}
            </label>
          </div>
        )}
      </div>
      <div className="flex justify-end gap-2 mt-4">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 border rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
          disabled={isLoading}
        >
          {tc("cancel")}
        </button>
        <button
          type="submit"
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors text-sm"
          disabled={isLoading || !name.trim() || !content.trim()}
        >
          {isLoading ? t("saving") : initialData ? tc("save") : t("createAction")}
        </button>
      </div>
    </form>
  );
}
