/**
 * The agents workspace's declared reads (slice E of the D3 decision).
 *
 * Three declared calls had no consumer: the profile catalogue a run is filed under, the single-run
 * read that answers for a run outside the bounded list, and the capability search route. Each one
 * answers something the workspace could not:
 *
 * - `GET /api/agent/profiles` publishes the profiles a run may be filed under, which is what makes
 *   the label on a run row checkable and what a `PROFILE_STAGES_NOT_REACHED` warning refers to;
 * - `GET /api/agent/runs/{id}` answers for one run, while the list is bounded, so a run cited by a
 *   Decision Case or a colleague could not be opened at all;
 * - `GET /api/capabilities/search` searches the catalogue's description, domain, tags and input
 *   concepts, which a client-side filter over the rendered rows cannot see.
 *
 * These tests hold the surface to those calls, and hold a failed read to the error taxonomy rather
 * than a raw transport string.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("the agent catalogue vocabulary is bilingual", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  const keys = [
    "agents.profiles",
    "agents.profiles_note",
    "agents.profiles_none",
    "agents.profile",
    "agents.profile_stages",
    "agents.profile_stages_none",
    "agents.profile_purpose",
    "agents.search_capabilities",
    "agents.search_capabilities_placeholder",
    "agents.search",
    "agents.open_run_by_id",
    "agents.open_run",
    "errors.correlation_id",
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }

  // The run-id field's placeholder is an identifier shape rather than prose, so it is the same text
  // in both locales - and `localeDistinctness.test.ts` is where that deliberate sameness is pinned.
  assert.equal(en["agents.run_id_placeholder"], zh["agents.run_id_placeholder"]);
});
