/**
 * Architecture V2 Wave 8 - error presentation tests (client half).
 *
 * Every failure a user meets must answer four questions in one consistent place,
 * and an unclassified failure must still be explainable. These tests pin that, and
 * that the vocabulary exists in both locales.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  describeApiError,
  describeFailure,
  errorFamilyIds,
  isRetryable,
  presentError,
  requiresUserAction,
} from "../src/app/experience/index.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

/** The real English vocabulary, so "does this text exist" is a real question. */
function englishTranslator(): (key: string) => string {
  const strings = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  return (key: string) => strings[key] ?? key;
}

test("a catalogued failure becomes the four V2 questions", () => {
  const presentation = describeApiError({
    error: "entitlement_denied",
    family: "ENTITLEMENT",
    severity: "error",
    recoverability: "permanent",
    message_key: "errors.entitlement_denied.message",
    action_key: "errors.entitlement_denied.action",
    correlation_id: "corr-7",
  });

  assert.equal(presentation.code, "entitlement_denied");
  assert.equal(presentation.family, "ENTITLEMENT");
  assert.equal(presentation.severity, "error");
  assert.equal(presentation.recoverability, "permanent");
  assert.equal(presentation.titleKey, "errors.entitlement_denied.message");
  assert.equal(presentation.impactKey, "errors.family.ENTITLEMENT.impact");
  assert.equal(presentation.causeKey, "errors.cause.licence_restriction");
  assert.equal(presentation.actionKey, "errors.entitlement_denied.action");
  assert.equal(presentation.correlationId, "corr-7");
  assert.equal(isRetryable(presentation), false);
  assert.equal(requiresUserAction(presentation), false);
});

test("the administration-versus-commercial refusal explains itself", () => {
  const presentation = describeApiError({
    error: "commercial_access_not_granted",
    family: "ENTITLEMENT",
    recoverability: "after_user_action",
    action_key: "errors.family.ENTITLEMENT.action",
  });

  assert.equal(presentation.causeKey, "errors.cause.administration_is_not_commercial");
  assert.equal(requiresUserAction(presentation), true);
  assert.equal(isRetryable(presentation), false);
});

test("recoverable failures offer a retry and warning-class data states do not alarm", () => {
  assert.equal(
    isRetryable(describeApiError({ error: "PROVIDER_UNAVAILABLE", family: "DEPENDENCY", recoverability: "retry" })),
    true,
  );
  assert.equal(
    describeApiError({ error: "DATA_STALE", family: "DATA", severity: "warning" }).severity,
    "warning",
  );
  assert.equal(
    describeApiError({ error: "DATA_STALE", family: "DATA", severity: "warning" }).causeKey,
    "errors.cause.data_beyond_freshness",
  );
});

test("an unknown or missing error fails closed to a generic explanation", () => {
  const unknown = describeApiError({ error: "something_new" });
  assert.equal(unknown.code, "something_new");
  assert.equal(unknown.family, "SYSTEM");
  assert.equal(unknown.severity, "error");
  assert.equal(unknown.recoverability, "unknown");
  assert.equal(unknown.titleKey, "errors.something_new.message");
  assert.equal(unknown.causeKey, "errors.family.SYSTEM.cause");
  assert.equal(unknown.actionKey, "errors.family.SYSTEM.action");

  const missing = describeApiError(null);
  assert.equal(missing.code, "UNCLASSIFIED_ERROR");
  assert.equal(missing.family, "SYSTEM");
  assert.equal(missing.message, null);

  // An unrecognised family or severity degrades to the safe default, never to a
  // lower-severity claim.
  const malformed = describeApiError({
    error: "runtime_db_unavailable",
    family: "NOT_A_FAMILY" as unknown as string,
    severity: "nonsense" as unknown as string,
    recoverability: "nonsense" as unknown as string,
  });
  assert.equal(malformed.family, "SYSTEM");
  assert.equal(malformed.severity, "error");
  assert.equal(malformed.recoverability, "unknown");
});

test("the backend's safe message is preferred over a translation key", () => {
  const presentation = describeApiError({
    error: "DATA_STALE",
    family: "DATA",
    message: "  Last verified 12 minutes ago.  ",
    message_key: "errors.DATA_STALE.message",
  });

  assert.equal(presentation.message, "Last verified 12 minutes ago.");
  assert.equal(presentation.titleKey, "errors.DATA_STALE.message");
});

test("the whole error envelope reaches the presentation, not only its detail", () => {
  // The backend writes the taxonomy at the top level of the body and passes the
  // endpoint's `detail` through beside it. A cause that kept only `detail` would present
  // every failure as a generic SYSTEM fault and lose the correlation id.
  const body = {
    detail: { error: "entitlement_denied", blockers: ["EVIDENCE_REQUIRED"] },
    error: "entitlement_denied",
    family: "ENTITLEMENT",
    severity: "error",
    recoverability: "permanent",
    message_key: "errors.entitlement_denied.message",
    action_key: "errors.entitlement_denied.action",
    correlation_id: "corr-9",
  };

  for (const cause of [
    body,
    { status: 403, detail: body.detail, body },
    { status: 403, detail: body.detail, body, message: "API 403: denied" },
  ]) {
    const presentation = describeFailure(cause);
    assert.equal(presentation.code, "entitlement_denied");
    assert.equal(presentation.family, "ENTITLEMENT");
    assert.equal(presentation.correlationId, "corr-9");
    assert.equal(presentation.titleKey, "errors.entitlement_denied.message");
  }

  // A transport failure that carries no envelope at all is unclassified, not a claimed
  // dependency outage: nothing in it says a service was unavailable.
  assert.equal(describeFailure(new Error("boom")).code, "unclassified");
  assert.equal(describeFailure(undefined).family, "SYSTEM");
});

