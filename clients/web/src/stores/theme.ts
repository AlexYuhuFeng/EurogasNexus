import { create } from "zustand";

export type ThemeMode = "light" | "dark" | "system";

interface ThemeState {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  mode: (localStorage.getItem("theme") as ThemeMode) || "system",
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

applyTheme((localStorage.getItem("theme") as ThemeMode) || "system");
