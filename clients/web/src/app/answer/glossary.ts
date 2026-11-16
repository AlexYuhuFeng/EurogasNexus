/**
 * Glossary answers: a query that names a glossary term (English or Chinese question forms,
 * acronyms, aliases, any case) shows the term's short definition, from the product's glossary
 * (`GET /api/glossary`, the terms the palette already loads). Enter opens the entry.
 */

import { normalizeTyped } from "./numbers.ts";

export interface GlossaryEntry {
  term: string;
  aliases?: readonly string[];
  category?: string;
  definition_en?: string;
  definition_zh_cn?: string;
  definition?: string;
}

export interface GlossaryAnswer {
  term: string;
  category: string | null;
  /** The first sentence of the definition, in the reader's language. */
  definition: string;
}

const EN_QUESTION = [
  /^(?:what|who)(?:\s+is|\s+are|'s|'re)\s+(?:an?\s+|the\s+)?(.+?)$/,
  /^(?:define|definition\s+of|meaning\s+of|explain\s+the\s+term)\s+(.+?)$/,
  /^what\s+does\s+(.+?)\s+(?:mean|stand\s+for)$/,
  /^(.+?)\s+(?:meaning|definition)$/,
];
const ZH_QUESTION = [
  /^(?:什么是|何为|什麼是)\s*(.+?)$/,
  /^(.+?)\s*(?:是什么意思|是什么|是什麼|的定义|的意思|指什么|什么意思)$/,
];

/** The term a definition question asks about (`what is TTF`, `TTF 是什么`), or null. */
export function definitionSubject(raw: string): string | null {
  const text = normalizeTyped(raw).trim().replace(/[?？。.!！]+$/, "").trim();
  for (const pattern of [...EN_QUESTION, ...ZH_QUESTION]) {
    const match = pattern.exec(text.toLowerCase());
    if (match) {
      // Keep the typed case of the subject (it is matched case-insensitively anyway).
      const start = text.toLowerCase().indexOf(match[1]);
      return text.slice(start, start + match[1].length).trim();
    }
  }
  return null;
}

function key(text: string): string {
  return normalizeTyped(text).trim().toLowerCase().replace(/[\s\-_.]+/g, " ");
}

/** The glossary entry `subject` names exactly (term or alias, any case), or null. */
export function findTerm(subject: string, terms: readonly GlossaryEntry[]): GlossaryEntry | null {
  const wanted = key(subject);
  if (!wanted) return null;
  return (
    terms.find((entry) => key(entry.term) === wanted) ??
    terms.find((entry) => (entry.aliases ?? []).some((alias) => key(alias) === wanted)) ??
    null
  );
}

/** The first sentence of a definition, bounded so it fits one line of the answer row. */
export function shortDefinition(text: string, maxChars = 180): string {
  const clean = text.trim().replace(/\s+/g, " ");
  const end = clean.search(/(?<=[.!?])\s|(?<=[。！？])/);
  const sentence = end > 0 ? clean.slice(0, end).trim() : clean;
  return sentence.length <= maxChars ? sentence : `${sentence.slice(0, maxChars - 1).trimEnd()}…`;
}

export function glossaryAnswer(entry: GlossaryEntry, zh: boolean): GlossaryAnswer {
  const definition = (zh ? entry.definition_zh_cn : entry.definition_en) || entry.definition || entry.definition_en || "";
  return { term: entry.term, category: entry.category ?? null, definition: shortDefinition(definition) };
}
