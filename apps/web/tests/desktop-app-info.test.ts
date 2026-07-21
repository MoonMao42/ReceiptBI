import { afterEach, describe, expect, it, vi } from "vitest";
import { formatDesktopPlatform, readDesktopAppInfo } from "@/lib/desktop-app-info";

describe("desktop app info bridge", () => {
  afterEach(() => {
    Reflect.deleteProperty(window, "electronAPI");
  });

  it("returns no app info in a browser preview", async () => {
    await expect(readDesktopAppInfo()).resolves.toBeUndefined();
  });

  it("reads the packaged state from the desktop contract", async () => {
    const getAppInfo = vi.fn().mockResolvedValue({
      version: "0.1.0",
      platform: "darwin",
      isPackaged: true,
    });
    Object.defineProperty(window, "electronAPI", {
      configurable: true,
      value: { getAppInfo },
    });

    await expect(readDesktopAppInfo()).resolves.toEqual({
      version: "0.1.0",
      platform: "darwin",
      isPackaged: true,
    });
    expect(getAppInfo).toHaveBeenCalledOnce();
    expect(formatDesktopPlatform("darwin")).toBe("macOS");
  });
});
