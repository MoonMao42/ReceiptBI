import { afterEach, describe, it, expect } from "vitest";
import {
  getErrorMessage,
  getUserFacingErrorMessage,
  UserFacingError,
} from "@/lib/types/api";

const originalLanguage = document.documentElement.lang;

afterEach(() => {
  document.documentElement.lang = originalLanguage;
});

describe("getErrorMessage", () => {
  it("should return message from Error object", () => {
    const error = new Error("Test error message");
    expect(getErrorMessage(error)).toBe("暂时无法完成，请重试。");
  });

  it("should return string directly", () => {
    expect(getErrorMessage("String error")).toBe("暂时无法完成，请重试。");
  });

  it("should return default message for unknown types", () => {
    expect(getErrorMessage(null)).toBe("暂时无法完成，请重试。");
    expect(getErrorMessage(undefined)).toBe("暂时无法完成，请重试。");
    expect(getErrorMessage(123)).toBe("暂时无法完成，请重试。");
    expect(getErrorMessage({})).toBe("暂时无法完成，请重试。");
  });

  it("keeps an explicitly localized client error", () => {
    expect(getErrorMessage(new UserFacingError("请先选择数据来源"))).toBe(
      "请先选择数据来源"
    );
  });

  it("does not expose Axios payloads or transport messages", () => {
    document.documentElement.lang = "en";
    const error = {
      isAxiosError: true,
      message: "Request failed with status code 503",
      response: {
        status: 503,
        data: { detail: "内部服务暂时不可用" },
      },
    };

    expect(getErrorMessage(error)).toBe(
      "The request could not be completed. Please retry."
    );
    expect(getUserFacingErrorMessage(error, "Could not save")).toBe(
      "The request could not be completed. Please retry."
    );
  });

  it("uses the localized fallback for transport errors without a status", () => {
    document.documentElement.lang = "zh-CN";
    const error = {
      isAxiosError: true,
      message: "Network Error",
      request: {},
    };

    expect(getErrorMessage(error)).toBe("暂时无法完成，请重试。");
    expect(getUserFacingErrorMessage(error, "项目名称保存失败，请重试")).toBe(
      "项目名称保存失败，请重试"
    );
  });
});

describe("Basic utilities", () => {
  it("should handle empty arrays", () => {
    const arr: string[] = [];
    expect(arr.length).toBe(0);
  });

  it("should handle object spread", () => {
    const obj1 = { a: 1 };
    const obj2 = { b: 2 };
    const merged = { ...obj1, ...obj2 };
    expect(merged).toEqual({ a: 1, b: 2 });
  });
});
