import { afterEach, describe, expect, it, vi } from "vitest";
import { createSecureEventStream } from "@/lib/api/client";

describe("secure event stream transport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
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

  it("surfaces the API detail for a rejected stream request", async () => {
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

    await expect(stream.next()).rejects.toThrow("当前项目没有可用模型");
  });

  it("fails visibly when the server sends a malformed SSE event", async () => {
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

    await expect(stream.next()).rejects.toThrow("无法识别的事件");
    expect(releaseLock).toHaveBeenCalledOnce();
  });
});
