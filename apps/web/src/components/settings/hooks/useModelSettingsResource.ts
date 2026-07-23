"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import {
  buildModelPayload,
  type ModelFormData,
  type ModelTestResult,
} from "@/lib/settings/models";
import type { ConfiguredModel } from "@/lib/types/api";

export interface ModelSettingsResourceMessages {
  connectionCheckFailed: string;
  savedButConnectionCheckFailed: string;
  addModelFailed: string;
  updateModelFailed: string;
  deleteModelFailed: string;
}

export function useModelSettingsResource(messages: ModelSettingsResourceMessages) {
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ModelTestResult | null>(null);
  const queryClient = useQueryClient();

  const { data: models, isLoading } = useQuery({
    queryKey: ["models"],
    queryFn: async () => {
      const response = await api.get("/api/v1/config/models");
      return response.data.data as ConfiguredModel[];
    },
  });

  const testMutation = useMutation({
    mutationFn: async ({ id }: { id: string; afterSave?: boolean }) => {
      const response = await api.post(`/api/v1/config/models/${id}/test`);
      return { id, ...response.data.data } as ModelTestResult;
    },
    onMutate: () => {
      setError(null);
      setTestResult(null);
    },
    onSuccess: (result) => {
      setError(null);
      setTestResult(result);
    },
    onError: (error, variables) => {
      void error;
      setError(
        variables.afterSave
          ? messages.savedButConnectionCheckFailed
          : messages.connectionCheckFailed
      );
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });

  const addMutation = useMutation({
    mutationFn: async (data: ModelFormData) => {
      const response = await api.post("/api/v1/config/models", buildModelPayload(data));
      return response.data.data as ConfiguredModel;
    },
    onSuccess: (model) => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["models"] });
      testMutation.mutate({ id: model.id, afterSave: true });
    },
    onError: () => {
      setError(messages.addModelFailed);
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: ModelFormData }) => {
      const response = await api.put(`/api/v1/config/models/${id}`, buildModelPayload(data));
      return response.data.data as ConfiguredModel;
    },
    onSuccess: (model) => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["models"] });
      testMutation.mutate({ id: model.id, afterSave: true });
    },
    onError: () => {
      setError(messages.updateModelFailed);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/config/models/${id}`);
    },
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
    onError: () => {
      setError(messages.deleteModelFailed);
    },
  });

  return {
    models: models || [],
    isLoading,
    error,
    testResult,
    isSubmitting: addMutation.isPending || updateMutation.isPending,
    testingModelId: testMutation.isPending ? testMutation.variables?.id : null,
    deletePending: deleteMutation.isPending,
    clearError: () => setError(null),
    clearTestResult: () => setTestResult(null),
    addModel: (data: ModelFormData) => addMutation.mutateAsync(data),
    updateModel: (id: string, data: ModelFormData) => updateMutation.mutateAsync({ id, data }),
    deleteModel: (id: string) => deleteMutation.mutate(id),
    testModel: (id: string) => testMutation.mutate({ id }),
  };
}
