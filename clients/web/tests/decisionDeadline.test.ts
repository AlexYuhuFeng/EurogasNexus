/** Decision deadlines are typed locally, stored and confirmed in UTC (#58). */
import assert from "node:assert/strict";
import test from "node:test";
import { deadlineStateKey, formatDeadlineUtc, localDeadlineToUtc } from "../src/app/model/decisionDeadline.ts";

test("a local deadline becomes one UTC instant", () => {
  // Fixed offset +01:00 stands in for the browser's zone.
  const asParis = (value: string) => new Date(`${value}:00+01:00`);
  assert.equal(localDeadlineToUtc("2026-11-06T16:00", asParis), "2026-11-06T15:00:00.000Z");
  assert.equal(formatDeadlineUtc("2026-11-06T15:00:00.000Z"), "2026-11-06 15:00 UTC");
});

test("an empty or malformed value is no deadline", () => {
  assert.equal(localDeadlineToUtc(""), null);
  assert.equal(localDeadlineToUtc("tomorrow"), null);
});

test("each reported state has a label; none has none", () => {
  assert.equal(deadlineStateKey("overdue"), "decision_case.deadline.overdue");
  assert.equal(deadlineStateKey("decided_late"), "decision_case.deadline.late");
  assert.equal(deadlineStateKey("none"), null);
});
