/**
 * A country or region in the reader's language. The fundamentals reads name places in English
 * ("Germany", "EU total"); the code beside the name is enough to say it in any language: a
 * region through `place.region.<code>`, a country through the browser's own region names.
 */
import i18n from "i18next";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const cache = new Map<string, Intl.DisplayNames | null>();

function regionNames(language: string): Intl.DisplayNames | null {
  if (!cache.has(language)) {
    try {
      cache.set(language, new Intl.DisplayNames([language], { type: "region" }));
    } catch {
      cache.set(language, null);
    }
  }
  return cache.get(language) ?? null;
}

export function placeName(place: { code?: string | null; name?: string | null } | null | undefined, t: Translate, language = i18n.language ?? "en"): string {
  const code = String(place?.code ?? "").trim();
  const name = String(place?.name ?? code);
  if (!code) return name;
  const key = `place.region.${code.toLowerCase()}`;
  const region = t(key);
  if (region !== key) return region;
  if (/^[A-Z]{2}$/.test(code) && !/^en/i.test(language)) {
    const said = regionNames(language)?.of(code);
    if (said && said !== code) return said;
  }
  return name;
}
