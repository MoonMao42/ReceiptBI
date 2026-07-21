"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  migrateThemeStorage,
  THEME_STORAGE_KEY,
} from "@/lib/storage/legacy";

export { LEGACY_THEME_STORAGE_KEY, THEME_STORAGE_KEY } from "@/lib/storage/legacy";

// Theme definitions - names and descriptions are keys, translated by UI layer
export const THEMES = {
  dawn: { id: "dawn", name: "dawn", description: "dawn" },
  midnight: { id: "midnight", name: "midnight", description: "midnight" },
} as const;

export type ThemeId = keyof typeof THEMES;

const LEGACY_THEME_IDS = ["monet", "vangogh", "sakura", "forest", "aurora"];

function isThemeId(value: unknown): value is ThemeId {
  return typeof value === "string" && Object.prototype.hasOwnProperty.call(THEMES, value);
}

export function migrateLegacyThemeStorage(storage?: Storage): void {
  if (typeof window === "undefined" && !storage) return;
  try {
    migrateThemeStorage(storage || window.localStorage);
  } catch {
    // A blocked storage backend should never prevent the workspace from opening.
  }
}

interface ThemeState {
  theme: ThemeId;
  setTheme: (theme: ThemeId) => void;
  initTheme: () => void;
}

// Apply theme to HTML
const applyTheme = (theme: ThemeId) => {
  if (typeof document === "undefined") return;
  const root = document.documentElement;

  // Remove all theme classes
  [...Object.keys(THEMES), ...LEGACY_THEME_IDS].forEach((t) => {
    root.classList.remove(`theme-${t}`);
  });

  // Add new theme class
  root.classList.add(`theme-${theme}`);
};

migrateLegacyThemeStorage();

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: "dawn",

      setTheme: (theme: ThemeId) => {
        applyTheme(theme);
        set({ theme });
      },

      initTheme: () => {
        const { theme } = get();
        applyTheme(theme);
      },
    }),
    {
      name: THEME_STORAGE_KEY,
      partialize: (state) => ({ theme: state.theme }),
      merge: (persisted, current) => {
        const savedTheme = (persisted as { theme?: unknown } | undefined)?.theme;
        return {
          ...current,
          theme: isThemeId(savedTheme) ? savedTheme : "dawn",
        };
      },
    }
  )
);
