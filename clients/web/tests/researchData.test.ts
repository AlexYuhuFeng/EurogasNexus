import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  isCurrentResearchSelection,
  isResearchDetailForSelection,
  researchDisplayValue,
  researchExportDecision,
  safeResearchErrorMessage,
} from "../src/app/model/researchDataModel.ts";
import { WorkspaceLoadCoordinator } from "../src/stores/workspaceLoading.ts";

const messages = {
  generic: "The request failed.",
  unauthorized: "Sign in required.",
  forbidden: "Access forbidden.",
  exportDenied: "Export denied by entitlement policy (403).",
};

function source(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("research display preserves known zero and distinguishes unknown", () => {
  assert.equal(researchDisplayValue(0, "Unknown"), "0");
  assert.equal(researchDisplayValue(null, "Unknown"), "Unknown");
  assert.equal(researchDisplayValue(undefined, "Unknown"), "Unknown");
});

test("research export policy fails closed for unknown and restricted rights", () => {
  assert.equal(researchExportDecision("EXPORT_ALLOWED"), "allowed");
  assert.equal(researchExportDecision("EXPORT_RESTRICTED"), "restricted");
  assert.equal(researchExportDecision(undefined), "unknown");
  assert.equal(researchExportDecision(0), "unknown");
});

test("stale dataset selection cannot commit a response for a different identity", () => {
  assert.equal(isCurrentResearchSelection("snapshot-a", "snapshot-a", "operator-a", "operator-a"), true);
  assert.equal(isCurrentResearchSelection("snapshot-b", "snapshot-a", "operator-a", "operator-a"), false);
  assert.equal(isCurrentResearchSelection("snapshot-a", "snapshot-a", "operator-b", "operator-a"), false);
});

test("selection change aborts an in-flight export generation", () => {
  const coordinator = new WorkspaceLoadCoordinator();
  const first = coordinator.start();
  const second = coordinator.start();

  assert.equal(first.signal.aborted, true);
  assert.equal(coordinator.isCurrent(first.generation, first.signal), false);
  assert.equal(coordinator.isCurrent(second.generation, second.signal), true);
});

test("detail data is renderable only for the selected snapshot", () => {
  assert.equal(isResearchDetailForSelection("snapshot-a", "snapshot-a"), true);
  assert.equal(isResearchDetailForSelection("snapshot-b", "snapshot-a"), false);
  assert.equal(isResearchDetailForSelection(null, "snapshot-a"), false);
});

test("research errors are localized and do not expose raw backend details", () => {
  assert.equal(safeResearchErrorMessage(new Error("API 403: export_denied_entitlement"), messages), messages.exportDenied);
  assert.equal(safeResearchErrorMessage(new Error("API 403: /srv/app/sql/password=secret"), messages), messages.forbidden);
  assert.equal(safeResearchErrorMessage(new Error("API 500: SELECT * FROM internal_table"), messages), messages.generic);
  assert.doesNotMatch(safeResearchErrorMessage(new Error("API 500: /srv/app/sql/password=secret"), messages), /secret|sql|srv/);
});

test("research client uses the existing detail, quality, and artifact-reference contracts", () => {
  const client = source("api/client.ts");
  assert.match(client, /researchDataset: \(datasetSnapshotId: string/);
  assert.match(client, /\/research\/datasets\/\$\{encodeURIComponent\(datasetSnapshotId\)\}\/quality/);
  assert.match(client, /exportResearchDataset:/);
  assert.match(client, /post<ResearchDatasetExportDTO>/);
  assert.match(client, /artifact_ref: string \| null/);
});
