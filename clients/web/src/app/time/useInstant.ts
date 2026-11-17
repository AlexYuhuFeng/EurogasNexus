import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useTimePreferenceStore } from "@/stores/timePreference";
import { formatInstant, type FormattedInstant, type InstantFormatOptions } from "./timeFormat";

export type InstantFormatter = (
  value: string | number | Date | null | undefined,
  options?: Omit<InstantFormatOptions, "language" | "preference">,
) => FormattedInstant | null;

/** Format instants in the reader's zone and the app's language (re-renders when either changes). */
export function useInstantFormatter(): InstantFormatter {
  const { i18n } = useTranslation();
  const preference = useTimePreferenceStore((state) => state.preference);
  const language = i18n.language;
  return useCallback(
    (value, options = {}) => formatInstant(value, { ...options, language, preference }),
    [language, preference],
  );
}
