/**
 * Enums never reach the screen as code (docs/product/UX_REFERENCE.md, rule 21). A state, a kind or
 * a reason the server sends as `SUCCEEDED_WITH_WARNINGS` reads "Succeeded with warnings" (or its
 * translation, `enum.<value>` in the locale files); the code itself stays in the `title` for
 * support. A source system's identifier (`ICE_ENDEX`) reads as the desk names it ("ICE Endex").
 */

/** An identifier written as an enum: two or more upper-case words joined by underscores. */
export const ENUM_TOKEN = /^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$/;

const ACRONYMS = new Set(["API", "CET", "DA", "ECB", "EEX", "ENTSOG", "ETRM", "FX", "GIE", "ICE", "LNG", "NBP", "OCM", "OIDC", "PDF", "PEG", "SSE", "SSO", "TSO", "TTF", "UMM", "UTC", "WD", "ZTP"]);

/** "SUCCEEDED_WITH_WARNINGS" -> "Succeeded with warnings"; acronyms stay upper case. */
export function humanizeEnum(value: string): string {
  const words = value.toLowerCase().split(/[_\s]+/).filter(Boolean);
  return words
    .map((word, index) => {
      const upper = word.toUpperCase();
      if (ACRONYMS.has(upper)) return upper;
      return index === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word;
    })
    .join(" ");
}

/** Whether a piece of text is a bare enum code. */
export function isEnumToken(value: unknown): value is string {
  return typeof value === "string" && ENUM_TOKEN.test(value.trim());
}

/**
 * A status word sent in capitals ("AVAILABLE", "UNKNOWN"): a code too, unless it is an acronym
 * the desk writes that way (TTF, NBP, LNG).
 */
export function isStatusCode(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const text = value.trim();
  return isEnumToken(text) || (/^[A-Z]{4,}$/.test(text) && !ACRONYMS.has(text));
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** The words for an enum value: the locale's `enum.<value>`, else the humanized code. */
export function enumLabel(value: string | null | undefined, t?: Translate): string {
  if (!value) return "";
  const fallback = humanizeEnum(value);
  if (!t) return fallback;
  return t(`enum.${value.toLowerCase()}`, { defaultValue: fallback });
}

const SOURCE_NAMES: Record<string, string> = {
  ICE_ENDEX: "ICE Endex",
  ICE_OCM: "ICE OCM",
  ECB_ESTR: "ECB €STR",
  ECMWF_OPEN_DATA: "ECMWF open data",
  ENTSOG_UMM: "ENTSOG UMM",
  NATIONAL_GAS: "National Gas",
  NATIONAL_GAS_DEMAND: "National Gas demand",
};

/** A source system as the desk names it; an identifier without a known name is humanized. */
export function sourceSystemLabel(id: string): string {
  return SOURCE_NAMES[id] ?? (isEnumToken(id) ? humanizeEnum(id) : id);
}

/**
 * Every enum code inside a text said in words ("route R-2: TARIFF_MISSING" → "route R-2: tariff
 * missing"), so a server sentence that quotes a code never shows it bare (UX_REFERENCE rule 21).
 */
export function enumWordsIn(text: string | null | undefined): string {
  return String(text ?? "").replace(/\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/g, (code, offset: number) => {
    const words = humanizeEnum(code);
    // Capitalised only where it opens the text; mid-sentence it reads in lower case.
    const acronymFirst = /^[A-Z0-9]{2,}\b/.test(words);
    return offset === 0 || acronymFirst ? words : words.charAt(0).toLowerCase() + words.slice(1);
  });
}
