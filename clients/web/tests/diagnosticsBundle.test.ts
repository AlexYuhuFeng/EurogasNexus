/**
 * Diagnostics bundle consumer tests (Architecture V2 Wave 10).
 *
 * Wave 10 declared the bundle contract and nothing ever composed one, so these tests pin both
 * halves of making it real: the rule that turns facts the client already holds into the exact
 * bundle that would leave the machine, and the surface that shows it before it leaves. The
 * honesty rules are asserted, not assumed - a field the deployment did not report is reported
 * as unavailable rather than as a zero, and nothing outside the allowlist can travel.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  composeDiagnosticsBundle,
  diagnosticsBundleFileName,
  diagnosticsHandover,
  type DiagnosticsFacts,
} from "../src/app/host/diagnosticsBundle.ts";
import { hostCapabilities } from "../src/app/host/hostCapabilities.ts";
import { DIAGNOSTICS_ALLOWED_FIELDS, DIAGNOSTICS_FORBIDDEN_FIELDS } from "../src/app/host/workstation.ts";
import { CLIENT_RELEASE_METADATA } from "../src/app/releaseCompatibility.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function facts(overrides: Partial<DiagnosticsFacts> = {}): DiagnosticsFacts {
  return {
    hostKind: "browser",
    capabilities: hostCapabilities("browser"),
    language: "en",
    serverVersion: "0.5.0",
    schemaRevision: "0036_job_records",
    releaseCompatibility: "compatible",
    dataStatus: "runtime",
    endpointFailureCodes: { marketContext: "timeout" },
    degradedSlices: ["market:quotes:STALE"],
    jobStates: { SUCCEEDED: 3, RUNNING: 1 },
    generatedAtUtc: "2026-02-01T09:30:00.000Z",
    ...overrides,
  };
}

test("the bundle carries the client's own facts and nothing outside the allowlist", () => {
  const { bundle, unavailableFields } = composeDiagnosticsBundle(facts());

  assert.equal(bundle.clientVersion, CLIENT_RELEASE_METADATA.version);
  assert.equal(bundle.serverVersion, "0.5.0");
  assert.equal(bundle.schemaRevision, "0036_job_records");
  assert.equal(bundle.hostKind, "browser");
  assert.equal(bundle.language, "en");
  assert.equal(bundle.dataStatus, "runtime");
  assert.deepEqual(bundle.endpointFailureCodes, { marketContext: "timeout" });
  assert.deepEqual(bundle.degradedSlices, ["market:quotes:STALE"]);
  assert.deepEqual(bundle.jobStates, { SUCCEEDED: 3, RUNNING: 1 });
  assert.deepEqual(unavailableFields, []);

  // Reported plus unavailable is the whole contract: nothing is invented and nothing is lost.
  assert.equal(
    Object.keys(bundle).length + unavailableFields.length,
    DIAGNOSTICS_ALLOWED_FIELDS.length,
  );
});

test("a fact the client does not hold is reported as unavailable, never as a zero", () => {
  const { bundle, unavailableFields } = composeDiagnosticsBundle(
    facts({
      serverVersion: null,
      schemaRevision: null,
      releaseCompatibility: null,
      endpointFailureCodes: null,
      degradedSlices: null,
      jobStates: null,
    }),
  );

  for (const field of [
    "serverVersion",
    "schemaRevision",
    "releaseCompatibility",
    "endpointFailureCodes",
    "degradedSlices",
    "jobStates",
  ]) {
    assert.equal(field in bundle, false, `${field} was sent without a fact behind it`);
    assert.ok(unavailableFields.includes(field), `${field} was not reported as unavailable`);
  }
  // The client's own identity is always known, so the bundle is never empty.
  assert.equal(bundle.clientVersion, CLIENT_RELEASE_METADATA.version);
  assert.equal(bundle.language, "en");
});

test("a fact the surface was handed but must not export cannot reach the bundle", () => {
  // The composer takes named facts, so a caller that passes more than it should - a job row,
  // a token, a price - cannot widen the bundle: everything outside the allowlist is dropped.
  const polluted = {
    ...facts(),
    accessToken: "secret-token",
    price: 31.25,
    counterparty: "Operator",
    jobs: [{ job_id: "job-1", principal: "analyst-1", inputs: { objective: "x" } }],
  } as unknown as DiagnosticsFacts;

  const { bundle } = composeDiagnosticsBundle(polluted);
  const serialised = JSON.stringify(bundle);

  for (const forbidden of ["accessToken", "secret-token", "price", "counterparty", "principal"]) {
    assert.equal(serialised.includes(forbidden), false, `${forbidden} reached the bundle`);
  }
  for (const key of Object.keys(bundle)) {
    assert.ok(
      (DIAGNOSTICS_ALLOWED_FIELDS as readonly string[]).includes(key),
      `${key} is not a declared field`,
    );
  }
  // Nothing forbidden is even declared as allowed, which is what makes the exclusion reviewable.
  for (const forbidden of DIAGNOSTICS_FORBIDDEN_FIELDS) {
    assert.equal(
      (DIAGNOSTICS_ALLOWED_FIELDS as readonly string[]).includes(forbidden),
      false,
      `${forbidden} is declared both allowed and forbidden`,
    );
  }
});

test("the bundle says which host composed it, so a support reader knows what was possible", () => {
  const desktop = composeDiagnosticsBundle(
    facts({ hostKind: "desktop", capabilities: hostCapabilities("desktop") }),
  ).bundle;
  const browser = composeDiagnosticsBundle(facts()).bundle;

  assert.equal(desktop.hostKind, "desktop");
  assert.deepEqual(desktop.capabilities, hostCapabilities("desktop"));
  assert.deepEqual(browser.capabilities, hostCapabilities("browser"));
  // The two differ, which is why the handover note differs rather than being copy-pasted.
  assert.notDeepEqual(desktop.capabilities, browser.capabilities);
});

test("the handover is a download, and a declared-but-unimplemented native export is said so", () => {
  const browser = diagnosticsHandover("browser");
  assert.equal(browser.method, "browser-download");
  assert.deepEqual(browser.noteKeys, ["diagnostics.handover.download"]);

  // The desktop host declares `diagnosticsExport`, but no allowlisted command implements it,
  // so the surface states that instead of offering a control with nothing behind it.
  const desktop = diagnosticsHandover("desktop");
  assert.equal(desktop.method, "browser-download");
  assert.deepEqual(desktop.noteKeys, [
    "diagnostics.handover.download",
    "diagnostics.handover.native_export_pending",
  ]);
});

test("the file name identifies when the bundle was taken and nothing else", () => {
  assert.equal(
    diagnosticsBundleFileName("2026-02-01T09:30:00.000Z"),
    "eurogas-nexus-diagnostics-20260201T093000.json",
  );
  // No host name, principal or deployment identifier can appear, whatever the caller passes:
  // only an ISO-8601 instant is read, and anything else produces the unnamed fallback rather
  // than a name built out of the string it was handed.
  const named = diagnosticsBundleFileName("analyst-1@trading-desk");
  assert.equal(named, "eurogas-nexus-diagnostics.json");
  assert.equal(named.includes("analyst"), false);
  assert.equal(named.includes("@"), false);
  assert.equal(diagnosticsBundleFileName(""), "eurogas-nexus-diagnostics.json");
  assert.equal(diagnosticsBundleFileName("not-a-time"), "eurogas-nexus-diagnostics.json");
});

test("the surface composes through the rule, shows what is missing, and reports the handover", () => {
  const panel = readWebSource("components/DiagnosticsPanel.tsx");

  // The rule is applied, not restated: no bundle object is assembled in the component.
  assert.match(
    panel,
    /import \{\s*composeDiagnosticsBundle,\s*diagnosticsBundleFileName,\s*diagnosticsHandover,\s*type DiagnosticsComposition,\s*\} from "@\/app\/host\/diagnosticsBundle";/s,
  );
  assert.match(panel, /composeDiagnosticsBundle\(\{/);
  assert.equal(panel.includes('clientVersion:'), false);
  assert.equal(panel.includes("buildDiagnosticsBundle"), false);

  // A read that failed is reported as unavailable rather than as zero work.
  assert.match(panel, /jobStates = null;/);
  assert.match(panel, /const slicesLoaded = dataStatus !== "unavailable";/);
  assert.match(panel, /endpointFailureCodes: slicesLoaded \? \{ \.\.\.endpointErrorCodes \} : null/);

  // What leaves is shown before it leaves, including the fields that could not be reported.
  assert.match(panel, /composition\.unavailableFields\.map/);
  assert.match(panel, /t\("diagnostics\.unavailable_hint"\)/);
  assert.match(panel, /t\("diagnostics\.guarantee"\)/);
  assert.match(panel, /handover\.noteKeys\.map/);
  assert.match(panel, /anchor\.download = diagnosticsBundleFileName\(/);
  assert.match(panel, /URL\.revokeObjectURL\(href\);/);
  // The preview is the same data that would be written, not a summary of it.
  assert.match(panel, /Object\.entries\(composition\.bundle\)/);

  // It is an operator surface: mounted with the runtime readiness evidence.
  const runtime = readWebSource("components/RuntimeWorkspace.tsx");
  assert.match(runtime, /import \{ DiagnosticsPanel \} from "@\/components\/DiagnosticsPanel";/);
  assert.match(runtime, /<JobTimeline t=\{t\} \/>[\s\S]*?<DiagnosticsPanel t=\{t\} \/>/);
});

test("every diagnostics string exists in both locales, and says something different", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  const keys = [
    "diagnostics.title",
    "diagnostics.subtitle",
    "diagnostics.host",
    "diagnostics.reported",
    "diagnostics.unavailable",
    "diagnostics.unavailable_hint",
    "diagnostics.guarantee",
    "diagnostics.action.prepare",
    "diagnostics.action.preparing",
    "diagnostics.action.copy",
    "diagnostics.action.download",
    "diagnostics.message.copied",
    "diagnostics.message.copy_failed",
    "diagnostics.message.downloaded",
    ...diagnosticsHandover("desktop").noteKeys,
  ];

  for (const key of keys) {
    assert.ok(en[key], `en is missing ${key}`);
    assert.ok(zh[key], `zh is missing ${key}`);
    assert.notEqual(en[key], zh[key], `${key} is not translated`);
    assert.equal(en[key].includes("?"), false, `${key} carries a placeholder`);
    assert.equal(zh[key].includes("\ufffd"), false, `${key} carries a replacement character`);
  }
});
