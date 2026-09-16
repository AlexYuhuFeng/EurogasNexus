import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  EVIDENCE_TIME_BASIS,
  formatUtcTimestamp,
} from "../src/app/model/evidencePresentation.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("governed evidence timestamps are explicit UTC and fail closed on invalid values", () => {
  assert.equal(EVIDENCE_TIME_BASIS, "UTC");
  assert.equal(
    formatUtcTimestamp("2026-09-16T06:30:45+00:00"),
    "2026-09-16 06:30:45 UTC",
  );
  assert.equal(
    formatUtcTimestamp("2026-09-16T08:30:45+02:00"),
    "2026-09-16 06:30:45 UTC",
  );
  assert.equal(formatUtcTimestamp(null), "n/a");
  assert.equal(formatUtcTimestamp("not-a-time"), "n/a");
});

test("evidence-heavy workspaces use the shared block and explicit time basis", () => {
  const sourceController = readWebSource("app/hooks/useSourceCenterController.ts");
  const sources = readWebSource("components/SourceCenter.tsx");
  const capacity = readWebSource("components/CapacityWorkspace.tsx");
  const strategy = readWebSource("components/StrategyShadowRunTerminal.tsx");
  const review = readWebSource("components/ReviewWorkspace.tsx");
  const glossary = readWebSource("components/GlossaryWiki.tsx");

  assert.match(sourceController, /formatUtcTimestamp\(value\)/);
  assert.match(sources, /<EvidenceBlock/);
  assert.match(capacity, /<EvidenceBlock/);
  assert.match(capacity, /selected\.sourceReference \?\? t\("data\.unavailable"\)/);
  assert.doesNotMatch(capacity, /selected\.sourceReference \?\? "ENTSOG"/);
  assert.match(strategy, /<EvidenceBlock/);
  assert.match(strategy, /formatUtcTimestamp\(value\)/);
  assert.match(review, /<EvidenceBlock/);
  assert.match(review, /formatUtcTimestamp\(value, value\)/);
  assert.match(glossary, /t\("evidence\.time_basis"\)/);
  assert.match(glossary, /t\("evidence\.utc"\)/);
});

test("evidence labels remain paired across English and Mandarin", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  for (const key of [
    "data.stale",
    "evidence.lineage",
    "evidence.observed",
    "evidence.freshness",
    "evidence.review_boundary",
    "evidence.research_boundary",
    "evidence.time_basis",
    "evidence.utc",
  ]) {
    assert.ok(en[key], `en missing ${key}`);
    assert.ok(zh[key], `zh missing ${key}`);
  }
});
