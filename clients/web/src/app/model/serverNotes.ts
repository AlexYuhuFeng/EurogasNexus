/**
 * Server warnings in the reader's language (owner, 2026-11-26: no raw server text, no internal
 * identifiers on screen). A read such as `GET /api/desk/today` returns its warnings as English
 * diagnostic lines ("book: not available (OperationalError)"). They are evidence for support,
 * not copy: the screen says what is missing in words, the raw line stays in the `title`.
 *
 * Known shapes are translated from their parts; a method note (how a contract is shown, not that
 * something failed) is not a warning and is left out; anything else reads as a generic line so
 * a key or an id never reaches the screen.
 */
import { enumWordsIn } from "./enumLabels.ts";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** How a contract is shown on the ladder: normal method, not a failure (server `is_method_note`). */
const METHOD_NOTE_ENDINGS = [
  "; volume only on the ladder",
  ": an FOB cargo is not on a European hub until it is sold or discharged",
];

/** "book: not available (OperationalError)", "prices: not resolved (TimeoutError)". */
const UNAVAILABLE = /^([a-z][a-z -]*?)(?: findings)?: not (?:available|resolved)(?: \(([A-Za-z]+)\))?$/;

/** Internal identifiers: `contract demo-x:`, `upstream_resource_contract:demo-1`, dotted keys. */
const IDENTIFIER = /\b(?:[a-z]+_[a-z_]+:[\w.-]+|demo-[\w-]+|[a-z]+\.[a-z_]+)\b/;

export function isMethodNote(text: string): boolean {
  return METHOD_NOTE_ENDINGS.some((ending) => text.endsWith(ending));
}

/** The warnings worth showing (method notes left out), once each. */
export function shownServerNotes(warnings: readonly (string | null | undefined)[] | null | undefined): string[] {
  return [...new Set((warnings ?? []).filter((text): text is string => Boolean(text) && !isMethodNote(text as string)))];
}

/** One warning in words: "Book could not be read." / "账簿未能读取。" */
export function serverNoteText(text: string, t: Translate, language: string): string {
  const unavailable = UNAVAILABLE.exec(text.trim());
  if (unavailable) {
    const section = unavailable[1].trim().replace(/[\s-]+/g, "_");
    return t("server_note.unavailable", {
      section: t(`server_note.section.${section}`, { defaultValue: unavailable[1].trim() }),
    });
  }
  // Chinese never shows the English diagnostic; English shows it only without identifiers.
  if (language.toLowerCase().startsWith("zh") || IDENTIFIER.test(text)) return t("server_note.other");
  return enumWordsIn(text);
}
