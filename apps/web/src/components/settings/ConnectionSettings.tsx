"use client";

import { useState } from "react";
import {
  CheckCircle,
  Loader2,
  Pencil,
  Play,
  Plus,
  Star,
  XCircle,
} from "lucide-react";
import { ConnectionSettingsForm } from "@/components/settings/connection-settings/ConnectionSettingsForm";
import { useConnectionSettingsResource } from "@/components/settings/hooks/useConnectionSettingsResource";
import {
  applyDriverDefaults,
  buildConnectionFormData,
  defaultConnectionFormData,
  formatConnectionTarget,
  type ConnectionFormData,
} from "@/lib/settings/connections";
import type { ConfiguredConnection } from "@/lib/types/api";
import { cn } from "@/lib/utils";
import { useArmedAction } from "@/lib/hooks/useArmedAction";
import { ArmedDeleteButton } from "@/components/ui/armed-delete-button";
import { useLocale, useTranslations } from "next-intl";

export function ConnectionSettings() {
  const {
    connections,
    isLoading,
    testResult,
    deletePending,
    testingConnectionId,
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
  const t = useTranslations("connectionSettings");
  const tc = useTranslations("common");
  const { armedId: armedDeleteId, request: requestDelete } = useArmedAction();
  const isChinese = useLocale() === "zh";
  const copy = isChinese
    ? {
        title: "数据库",
        description:
          "添加 SQLite、MySQL 或 PostgreSQL 数据库连接，供分析项目只读使用。文件数据仍从项目工作台加入。",
        add: "添加数据库",
      }
    : {
        title: "Databases",
        description:
          "Add SQLite, MySQL, or PostgreSQL connections for read-only analysis. Add file data from the project workbench.",
        add: "Add database",
      };

  const handleSelectConnection = (id: string) => {
    setSelectedId(id);
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
    deleteConnection(id);
  };

  return (
    <div>
      <div className="mb-7 flex items-center justify-end">
        <button
          onClick={() => {
            resetForm();
            setShowForm(true);
          }}
          data-testid="connection-add-button"
          className="flex items-center gap-2 bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <Plus size={16} />
          {copy.add}
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

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="animate-spin text-muted-foreground" size={24} />
        </div>
      ) : !connections.length ? (
        <div className="py-12 text-center text-muted-foreground">
          <p>{t("noConnections")}</p>
          <p className="mt-1 text-sm">{t("addFirstConnection")}</p>
        </div>
      ) : (
        <div className="border-t border-border">
          {connections.map((connection) => (
            <div
              key={connection.id}
              onClick={() => handleSelectConnection(connection.id)}
              data-testid={`connection-card-${connection.id}`}
              className={cn(
                "flex cursor-pointer flex-col gap-4 border-b border-border px-4 py-4 transition-colors sm:flex-row sm:items-center sm:justify-between",
                selectedId === connection.id
                  ? "bg-primary/10 shadow-[inset_3px_0_0_hsl(var(--primary))]"
                  : "bg-card hover:bg-muted"
              )}
            >
              <div className="flex min-w-0 flex-1 items-center gap-3">
                {connection.is_default && (
                  <Star size={16} className="shrink-0 fill-yellow-500 text-yellow-500" />
                )}
                <div className="min-w-0">
                  <div className="truncate font-medium text-foreground">{connection.name}</div>
                  <div className="truncate font-mono text-xs text-muted-foreground">
                    {formatConnectionTarget(connection)}
                  </div>
                  {testResult?.id === connection.id && (
                    <div
                      className={cn(
                        "mt-1 flex items-center gap-1 text-sm",
                        testResult.success ? "text-success" : "text-destructive"
                      )}
                    >
                      {testResult.success ? <CheckCircle size={14} /> : <XCircle size={14} />}
                      {testResult.message}
                    </div>
                  )}
                </div>
              </div>
              <div className="flex w-full shrink-0 items-center justify-end gap-1 sm:w-auto">
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    testConnection(connection.id);
                  }}
                  disabled={testingConnectionId === connection.id}
                  data-testid={`connection-test-${connection.id}`}
                  className="p-2 text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary disabled:opacity-50"
                  title={t("testConnection")}
                >
                  {testingConnectionId === connection.id ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Play size={16} />
                  )}
                </button>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    handleEdit(connection);
                  }}
                  className="p-2 text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
                  title={tc("edit")}
                >
                  <Pencil size={16} />
                </button>
                <ArmedDeleteButton
                  armed={armedDeleteId === connection.id}
                  onRequest={() => requestDelete(connection.id, () => handleDelete(connection.id))}
                  confirmLabel={tc("confirmDelete")}
                  deleteLabel={tc("delete")}
                  disabled={deletePending}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
