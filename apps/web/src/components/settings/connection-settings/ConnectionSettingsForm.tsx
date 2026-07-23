"use client";

import { useEffect, useState, type FormEvent } from "react";
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
  const hasAdvancedOptions =
    formData.extra_options.sslmode !== "prefer" ||
    Boolean(
      formData.extra_options.schema ||
        formData.extra_options.sslrootcert ||
        formData.extra_options.sslcert ||
        formData.extra_options.sslkey
    );
  const [advancedOpen, setAdvancedOpen] = useState(hasAdvancedOptions);

  useEffect(() => {
    if (hasAdvancedOptions) setAdvancedOpen(true);
  }, [editingId, hasAdvancedOptions]);

  return (
    <form
      onSubmit={onSubmit}
      data-testid="connection-form"
      className="mb-7 border-y border-border bg-card px-4 py-5 sm:px-5"
    >
      <h3 className="text-sm font-medium text-foreground mb-4">
        {editingId ? t("editConnection") : t("addConnection")}
      </h3>
      <div className="grid gap-5 md:grid-cols-2">
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">{t("connectionName")}</label>
          <input
            type="text"
            value={formData.name}
            onChange={(event) => onChange({ ...formData, name: event.target.value })}
            data-testid="connection-name-input"
            className="w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
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
            className="w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
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
                className="w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
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
                className="w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                required
              />
            </div>
          </>
        )}
        <div className={formData.driver === "sqlite" ? "md:col-span-2" : ""}>
          <label className="block text-sm font-medium text-foreground mb-1">
            {formData.driver === "sqlite" ? t("databaseFilePath") : t("databaseName")}
          </label>
          <input
            type="text"
            value={formData.database}
            onChange={(event) => onChange({ ...formData, database: event.target.value })}
            data-testid="connection-database-input"
            className="w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
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
                className="w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
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
                className="w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                placeholder={editingId ? t("passwordPlaceholder") : "••••••••"}
              />
            </div>
          </>
        )}
        {formData.driver !== "sqlite" && (
          <details
            className="md:col-span-2 border-y border-border py-3"
            open={advancedOpen}
            onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}
            data-testid="connection-security-options"
          >
            <summary className="cursor-pointer select-none text-sm font-medium text-foreground">
              {t("security.title")}
            </summary>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  {t("security.encryption")}
                </label>
                <select
                  value={formData.extra_options.sslmode}
                  onChange={(event) => {
                    const sslmode =
                      event.target.value as typeof formData.extra_options.sslmode;
                    onChange({
                      ...formData,
                      extra_options: {
                        ...formData.extra_options,
                        sslmode,
                        ...(sslmode === "disable"
                          ? { sslrootcert: "", sslcert: "", sslkey: "" }
                          : {}),
                      },
                    });
                  }}
                  data-testid="connection-sslmode-select"
                  className="w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                >
                  <option value="prefer">{t("security.sslMode.prefer")}</option>
                  <option value="require">{t("security.sslMode.require")}</option>
                  <option value="verify-ca">{t("security.sslMode.verifyCa")}</option>
                  <option value="verify-full">{t("security.sslMode.verifyFull")}</option>
                  <option value="disable">{t("security.sslMode.disable")}</option>
                </select>
              </div>
              {formData.driver === "postgresql" && (
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    {t("security.schema")}
                  </label>
                  <input
                    type="text"
                    value={formData.extra_options.schema}
                    onChange={(event) =>
                      onChange({
                        ...formData,
                        extra_options: {
                          ...formData.extra_options,
                          schema: event.target.value,
                        },
                      })
                    }
                    data-testid="connection-schema-input"
                    className="w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                    placeholder="public"
                  />
                </div>
              )}
              {formData.extra_options.sslmode !== "disable" && (
                <>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-foreground">
                      {t("security.caCertificatePath")}
                    </label>
                    <input
                      type="text"
                      value={formData.extra_options.sslrootcert}
                      onChange={(event) =>
                        onChange({
                          ...formData,
                          extra_options: {
                            ...formData.extra_options,
                            sslrootcert: event.target.value,
                          },
                        })
                      }
                      data-testid="connection-ca-path-input"
                      className="w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                      placeholder="/path/to/ca.pem"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-foreground">
                      {t("security.clientCertificatePath")}
                    </label>
                    <input
                      type="text"
                      value={formData.extra_options.sslcert}
                      onChange={(event) =>
                        onChange({
                          ...formData,
                          extra_options: {
                            ...formData.extra_options,
                            sslcert: event.target.value,
                          },
                        })
                      }
                      data-testid="connection-client-cert-input"
                      className="w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                      placeholder="/path/to/client.pem"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-foreground">
                      {t("security.clientKeyPath")}
                    </label>
                    <input
                      type="text"
                      value={formData.extra_options.sslkey}
                      onChange={(event) =>
                        onChange({
                          ...formData,
                          extra_options: {
                            ...formData.extra_options,
                            sslkey: event.target.value,
                          },
                        })
                      }
                      data-testid="connection-client-key-input"
                      className="w-full border border-border bg-background px-3 py-2.5 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                      placeholder="/path/to/client.key"
                    />
                  </div>
                </>
              )}
            </div>
          </details>
        )}
        <div className="md:col-span-2">
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
          className="px-4 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted"
        >
          {tc("cancel")}
        </button>
        <button
          type="submit"
          disabled={isSubmitting}
          data-testid="connection-submit-button"
          className="flex items-center gap-2 bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          {isSubmitting && <Loader2 size={16} className="animate-spin" />}
          {editingId ? t("update") : tc("save")}
        </button>
      </div>
    </form>
  );
}
