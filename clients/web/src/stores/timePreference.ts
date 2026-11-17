/**
 * The reader's "Times shown in" choice (Account → Preferences): their device's zone by default,
 * UTC, or the gas market's time. Kept on this device and, where the server stores preferences,
 * with the user (app/preferences/remotePreferences.ts). Presentation only: every instant is still
 * stored and sent in UTC.
 */
import { create } from "zustand";
import { isTimeZonePreference, type TimeZonePreference } from "../app/time/timeFormat.ts";

export const TIME_ZONE_STORAGE_KEY = "eurogas.time_zone.v1";

function readStored(): TimeZonePreference {
  try {
    const stored = window.localStorage.getItem(TIME_ZONE_STORAGE_KEY);
    return isTimeZonePreference(stored) ? stored : "device";
  } catch {
    return "device";
  }
}

interface TimePreferenceState {
  preference: TimeZonePreference;
  setPreference: (preference: TimeZonePreference) => void;
}

export const useTimePreferenceStore = create<TimePreferenceState>((set) => ({
  preference: typeof window === "undefined" ? "device" : readStored(),
  setPreference: (preference) => {
    try {
      window.localStorage.setItem(TIME_ZONE_STORAGE_KEY, preference);
    } catch {
      // Private window: the choice holds for this session.
    }
    set({ preference });
  },
}));
