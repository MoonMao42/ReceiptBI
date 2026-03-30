import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AppSettings, ConnectionSummary, ModelSummary } from "@/lib/types/api";

const STORAGE_KEY_CONNECTION = "querygpt-selected-connection";
const STORAGE_KEY_MODEL = "querygpt-selected-model";

export function useChatAreaState(
  connections: ConnectionSummary[] | undefined,
  models: ModelSummary[] | undefined,
  appSettings: AppSettings | undefined,
  isLoading: boolean
) {
  const queryClient = useQueryClient();
  const [selectedConnectionId, setSelectedConnectionId] = useState<string | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const [showConnectionDropdown, setShowConnectionDropdown] = useState(false);
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const [input, setInput] = useState("");
  const prevIsLoadingRef = useRef(false);

  // Initialize from localStorage
  useEffect(() => {
    const savedConnection = localStorage.getItem(STORAGE_KEY_CONNECTION);
    const savedModel = localStorage.getItem(STORAGE_KEY_MODEL);
    if (savedConnection) setSelectedConnectionId(savedConnection);
    if (savedModel) setSelectedModelId(savedModel);
    setIsInitialized(true);
  }, []);

  // Refresh conversations when loading completes
  useEffect(() => {
    if (prevIsLoadingRef.current && !isLoading) {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    }
    prevIsLoadingRef.current = isLoading;
  }, [isLoading, queryClient]);

  // Auto-select connection if needed
  useEffect(() => {
    if (!isInitialized || !connections?.length) return;
    const savedExists = selectedConnectionId && connections.some((item) => item.id === selectedConnectionId);
    if (!savedExists) {
      const preferredId = appSettings?.default_connection_id;
      const nextId =
        connections.find((item) => item.id === preferredId)?.id ||
        connections.find((item) => item.is_default)?.id ||
        connections[0].id;
      handleSelectConnection(nextId);
    }
  }, [appSettings?.default_connection_id, connections, isInitialized, selectedConnectionId]);

  // Auto-select model if needed
  useEffect(() => {
    if (!isInitialized || !models?.length) return;
    const savedExists = selectedModelId && models.some((item) => item.id === selectedModelId);
    if (!savedExists) {
      const preferredId = appSettings?.default_model_id;
      const nextId =
        models.find((item) => item.id === preferredId)?.id ||
        models.find((item) => item.is_default)?.id ||
        models[0].id;
      handleSelectModel(nextId);
    }
  }, [appSettings?.default_model_id, isInitialized, models, selectedModelId]);

  // Close dropdowns on click outside
  useEffect(() => {
    const handleClickOutside = () => {
      setShowConnectionDropdown(false);
      setShowModelDropdown(false);
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelectConnection = (id: string) => {
    setSelectedConnectionId(id);
    localStorage.setItem(STORAGE_KEY_CONNECTION, id);
  };

  const handleSelectModel = (id: string) => {
    setSelectedModelId(id);
    localStorage.setItem(STORAGE_KEY_MODEL, id);
  };

  const selectedConnection = connections?.find((item) => item.id === selectedConnectionId);
  const selectedModel = models?.find((item) => item.id === selectedModelId);
  const readyToQuery = Boolean(selectedConnection && selectedModel);
  const modelReady = Boolean(
    selectedModel &&
      (selectedModel.api_key_configured || selectedModel.extra_options?.api_key_optional)
  );

  return {
    selectedConnectionId,
    selectedModelId,
    showConnectionDropdown,
    showModelDropdown,
    input,
    selectedConnection,
    selectedModel,
    readyToQuery,
    modelReady,
    handleSelectConnection,
    handleSelectModel,
    setShowConnectionDropdown,
    setShowModelDropdown,
    setInput,
  };
}
