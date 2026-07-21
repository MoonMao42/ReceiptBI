import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  LEGACY_THEME_STORAGE_KEY,
  migrateLegacyThemeStorage,
  THEME_STORAGE_KEY,
  useThemeStore,
} from "@/lib/stores/theme";

function createMemoryStorage(initial: Record<string, string> = {}): Storage {
  const values = new Map(Object.entries(initial));
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  };
}

describe("theme persistence", () => {
  beforeEach(() => {
    useThemeStore.setState({ theme: "dawn" });
    vi.mocked(localStorage.setItem).mockClear();
    document.documentElement.className = "";
  });

  it("copies the legacy QueryGPT theme only when the ReceiptBI key is absent", () => {
    const legacyValue = JSON.stringify({ state: { theme: "midnight" }, version: 0 });
    const storage = createMemoryStorage({ [LEGACY_THEME_STORAGE_KEY]: legacyValue });

    migrateLegacyThemeStorage(storage);

    expect(storage.getItem(THEME_STORAGE_KEY)).toBe(legacyValue);
    expect(storage.getItem(LEGACY_THEME_STORAGE_KEY)).toBeNull();
  });

  it("keeps an existing ReceiptBI preference during legacy migration", () => {
    const currentValue = JSON.stringify({ state: { theme: "dawn" }, version: 0 });
    const storage = createMemoryStorage({
      [THEME_STORAGE_KEY]: currentValue,
      [LEGACY_THEME_STORAGE_KEY]: JSON.stringify({
        state: { theme: "midnight" },
        version: 0,
      }),
    });

    migrateLegacyThemeStorage(storage);

    expect(storage.getItem(THEME_STORAGE_KEY)).toBe(currentValue);
    expect(storage.getItem(LEGACY_THEME_STORAGE_KEY)).toBeNull();
  });

  it("applies and persists a selected ReceiptBI theme", () => {
    useThemeStore.getState().setTheme("midnight");

    expect(document.documentElement).toHaveClass("theme-midnight");
    const persistenceCall = vi
      .mocked(localStorage.setItem)
      .mock.calls.find(([key]) => key === THEME_STORAGE_KEY);
    expect(persistenceCall).toBeDefined();
    expect(JSON.parse(persistenceCall?.[1] || "{}").state.theme).toBe("midnight");
  });
});
