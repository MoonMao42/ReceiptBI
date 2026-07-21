import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useModelSettingsResource } from "@/components/settings/hooks/useModelSettingsResource";
import { api } from "@/lib/api/client";
import { initialModelFormData } from "@/lib/settings/models";
import type { ConfiguredModel } from "@/lib/types/api";

vi.mock("@/lib/api/client", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const savedModel: ConfiguredModel = {
  id: "service-a",
  name: "日常分析",
  provider: "custom",
  model_id: "analysis-model",
  is_default: true,
  created_at: "2026-07-19T00:00:00Z",
  credential_state: "readable",
  health_status: "unknown",
};

const failedCheck = {
  success: false,
  message: "访问凭证需要更新",
  error_category: "auth",
  health_status: "unhealthy",
  checked_at: "2026-07-19T00:01:00Z",
};

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("useModelSettingsResource", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue({ data: { data: [] } });
  });

  it("checks a newly saved service without turning a failed check into a failed save", async () => {
    vi.mocked(api.post)
      .mockResolvedValueOnce({ data: { data: savedModel } })
      .mockResolvedValueOnce({ data: { data: failedCheck } });

    const { result } = renderHook(() => useModelSettingsResource(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await expect(
        result.current.addModel({
          ...initialModelFormData,
          name: savedModel.name,
          provider: savedModel.provider,
          model_id: savedModel.model_id,
          base_url: "https://gateway.example/v1",
          api_key: "secret",
        })
      ).resolves.toEqual(savedModel);
    });

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(`/api/v1/config/models/${savedModel.id}/test`)
    );
    await waitFor(() => expect(result.current.testResult).toMatchObject(failedCheck));
    expect(result.current.error).toBeNull();
    expect(vi.mocked(api.get).mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("checks an updated service after the update is safely stored", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: { data: savedModel } });
    vi.mocked(api.post).mockResolvedValue({
      data: {
        data: {
          ...failedCheck,
          success: true,
          message: "连接成功",
          error_category: null,
          health_status: "healthy",
        },
      },
    });

    const { result } = renderHook(() => useModelSettingsResource(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.updateModel(savedModel.id, {
        ...initialModelFormData,
        name: savedModel.name,
        provider: savedModel.provider,
        model_id: savedModel.model_id,
        base_url: "https://gateway.example/v1",
      });
    });

    expect(api.put).toHaveBeenCalledWith(
      `/api/v1/config/models/${savedModel.id}`,
      expect.objectContaining({ name: savedModel.name })
    );
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(`/api/v1/config/models/${savedModel.id}/test`)
    );
    await waitFor(() => expect(result.current.testResult?.success).toBe(true));
  });
});
