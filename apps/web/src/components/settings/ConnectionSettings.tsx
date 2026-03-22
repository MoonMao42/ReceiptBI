"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { ConnectionSettingsForm } from "@/components/settings/connection-settings/ConnectionSettingsForm";
import { ConnectionSettingsList } from "@/components/settings/connection-settings/ConnectionSettingsList";
import { useConnectionSettingsResource } from "@/components/settings/hooks/useConnectionSettingsResource";
import { ImportConfigDialog } from "@/components/settings/ImportConfigDialog";
import {
  applyDriverDefaults,
  buildConnectionFormData,
  defaultConnectionFormData,
  type ConnectionFormData,
} from "@/lib/settings/connections";
import type { ConfiguredConnection } from "@/lib/types/api";
import { useTranslations } from "next-intl";

interface ConnectionSettingsProps {
  onSelectConnection?: (id: string | null) => void;
}

export function ConnectionSettings({ onSelectConnection }: ConnectionSettingsProps) {
  const {
    connections,
    isLoading,
    testResult,
    deletePending,
    testingConnectionId,
    exportConnection,
    addConnection,
    updateConnection,
    deleteConnection,
    testConnection,
    isSubmitting,
  } = useConnectionSettingsResource();
  const [showForm, setShowForm] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState<ConnectionFormData>(defaultConnectionFormData);
  const [importDialogConnection, setImportDialogConnection] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const t = useTranslations("connectionSettings");

  const handleSelectConnection = (id: string) => {
    setSelectedId(id);
    onSelectConnection?.(id);
  };

  const resetForm = () => {
    setShowForm(false);
    setEditingId(null);
    setFormData(defaultConnectionFormData);
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      if (editingId) {
        await updateConnection(editingId, formData);
        resetForm();
        return;
      }
      await addConnection(formData);
      resetForm();
    } catch (error) {
      console.error(t("saveFailed"), error);
    }
  };

  const handleEdit = (connection: ConfiguredConnection) => {
    setEditingId(connection.id);
    setFormData(buildConnectionFormData(connection));
    setShowForm(true);
  };

  const handleDelete = (id: string) => {
    if (confirm(t("confirmDelete"))) {
      deleteConnection(id);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-foreground">{t("title")}</h2>
          <p className="text-sm text-muted-foreground mt-1">{t("description")}</p>
        </div>
        <button
          onClick={() => {
            resetForm();
            setShowForm(true);
          }}
          data-testid="connection-add-button"
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors text-sm"
        >
          <Plus size={16} />
          {t("addConnection")}
        </button>
      </div>

      {showForm && (
        <ConnectionSettingsForm
          editingId={editingId}
          formData={formData}
          isSubmitting={isSubmitting}
          onChange={setFormData}
          onDriverChange={(driver) => setFormData((current) => applyDriverDefaults(current, driver))}
          onReset={resetForm}
          onSubmit={handleSubmit}
        />
      )}

      <ConnectionSettingsList
        connections={connections}
        selectedId={selectedId}
        isLoading={isLoading}
        testResult={testResult}
        testingConnectionId={testingConnectionId ?? undefined}
        deletePending={deletePending}
        onSelect={handleSelectConnection}
        onExport={exportConnection}
        onImport={(connection) =>
          setImportDialogConnection({ id: connection.id, name: connection.name })
        }
        onTest={testConnection}
        onEdit={handleEdit}
        onDelete={handleDelete}
      />

      <ImportConfigDialog
        connectionId={importDialogConnection?.id || ""}
        connectionName={importDialogConnection?.name || ""}
        isOpen={!!importDialogConnection}
        onClose={() => setImportDialogConnection(null)}
      />
    </div>
  );
}
