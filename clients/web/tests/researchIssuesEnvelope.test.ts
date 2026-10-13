/**
 * Does the issues reader survive the API's REAL error envelope?
 *
 * `clients/web/tests/researchDatasetBuild.test.ts` feeds `researchIssuesFromAnswer` a
 * fixture with a top-level `status` and `detail.issues`. The live API returns a different
 * shape: the taxonomy envelope puts `error`, `family`, `severity`, `message` at the top
 * level and nests the refusal under `detail`. A user reported the structured-issues panel
 * rendering empty against the live service, so this checks the reader against the envelope
 * the service actually produces.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  researchIssuesFromAnswer,
  researchAnswerCode,
  groupResearchIssues,
  researchIssueTotal,
} from "../src/app/model/researchDataModel.ts";

/** Captured from POST /api/research/datasets on the seeded stack. */
const LIVE_422 = {
  detail: {
    error: "dataset_registry_invalid",
    message: "Dataset specification references unavailable registry ids.",
    issues: [
      { field: "feature_ids", code: "unknown_feature_id", message: "unknown feature_id: X" },
      { field: "target_ids", code: "unknown_target_id", message: "unknown target_id: Y" },
    ],
  },
  error: "dataset_registry_invalid",
  family: "VALIDATION",
  severity: "error",
  recoverability: "after_user_action",
  message_key: "errors.dataset_registry_invalid.message",
  action_key: "errors.dataset_registry_invalid.action",
  correlation_id: "61a2076b9bcd4dd6",
  message: "Dataset specification references unavailable registry ids.",
};

/** The shape the client may hand the reader once it has wrapped the response. */
const WRAPPED_422 = {
  status: 422,
  message: "API 422: dataset_registry_invalid — Dataset specification references unavailable registry ids.",
  detail: LIVE_422.detail,
};

test("the reader extracts issues from the envelope the live service returns", () => {
  const issues = researchIssuesFromAnswer(LIVE_422);
  assert.equal(
    issues.length,
    2,
    `the live envelope yielded ${issues.length} issues; the panel groups these, so zero ` +
      "means the user sees an empty panel explaining nothing",
  );
  assert.equal(issues[0]?.field, "feature_ids");
  assert.equal(issues[0]?.code, "unknown_feature_id");
});

test("the reader also handles the wrapped shape the existing fixture uses", () => {
  const issues = researchIssuesFromAnswer(WRAPPED_422);
  assert.equal(issues.length, 2);
});

test("the refusal code is readable from the live envelope", () => {
  assert.equal(
    researchAnswerCode(LIVE_422),
    "dataset_registry_invalid",
    "the code drives the localised message, so it must survive the envelope",
  );
});

test("the two shapes group identically", () => {
  const live = groupResearchIssues(researchIssuesFromAnswer(LIVE_422));
  const wrapped = groupResearchIssues(researchIssuesFromAnswer(WRAPPED_422));
  assert.equal(researchIssueTotal(live), researchIssueTotal(wrapped));
  assert.deepEqual(
    live.map((group) => group.field),
    wrapped.map((group) => group.field),
  );
});
