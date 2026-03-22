"use client";

import type { FormEvent } from "react";
import { Loader2 } from "lucide-react";
import {
  CONNECTION_DRIVERS,
  type ConnectionFormData,
} from "@/lib/settings/connections";
import { useTranslations } from "next-intl";

interface ConnectionSettingsFormProps {
  editingId: string | null;
  formData: ConnectionFormData;
  isSubmitting: boolean;
  onChange: (next: ConnectionFormData) => void;
  onDriverChange: (driver: string) => void;
  onReset: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

export function ConnectionSettingsForm({
  editingId,
  formData,
  isSubmitting,
  onChange,
  onDriverChange,
  onReset,
  onSubmit,
}: ConnectionSettingsFormProps) {
  const t = useTranslations("connectionSettings");
  const tc = useTranslations("common");
  return (
    <form
      onSubmit={onSubmit}
      data-testid="connection-form"
      className="mb-6 p-4 bg-secondary rounded-lg border border-border"
    >
      <h3 className="text-sm font-medium text-foreground mb-4">
        {editingId ? t("editConnection") : t("addConnection")}
      </h3>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">{t("connectionName")}</label>
          <input
            type="text"
            value={formData.name}
            onChange={(event) => onChange({ ...formData, name: event.target.value })}
            data-testid="connection-name-input"
            className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
            placeholder={t("connectionNamePlaceholder")}
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">{t("databaseType")}</label>
          <select
            value={formData.driver}
            onChange={(event) => onDriverChange(event.target.value)}
            data-testid="connection-driver-select"
            className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
          >
            {CONNECTION_DRIVERS.map((driver) => (
              <option key={driver.value} value={driver.value}>
                {driver.label}
              </option>
            ))}
          </select>
        </div>
        {formData.driver !== "sqlite" && (
          <>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">{t("hostAddress")}</label>
              <input
                type="text"
                value={formData.host}
                onChange={(event) => onChange({ ...formData, host: event.target.value })}
                data-testid="connection-host-input"
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
                placeholder="localhost"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">{t("port")}</label>
              <input
                type="number"
                value={formData.port}
                onChange={(event) =>
                  onChange({ ...formData, port: parseInt(event.target.value, 10) })
                }
                data-testid="connection-port-input"
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
                required
              />
            </div>
          </>
        )}
        <div className={formData.driver === "sqlite" ? "col-span-2" : ""}>
          <label className="block text-sm font-medium text-foreground mb-1">
            {formData.driver === "sqlite" ? t("databaseFilePath") : t("databaseName")}
          </label>
          <input
            type="text"
            value={formData.database}
            onChange={(event) => onChange({ ...formData, database: event.target.value })}
            data-testid="connection-database-input"
            className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
            placeholder={formData.driver === "sqlite" ? "/path/to/database.db" : "mydb"}
            required
          />
        </div>
        {formData.driver !== "sqlite" && (
          <>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">{t("username")}</label>
              <input
                type="text"
                value={formData.username}
                onChange={(event) => onChange({ ...formData, username: event.target.value })}
                data-testid="connection-username-input"
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
                placeholder="root"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                {t("password")}
                {editingId && (
                  <span className="text-muted-foreground font-normal ml-2">{t("passwordHint")}</span>
                )}
              </label>
              <input
                type="password"
                value={formData.password}
                onChange={(event) => onChange({ ...formData, password: event.target.value })}
                data-testid="connection-password-input"
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
                placeholder={editingId ? t("passwordPlaceholder") : "••••••••"}
              />
            </div>
          </>
        )}
        <div className="col-span-2">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={formData.is_default}
              onChange={(event) => onChange({ ...formData, is_default: event.target.checked })}
              data-testid="connection-default-checkbox"
              className="w-4 h-4 text-primary rounded focus:ring-ring"
            />
            <span className="text-sm text-foreground">{t("setAsDefault")}</span>
          </label>
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-4">
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
          data-testid="connection-submit-button"
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors text-sm"
        >
          {isSubmitting && <Loader2 size={16} className="animate-spin" />}
          {editingId ? t("update") : tc("save")}
        </button>
      </div>
    </form>
  );
}
