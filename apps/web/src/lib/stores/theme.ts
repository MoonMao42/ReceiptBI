"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

// Theme definitions - names and descriptions are keys, translated by UI layer
export const THEMES = {
  dawn: { id: "dawn", name: "dawn", description: "dawn" },
  midnight: { id: "midnight", name: "midnight", description: "midnight" },
  monet: { id: "monet", name: "monet", description: "monet" },
  vangogh: { id: "vangogh", name: "vangogh", description: "vangogh" },
  sakura: { id: "sakura", name: "sakura", description: "sakura" },
  forest: { id: "forest", name: "forest", description: "forest" },
  aurora: { id: "aurora", name: "aurora", description: "aurora" },
} as const;

export type ThemeId = keyof typeof THEMES;

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
  Object.keys(THEMES).forEach((t) => {
    root.classList.remove(`theme-${t}`);
  });

  // Add new theme class
  root.classList.add(`theme-${theme}`);
};

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
      name: "querygpt-theme",
      partialize: (state) => ({ theme: state.theme }),
    }
  )
);
