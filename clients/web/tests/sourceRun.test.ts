/**
 * Manual ingestion runs from the source surface (Architecture V2 Wave 4/8, client half).
 *
 * The Source Center *recommended* "Run the source ingestion job" as an operator's next action
 * while the product had no control that could do it, and the route that queues one
 * (`POST /api/sources/{source_id}/run`) had no client caller. These tests pin the rule for
 * offering it, and the line it draws: the platform's guards decide whether a run produces data,
 * so the surface *discloses* them and blocks only on facts that make the request meaningless.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  sourceRunOutcome,
  sourceRunReadiness,
  sourceRunReason,
  type SourceRunSubject,
} from "../src/app/model/sourceRunModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function subject(overrides: Partial<SourceRunSubject> = {}): SourceRunSubject {
  return {
    sourceId: "entsog",
    sourceSystem: "ENTSOG",
    schedulerEnabled: true,
    workflowReady: true,
    credentialState: "not_required",
    connectivityStatus: "ok",
    circuitState: "CLOSED",
    consecutiveFailures: 0,
    lastIngestionStatus: "success",
    ...overrides,
  };
}

function readiness(overrides: Partial<Parameters<typeof sourceRunReadiness>[0]> = {}) {
  return sourceRunReadiness({
    subject: subject(),
    runtimeDbReady: true,
    running: false,
    ...overrides,
  });
}

test("a healthy source may be run, with nothing to disclose", () => {
  assert.deepEqual(readiness(), {
    canRequest: true,
    blockerKeys: [],
    firstBlockerKey: null,
    disclosureKeys: [],
  });
});

test("nothing to run and nowhere to queue it are the only blockers", () => {
  assert.deepEqual(readiness({ subject: null }).blockerKeys, ["sources.run.blocker.no_source"]);
  assert.deepEqual(readiness({ runtimeDbReady: false }).blockerKeys, [
    "sources.run.blocker.runtime_db",
  ]);
  assert.deepEqual(readiness({ running: true }).blockerKeys, ["sources.run.blocker.in_flight"]);
  // A real precondition is reported before the transient one.
  assert.deepEqual(readiness({ subject: null, running: true }).blockerKeys, [
    "sources.run.blocker.no_source",
    "sources.run.blocker.in_flight",
  ]);
});

test("the platform's guards are disclosed, not used to hide the act", () => {
  // An operator retry is deliberate: the person may be retrying precisely because the circuit
  // tripped, so an open circuit is stated next to the control rather than removing it.
  const tripped = readiness({ subject: subject({ circuitState: "OPEN_CIRCUIT" }) });
  assert.equal(tripped.canRequest, true);
  assert.deepEqual(tripped.disclosureKeys, ["sources.run.disclosure.circuit_open"]);

  const noCredential = readiness({ subject: subject({ credentialState: "missing" }) });
  assert.equal(noCredential.canRequest, true);
  assert.ok(noCredential.disclosureKeys.includes("sources.run.disclosure.credential_missing"));

  const notReady = readiness({
    subject: subject({ workflowReady: false, connectivityStatus: "unreachable", consecutiveFailures: 4 }),
  });
  assert.equal(notReady.canRequest, true);
  // Several disclosures are all reported, in a stable order.
  assert.deepEqual(notReady.disclosureKeys, [
    "sources.run.disclosure.workflow_not_ready",
    "sources.run.disclosure.unreachable",
    "sources.run.disclosure.repeated_failures",
  ]);

  // A configured credential is not a disclosure, and neither is a closed circuit.
  assert.deepEqual(readiness({ subject: subject({ credentialState: "configured" }) }).disclosureKeys, []);
});

test("the reason names the operator request and the source, so the run is auditable", () => {
  assert.equal(
    sourceRunReason(subject()),
    "operator-requested from Source Center: ENTSOG",
  );
  // A source without a system label falls back to its id rather than recording an empty reason.
  assert.equal(
    sourceRunReason(subject({ sourceSystem: "  ", sourceId: "s-1" })),
    "operator-requested from Source Center: s-1",
  );
});

test("a queued run is read from what the route reported, with no invented fields", () => {
  const outcome = sourceRunOutcome({
    run_id: "run-42",
    status: "QUEUED",
    source_id: "entsog",
    trigger_type: "MANUAL",
  });
  assert.deepEqual(outcome, {
    runId: "run-42",
    status: "QUEUED",
    sourceId: "entsog",
    triggerType: "MANUAL",
  });
  // A response that did not report a field leaves it null rather than filling in a placeholder.
  assert.deepEqual(sourceRunOutcome({ run_id: "run-43" }), {
    runId: "run-43",
    status: null,
    sourceId: null,
    triggerType: null,
  });
  assert.equal(sourceRunOutcome(null), null);
});

test("the store queues through the platform and reports a refusal as itself", () => {
  const store = readWebSource("stores/api.ts");
  const client = readWebSource("api/client.ts");

  assert.match(
    client,
    /requestSourceRun: \(sourceId: string, reason: string, options\?: ApiRequestOptions\) =>\s*post<Record<string, unknown>>\(\s*`\/sources\/\$\{encodeURIComponent\(sourceId\)\}\/run`,\s*\{ reason \},\s*options,\s*\)/s,
  );
  assert.match(
    store,
    /requestSourceRun: async \(sourceId, reason\) => \{\s*if \(logoutInProgress\) return;\s*if \(!isIdentityGateOpen\(get\(\)\.authState\)\) return;/s,
  );
  assert.match(store, /set\(\{ sourceRunOutcome: sourceRunOutcome\(response\.data\), loading: false \}\);/);
  // A refused queue leaves no outcome behind, so the surface cannot show a run that never existed.
  assert.match(store, /set\(\{ sourceRunOutcome: null, error: String\(e\) \}\);/);
});

test("the control appears beside the recommendation that asks for it", () => {
  const center = readWebSource("components/SourceCenter.tsx");
  const renderer = readWebSource("app/workspaces/WorkspaceRenderer.tsx");

  // The control is offered only where the platform's own recommendation is the ingestion run.
  assert.match(
    center,
    /sourceNextAction\(selectedSource\) === t\("sources\.action\.run_ingestion"\)/,
  );
  assert.match(center, /disabled=\{!runReadiness\.canRequest\}/);
  assert.match(center, /runReadiness\.disclosureKeys\.map\(\(key\) => \(/);
  assert.match(center, /t\(runReadiness\.firstBlockerKey\)/);
  assert.match(center, /\{t\("sources\.action\.run_ingestion"\)\}/);
  // The queued run is shown from the response.
  assert.match(center, /\{sourceRunOutcome\?\.runId && \(/);
  assert.match(center, /t\("sources\.run\.queued"\)/);

  // The renderer supplies the facts the rule needs and the handler that posts.
  assert.match(renderer, /import \{ sourceRunReadiness, sourceRunReason \} from "@\/app\/model\/sourceRunModel";/);
  assert.match(renderer, /runReadiness=\{sourceRunReadiness\(\{/);
  assert.match(renderer, /sourceRunOutcome=\{api\.sourceRunOutcome\}/);
  assert.match(renderer, /void api\.requestSourceRun\(/);
});

test("every new source-run string exists in both locales, and says something different", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  const keys = Object.keys(en).filter((key) => key.startsWith("sources.run."));
  assert.ok(keys.length >= 9, `only ${keys.length} source-run keys were found`);
  assert.deepEqual(
    Object.keys(zh).filter((key) => key.startsWith("sources.run.")).sort(),
    [...keys].sort(),
  );
  for (const key of keys) {
    assert.notEqual(en[key], zh[key], `${key} is not translated`);
    assert.equal(en[key].includes("?"), false, `${key} carries a placeholder`);
    assert.equal(zh[key].includes("\ufffd"), false, `${key} carries a replacement character`);
  }
});
