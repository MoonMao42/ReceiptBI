"use client";

import {
  CheckCircle,
  Download,
  Loader2,
  Pencil,
  Play,
  Star,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import type { ConfiguredConnection } from "@/lib/types/api";
import type { ConnectionTestResult } from "@/lib/settings/connections";
import { cn } from "@/lib/utils";
import { useTranslations } from "next-intl";

interface ConnectionSettingsListProps {
  connections: ConfiguredConnection[];
  selectedId: string | null;
  isLoading: boolean;
  testResult: ConnectionTestResult | null;
  testingConnectionId: string | undefined;
  deletePending: boolean;
  onSelect: (id: string) => void;
  onExport: (connection: ConfiguredConnection) => void;
  onImport: (connection: ConfiguredConnection) => void;
  onTest: (id: string) => void;
  onEdit: (connection: ConfiguredConnection) => void;
  onDelete: (id: string) => void;
}

export function ConnectionSettingsList({
  connections,
  selectedId,
  isLoading,
  testResult,
  testingConnectionId,
  deletePending,
  onSelect,
  onExport,
  onImport,
  onTest,
  onEdit,
  onDelete,
}: ConnectionSettingsListProps) {
  const t = useTranslations("connectionSettings");
  const tc = useTranslations("common");
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin text-muted-foreground" size={24} />
      </div>
    );
  }

  if (!connections.length) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p>{t("noConnections")}</p>
        <p className="text-sm mt-1">{t("addFirstConnection")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {connections.map((connection) => (
        <div
          key={connection.id}
          onClick={() => onSelect(connection.id)}
          data-testid={`connection-card-${connection.id}`}
          className={cn(
            "flex items-center justify-between p-4 bg-secondary rounded-lg border cursor-pointer transition-colors",
            selectedId === connection.id
              ? "border-primary bg-primary/5"
              : "border-border hover:border-primary/50"
          )}
        >
          <div className="flex min-w-0 flex-1 items-center gap-3">
            {connection.is_default && (
              <Star size={16} className="flex-shrink-0 text-yellow-500 fill-yellow-500" />
            )}
            <div className="min-w-0">
              <div className="truncate font-medium text-foreground">{connection.name}</div>
              <div className="truncate text-sm text-muted-foreground">
                {connection.driver}://{connection.username}@{connection.host}:{connection.port}/
                {connection.database_name}
              </div>
              {testResult?.id === connection.id && (
                <div
                  className={cn(
                    "flex items-center gap-1 text-sm mt-1",
                    testResult.success ? "text-green-600" : "text-destructive"
                  )}
                >
                  {testResult.success ? <CheckCircle size={14} /> : <XCircle size={14} />}
                  {testResult.message}
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-shrink-0 items-center gap-1">
            <div className="flex items-center border border-border rounded-lg overflow-hidden mr-2">
              <button
                onClick={(event) => {
                  event.stopPropagation();
                  onExport(connection);
                }}
                className="flex items-center gap-1 px-2 py-1.5 text-xs text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors border-r border-border"
                title={t("exportConfig")}
              >
                <Download size={14} />
                <span>{t("backup")}</span>
              </button>
              <button
                onClick={(event) => {
                  event.stopPropagation();
                  onImport(connection);
                }}
                className="flex items-center gap-1 px-2 py-1.5 text-xs text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                title={t("restoreConfig")}
              >
                <Upload size={14} />
                <span>{t("restore")}</span>
              </button>
            </div>

            <button
              onClick={(event) => {
                event.stopPropagation();
                onTest(connection.id);
              }}
              disabled={testingConnectionId === connection.id}
              data-testid={`connection-test-${connection.id}`}
              className="p-2 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
              title={t("testConnection")}
            >
              {testingConnectionId === connection.id ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Play size={16} />
              )}
            </button>
            <button
              onClick={(event) => {
                event.stopPropagation();
                onEdit(connection);
              }}
              className="p-2 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
              title={tc("edit")}
            >
              <Pencil size={16} />
            </button>
            <button
              onClick={(event) => {
                event.stopPropagation();
                onDelete(connection.id);
              }}
              disabled={deletePending}
              className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
              title={tc("delete")}
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
