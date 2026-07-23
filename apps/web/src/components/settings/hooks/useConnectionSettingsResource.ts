"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { type ConnectionFormData } from "@/lib/settings/connections";
import type { ConfiguredConnection } from "@/lib/types/api";

export interface ConnectionSettingsResourceMessages {
  success: string;
  failure: string;
  requestFailure: string;
}

export interface LocalizedConnectionTestResult {
  id: string;
  success: boolean;
  text: string;
}

export function useConnectionSettingsResource(
  messages: ConnectionSettingsResourceMessages
) {
  const [testResult, setTestResult] =
    useState<LocalizedConnectionTestResult | null>(null);
  const testResultTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queryClient = useQueryClient();

  useEffect(
    () => () => {
      if (testResultTimerRef.current) {
        clearTimeout(testResultTimerRef.current);
      }
    },
    []
  );

  const showTestResult = (result: LocalizedConnectionTestResult) => {
    if (testResultTimerRef.current) {
      clearTimeout(testResultTimerRef.current);
    }
    setTestResult(result);
    testResultTimerRef.current = setTimeout(() => {
      setTestResult((current) => (current?.id === result.id ? null : current));
      testResultTimerRef.current = null;
    }, 5000);
  };

  const { data: connections, isLoading } = useQuery({
    queryKey: ["connections"],
    queryFn: async () => {
      const response = await api.get("/api/v1/config/connections");
      return response.data.data as ConfiguredConnection[];
    },
  });

  const addMutation = useMutation({
    mutationFn: async (data: ConnectionFormData) => {
      const response = await api.post("/api/v1/config/connections", data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: ConnectionFormData }) => {
      const response = await api.put(`/api/v1/config/connections/${id}`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/config/connections/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
  });

  const testMutation = useMutation({
    mutationFn: async (id: string) => {
      const response = await api.post(`/api/v1/config/connections/${id}/test`);
      const success = Boolean(response.data.data.connected);
      return {
        id,
        success,
        text: success ? messages.success : messages.failure,
      } satisfies LocalizedConnectionTestResult;
    },
    onMutate: () => {
      setTestResult(null);
    },
    onSuccess: (result) => showTestResult(result),
    onError: (_error, id) => {
      showTestResult({
        id,
        success: false,
        text: messages.requestFailure,
      });
    },
  });

  return {
    connections: connections || [],
    isLoading,
    testResult,
    deletePending: deleteMutation.isPending,
    testingConnectionId: testMutation.isPending ? testMutation.variables : null,
    addConnection: (data: ConnectionFormData) => addMutation.mutateAsync(data),
    updateConnection: (id: string, data: ConnectionFormData) =>
      updateMutation.mutateAsync({ id, data }),
    deleteConnection: (id: string) => deleteMutation.mutate(id),
    testConnection: (id: string) => testMutation.mutate(id),
    isSubmitting: addMutation.isPending || updateMutation.isPending,
  };
}
