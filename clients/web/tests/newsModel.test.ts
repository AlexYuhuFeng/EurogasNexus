import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { NewsNoteDTO } from "../src/api/client.ts";
import {
  NEWS_EVENT_TYPES,
  isAiNote,
  newsKey,
  noteSentences,
  noteStatusKey,
  safeHref,
  touchesBook,
} from "../src/app/model/newsModel.ts";
import en from "../src/i18n/en.json" with { type: "json" };
import zh from "../src/i18n/zh.json" with { type: "json" };

const read = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

function note(overrides: Partial<NewsNoteDTO> = {}): NewsNoteDTO {
  return {
    basis: "rule",
    label: null,
    sentences: [
      { text: "Gassco reports an outage at Nyhamna.", cites: ["N1"] },
      { text: "Book uk-nbp: contract delivers 12,000 MWh/d at NBP.", cites: ["N1", "F1"] },
    ],
    rule_sentences: [],
    citations: [
      { id: "N1", kind: "item", text: "Gassco, 20 Nov 2026: outage", url: "https://www.gov.uk/government/news/x" },
      { id: "F1", kind: "contract", text: "Book uk-nbp: contract", url: undefined },
    ],
    ai: { status: "off", check: null, flags: [], prompt_version: null },
    advisory: "Decision support",
    ...overrides,
  };
}

test("each sentence shows its citations, linking only to https pages", () => {
  const sentences = noteSentences(note());
  assert.deepEqual(sentences[1].citations.map((c) => [c.id, c.href]), [
    ["N1", "https://www.gov.uk/government/news/x"],
    ["F1", null],
  ]);
  assert.equal(sentences[1].citations[1].title, "Book uk-nbp: contract");
  assert.equal(safeHref("javascript:alert(1)"), null);
  assert.equal(safeHref("http://www.gov.uk/x"), null);
  assert.equal(safeHref("https://user:pw@www.gov.uk/x"), null);
  assert.equal(safeHref("not a url"), null);
});

test("only a model note carries the AI label, and the reader is told which note is shown", () => {
  assert.equal(isAiNote(note()), false);
  assert.equal(noteStatusKey(note()), "news.note.status.rule");
  const model = note({ basis: "model", label: "AI-generated", ai: { status: "used", check: null, flags: [], prompt_version: "news-note-2026.11.25" } });
  assert.equal(isAiNote(model), true);
  assert.equal(noteStatusKey(model), "news.note.status.used");
  const refused = note({ ai: { status: "refused", check: "number", flags: [], prompt_version: "v" } });
  assert.equal(isAiNote(refused), false);
  assert.equal(noteStatusKey(refused), "news.note.status.refused");
});

test("filters become query parameters and a stable cache key", () => {
  assert.match(read("api/client.ts"), /if \(filters\.mine\) params\.mine = "true";/);
  assert.equal(newsKey({ type: "outage", hub: "NBP", mine: false, country: "" }), "/news?hub=NBP&type=outage");
  assert.equal(newsKey({}), "/news");
  assert.equal(touchesBook({ relevance: { score: 2, matches: 1, roles: ["trader"], reasons: [] } }), true);
});

test("every string the panel shows exists in English and Chinese", () => {
  const source = read("components/NewsPanel.tsx") + read("app/model/newsModel.ts");
  const keys = new Set<string>();
  for (const match of source.matchAll(/["`](news\.[a-z_.]+)["`]/g)) keys.add(match[1]);
  for (const kind of NEWS_EVENT_TYPES) keys.add(`news.type.${kind}`);
  for (const role of ["trader", "lng", "scheduler"]) keys.add(`news.role.${role}`);
  assert.ok(keys.size > 30);
  for (const key of keys) {
    assert.ok(key in en, `en: ${key}`);
    assert.ok(key in zh, `zh: ${key}`);
  }
});

test("the panel uses shared ui components and its styles sit in the design-system layer", () => {
  const panel = read("components/NewsPanel.tsx");
  assert.match(panel, /from "@\/components\/ui"/);
  assert.doesNotMatch(panel, /dangerouslySetInnerHTML/);
  assert.match(panel, /rel="noopener noreferrer"/);
  const css = read("components/news-panel.css");
  assert.match(css, /^\/\*[^]*?\*\/\s*@layer ds-components \{/);
  assert.doesNotMatch(css, /#[0-9a-fA-F]{3,6}\b/);
  assert.match(read("styles/design-system.css"), /news-panel\.css/);
  assert.match(read("components/MarketCockpit.tsx"), /<NewsPanel /);
});
