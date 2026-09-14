import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ResearchSpecDraft } from "../src/app/model/researchDataModel.ts";
import {
  EMPTY_RESEARCH_SPEC_DRAFT,
  RESEARCH_EXPORT_FORMATS,
  groupResearchIssues,
  normalizeResearchIssues,
  researchAnswerCode,
  researchAvailableFormats,
  researchBuildGate,
  researchBuildSummary,
  researchFormatAvailability,
  researchFormatOptions,
  researchFormatRows,
  researchHttpStatus,
  researchIssueTotal,
  researchIssuesFromAnswer,
  researchPreferredFormat,
  researchSpecFingerprint,
  researchSpecFromDraft,
  researchSpecMissingInputs,
  researchValidationOutcome,
  researchExportStateFromAnswer,
  researchExportCanRequest,
  researchExportDecision,
  researchRequestErrorMessage,
} from "../src/app/model/researchDataModel.ts";

function source(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const draft = (overrides: Partial<ResearchSpecDraft> = {}): ResearchSpecDraft => ({
  ...EMPTY_RESEARCH_SPEC_DRAFT,
  ...overrides,
});

const VALIDATE_REFUSAL = {
  ok: false,
  issues: [
    { field: "feature_ids", code: "unknown_feature_id", message: "unknown feature_id: feature.alpha" },
    { field: "target_ids", code: "unknown_target_id", message: "unknown target_id: target.beta" },
    { field: "entity_ids", code: "unknown_entity_id", message: "unknown canonical entity_id: hub.gamma" },
    { field: "resampling_policy_id", code: "unknown_resampling_policy_id", message: "unknown resampling_policy_id: resampling/v1" },
  ],
  spec_hash: "cbe55bb67121bcc5026ff85e9b3aad83b6778be862ce93172a51aefd8d579402",
  registry_resolution: "RESOLVED",
};

const BUILD_422 = {
  status: 422,
  message: "API 422: dataset_registry_invalid — Dataset specification references unavailable registry ids.",
  detail: {
    error: "dataset_registry_invalid",
    message: "Dataset specification references unavailable registry ids.",
    issues: [
      { field: "feature_ids", code: "unknown_feature_id", message: "unknown feature_id: feature.alpha" },
      { field: "target_ids", code: "unknown_target_id", message: "unknown target_id: target.beta" },
      { field: "feature_ids", code: "unknown_feature_id", message: "unknown feature_id: feature.alpha" },
    ],
  },
};

test("structured issues are normalised, deduplicated, and grouped by field", () => {
  assert.equal(normalizeResearchIssues(undefined).length, 0);
  assert.equal(normalizeResearchIssues(["plain text", 12, null]).length, 0);
  assert.equal(normalizeResearchIssues([{ field: "x", code: "", message: "" }]).length, 0);

  const fromRefusal = researchIssuesFromAnswer(VALIDATE_REFUSAL);
  assert.equal(fromRefusal.length, 4);
  assert.deepEqual(fromRefusal[0], {
    field: "feature_ids",
    code: "unknown_feature_id",
    message: "unknown feature_id: feature.alpha",
  });

  const grouped = groupResearchIssues(researchIssuesFromAnswer(BUILD_422));
  assert.equal(researchIssueTotal(grouped), 2, "the repeated server issue is collapsed once");
  assert.deepEqual(grouped.map((group) => group.field), ["feature_ids", "target_ids"]);
  assert.equal(grouped[0]?.issues.length, 1);
});

test("issues without a field are grouped last under the unassigned bucket", () => {
  const grouped = groupResearchIssues([
    { field: "", code: "registry_unavailable", message: "Runtime PostgreSQL is required." },
    { field: "dataset_spec", code: "dataset_field_invalid", message: "The dataset specification contains an invalid field." },
    { field: "feature_ids", code: "unknown_feature_id", message: "unknown feature_id: feature.alpha" },
  ]);
  assert.deepEqual(grouped.map((group) => group.field), ["dataset_spec", "feature_ids", ""]);
  assert.equal(researchIssueTotal(grouped), 3);
});

test("a validate answer reports ok only when the backend accepts a spec with no issues", () => {
  const refused = researchValidationOutcome(VALIDATE_REFUSAL);
  assert.equal(refused.ok, false);
  assert.equal(refused.issues.length, 4);
  assert.equal(refused.registryResolution, "RESOLVED");
  assert.match(refused.specHash, /^cbe55bb6/);

  const contradictory = researchValidationOutcome({ ok: true, issues: VALIDATE_REFUSAL.issues, spec_hash: "a", registry_resolution: "RESOLVED" });
  assert.equal(contradictory.ok, false, "ok:true with issues must never unlock a build");

  const accepted = researchValidationOutcome({ ok: true, issues: [], spec_hash: "b", registry_resolution: "RESOLVED" });
  assert.equal(accepted.ok, true);
  assert.equal(accepted.issues.length, 0);
});

test("a 422 validate refusal keeps its safe code and structured issues", () => {
  const specInvalid = {
    status: 422,
    message: "API 422: dataset_spec_invalid — Dataset specification failed validation.",
    detail: {
      error: "dataset_spec_invalid",
      message: "Dataset specification failed validation.",
      issues: [{ field: "start/end", code: "date_bounds_invalid", message: "end must be after start." }],
    },
  };
  const outcome = researchValidationOutcome(specInvalid);
  assert.equal(outcome.ok, false);
  assert.equal(outcome.code, "dataset_spec_invalid");
  assert.equal(outcome.issues[0]?.code, "date_bounds_invalid");
  assert.equal(outcome.specHash, "");
});

test("build stays locked until the exact validated spec still matches the draft", () => {
  const spec = researchSpecFromDraft(draft({ datasetSpecId: "s", name: "n", description: "d", targetIds: "t", start: "a", end: "b" }));
  const fingerprint = researchSpecFingerprint(spec);

    assert.deepEqual(researchBuildGate(null, fingerprint), { canBuild: false, reason: "not_validated" });
    assert.deepEqual(researchBuildGate({ fingerprint, ok: true }, researchSpecFingerprint({ ...spec, name: "changed" })), {
      canBuild: false,
      reason: "spec_changed",
    });
    assert.deepEqual(researchBuildGate({ fingerprint, ok: true }, fingerprint), { canBuild: true, reason: "ready" });
    assert.deepEqual(researchBuildGate({ fingerprint, ok: false }, fingerprint), {
      canBuild: false,
      reason: "validation_failed",
    });
    const failedOther = researchSpecFingerprint({ ...spec, name: "changed" });
    assert.deepEqual(researchBuildGate({ fingerprint, ok: false }, failedOther), {
      canBuild: false,
      reason: "spec_changed",
    });
});

test("the spec body carries only typed values and never a fabricated default", () => {
  const empty = researchSpecFromDraft(EMPTY_RESEARCH_SPEC_DRAFT);
  assert.deepEqual(empty, {}, "a blank form sends no defaults at all");

  const partial = researchSpecFromDraft(draft({
    datasetSpecId: "cr14.spec",
    targetIds: "target.one, target.two\n target.three",
    forecastOriginFrequency: "",
  }));
  assert.deepEqual(partial, {
    dataset_spec_id: "cr14.spec",
    target_ids: ["target.one", "target.two", "target.three"],
  });
  assert.equal("forecast_origin_frequency" in partial, false);
  assert.equal("output_format" in partial, false);

  assert.deepEqual(researchSpecMissingInputs(EMPTY_RESEARCH_SPEC_DRAFT), [
    "datasetSpecId", "name", "description", "targetIds", "start", "end",
  ]);
  assert.deepEqual(researchSpecMissingInputs(draft({ datasetSpecId: "s", name: "n", description: "d", targetIds: "t", start: "a", end: "b" })), []);
});

test("the spec fingerprint is stable across key order but changes with any value", () => {
  const left = researchSpecFingerprint({ b: ["2", "1"], a: "1" });
  const right = researchSpecFingerprint({ a: "1", b: ["2", "1"] });
  assert.equal(left, right);
  assert.notEqual(left, researchSpecFingerprint({ a: "1", b: ["1", "2"] }));
});

test("export state is derived from the backend answer, never assumed", () => {
  const idle = researchExportStateFromAnswer(null);
  assert.equal(idle.status, "not_requested");
  assert.equal(idle.artifactRef, null);

  const granted = researchExportStateFromAnswer({
    dataset_snapshot_id: "snapshot-1",
    format: "parquet",
    artifact_ref: "/srv/artifacts/snapshot-1/dataset.parquet",
    artifact_id: "artifact:parquet:abc",
    artifact_sha256: "f".repeat(64),
    available_formats: ["csv", "parquet"],
    entitlement_policy: "EXPORT_ALLOWED",
  });
  assert.equal(granted.status, "granted");
  assert.equal(granted.artifactRef, "/srv/artifacts/snapshot-1/dataset.parquet");
  assert.deepEqual(granted.availableFormats, ["csv", "parquet"]);
  assert.equal(granted.entitlementPolicy, "EXPORT_ALLOWED");

  const restricted = researchExportStateFromAnswer({
    status: 403,
    message: "API 403: export_denied_entitlement — Export is not permitted by the canonical source policy.",
    detail: {
      code: "export_denied_entitlement",
      message: "Export is not permitted by the canonical source policy.",
      policy: "EXPORT_RESTRICTED",
    },
  });
  assert.equal(restricted.status, "restricted");
  assert.equal(restricted.httpStatus, 403);
  assert.equal(restricted.code, "export_denied_entitlement");
  assert.equal(restricted.entitlementPolicy, "EXPORT_RESTRICTED");
  assert.equal(restricted.artifactRef, null);
  assert.equal(restricted.availableFormats, null);

  const sourceDenied = researchExportStateFromAnswer({
    status: 403,
    message: "API 403: source_entitlement_denied — The current identity is not entitled to the requested sources.",
    detail: { code: "source_entitlement_denied" },
  });
  assert.equal(sourceDenied.status, "restricted");
  assert.equal(sourceDenied.code, "source_entitlement_denied");

  const unregistered = researchExportStateFromAnswer({
    status: 409,
    message: "API 409: artifact_not_available — No stored artifact matches the requested format for this snapshot.",
    detail: {
      code: "artifact_not_available",
      reason: "FORMAT_NOT_REGISTERED",
      format: "parquet",
      available_formats: ["csv"],
    },
  });
  assert.equal(unregistered.status, "format_unregistered");
  assert.equal(unregistered.reason, "FORMAT_NOT_REGISTERED");
  assert.equal(unregistered.format, "parquet");
  assert.deepEqual(unregistered.availableFormats, ["csv"]);

  const missing = researchExportStateFromAnswer({
    status: 409,
    message: "API 409: artifact_not_available — The registered artifact is no longer present in storage.",
    detail: { code: "artifact_not_available", reason: "FILE_MISSING", format: "csv", available_formats: ["csv"] },
  });
  assert.equal(missing.status, "file_missing");

  const other = researchExportStateFromAnswer({
    status: 503,
    message: "API 503: artifact_store_unavailable",
    detail: { code: "artifact_store_unavailable" },
  });
  assert.equal(other.status, "unavailable");
  assert.equal(other.code, "artifact_store_unavailable");
});

test("requestable formats follow the last server answer and never repeat a refusal", () => {
  assert.deepEqual(researchFormatOptions(null), [...RESEARCH_EXPORT_FORMATS]);
  assert.deepEqual(researchFormatOptions([]), [], "a reported empty list registers nothing");
  assert.deepEqual(researchFormatOptions(["csv"]), ["csv"]);

  assert.equal(researchFormatAvailability(null, "parquet"), "unknown");
  assert.equal(researchFormatAvailability(["csv"], "parquet"), "unregistered");
  assert.equal(researchFormatAvailability(["csv", "parquet"], "parquet"), "registered");

  assert.deepEqual(
    researchFormatRows(["csv"]),
    [{ format: "parquet", availability: "unregistered" }, { format: "csv", availability: "registered" }],
  );
  assert.deepEqual(
    researchFormatRows(null),
    [{ format: "parquet", availability: "unknown" }, { format: "csv", availability: "unknown" }],
  );

  assert.equal(researchPreferredFormat(["csv"], "parquet"), "csv");
  assert.equal(researchPreferredFormat(["parquet", "csv"], "parquet"), "parquet");
  assert.equal(researchPreferredFormat([], "parquet"), null);
});

test("an artifact control is offered only for a server-confirmed export clearance", () => {
  assert.equal(researchExportDecision("EXPORT_ALLOWED"), "allowed");
  assert.equal(researchExportDecision("EXPORT_RESTRICTED"), "restricted");
  assert.equal(researchExportDecision("UNKNOWN"), "unknown");
  assert.equal(researchExportCanRequest(researchExportDecision("EXPORT_ALLOWED")), true);
  assert.equal(researchExportCanRequest(researchExportDecision("EXPORT_RESTRICTED")), false);
  assert.equal(researchExportCanRequest(researchExportDecision(undefined)), false);
  assert.equal(researchExportCanRequest(researchExportDecision("")), false);
});

test("build summaries read the snapshot the backend created", () => {
  const summary = researchBuildSummary({
    dataset_snapshot_id: "dataset-snapshot-abc123-cr14.spec",
    dataset_spec_id: "cr14.spec",
    dataset_spec_version: "cr14.spec@dataset-spec/v1@f00dbabe",
    row_count: 12,
    column_count: 7,
    entitlement_envelope: { export_policy: "EXPORT_RESTRICTED" },
  });
  assert.equal(summary?.datasetSnapshotId, "dataset-snapshot-abc123-cr14.spec");
  assert.equal(summary?.specHash, "f00dbabe");
  assert.equal(summary?.artifactRef, null);
  assert.equal(summary?.availableFormats, null, "the build answer lists no formats, so none may be implied");
  assert.equal(researchBuildSummary({ detail: { error: "dataset_build_invalid" } }), null);
});

test("status, code, and format extraction tolerate flattened transport errors", () => {
  assert.equal(researchHttpStatus({ status: 409 }), 409);
  assert.equal(researchHttpStatus(new Error("API 403: export_denied_entitlement — refused")), 403);
  assert.equal(researchHttpStatus("Network request failed"), null);
  assert.equal(researchAnswerCode({ detail: { error: "dataset_spec_invalid" } }), "dataset_spec_invalid");
  assert.equal(researchAnswerCode({ detail: { code: "artifact_not_available" } }), "artifact_not_available");
  assert.deepEqual(researchAvailableFormats({ detail: { available_formats: ["csv"] } }), ["csv"]);
  assert.equal(researchAvailableFormats({ detail: { code: "artifact_not_available" } }), null);
});

test("request error copy is localised and never echoes backend detail", () => {
  const messages = { generic: "generic", unauthorized: "unauthorized", forbidden: "forbidden" };
  assert.equal(researchRequestErrorMessage({ status: 403, detail: { message: "password=secret" } }, messages), "forbidden");
  assert.equal(researchRequestErrorMessage(new Error("API 401: unauthenticated"), messages), "unauthorized");
  assert.equal(researchRequestErrorMessage(new Error("API 422: dataset_registry_invalid — /srv/app/sql/secret"), messages), "generic");
});

test("the workspace wires the governed surface and gates the artifact control on the answer", () => {
  const workspace = source("components/ResearchDataWorkspace.tsx");
  assert.match(workspace, /validateResearchDataset\(requestedSpec, options\)/);
  assert.match(workspace, /buildResearchDataset\(requestedSpec, options\)/);
  assert.match(workspace, /researchBuildGate\(lastValidation, specFingerprint\)/);
  assert.match(workspace, /disabled=\{busy \|\| !gate\.canBuild\}/);
  assert.match(workspace, /researchValidationOutcome\(answer\)/);
  assert.match(workspace, /researchIssuesFromAnswer\(failure\)/);
  assert.match(workspace, /researchExportStateFromAnswer\(/);
  assert.match(workspace, /researchExportCanRequest\(researchExportDecision\(policy\)\)/);
  assert.match(workspace, /const showControl = canRequest && requestableFormats\.length > 0/);
  assert.match(workspace, /exportState\.status !== "restricted"/);
  assert.match(workspace, /pendingSnapshotRef\.current = summary\.datasetSnapshotId/);
  assert.match(workspace, /setCatalogReloadKey\(\(value\) => value \+ 1\)/);
  assert.match(workspace, /buildState\.summary\.availableFormats === null/);
  assert.match(workspace, /<PanelHeader/);
  assert.match(workspace, /<MetricStrip/);
  assert.match(workspace, /<StatusBadge/);
  assert.match(workspace, /<WorkspaceTabs/);
  assert.doesNotMatch(workspace, /<button[^>]*role="tab"/);
});

test("the transport keeps the structured HTTP envelope for governed surfaces", () => {
  const client = source("api/client.ts");
  assert.match(client, /export class ApiError extends Error/);
  assert.match(client, /readonly detail: unknown;/);
  assert.match(client, /export async function apiOutcome<T>/);
  assert.match(client, /apiOutcome/);
  assert.match(client, /validateResearchDataset: \(spec: Record<string, unknown>, options\?: ApiRequestOptions\)/);
  assert.match(client, /buildResearchDataset: \(spec: Record<string, unknown>, options\?: ApiRequestOptions\)/);
  assert.match(client, /available_formats\?: string\[\]/);
});
