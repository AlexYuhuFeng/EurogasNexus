import { create } from "zustand";

export type ThemeMode = "light" | "dark" | "system";

/**
 * Light until the person chooses (SMALL_DESK_PLAN section 9: the small desk, the default profile,
 * reads light beside its trading screen; dark stays one choice away, "system" too).
 */
export const DEFAULT_THEME: ThemeMode = "light";

interface ThemeState {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  mode: (localStorage.getItem("theme") as ThemeMode) || DEFAULT_THEME,
  setMode: (mode) => {
    localStorage.setItem("theme", mode);
    set({ mode });
    applyTheme(mode);
  },
}));

function applyTheme(mode: ThemeMode): void {
  const root = document.documentElement;
  root.classList.remove("light", "dark");
  if (mode === "system") {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    root.classList.add(prefersDark ? "dark" : "light");
  } else {
    root.classList.add(mode);
  }
}

applyTheme((localStorage.getItem("theme") as ThemeMode) || DEFAULT_THEME);
