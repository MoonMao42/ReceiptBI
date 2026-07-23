import { afterEach, describe, expect, it, vi } from "vitest";
import { createSecureEventStream } from "@/lib/api/client";

const originalLanguage = document.documentElement.lang;

describe("secure event stream transport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.lang = originalLanguage;
  });

  it("sends private analysis input in a POST body instead of the URL", async () => {
    const releaseLock = vi.fn();
    const read = vi
      .fn()
      .mockResolvedValueOnce({
        done: false,
        value: new TextEncoder().encode(
          'data: {"type":"progress","data":{"message":"正在调查"}}\n'
        ),
      })
      .mockResolvedValueOnce({ done: true, value: undefined });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => ({ read, releaseLock }) },
    });
    vi.stubGlobal("fetch", fetchMock);

    const stream = createSecureEventStream("/api/v1/chat/stream", {
      query: "私人经营问题",
      project_id: "project-a",
    });

    await expect(stream.next()).resolves.toEqual({
      done: false,
      value: { type: "progress", data: { message: "正在调查" } },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/chat/stream",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ query: "私人经营问题", project_id: "project-a" }),
      })
    );
    await stream.return(undefined);
    expect(releaseLock).toHaveBeenCalledOnce();
  });

  it("keeps a rejected request's raw API detail out of the Chinese UI", async () => {
    document.documentElement.lang = "zh-CN";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "当前项目没有可用模型" }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        })
      )
    );

    const stream = createSecureEventStream("/api/v1/chat/stream", { query: "分析销售" });

    await expect(stream.next()).rejects.toThrow("请求未能完成，请重试。");
  });

  it("localizes rejected request status in English instead of leaking Chinese detail", async () => {
    document.documentElement.lang = "en";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "当前项目没有可用模型" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        })
      )
    );

    const stream = createSecureEventStream("/api/v1/chat/stream", { query: "Analyze sales" });

    await expect(stream.next()).rejects.toThrow(
      "The request could not be completed. Please retry."
    );
  });

  it("localizes a transport failure instead of exposing the browser message", async () => {
    document.documentElement.lang = "zh-CN";
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const stream = createSecureEventStream("/api/v1/chat/stream", { query: "分析销售" });

    await expect(stream.next()).rejects.toThrow(
      "分析连接意外中断，未收到完成状态，请重试。"
    );
  });

  it("fails visibly when the server sends a malformed SSE event", async () => {
    document.documentElement.lang = "zh-CN";
    const releaseLock = vi.fn();
    const read = vi
      .fn()
      .mockResolvedValueOnce({
        done: false,
        value: new TextEncoder().encode("data: not-json\n"),
      })
      .mockResolvedValueOnce({ done: true, value: undefined });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: { getReader: () => ({ read, releaseLock }) },
      })
    );

    const stream = createSecureEventStream("/api/v1/chat/stream", { query: "分析销售" });

    await expect(stream.next()).rejects.toThrow("这次调查中断，请重试。");
    expect(releaseLock).toHaveBeenCalledOnce();
  });
});