test("presentation resolves to text and never hands a user a raw key", () => {
  const t = englishTranslator();

  const catalogued = presentError(
    t,
    describeFailure({
      error: "entitlement_denied",
      family: "ENTITLEMENT",
      recoverability: "permanent",
      message_key: "errors.entitlement_denied.message",
      action_key: "errors.entitlement_denied.action",
      correlation_id: "corr-9",
    }),
  );
  assert.equal(catalogued.title, "The data licence does not cover this principal.");
  assert.equal(catalogued.action, "Request the entitlement for this data family.");
  assert.equal(catalogued.correlationId, "corr-9");
  for (const text of Object.values(catalogued)) {
    assert.doesNotMatch(String(text), /^errors\./, String(text));
  }

  // A code the vocabulary does not cover falls back to the family's own wording.
  const unmapped = presentError(t, describeApiError({ error: "brand_new_refusal" }));
  assert.equal(unmapped.title, "Unexpected system error");
  assert.equal(unmapped.action, "Retry once, then quote the correlation id to an operator.");

  // The severity floor still holds: an unknown code is not presented as retryable.
  assert.equal(isRetryable(describeApiError({ error: "brand_new_refusal" })), false);
});

test("the four answers answer the four questions in both locales", () => {
  const locales = {
    en: JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>,
    zh: JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>,
  };

  for (const [locale, strings] of Object.entries(locales)) {
    const text = presentError((key) => strings[key] ?? key, describeFailure({
      error: "runtime_db_unavailable",
      family: "DEPENDENCY",
      severity: "error",
      recoverability: "retry",
      message_key: "errors.runtime_db_unavailable.message",
      action_key: "errors.runtime_db_unavailable.action",
      correlation_id: "c-1",
    }));
    for (const [field, value] of Object.entries(text)) {
      if (field === "correlationId") continue;
      assert.ok(value.trim(), `${locale}.${field}`);
      assert.doesNotMatch(value, /^errors\./, `${locale}.${field}=${value}`);
    }
    assert.equal(text.correlationId, "c-1");
  }
});

test("a catalogued code's own text is what a job timeline renders", () => {
  // `JobTimeline` explains a failed job from its stored error code alone.
  const presentation = describeApiError({ error: "PROVIDER_UNAVAILABLE" });
  const text = presentError(englishTranslator(), presentation);
  assert.equal(text.title, "The provider connection did not answer.");
  assert.match(readWebSource("components/JobTimeline.tsx"), /presentError\(t, describeApiError\(\{ error: job\.error_code \}\)\)\.title/);
});

test("every family and the causes it uses exist in both locales", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  assert.deepEqual(
    [...errorFamilyIds()],
    [
      "AUTH",
      "ENTITLEMENT",
      "VALIDATION",
      "DATA",
      "CALCULATION",
      "DEPENDENCY",
      "CONFIGURATION",
      "JOB",
      "AGENT",
      "SYSTEM",
    ],
  );

  for (const family of errorFamilyIds()) {
    for (const suffix of ["impact", "cause", "action"]) {
      const key = `errors.family.${family}.${suffix}`;
      assert.ok(en[key]?.trim(), key);
      assert.ok(zh[key]?.trim(), key);
      assert.notEqual(en[key], zh[key], key);
    }
  }

  // Every cause key the presentation can emit is translated.
  const presentations = [
    describeApiError({ error: "unauthenticated", family: "AUTH" }),
    describeApiError({ error: "commercial_access_not_granted", family: "ENTITLEMENT" }),
    describeApiError({ error: "OPTIMIZATION_INFEASIBLE", family: "CALCULATION" }),
    describeApiError({ error: "AGENT_BUDGET_EXCEEDED", family: "AGENT" }),
    describeApiError({ error: "JOB_FAILED", family: "JOB" }),
    describeApiError({ error: "PORTFOLIO_INCOMPLETE", family: "DATA" }),
    describeApiError({ error: "SNAPSHOT_EXPIRED", family: "DATA" }),
    describeApiError({ error: "ROUTE_INFEASIBLE", family: "CALCULATION" }),
    describeApiError({ error: "runtime_db_unavailable", family: "DEPENDENCY" }),
    describeApiError({ error: "no_such_code" }),
  ];
  for (const presentation of presentations) {
    assert.ok(en[presentation.causeKey]?.trim(), presentation.causeKey);
    assert.ok(zh[presentation.causeKey]?.trim(), presentation.causeKey);
  }

  assert.ok(en["errors.unclassified.message"]?.trim());
  assert.ok(zh["errors.unclassified.action"]?.trim());
  assert.equal(Object.keys(en).length, Object.keys(zh).length);
});
