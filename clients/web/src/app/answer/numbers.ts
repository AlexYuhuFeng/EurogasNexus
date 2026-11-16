/**
 * How the answer bar reads and writes numbers.
 *
 * Number policy (stated once, tested in `tests/answerParser.test.ts`):
 * - The decimal mark is the point: `42.5`, `.5`.
 * - A comma is a thousands separator only in well-formed groups of three: `1,000`,
 *   `12,345.6`. Anything else with a comma (`3,5`, `1,00`) is not read at all, so a decimal
 *   comma never turns into a silently wrong figure: the bar shows no answer instead.
 * - Full-width digits and operators typed with a Chinese input method (`１２．５`, `（`, `＋`, `％`)
 *   are read as their ASCII forms, as are `×`, `÷` and the minus sign `−`.
 * - Answers are written with a point and comma grouping (`1,234.5`) in both languages, the way
 *   the desk's screens write them.
 */

/** Full-width forms and typographic operators as ASCII. */
export function normalizeTyped(raw: string): string {
  let out = "";
  for (const char of raw) {
    const code = char.codePointAt(0) ?? 0;
    if (code >= 0xff01 && code <= 0xff5e) out += String.fromCodePoint(code - 0xfee0);
    else if (char === "　") out += " ";
    else if (char === "×" || char === "✕") out += "*";
    else if (char === "÷") out += "/";
    else if (char === "−" || char === "–") out += "-";
    else out += char;
  }
  return out;
}

/** A number at the start of `text` under the policy above, with its length; null when none. */
export function readNumber(text: string): { value: number; length: number } | null {
  const match = /^(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)/.exec(text);
  if (!match) return null;
  // "3,5" or "1,00": a comma that is not a thousands group refuses the whole number.
  if (/^[,]\d/.test(text.slice(match[0].length))) return null;
  const value = Number(match[0].replace(/,/g, ""));
  return Number.isFinite(value) ? { value, length: match[0].length } : null;
}

/** The whole of `text` as one number, or null. */
export function parseNumber(text: string): number | null {
  const trimmed = normalizeTyped(text).trim();
  const found = readNumber(trimmed);
  return found && found.length === trimmed.length ? found.value : null;
}

/**
 * A computed value as the desk writes it: comma grouping, no float noise, at most `maxDecimals`
 * decimals (fewer when they are zeros). `-0` is `0`; the minus sign is the true minus.
 */
export function formatAnswerNumber(value: number, maxDecimals = 6): string {
  if (!Number.isFinite(value)) return "–";
  const magnitude = Math.abs(value);
  // Large figures need fewer decimals; tiny ones keep significant digits.
  const decimals = magnitude >= 1e6 ? Math.min(maxDecimals, 2) : magnitude >= 1000 ? Math.min(maxDecimals, 3) : maxDecimals;
  const rounded = Number(value.toPrecision(12));
  const text = Math.abs(rounded).toLocaleString("en-GB", { maximumFractionDigits: decimals, minimumFractionDigits: 0 });
  if (text === "0" || /^0(\.0+)?$/.test(text)) {
    if (magnitude === 0 || magnitude >= 10 ** -decimals) return "0";
    // Below the shown precision but not zero: write it in significant digits instead.
    return `${value < 0 ? "−" : ""}${Math.abs(rounded).toPrecision(3)}`;
  }
  return `${rounded < 0 ? "−" : ""}${text}`;
}

/** The value as a plain number for the clipboard: no grouping, a point, an ASCII minus. */
export function clipboardNumber(value: number, maxDecimals = 6): string {
  if (!Number.isFinite(value)) return "";
  const rounded = Number(value.toPrecision(12));
  return String(Number(rounded.toFixed(maxDecimals)));
}
