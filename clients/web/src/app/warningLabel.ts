/** Human-readable display for backend warning codes.
 *
 * Backend warnings use stable `CODE:detail` strings so clients can translate
 * them without parsing arbitrary prose. Unknown codes remain visible and are
 * never silently hidden.
 */

import { enumWordsIn, humanizeEnum } from "./model/enumLabels.ts";
import { serverSentence } from "./model/serverSentences.ts";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export function warningLabel(warning: string, t: Translate): string {
  const separator = warning.indexOf(":");
  const code = (separator >= 0 ? warning.slice(0, separator) : warning).trim().toLowerCase();
  const detail = separator >= 0 ? warning.slice(separator + 1).trim() : "";
  // `warning.<code>` first, then the shared enum words, then the code in words (never the raw
  // key): tests/serverWarningCodes.test.ts keeps every server code in both locale files.
  const key = `warning.${code}`;
  const translated = t(key);
  const enumKey = `enum.${code}`;
  const enumWords = translated === key ? t(enumKey) : enumKey;
  const label = translated !== key ? translated : enumWords !== enumKey ? enumWords : humanizeEnum(code);
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

/** A server warning that opens with a stable code (`ROUTE_COST_MISSING:R-2`). */
const LEADING_CODE = /^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+(?=:|$)/;

/**
 * Any server warning as a reader sees it: a coded warning through `warning.<code>` (both
 * languages), a sentence as sent with any enum code inside it said in words. The one function a
 * list of server warnings renders through, so a new code never reaches the screen raw.
 */
/**
 * A server notice (`domain/notices.py`): the warning as data, `{code, params, text}`. The
 * client says it by code; `text` is the English fallback.
 */
export interface ServerNotice {
  readonly code: string;
  readonly params?: Readonly<Record<string, string>>;
  readonly text: string;
}

function isNotice(value: unknown): value is ServerNotice {
  return typeof value === "object" && value !== null && typeof (value as ServerNotice).code === "string";
}

/** A notice in words: `server.sentence.<code>` or `warning.<code>` with its params, else the
 * English text through the sentence path (an older server's line). */
function noticeText(notice: ServerNotice, t: Translate, names?: ReadonlyMap<string, string>): string {
  const params: Record<string, string> = {};
  for (const [name, value] of Object.entries(notice.params ?? {})) {
    params[name] = name === "contract" || name === "cargo" ? names?.get(value) ?? value : value;
  }
  if (notice.code !== "text") {
    for (const key of [`server.sentence.${notice.code}`, `warning.${notice.code.toLowerCase()}`]) {
      const said = t(key, params);
      if (said !== key) return params.detail && key.startsWith("warning.") ? `${said}: ${params.detail}` : said;
    }
  }
  return serverWarningText(notice.text, t, names);
}

/**
 * Any server warning as a reader sees it: a notice by its code, a coded line through
 * `warning.<code>` (both languages), a sentence as sent with any enum code inside it said in
 * words. The one function a list of server warnings renders through, so a new code never
 * reaches the screen raw.
 */
export function serverWarningText(warning: string | ServerNotice, t: Translate, names?: ReadonlyMap<string, string>): string {
  if (isNotice(warning)) return noticeText(warning, t, names);
  const text = String(warning ?? "").trim();
  if (LEADING_CODE.test(text)) return warningLabel(text, t);
  return serverSentence(text, t, names) ?? enumWordsIn(text);
}

/** What a response warns about: its notices when the server sent them, else its English lines. */
export function serverNotices(
  source: { notices?: readonly ServerNotice[] | null; warnings?: readonly string[] | null } | null | undefined,
): Array<string | ServerNotice> {
  if (source?.notices && source.notices.length > 0) return [...source.notices];
  return [...(source?.warnings ?? [])];
}

/** A stable React key and title for a warning or a notice. */
export function warningKey(warning: string | ServerNotice): string {
  return isNotice(warning) ? warning.text || warning.code : warning;
}
