import axios from "axios";
import { runtimeMessage } from "@/i18n/runtime";
import { UserFacingError, type SSEEventData } from "@/lib/types/api";

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

function responseErrorMessage(response: Response): string {
  return runtimeMessage("requestFailedHttp", { status: response.status });
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
    throw new UserFacingError(runtimeMessage("unrecognizedAnalysisEvent"));
  }
}

export async function* createSecureEventStream(
  url: string,
  payload: Record<string, string>,
  signal?: AbortSignal
): AsyncGenerator<SSEEventData> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${url}`, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (error) {
    if (isRecord(error) && error.name === "AbortError") throw error;
    throw new UserFacingError(runtimeMessage("analysisConnectionInterrupted"));
  }

  if (!response.ok) {
    throw new UserFacingError(responseErrorMessage(response));
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new UserFacingError(runtimeMessage("missingResponseBody"));
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
