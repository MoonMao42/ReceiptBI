import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PreferencesSettings } from "@/components/settings/PreferencesSettings";
import enMessages from "@/messages/en.json";
import zhMessages from "@/messages/zh.json";

const mocks = vi.hoisted(() => ({
  refresh: vi.fn(),
  setLocale: vi.fn(),
  get: vi.fn(),
  put: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: mocks.refresh }),
}));

vi.mock("@/lib/actions/locale", () => ({
  setLocale: mocks.setLocale,
}));

vi.mock("@/lib/api/client", () => ({
  api: { get: mocks.get, put: mocks.put },
}));

describe("PreferencesSettings locale switch", () => {
  beforeEach(() => {
    mocks.refresh.mockReset();
    mocks.setLocale.mockReset();
    mocks.get.mockReset();
    mocks.put.mockReset();
  });

  afterEach(cleanup);

  it("refreshes only after the locale cookie action has completed", async () => {
    let completeLocaleChange!: () => void;
    mocks.setLocale.mockImplementation(
      () => new Promise<void>((resolve) => {
        completeLocaleChange = resolve;
      })
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <NextIntlClientProvider locale="zh" messages={zhMessages}>
        <QueryClientProvider client={queryClient}>
          <PreferencesSettings section="appearance" />
        </QueryClientProvider>
      </NextIntlClientProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(mocks.setLocale).toHaveBeenCalledWith("en");
    expect(mocks.refresh).not.toHaveBeenCalled();

    await act(async () => completeLocaleChange());
    await waitFor(() => expect(mocks.refresh).toHaveBeenCalledTimes(1));
  });

  it("persists preprocessing and self-analysis permissions independently", async () => {
    const settings = {
      context_rounds: 5,
      default_model_id: null,
      default_connection_id: null,
      python_enabled: true,
      diagnostics_enabled: true,
      auto_repair_enabled: true,
      preprocessing_enabled: true,
      self_analysis_enabled: true,
    };
    mocks.get.mockResolvedValue({ data: { data: settings } });
    mocks.put.mockImplementation((_url: string, data: unknown) =>
      Promise.resolve({ data: { data } })
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <NextIntlClientProvider locale="zh" messages={zhMessages}>
        <QueryClientProvider client={queryClient}>
          <PreferencesSettings section="execution" />
        </QueryClientProvider>
      </NextIntlClientProvider>
    );

    const preprocessing = await screen.findByRole("checkbox", {
      name: /允许检查并准备数据/,
    });
    const selfAnalysis = screen.getByRole("checkbox", {
      name: /允许生成分析建议/,
    });
    expect(preprocessing).toHaveAttribute("type", "checkbox");
    fireEvent.click(screen.getByText("允许检查并准备数据"));
    expect(preprocessing).not.toBeChecked();
    fireEvent.click(selfAnalysis);
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(mocks.put).toHaveBeenCalledWith(
        "/api/v1/settings",
        {
          preprocessing_enabled: false,
          self_analysis_enabled: false,
        }
      )
    );
  });

  it("fails closed when settings cannot be read and recovers through retry", async () => {
    const settings = {
      context_rounds: 5,
      default_model_id: null,
      default_connection_id: null,
      python_enabled: true,
      diagnostics_enabled: true,
      auto_repair_enabled: true,
      preprocessing_enabled: true,
      self_analysis_enabled: true,
    };
    mocks.get
      .mockRejectedValueOnce(new Error("network unavailable"))
      .mockResolvedValueOnce({ data: { data: settings } });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <QueryClientProvider client={queryClient}>
          <PreferencesSettings section="execution" />
        </QueryClientProvider>
      </NextIntlClientProvider>
    );

    expect(
      await screen.findByText("Settings are temporarily unavailable.")
    ).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(
      await screen.findByRole("checkbox", {
        name: /Allow checking and preparing data/,
      })
    ).toBeChecked();
  });

  it("uses the saved server response as the next partial-update baseline", async () => {
    const initialSettings = {
      context_rounds: 5,
      default_model_id: null,
      default_connection_id: null,
      python_enabled: true,
      diagnostics_enabled: true,
      auto_repair_enabled: true,
      preprocessing_enabled: true,
      self_analysis_enabled: true,
    };
    const savedSettings = {
      ...initialSettings,
      preprocessing_enabled: false,
      self_analysis_enabled: false,
    };
    mocks.get.mockResolvedValue({ data: { data: initialSettings } });
    mocks.put
      .mockResolvedValueOnce({ data: { data: savedSettings } })
      .mockResolvedValueOnce({
        data: { data: { ...savedSettings, self_analysis_enabled: true } },
      });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <QueryClientProvider client={queryClient}>
          <PreferencesSettings section="execution" />
        </QueryClientProvider>
      </NextIntlClientProvider>
    );

    const preprocessing = await screen.findByRole("checkbox", {
      name: /Allow checking and preparing data/,
    });
    const selfAnalysis = screen.getByRole("checkbox", {
      name: /Allow generating analysis suggestions/,
    });
    const save = screen.getByRole("button", { name: "Save settings" });

    fireEvent.click(preprocessing);
    fireEvent.click(save);

    await waitFor(() =>
      expect(mocks.put).toHaveBeenNthCalledWith(1, "/api/v1/settings", {
        preprocessing_enabled: false,
      })
    );
    expect(await screen.findByText("Settings saved")).toBeInTheDocument();
    await waitFor(() => expect(selfAnalysis).not.toBeChecked());
    expect(save).toBeDisabled();

    fireEvent.click(selfAnalysis);
    fireEvent.click(save);

    await waitFor(() =>
      expect(mocks.put).toHaveBeenNthCalledWith(2, "/api/v1/settings", {
        self_analysis_enabled: true,
      })
    );
  });

  it("renders execution permissions from the English catalog", async () => {
    mocks.get.mockResolvedValue({
      data: {
        data: {
          context_rounds: 5,
          default_model_id: null,
          default_connection_id: null,
          python_enabled: true,
          diagnostics_enabled: true,
          auto_repair_enabled: true,
          preprocessing_enabled: true,
          self_analysis_enabled: true,
        },
      },
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <QueryClientProvider client={queryClient}>
          <PreferencesSettings section="execution" />
        </QueryClientProvider>
      </NextIntlClientProvider>
    );

    expect(
      await screen.findByRole("checkbox", { name: /Allow checking and preparing data/ })
    ).toBeInTheDocument();
    expect(screen.getByText("Execution behavior")).toBeInTheDocument();
  });
});
