/** Human-readable display for backend warning codes.
 *
 * Backend warnings use stable `CODE:detail` strings so clients can translate
 * them without parsing arbitrary prose. Unknown codes remain visible and are
 * never silently hidden.
 */

type Translate = (key: string) => string;

export function warningLabel(warning: string, t: Translate): string {
  const separator = warning.indexOf(":");
  const code = (separator >= 0 ? warning.slice(0, separator) : warning).trim().toLowerCase();
  const detail = separator >= 0 ? warning.slice(separator + 1).trim() : "";
  const key = `warning.${code}`;
  const translated = t(key);
  const label = translated === key ? code.replaceAll("_", " ") : translated;
  // The detail is the code's own tokens ("C-1:EUR->GBP"); written for a reader, not a parser.
  const readable = detail.replaceAll("->", " → ").split(":").map((part) => part.trim()).filter(Boolean).join(" · ");
  return readable ? `${label}: ${readable}` : label;
}

/** The raw code of a warning, for a `title` or `data-` attribute that support can read. */
export function warningCode(warning: string): string {
  const separator = warning.indexOf(":");
  return (separator >= 0 ? warning.slice(0, separator) : warning).trim();
}

export function warningLabels(warnings: Array<string | null | undefined>, t: Translate): string[] {
  return warnings.filter((warning): warning is string => Boolean(warning)).map((warning) => warningLabel(warning, t));
}
