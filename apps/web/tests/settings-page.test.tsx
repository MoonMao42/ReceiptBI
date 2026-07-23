import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SettingsPage from "@/app/settings/page";
import enMessages from "@/messages/en.json";
import zhMessages from "@/messages/zh.json";

vi.mock("@/components/settings/ModelSettings", () => ({
  ModelSettings: () => <div data-testid="model-settings">models</div>,
}));

vi.mock("@/components/settings/ConnectionSettings", () => ({
  ConnectionSettings: () => <div data-testid="connection-settings">connections</div>,
}));

vi.mock("@/components/settings/PreferencesSettings", () => ({
  PreferencesSettings: ({ section }: { section: string }) => (
    <div data-testid={`preferences-${section}`}>{section}</div>
  ),
}));

function renderPage(locale: "en" | "zh" = "zh") {
  return render(
    <NextIntlClientProvider
      locale={locale}
      messages={locale === "zh" ? zhMessages : enMessages}
    >
      <SettingsPage />
    </NextIntlClientProvider>
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/settings");
  });

  it("keeps current settings and removes legacy prompt, schema, semantic and config migration UI", async () => {
    renderPage();

    expect(await screen.findByTestId("model-settings")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "分析服务" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "设置" })).not.toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-connections")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-execution")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-appearance")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-advanced")).toBeInTheDocument();
    expect(screen.queryByTestId("settings-tab-prompts")).not.toBeInTheDocument();
    expect(screen.queryByTestId("settings-tab-schema")).not.toBeInTheDocument();
    expect(screen.queryByTestId("settings-tab-semantic")).not.toBeInTheDocument();
    expect(screen.queryByTestId("legacy-connection-migration")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "关于" })).toHaveAttribute("href", "/about");

    fireEvent.click(screen.getByTestId("settings-tab-appearance"));
    expect(await screen.findByTestId("preferences-appearance")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "外观" })).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("settings-tab-execution"));
    expect(await screen.findByTestId("preferences-execution")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "执行" })).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("settings-tab-advanced"));
    expect(await screen.findByTestId("preferences-diagnostics")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "调查诊断" })).toBeInTheDocument();
  });

  it("does not revive a retired settings panel from an old URL", async () => {
    window.history.replaceState({}, "", "/settings?tab=prompts");

    renderPage();

    expect(await screen.findByTestId("model-settings")).toBeInTheDocument();
    expect(screen.queryByTestId("preferences-diagnostics")).not.toBeInTheDocument();
  });

  it("opens a requested tab without mounting the default panel first", async () => {
    window.history.replaceState({}, "", "/settings?tab=connections");

    renderPage();

    expect(await screen.findByTestId("connection-settings")).toBeInTheDocument();
    expect(screen.queryByTestId("model-settings")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "数据连接" })).toBeInTheDocument();
  });

  it("renders navigation and panel titles from the English settings catalog", async () => {
    renderPage("en");

    expect(await screen.findByTestId("model-settings")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 1, name: "Analysis service" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Data connections" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", "/about");

    fireEvent.click(screen.getByTestId("settings-tab-execution"));
    expect(await screen.findByTestId("preferences-execution")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Execution" })).toBeInTheDocument();
  });
});
