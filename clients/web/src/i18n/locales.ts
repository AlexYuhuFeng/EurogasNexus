/**
 * The interface languages, in one registry. Adding a language is: a translation file next
 * to `en.json`, one entry here, and the same code in the server vocabulary
 * (`domain/settings/preferences.py`). Menus, `<html lang>`, number and date formatting all
 * read this list; nothing else names a language. Missing keys fall back to English.
 */

export interface LocaleDefinition {
  /** BCP 47 tag stored as the preference. */
  readonly code: string;
  /** The language's name in itself, as language pickers show it. */
  readonly nativeName: string;
  /** Short label for compact pickers (sign-in screen). */
  readonly shortLabel: string;
  /** Locale used for `Intl` number and date formatting. */
  readonly intlLocale: string;
  readonly direction: "ltr" | "rtl";
}

export const LOCALES = [
  { code: "en", nativeName: "English", shortLabel: "EN", intlLocale: "en-GB", direction: "ltr" },
  { code: "zh-CN", nativeName: "简体中文", shortLabel: "中文", intlLocale: "zh-CN", direction: "ltr" },
] as const satisfies readonly LocaleDefinition[];

export type LocaleCode = (typeof LOCALES)[number]["code"];

export function localeFor(code: string): LocaleDefinition {
  const lower = code.trim().toLowerCase();
  return (
    LOCALES.find((locale) => locale.code.toLowerCase() === lower) ??
    LOCALES.find((locale) => lower.split("-")[0] === locale.code.toLowerCase().split("-")[0]) ??
    LOCALES[0]
  );
}

/** The `Intl` locale for a language preference ("zh-CN" → "zh-CN", "en" → "en-GB"). */
export function intlLocaleFor(language: string): string {
  return localeFor(language).intlLocale;
}
