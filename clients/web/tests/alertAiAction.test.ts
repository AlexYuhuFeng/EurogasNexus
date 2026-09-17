/**
 * Architecture V2 Wave 7 convergence - the alert surface offers the canonical `ask` action.
 *
 * The alert drawer used to carry its own provider-branded "Ask DeepSeek" button with no
 * gating: a competing magic-AI entry point and, worse, one that could be pressed on an
 * alert with no evidence at all. These tests pin that the surface now runs the declared
 * `ask` action - withheld without an evidence reference, carrying the contract's posture
 * and produces copy, and branded by the provider the backend reports rather than by a
 * vendor name written into the client.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { aiActionContract, aiActionIsAvailable } from "../src/app/experience/aiActions.ts";
import { declaredAiActions } from "../src/app/experience/aiActions.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("the alert question runs the declared ask action, not a button of its own", () => {
  const alertCenter = readWebSource("components/AlertCenter.tsx");

  assert.match(alertCenter, /import \{ aiActionContract, aiActionIsAvailable \} from "@\/app\/experience\/aiActions"/);
  assert.match(alertCenter, /const ALERT_ASK_ACTION = "ask" as const;/);
  assert.match(alertCenter, /const contract = aiActionContract\(ALERT_ASK_ACTION\);/);
  assert.match(alertCenter, /aiActionIsAvailable\(ALERT_ASK_ACTION, \{/);

  // The action's own vocabulary, not a second one.
  assert.match(alertCenter, /\{t\("experience\.ai\.ask"\)\}/);
  assert.match(alertCenter, /t\(`experience\.copilot\.posture\.\$\{contract\.posture\}`\)/);
  assert.match(alertCenter, /t\(`experience\.copilot\.produces\.\$\{contract\.action\}`\)/);
  assert.match(alertCenter, /t\("experience\.copilot\.evidence"\)/);
  assert.match(alertCenter, /t\("experience\.copilot\.withheld_evidence"\)/);

  // The old ad-hoc entry point is gone, including its provider-branded copy and the
  // hardcoded vendor name in the result line.
  assert.equal(alertCenter.includes("Ask DeepSeek"), false);
  assert.equal(alertCenter.includes("询问 DeepSeek"), false);
  assert.equal(alertCenter.includes("DeepSeek ·"), false);
  assert.equal(alertCenter.includes("<strong>DeepSeek</strong>"), false);
  // Provenance comes from the response, so the client names no vendor of its own.
  assert.match(alertCenter, /analysis\.provider_id/);
});

test("an alert without evidence withholds the action instead of guessing", () => {
  const contract = aiActionContract("ask");

  // The contract requires evidence, and the surface applies that requirement rather than
  // assuming it: no reference means no action.
  assert.equal(contract.requiresEvidenceRefs, true);
  assert.equal(
    aiActionIsAvailable("ask", { activeContextComplete: true, evidenceRefCount: 0 }),
    false,
  );
  assert.equal(
    aiActionIsAvailable("ask", { activeContextComplete: true, evidenceRefCount: 1 }),
    true,
  );

  const alertCenter = readWebSource("components/AlertCenter.tsx");
  // The gate is wired to the alert's own source references, and the unavailable state is
  // explained rather than silently disabled.
  assert.match(alertCenter, /const evidenceRefs = alert\.source_refs \?\? \[\];/);
  assert.match(alertCenter, /evidenceRefCount: evidenceRefs\.length,/);
  assert.match(alertCenter, /disabled=\{!askAvailable\}/);
  assert.match(alertCenter, /title=\{askAvailable \? undefined : t\("experience\.copilot\.withheld_evidence"\)\}/);
  // The discussion surface itself is withheld too: no question box without an action.
  assert.match(alertCenter, /\{discussing && askAvailable && \(/);
});

test("the alert surface still offers exactly the declared action set", () => {
  const alertCenter = readWebSource("components/AlertCenter.tsx");

  // One canonical action on this surface, and it is one of the five.
  assert.equal(declaredAiActions().includes("ask"), true);
  assert.equal((alertCenter.match(/aiActionContract\(/g) ?? []).length, 1);
  assert.equal(alertCenter.includes('"explain"'), false);
  assert.equal(alertCenter.includes('"compare"'), false);
  assert.equal(alertCenter.includes('"challenge"'), false);
  assert.equal(alertCenter.includes('"draft"'), false);

  // The surface never claims a numeric authority for the answer.
  assert.match(alertCenter, /t\("experience\.copilot\.result_interpretation"\)/);
});
