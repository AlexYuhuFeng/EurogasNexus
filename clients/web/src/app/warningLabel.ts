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
 * A server note as the server declares it (`domain/ontology/notes.py`): a stable code, its
 * parameters and the English text. A parameter naming a record comes with its name (`ref_name`).
 */
export interface ServerNote {
  code: string;
  params?: Record<string, unknown>;
  text?: string;
}

function isServerNote(value: unknown): value is ServerNote {
  return typeof value === "object" && value !== null && typeof (value as ServerNote).code === "string";
}

/** A declared note in words: `warning.<code>` with its parameters, the server's text otherwise. */
export function serverNoteText(note: ServerNote, t: Translate, names?: ReadonlyMap<string, string>): string {
  const params: Record<string, unknown> = { ...(note.params ?? {}) };
  // A record is said by its name: the one the server sent, else one this page holds, else its id.
  if (params.ref !== undefined) params.ref = params.ref_name ?? names?.get(String(params.ref)) ?? params.ref;
  // A parameter that is a word the desk says in its language ("book" in "book: not
  // available") is translated through warning.param.<name>.<value>; names and figures stay.
  for (const [name, value] of Object.entries(params)) {
    if (typeof value !== "string" || !value) continue;
    const paramKey = `warning.param.${name}.${value.trim().toLowerCase().replace(/[\s-]+/g, "_")}`;
    const word = t(paramKey);
    if (word !== paramKey) params[name] = word;
  }
  const key = `warning.${note.code.toLowerCase()}`;
  const said = t(key, params);
  if (said !== key) return said;
  return note.text ? serverWarningText(note.text, t, names) : humanizeEnum(note.code);
}

export function serverWarningText(warning: string | ServerNote, t: Translate, names?: ReadonlyMap<string, string>): string {
  if (isServerNote(warning)) return serverNoteText(warning, t, names);
  const text = String(warning ?? "").trim();
  if (LEADING_CODE.test(text)) return warningLabel(text, t);
  return serverSentence(text, t, names) ?? enumWordsIn(text);
}

/**
 * What a response warns about: its declared notes when the server sent them
 * (`notes`, from `domain/ontology/notes.py`), else its English lines (an older server).
 */
export function serverNotes(
  source: { notes?: readonly ServerNote[] | null; warnings?: readonly string[] | null } | null | undefined,
): Array<string | ServerNote> {
  if (source?.notes && source.notes.length > 0) return [...source.notes];
  return [...(source?.warnings ?? [])];
}

/** A stable React key and title for a warning line or a note. */
export function warningKey(warning: string | ServerNote): string {
  return isServerNote(warning) ? warning.text || warning.code : warning;
}
