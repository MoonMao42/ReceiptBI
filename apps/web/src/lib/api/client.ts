import axios from "axios";
import type { SSEEventData } from "@/lib/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isSSEEventData(value: unknown): value is SSEEventData {
  return isRecord(value) && typeof value.type === "string" && isRecord(value.data);
}

async function responseErrorMessage(response: Response): Promise<string> {
  const fallback = `请求失败（HTTP ${response.status}）`;
  try {
    const text = (await response.text()).trim();
    if (!text) return fallback;
    const payload = JSON.parse(text) as unknown;
    if (isRecord(payload)) {
      const detail = payload.detail;
      if (typeof detail === "string" && detail.trim()) return detail.trim();
      const message = payload.message;
      if (typeof message === "string" && message.trim()) return message.trim();
    }
    return text.length <= 300 ? text : fallback;
  } catch {
    return fallback;
  }
}

function parseEventLine(line: string): SSEEventData | null {
  const normalized = line.endsWith("\r") ? line.slice(0, -1) : line;
  if (!normalized.startsWith("data:")) return null;
  const payload = normalized.slice(5).trimStart();
  if (!payload) return null;
  try {
    const data = JSON.parse(payload) as unknown;
    if (!isSSEEventData(data)) {
      throw new Error("invalid event shape");
    }
    return data;
  } catch {
    throw new Error("分析服务返回了无法识别的事件，连接已停止，请重试。");
  }
}

export async function* createSecureEventStream(
  url: string,
  payload: Record<string, string>,
  signal?: AbortSignal
): AsyncGenerator<SSEEventData> {
  const response = await fetch(`${API_URL}${url}`, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("No response body");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const event = parseEventLine(line);
        if (event) yield event;
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) {
      const event = parseEventLine(buffer);
      if (event) yield event;
    }
  } finally {
    reader.releaseLock();
  }
}
