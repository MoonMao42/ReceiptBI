import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import { ConnectionSettingsForm } from "@/components/settings/connection-settings/ConnectionSettingsForm";
import {
  applyDriverDefaults,
  defaultConnectionFormData,
  type ConnectionFormData,
} from "@/lib/settings/connections";
import enMessages from "@/messages/en.json";
import zhMessages from "@/messages/zh.json";

function renderForm(
  formData: ConnectionFormData,
  onChange = vi.fn(),
  locale: "en" | "zh" = "zh"
) {
  render(
    <NextIntlClientProvider
      locale={locale}
      messages={locale === "zh" ? zhMessages : enMessages}
    >
      <ConnectionSettingsForm
        editingId={null}
        formData={formData}
        isSubmitting={false}
        onChange={onChange}
        onDriverChange={vi.fn()}
        onReset={vi.fn()}
        onSubmit={vi.fn()}
      />
    </NextIntlClientProvider>
  );
  return onChange;
}

describe("ConnectionSettingsForm", () => {
  it("keeps remote security and scope in one compact disclosure", () => {
    const onChange = renderForm({
      ...defaultConnectionFormData,
      driver: "postgresql",
      extra_options: {
        sslmode: "verify-full",
        sslrootcert: "/certs/root.pem",
        sslcert: "/certs/client.pem",
        sslkey: "/certs/client.key",
        schema: "finance",
      },
    });

    expect(screen.getByTestId("connection-security-options")).toHaveTextContent(
      "连接安全与范围"
    );
    expect(screen.getByText("数据库模式")).toBeInTheDocument();
    expect(screen.getByTestId("connection-schema-input")).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("connection-sslmode-select"), {
      target: { value: "disable" },
    });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        extra_options: expect.objectContaining({
          sslmode: "disable",
          sslrootcert: "",
          sslcert: "",
          sslkey: "",
          schema: "finance",
        }),
      })
    );
  });

  it("does not show remote options for SQLite", () => {
    renderForm(applyDriverDefaults(defaultConnectionFormData, "sqlite"));

    expect(screen.queryByTestId("connection-security-options")).not.toBeInTheDocument();
  });

  it("reads the remote security labels from the active locale catalog", () => {
    renderForm(
      applyDriverDefaults(defaultConnectionFormData, "postgresql"),
      vi.fn(),
      "en"
    );

    expect(screen.getByTestId("connection-security-options")).toHaveTextContent(
      "Connection security and scope"
    );
    expect(screen.getByRole("option", { name: "Verify CA and host" })).toBeInTheDocument();
  });
});
