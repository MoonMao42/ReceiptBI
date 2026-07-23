import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConnectionSettings } from "@/components/settings/ConnectionSettings";
import enMessages from "@/messages/en.json";
import zhMessages from "@/messages/zh.json";

const resourceState = vi.hoisted(() => ({
  testResult: null as null | {
    id: string;
    success: boolean;
    text: string;
  },
}));

vi.mock("@/components/settings/hooks/useConnectionSettingsResource", () => ({
  useConnectionSettingsResource: () => ({
    connections: [
      {
        id: "connection-a",
        name: "Warehouse",
        driver: "sqlite",
        database: "/data/warehouse.db",
        is_default: false,
        created_at: "2026-07-22T00:00:00Z",
      },
    ],
    isLoading: false,
    testResult: resourceState.testResult,
    deletePending: false,
    testingConnectionId: null,
    addConnection: vi.fn(),
    updateConnection: vi.fn(),
    deleteConnection: vi.fn(),
    testConnection: vi.fn(),
    isSubmitting: false,
  }),
}));

function renderSettings(locale: "en" | "zh") {
  render(
    <NextIntlClientProvider
      locale={locale}
      messages={locale === "zh" ? zhMessages : enMessages}
    >
      <ConnectionSettings />
    </NextIntlClientProvider>
  );
}

describe("ConnectionSettings test-result i18n", () => {
  beforeEach(() => {
    resourceState.testResult = null;
  });

  it("renders the English success copy supplied by the resource boundary", () => {
    resourceState.testResult = {
      id: "connection-a",
      success: true,
      text: "Connection succeeded.",
    };

    renderSettings("en");

    expect(screen.getByText("Connection succeeded.")).toBeInTheDocument();
  });

  it("renders the safe Chinese failure supplied by the resource boundary", () => {
    resourceState.testResult = {
      id: "connection-a",
      success: false,
      text: "连接失败，请检查数据库设置后重试。",
    };

    renderSettings("zh");

    expect(screen.getByText("连接失败，请检查数据库设置后重试。")).toBeInTheDocument();
  });
});
