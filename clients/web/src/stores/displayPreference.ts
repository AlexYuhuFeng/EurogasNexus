/**
 * The reader's reporting currency and energy unit (Account → Preferences, design basis G2): the
 * secondary value beside a native figure and totals across currencies read in them. Kept on this
 * device and, where the server stores preferences, with the user. Presentation only: a traded
 * price, a contract term or a limit keeps its native unit (app/time/valueFormat.ts).
 */
import { create } from "zustand";
import {
  DEFAULT_DISPLAY_PREFERENCE,
  isEnergyUnit,
  isReportingCurrency,
  type DisplayPreference,
} from "../app/time/valueFormat.ts";

export const DISPLAY_PREFERENCE_STORAGE_KEY = "eurogas.display_units.v1";

function readStored(): DisplayPreference {
  try {
    const stored = JSON.parse(window.localStorage.getItem(DISPLAY_PREFERENCE_STORAGE_KEY) ?? "{}") as Partial<DisplayPreference>;
    return {
      reportingCurrency: isReportingCurrency(stored.reportingCurrency) ? stored.reportingCurrency : DEFAULT_DISPLAY_PREFERENCE.reportingCurrency,
      energyUnit: isEnergyUnit(stored.energyUnit) ? stored.energyUnit : DEFAULT_DISPLAY_PREFERENCE.energyUnit,
    };
  } catch {
    return DEFAULT_DISPLAY_PREFERENCE;
  }
}

interface DisplayPreferenceState extends DisplayPreference {
  setDisplayPreference: (next: Partial<DisplayPreference>) => void;
}

export const useDisplayPreferenceStore = create<DisplayPreferenceState>((set, get) => ({
  ...(typeof window === "undefined" ? DEFAULT_DISPLAY_PREFERENCE : readStored()),
  setDisplayPreference: (next) => {
    const merged: DisplayPreference = {
      reportingCurrency: isReportingCurrency(next.reportingCurrency) ? next.reportingCurrency : get().reportingCurrency,
      energyUnit: isEnergyUnit(next.energyUnit) ? next.energyUnit : get().energyUnit,
    };
    try {
      window.localStorage.setItem(DISPLAY_PREFERENCE_STORAGE_KEY, JSON.stringify(merged));
    } catch {
      // Private window: the choice holds for this session.
    }
    set(merged);
  },
}));
