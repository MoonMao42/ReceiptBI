import { describe, expect, it, vi } from "vitest";
import {
  inlineThemeStorageMigration,
  LEGACY_PENDING_TASK_STORAGE_KEY,
  LEGACY_PROJECT_STORAGE_KEY,
  LEGACY_SELECTED_MODEL_STORAGE_KEY,
  LEGACY_THEME_STORAGE_KEY,
  migrateLegacyStorageValue,
  migratePendingTaskStorage,
  migrateProjectStorage,
  migrateSelectedModelStorage,
  migrateThemeStorage,
  PENDING_TASK_STORAGE_KEY,
  PROJECT_STORAGE_KEY,
  SELECTED_MODEL_STORAGE_KEY,
  THEME_STORAGE_KEY,
} from "@/lib/storage/legacy";

function createMemoryStorage(initial: Record<string, string> = {}): Storage {
  const values = new Map(Object.entries(initial));
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => {
      values.delete(key);
    },
    setItem: (key, value) => {
      values.set(key, value);
    },
  };
}

const migrations = [
  {
    name: "theme",
    currentKey: THEME_STORAGE_KEY,
    legacyKey: LEGACY_THEME_STORAGE_KEY,
    migrate: migrateThemeStorage,
  },
  {
    name: "project",
    currentKey: PROJECT_STORAGE_KEY,
    legacyKey: LEGACY_PROJECT_STORAGE_KEY,
    migrate: migrateProjectStorage,
  },
  {
    name: "selected model",
    currentKey: SELECTED_MODEL_STORAGE_KEY,
    legacyKey: LEGACY_SELECTED_MODEL_STORAGE_KEY,
    migrate: migrateSelectedModelStorage,
  },
  {
    name: "pending task",
    currentKey: PENDING_TASK_STORAGE_KEY,
    legacyKey: LEGACY_PENDING_TASK_STORAGE_KEY,
    migrate: migratePendingTaskStorage,
  },
] as const;

describe.each(migrations)("$name legacy storage migration", (migration) => {
  it("copies a legacy value, verifies it, and removes the legacy key", () => {
    const storage = createMemoryStorage({ [migration.legacyKey]: "legacy-value" });

    expect(migration.migrate(storage)).toBe("legacy-value");
    expect(storage.getItem(migration.currentKey)).toBe("legacy-value");
    expect(storage.getItem(migration.legacyKey)).toBeNull();
  });

  it("preserves an existing ReceiptBI value and still removes the legacy key", () => {
    const storage = createMemoryStorage({
      [migration.currentKey]: "current-value",
      [migration.legacyKey]: "legacy-value",
    });

    expect(migration.migrate(storage)).toBe("current-value");
    expect(storage.getItem(migration.currentKey)).toBe("current-value");
    expect(storage.getItem(migration.legacyKey)).toBeNull();
  });
});

describe("failed legacy storage migration", () => {
  it("keeps the legacy key when a write throws", () => {
    const storage = createMemoryStorage({ legacy: "keep-me" });
    vi.spyOn(storage, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    expect(migrateLegacyStorageValue(storage, "current", "legacy")).toBe("keep-me");
    expect(storage.getItem("current")).toBeNull();
    expect(storage.getItem("legacy")).toBe("keep-me");
  });

  it("keeps the legacy key when a write cannot be read back", () => {
    const storage = createMemoryStorage({ legacy: "keep-me" });
    vi.spyOn(storage, "setItem").mockImplementation(() => undefined);

    expect(migrateLegacyStorageValue(storage, "current", "legacy")).toBe("keep-me");
    expect(storage.getItem("current")).toBeNull();
    expect(storage.getItem("legacy")).toBe("keep-me");
  });
});

describe("early theme migration", () => {
  it("embeds the shared migration implementation used by the runtime", () => {
    const storage = createMemoryStorage({
      [LEGACY_THEME_STORAGE_KEY]: "legacy-theme",
    });
    const execute = new Function(
      "localStorage",
      `return ${inlineThemeStorageMigration()};`
    ) as (target: Storage) => string | null;

    expect(execute(storage)).toBe("legacy-theme");
    expect(storage.getItem(THEME_STORAGE_KEY)).toBe("legacy-theme");
    expect(storage.getItem(LEGACY_THEME_STORAGE_KEY)).toBeNull();
  });
});
