import { create } from "zustand";
import { applyDensity, readStoredDensity, writeStoredDensity, type Density } from "@/app/model/density";

/** The row density in force on this device (UX R11); the server copy follows the person. */
interface DensityState {
  density: Density;
  setDensity: (density: string) => void;
}

export const useDensityStore = create<DensityState>((set) => ({
  density: typeof window === "undefined" ? "comfortable" : readStoredDensity(),
  setDensity: (density) => {
    const value = applyDensity(density);
    writeStoredDensity(value);
    set({ density: value });
  },
}));
