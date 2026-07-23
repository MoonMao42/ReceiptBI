import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useConnectionSettingsResource } from "@/components/settings/hooks/useConnectionSettingsResource";
import { api } from "@/lib/api/client";
import enMessages from "@/messages/en.json";
import zhMessages from "@/messages/zh.json";

vi.mock("@/lib/api/client", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function resourceMessages(locale: "en" | "zh") {
  const messages =
    locale === "zh" ? zhMessages.connectionSettings : enMessages.connectionSettings;
  return {
    success: messages.testResultSuccess,
    failure: messages.testResultFailed,
    requestFailure: messages.testRequestFailed,
  };
}

describe("useConnectionSettingsResource", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue({ data: { data: [] } });
  });

  it("maps a successful check to the English catalog and ignores the raw API message", async () => {
    vi.mocked(api.post).mockResolvedValueOnce({
      data: { data: { connected: true, message: "连接成功" } },
    });

    const { result } = renderHook(
      () => useConnectionSettingsResource(resourceMessages("en")),
      { wrapper: createWrapper() }
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.testConnection("connection-a"));

    await waitFor(() =>
      expect(result.current.testResult).toEqual({
        id: "connection-a",
        success: true,
        text: "Connection succeeded.",
      })
    );
    expect(result.current.testResult?.text).not.toBe("连接成功");
  });

  it("maps a failed check to the Chinese catalog and ignores the raw API message", async () => {
    vi.mocked(api.post).mockResolvedValueOnce({
      data: { data: { connected: false, message: "connection refused by upstream" } },
    });

    const { result } = renderHook(
      () => useConnectionSettingsResource(resourceMessages("zh")),
      { wrapper: createWrapper() }
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.testConnection("connection-a"));

    await waitFor(() =>
      expect(result.current.testResult).toEqual({
        id: "connection-a",
        success: false,
        text: "连接失败，请检查数据库设置后重试。",
      })
    );
    expect(result.current.testResult?.text).not.toBe("connection refused by upstream");
  });

  it("uses a safe English fallback when the check request itself fails", async () => {
    vi.mocked(api.post).mockRejectedValueOnce({
      response: { data: { error: { message: "固定中文服务错误" } } },
    });

    const { result } = renderHook(
      () => useConnectionSettingsResource(resourceMessages("en")),
      { wrapper: createWrapper() }
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.testConnection("connection-a"));

    await waitFor(() =>
      expect(result.current.testResult).toEqual({
        id: "connection-a",
        success: false,
        text: "Connection check could not be completed. Try again.",
      })
    );
    expect(result.current.testResult?.text).not.toBe("固定中文服务错误");
  });
});
