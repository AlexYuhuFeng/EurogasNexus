/**
 * The instant formatter for code that is not a hook (a column's `format`, a model building a label):
 * the same rules as `useInstantFormatter`, reading the reader's zone and the app's language at the
 * moment it is called. The shell re-renders when either changes (AppShell subscribes to both).
 */
import i18n from "i18next";
import { useTimePreferenceStore } from "../../stores/timePreference.ts";
import { formatInstant, type FormattedInstant, type InstantFormatOptions } from "./timeFormat.ts";

type DisplayOptions = Omit<InstantFormatOptions, "language" | "preference">;

export function displayInstant(
  value: string | number | Date | null | undefined,
  options: DisplayOptions = {},
): FormattedInstant | null {
  return formatInstant(value, {
    ...options,
    language: i18n.language || "en",
    preference: useTimePreferenceStore.getState().preference,
  });
}

/** The short text ("00:57 CET", "16 Nov 22:57 UTC"), or `fallback` when there is no instant. */
export function displayTime(
  value: string | number | Date | null | undefined,
  fallback = "–",
  options: DisplayOptions = {},
): string {
  return displayInstant(value, options)?.text ?? fallback;
}
