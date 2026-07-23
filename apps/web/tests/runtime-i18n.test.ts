import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { runtimeMessage } from "@/i18n/runtime";

describe("runtime i18n fallbacks", () => {
  let originalLanguage = "";

  beforeEach(() => {
    originalLanguage = document.documentElement.lang;
  });

  afterEach(() => {
    document.documentElement.lang = originalLanguage;
  });

  it("uses English fallbacks when the document is in English", () => {
    document.documentElement.lang = "en";

    expect(runtimeMessage("requestFailedHttp", { status: 503 })).toBe(
      "The request could not be completed. Please retry."
    );
    expect(runtimeMessage("executionFailed")).toBe(
      "The investigation could not be completed."
    );
  });

  it("uses Chinese fallbacks when the document is in Chinese", () => {
    document.documentElement.lang = "zh-CN";

    expect(runtimeMessage("requestFailedHttp", { status: 503 })).toBe(
      "请求未能完成，请重试。"
    );
    expect(runtimeMessage("executionFailed")).toBe("这次调查未能完成。");
  });
});
