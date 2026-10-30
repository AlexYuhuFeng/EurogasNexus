import { api, type PreferenceKey, type PreferencesDTO } from "@/api/client";
import { changeAppLanguage } from "@/i18n";
import { LANGUAGE_STORAGE_KEY, normalizeLanguage } from "@/i18n/language";
import { useThemeStore, type ThemeMode } from "@/stores/theme";
import {
  normalizeMarketViewPreference,
  readMarketViewPreference,
  writeMarketViewPreference,
} from "@/app/context/viewPreference";
import { resolveSignInPreferences } from "./preferenceResolution";

/**
 * Personal preferences live on the server per principal (`/api/me/preferences`), so a
 * trader's language, theme and landing views follow them from the web client to the
 * desktop client and between offices. The browser keeps a local copy so the interface
 * starts in the right state before the server answers and keeps working offline; the
 * server copy wins once it arrives.
 *
 * Organisation defaults (set by a platform administrator) apply wherever the user has
 * not chosen. None of this changes what a person may see.
 */

export const BOARD_LAYOUT_STORAGE_KEY = "eurogas.market.board_view";
export const PREFERENCES_APPLIED_EVENT = "eurogas:preferences-applied";

export function readBoardLayout(): "board" | "ladder" {
  try {
    return window.localStorage.getItem(BOARD_LAYOUT_STORAGE_KEY) === "ladder" ? "ladder" : "board";
  } catch {
    return "board";
  }
}

function writeBoardLayout(layout: string): void {
  try {
    window.localStorage.setItem(BOARD_LAYOUT_STORAGE_KEY, layout === "ladder" ? "ladder" : "board");
  } catch {
    // Storage may be unavailable (private window); the server copy still holds it.
  }
}

/** Apply the effective preferences to the local stores the interface reads. */
export async function applyEffectivePreferences(
  effective: PreferencesDTO["effective"],
  principalId: string | null,
): Promise<void> {
  await changeAppLanguage(effective.language);
  useThemeStore.getState().setMode(effective.theme as ThemeMode);
  writeMarketViewPreference(principalId, normalizeMarketViewPreference(effective.market_view));
  writeBoardLayout(effective.market_board_layout);
  window.dispatchEvent(new Event(PREFERENCES_APPLIED_EVENT));
}

/** Keys the user chose explicitly on this device (sign-in language picker, theme menu, …). */
function locallyChosen(principalId: string): Partial<Record<PreferenceKey, string>> {
  const chosen: Partial<Record<PreferenceKey, string>> = {};
  try {
    const language = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (language) chosen.language = normalizeLanguage(language);
    const theme = window.localStorage.getItem("theme");
    if (theme === "system" || theme === "light" || theme === "dark") chosen.theme = theme;
    const layout = window.localStorage.getItem(BOARD_LAYOUT_STORAGE_KEY);
    if (layout === "board" || layout === "ladder") chosen.market_board_layout = layout;
  } catch {
    // Storage unavailable: nothing was chosen on this device.
  }
  const view = readMarketViewPreference(principalId);
  if (view) chosen.market_view = view;
  return chosen;
}

/** Load and apply once per signed-in principal; a failed read keeps the local copy. */
export async function loadRemotePreferences(principalId: string): Promise<PreferencesDTO | null> {
  try {
    const response = await api.myPreferences();
    const { effective, seed } = resolveSignInPreferences(response.data, locallyChosen(principalId));
    await applyEffectivePreferences(effective, principalId);
    if (Object.keys(seed).length > 0) void api.saveMyPreferences(seed).catch(() => undefined);
    return response.data;
  } catch {
    return null;
  }
}

/**
 * Record a personal choice on the server. The local change has already been applied by
 * the caller; a failed save leaves it local for this browser, which is the old behaviour.
 */
export function saveRemotePreference(key: PreferenceKey, value: string | null): void {
  void api.saveMyPreferences({ [key]: value }).catch(() => undefined);
}

export function writeLocalBoardLayout(layout: "board" | "ladder"): void {
  writeBoardLayout(layout);
  saveRemotePreference("market_board_layout", layout);
}
