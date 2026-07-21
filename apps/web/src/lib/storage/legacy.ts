export type StorageMigrationTarget = Pick<
  Storage,
  "getItem" | "setItem" | "removeItem"
>;

export const THEME_STORAGE_KEY = "receiptbi-theme";
export const LEGACY_THEME_STORAGE_KEY = "querygpt-theme";
export const PROJECT_STORAGE_KEY = "receiptbi-current-project";
export const LEGACY_PROJECT_STORAGE_KEY = "querygpt-current-project";
export const SELECTED_MODEL_STORAGE_KEY = "receiptbi-selected-model";
export const LEGACY_SELECTED_MODEL_STORAGE_KEY = "querygpt-selected-model";
export const PENDING_TASK_STORAGE_KEY = "receiptbi-pending-task";
export const LEGACY_PENDING_TASK_STORAGE_KEY = "querygpt-pending-task";

/**
 * Move a persisted value to its ReceiptBI key without risking data loss.
 *
 * The legacy key is removed only when the ReceiptBI value already exists or
 * when a copied value can be read back unchanged. A failed/blocked write leaves
 * the legacy value in place so a later launch can retry the migration.
 */
export function migrateLegacyStorageValue(
  storage: StorageMigrationTarget,
  currentKey: string,
  legacyKey: string
): string | null {
  let currentValue: string | null;
  try {
    const value = storage.getItem(currentKey);
    currentValue = typeof value === "string" ? value : null;
  } catch {
    return null;
  }

  if (currentValue !== null) {
    try {
      storage.removeItem(legacyKey);
    } catch {
      // Keeping a redundant legacy value is safer than blocking app startup.
    }
    return currentValue;
  }

  let legacyValue: string | null;
  try {
    const value = storage.getItem(legacyKey);
    legacyValue = typeof value === "string" ? value : null;
  } catch {
    return null;
  }
  if (legacyValue === null) return null;

  try {
    storage.setItem(currentKey, legacyValue);
  } catch {
    return legacyValue;
  }

  let copiedValue: string | null;
  try {
    const value = storage.getItem(currentKey);
    copiedValue = typeof value === "string" ? value : null;
  } catch {
    return legacyValue;
  }

  if (copiedValue === legacyValue) {
    try {
      storage.removeItem(legacyKey);
    } catch {
      // The ReceiptBI copy is already durable; cleanup can retry next launch.
    }
  }
  return copiedValue ?? legacyValue;
}

/** Build an early inline migration from the same implementation used at runtime. */
export function inlineStorageMigration(
  currentKey: string,
  legacyKey: string
): string {
  return `(${migrateLegacyStorageValue.toString()})(localStorage,${JSON.stringify(
    currentKey
  )},${JSON.stringify(legacyKey)})`;
}

export function migrateThemeStorage(storage: StorageMigrationTarget): string | null {
  return migrateLegacyStorageValue(
    storage,
    THEME_STORAGE_KEY,
    LEGACY_THEME_STORAGE_KEY
  );
}

export function migrateProjectStorage(storage: StorageMigrationTarget): string | null {
  return migrateLegacyStorageValue(
    storage,
    PROJECT_STORAGE_KEY,
    LEGACY_PROJECT_STORAGE_KEY
  );
}

export function migrateSelectedModelStorage(
  storage: StorageMigrationTarget
): string | null {
  return migrateLegacyStorageValue(
    storage,
    SELECTED_MODEL_STORAGE_KEY,
    LEGACY_SELECTED_MODEL_STORAGE_KEY
  );
}

export function migratePendingTaskStorage(
  storage: StorageMigrationTarget
): string | null {
  return migrateLegacyStorageValue(
    storage,
    PENDING_TASK_STORAGE_KEY,
    LEGACY_PENDING_TASK_STORAGE_KEY
  );
}

export function inlineThemeStorageMigration(): string {
  return inlineStorageMigration(THEME_STORAGE_KEY, LEGACY_THEME_STORAGE_KEY);
}
