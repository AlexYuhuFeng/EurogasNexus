import type { PreferenceKey, PreferencesDTO } from "@/api/client";

export const PREFERENCE_KEYS: PreferenceKey[] = ["language", "theme", "market_view", "market_board_layout"];

/**
 * What takes effect after sign-in, per setting: an explicit choice made on this device
 * (the sign-in language picker, the account menu) wins on this device and is saved as the
 * personal value, so a device with no choice of its own starts from it; a device with no
 * choice takes the personal value, else the organisation default. A language the
 * organisation no longer offers is not kept.
 */
export function resolveSignInPreferences(
  server: PreferencesDTO,
  local: Partial<Record<PreferenceKey, string>>,
): { effective: PreferencesDTO["effective"]; seed: Partial<Record<PreferenceKey, string>> } {
  const effective = { ...server.effective };
  const seed: Partial<Record<PreferenceKey, string>> = {};
  for (const key of PREFERENCE_KEYS) {
    const mine = local[key];
    if (!mine) continue;
    if (key === "language" && !server.effective.enabled_languages.includes(mine)) continue;
    effective[key] = mine;
    if (server.personal[key] !== mine) seed[key] = mine;
  }
  return { effective, seed };
}

