/**
 * Language preference: the one place that knows the storage key, the supported
 * set, and what a stored value is allowed to be. Theme already persists this way
 * (`stores/theme.ts`); language did not, so a choice made in settings died on
 * every reload and the workspace silently returned to English.
 *
 * Kept free of any i18next import so it stays a pure module the test runner can
 * exercise with a fake storage. `i18n/index.ts` applies it at init and
 * `changeAppLanguage` writes it whenever a surface switches language.
 */

export const LANGUAGE_STORAGE_KEY = "eurogas.language.v1";

export const SUPPORTED_LANGUAGES = ["en", "zh-CN"] as const;

export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

export const DEFAULT_LANGUAGE: SupportedLanguage = "en";

export interface PreferenceStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export function isSupportedLanguage(value: unknown): value is SupportedLanguage {
  return typeof value === "string" && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

/**
 * Coerce anything - a stored value, an i18next language tag such as `zh` or
 * `zh-Hans`, or a hostile string - to a supported language. English is the
 * fallback because it is the language the interface ships complete in.
 */
export function normalizeLanguage(value: unknown): SupportedLanguage {
  if (isSupportedLanguage(value)) return value;
  if (typeof value === "string") {
    const lower = value.trim().toLowerCase();
    if (lower === "zh" || lower.startsWith("zh-")) return "zh-CN";
    if (lower.startsWith("en")) return "en";
  }
  return DEFAULT_LANGUAGE;
}

/** Read the persisted language, falling back to the default when storage is unusable. */
export function readStoredLanguage(storage?: PreferenceStorage | null): SupportedLanguage {
  const store = storage ?? safeStorage();
  if (!store) return DEFAULT_LANGUAGE;
  try {
    return normalizeLanguage(store.getItem(LANGUAGE_STORAGE_KEY));
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

/** Persist the language. Storage failures are ignored: the session keeps the choice. */
export function storeLanguage(language: unknown, storage?: PreferenceStorage | null): SupportedLanguage {
  const normalized = normalizeLanguage(language);
  const store = storage ?? safeStorage();
  if (store) {
    try {
      store.setItem(LANGUAGE_STORAGE_KEY, normalized);
    } catch {
      // Private mode or a full quota must not break the language switch.
    }
  }
  return normalized;
}

function safeStorage(): PreferenceStorage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}
