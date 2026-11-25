/**
 * NEWS-1: what the news panel shows, as pure functions the node tests read.
 *
 * A note is a list of sentences, each citing evidence lines (`N1` a news item, `F1` one of the
 * platform's figures). The panel shows each citation inline beside its sentence; a citation
 * links out only to an `https` address the server gave for that item (the publisher's page).
 * A model note carries its "AI-generated" label; a rule note carries none.
 */
import type { NewsCitationDTO, NewsFilterInput, NewsItemDTO, NewsNoteDTO } from "@/api/client";

export const NEWS_EVENT_TYPES = ["outage", "sanction", "policy", "weather", "strike", "geopolitical"] as const;
export type NewsEventType = (typeof NEWS_EVENT_TYPES)[number];

export const NEWS_HUBS = ["TTF", "NBP", "THE", "PEG", "ZTP", "PSV", "CEGH", "PVB", "ETF"] as const;

export interface NoteCitation {
  id: string;
  href: string | null;
  title: string;
}

export interface NoteSentence {
  text: string;
  citations: NoteCitation[];
}

/** The address a citation may link to: the publisher's own `https` page, nothing else. */
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && !parsed.username && !parsed.password ? parsed.toString() : null;
  } catch {
    return null;
  }
}

/** Each sentence of the note with its citations resolved to their lines and links. */
export function noteSentences(note: NewsNoteDTO | null | undefined): NoteSentence[] {
  if (!note) return [];
  const byId = new Map<string, NewsCitationDTO>(note.citations.map((citation) => [citation.id, citation]));
  return note.sentences.map((sentence) => ({
    text: sentence.text,
    citations: sentence.cites.map((id) => {
      const citation = byId.get(id);
      return { id, href: safeHref(citation?.url), title: citation?.text ?? id };
    }),
  }));
}

/** Whether the note shown is the model's (and so must show its label). */
export function isAiNote(note: NewsNoteDTO | null | undefined): boolean {
  return Boolean(note && note.basis === "model" && note.label);
}

/** The i18n key of the line under a note that says why the reader sees the rule note. */
export function noteStatusKey(note: NewsNoteDTO | null | undefined): string | null {
  if (!note) return null;
  switch (note.ai.status) {
    case "used":
      return "news.note.status.used";
    case "refused":
      return "news.note.status.refused";
    case "unavailable":
      return "news.note.status.unavailable";
    default:
      return note.ai.prompt_version === null && note.basis === "rule" ? "news.note.status.rule" : null;
  }
}

/** The cache key of a list read: the endpoint and the filters set. */
export function newsKey(filters: NewsFilterInput): string {
  const parts = Object.entries(filters)
    .filter(([, value]) => value !== undefined && value !== "" && value !== false)
    .map(([key, value]) => `${key}=${String(value)}`)
    .sort();
  return `/news${parts.length ? `?${parts.join("&")}` : ""}`;
}

/** Whether an item touches the caller's book. */
export function touchesBook(item: Pick<NewsItemDTO, "relevance">): boolean {
  return item.relevance.score > 0;
}
