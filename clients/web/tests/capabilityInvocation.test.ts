/**
 * Capability invocation tests (Architecture V2 Wave 7 / CR-15, client half).
 *
 * The catalogue was published to the surface with no way to act on it, so the posture each
 * capability declares - `AUTO_ALLOWED`, `HUMAN_CONFIRMATION`, `HUMAN_ONLY` - governed nothing a
 * user could see. These tests pin the rule the surface now gates on, and the honesty rules it
 * must keep while mirroring what the runtime enforces:
 *
 * - a `HUMAN_ONLY` capability is never offered, because the runtime never invokes it;
 * - a confirmation is required before a `HUMAN_CONFIRMATION` capability runs, and is cleared when
 *   the target changes, so nobody confirms one capability and runs another;
 * - invalid JSON blocks the invocation instead of sending `{}`, because invoking with inputs the
 *   user never wrote is worse than a refusal;
 * - a `BLOCKED` result is rendered as the result it is, codes and all, never rewritten as an
 *   error or smoothed into a success.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  argumentsParsed,
  capabilityInvocationReadiness,
  capabilityInvocationRequest,
  capabilityOutcome,
  capabilityPolicyKey,
} from "../src/app/model/capabilityInvocationModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function subject(actionPolicy: string) {
  return {
    capabilityId: "market.curve.read",
    actionPolicy,
    sideEffectClass: "READ_ONLY",
    determinismClass: "DETERMINISTIC",
  };
}

test("an auto-allowed capability may be invoked without a confirmation", () => {
  const readiness = capabilityInvocationReadiness({
    capability: subject("AUTO_ALLOWED"),
    argumentsText: "{}",
    confirmed: false,
    running: false,
  });

  assert.equal(readiness.canInvoke, true);
  assert.equal(readiness.requiresConfirmation, false);
  assert.deepEqual(readiness.blockerKeys, []);
});

test("a human-only capability is never offered, whatever the caller sends", () => {
  const readiness = capabilityInvocationReadiness({
    capability: subject("HUMAN_ONLY"),
    argumentsText: "{}",
    confirmed: true,
    running: false,
  });

  assert.equal(readiness.canInvoke, false);
  assert.deepEqual(readiness.blockerKeys, ["capabilities.blocker.human_only"]);
  // Even the request builder refuses it, so no path can post one.
  assert.equal(
    capabilityInvocationRequest({
      capability: subject("HUMAN_ONLY"),
      argumentsText: "{}",
      confirmed: true,
      confirmationNote: "confirmed",
    }),
    null,
  );
});

test("a confirmation is required, and only the policy that asks for it gets one", () => {
  const unconfirmed = capabilityInvocationReadiness({
    capability: subject("HUMAN_CONFIRMATION"),
    argumentsText: "{}",
    confirmed: false,
    running: false,
  });
  assert.equal(unconfirmed.canInvoke, false);
  assert.equal(unconfirmed.requiresConfirmation, true);
  assert.deepEqual(unconfirmed.blockerKeys, ["capabilities.blocker.confirmation_required"]);

  const confirmed = capabilityInvocationReadiness({
    capability: subject("HUMAN_CONFIRMATION"),
    argumentsText: "{}",
    confirmed: true,
    running: false,
  });
  assert.equal(confirmed.canInvoke, true);

  // A confirmation is not carried for a capability that did not ask for one, so the request never
  // claims a review that never happened.
  assert.equal(
    capabilityInvocationRequest({
      capability: subject("AUTO_ALLOWED"),
      argumentsText: "{}",
      confirmed: true,
      confirmationNote: "reviewed",
    })?.humanConfirmation,
    false,
  );
  // ...and a note without a confirmation is not carried either.
  assert.equal(
    capabilityInvocationRequest({
      capability: subject("HUMAN_CONFIRMATION"),
      argumentsText: "{}",
      confirmed: true,
      confirmationNote: "  reviewed the curve evidence  ",
    })?.confirmationNote,
    "reviewed the curve evidence",
  );
  assert.equal(
    capabilityInvocationRequest({
      capability: subject("AUTO_ALLOWED"),
      argumentsText: "{}",
      confirmed: false,
      confirmationNote: "not a confirmation",
    })?.confirmationNote,
    "",
  );
});

test("arguments must be a JSON object, and a mistyped editor sends nothing", () => {
  assert.deepEqual(argumentsParsed(""), {});
  assert.deepEqual(argumentsParsed("  {\"a\": 1}  "), { a: 1 });
  // An array or a scalar is not a set of fields the runtime can validate.
  assert.equal(argumentsParsed("[1, 2]"), null);
  assert.equal(argumentsParsed("42"), null);
  assert.equal(argumentsParsed("null"), null);
  assert.equal(argumentsParsed("{not json}"), null);

  const readiness = capabilityInvocationReadiness({
    capability: subject("AUTO_ALLOWED"),
    argumentsText: "{oops}",
    confirmed: false,
    running: false,
  });
  assert.deepEqual(readiness.blockerKeys, ["capabilities.blocker.arguments_invalid"]);
  assert.equal(
    capabilityInvocationRequest({
      capability: subject("AUTO_ALLOWED"),
      argumentsText: "{oops}",
      confirmed: false,
      confirmationNote: "",
    }),
    null,
  );
});

test("no selection, and an invocation already in flight, both block", () => {
  assert.deepEqual(
    capabilityInvocationReadiness({
      capability: null,
      argumentsText: "{}",
      confirmed: true,
      running: false,
    }).blockerKeys,
    ["capabilities.blocker.no_selection"],
  );
  assert.deepEqual(
    capabilityInvocationReadiness({
      capability: subject("AUTO_ALLOWED"),
      argumentsText: "{}",
      confirmed: false,
      running: true,
    }).blockerKeys,
    ["capabilities.blocker.in_flight"],
  );
  // A real precondition is reported before a transient one.
  assert.deepEqual(
    capabilityInvocationReadiness({
      capability: subject("HUMAN_CONFIRMATION"),
      argumentsText: "{}",
      confirmed: false,
      running: true,
    }).blockerKeys,
    ["capabilities.blocker.confirmation_required", "capabilities.blocker.in_flight"],
  );
});

test("a blocked result is read as the result it is", () => {
  const outcome = capabilityOutcome({
    status: "BLOCKED",
    capability: "market.curve.read",
    failure: { code: "ENTITLEMENT_DENIED", detail: "source family withheld", retryable: false },
    blockers: ["EEX"],
    warnings: ["partial"],
    evidence_refs: ["/api/market/observations"],
    entitlement_state: "RESTRICTED",
    quality_state: "UNKNOWN",
    as_of: "2026-02-01T09:00:00Z",
  });

  assert.equal(outcome?.status, "BLOCKED");
  assert.equal(outcome?.failureCode, "ENTITLEMENT_DENIED");
  assert.equal(outcome?.failureDetail, "source family withheld");
  assert.deepEqual(outcome?.blockers, ["EEX"]);
  assert.equal(outcome?.entitlementState, "RESTRICTED");

  // Nothing the backend did not report is invented.
  const sparse = capabilityOutcome({ status: "SUCCESS", capability: "x" });
  assert.equal(sparse?.failureCode, null);
  assert.deepEqual(sparse?.evidenceRefs, []);
  assert.equal(sparse?.entitlementState, "NOT_REPORTED");
  assert.equal(sparse?.asOf, null);
  assert.equal(capabilityOutcome(null), null);
});

test("an unknown policy is shown as its own code rather than a wrong word", () => {
  assert.equal(capabilityPolicyKey("AUTO_ALLOWED"), "capabilities.policy.auto_allowed");
  assert.equal(
    capabilityPolicyKey("HUMAN_CONFIRMATION"),
    "capabilities.policy.human_confirmation",
  );
  assert.equal(capabilityPolicyKey("FUTURE_POLICY"), "FUTURE_POLICY");
});

test("the surface offers invocation and the header runs it", () => {
  const workspace = readWebSource("components/AgentsWorkspace.tsx");
  const client = readWebSource("api/client.ts");

  // The transport carries the confirmation the runtime reads.
  assert.match(client, /invokeCapability: \(\s*capabilityId: string,\s*argumentsBody: Record<string, unknown>,\s*confirmation\?: \{ humanConfirmation: boolean; confirmationNote\?: string \},\s*\)/s);
  assert.match(client, /human_confirmation: confirmation\?\.humanConfirmation \?\? false,/);
  assert.match(client, /confirmation_note: confirmation\?\.confirmationNote \?\? "",/);

  // The action is the workspace's primary action for the capabilities view, gated by the rule
  // the panel lists, and the catalogue no longer just reports postures.
  assert.match(workspace, /activeView === "capabilities" \? \(/);
  assert.match(workspace, /disabled=\{!invokeReadiness\.canInvoke\}/);
  assert.match(workspace, /capabilityInvocationRequest\(\{/);
  assert.match(workspace, /api\.invokeCapability\(invokeSubject\.capabilityId, request\.arguments,/);
  // Changing the target clears the confirmation: nobody confirms one capability and runs another.
  assert.match(workspace, /setInvokeConfirmed\(false\);/);
  // A blocked result is shown with its code, not rewritten.
  assert.match(workspace, /\{invokeOutcome\.failureCode && \(/);
});

test("every capability string exists in both locales, and says something different", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  const keys = Object.keys(en).filter((key) => key.startsWith("capabilities."));
  assert.ok(keys.length >= 16, `only ${keys.length} capability keys were found`);
  assert.deepEqual(
    Object.keys(zh).filter((key) => key.startsWith("capabilities.")).sort(),
    [...keys].sort(),
  );
  for (const key of keys) {
    assert.notEqual(en[key], zh[key], `${key} is not translated`);
    assert.equal(en[key].includes("?"), false, `${key} carries a placeholder`);
    assert.equal(zh[key].includes("\ufffd"), false, `${key} carries a replacement character`);
  }
});
