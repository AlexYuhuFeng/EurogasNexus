/**
 * Admin -> Users and the local sign-in: the client presents what the backend decided.
 *
 * The state shown per person, the words for each refusal code the backend sends, the sign-in
 * form shown only when the deployment offers it (the "Tester sign-in" title only with the
 * tester sign-in), and the client's own first check of a new password (the server re-checks).
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { accessErrorKey, segregationConflict, userState } from "../src/app/model/accessUsersModel.ts";
import {
  authStatusSnapshot,
  devLoginErrorKey,
  newPasswordProblem,
  passwordChangeErrorKey,
  passwordFormOffered,
  shouldTryLocalAfterDevFailure,
} from "../src/stores/authGate.ts";

const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8")) as Record<string, string>;
const source = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

test("the state shown is the backend's account state, falling back to the status", () => {
  assert.equal(userState({ account_state: "INVITED", status: "ACTIVE" }), "INVITED");
  assert.equal(userState({ status: "DISABLED" }), "DISABLED");
  for (const state of ["ACTIVE", "INVITED", "DISABLED", "LOCKED", "PENDING"]) {
    assert.ok(en[`access.users.state.${state}`] && zh[`access.users.state.${state}`], state);
  }
});

test("every refusal code the backend sends has words in both languages", () => {
  assert.equal(accessErrorKey(new Error("API 409: last_administrator — This is the last")), "access.error.last_administrator");
  assert.equal(accessErrorKey(new Error("API 409: user_has_history — kept")), "access.error.user_has_history");
  assert.equal(accessErrorKey(new Error("API 500: boom")), "access.mutation_failed");
  const panel = source("app/model/accessUsersModel.ts");
  const codes = [...panel.matchAll(/^\s+"([a-z_]+)",$/gm)].map((match) => match[1]!);
  assert.ok(codes.length >= 10);
  for (const code of codes) {
    assert.ok(en[`access.error.${code}`], `en ${code}`);
    assert.ok(zh[`access.error.${code}`], `zh ${code}`);
  }
});

test("the password form appears for local accounts or the tester sign-in, never by itself", () => {
  const none = authStatusSnapshot({ oidc_configured: true, dev_login: false });
  assert.equal(passwordFormOffered(none), false);
  const local = authStatusSnapshot({ oidc_configured: false, dev_login: false, local_login: true });
  assert.equal(local.localLoginAvailable, true);
  assert.equal(passwordFormOffered(local), true);
  const demo = authStatusSnapshot({ dev_login: true, local_login: true });
  assert.equal(passwordFormOffered(demo), true);
  // A tester sign-in refusal is retried as a local account only when local accounts exist.
  assert.equal(shouldTryLocalAfterDevFailure(demo, "API 401: invalid_credentials"), true);
  assert.equal(shouldTryLocalAfterDevFailure(demo, "API 503: runtime_db_unavailable"), false);
  assert.equal(shouldTryLocalAfterDevFailure(authStatusSnapshot({ dev_login: true }), "API 401: x"), false);
  // The small "Tester sign-in" title belongs to the tester sign-in only.
  const screen = source("components/SignInScreen.tsx");
  assert.match(screen, /devLoginAvailable && <span className="sign-in-block-title">\{t\("auth\.dev_title"\)\}/);
});

test("refusals of a sign-in and of a new password are named", () => {
  assert.equal(devLoginErrorKey("API 401: temporary_password_expired — x"), "auth.error_temporary_expired");
  assert.equal(devLoginErrorKey("API 429: rate_limited"), "auth.error_rate_limited");
  assert.equal(devLoginErrorKey("API 401: invalid_credentials"), "auth.error_invalid_credentials");
  assert.equal(passwordChangeErrorKey("API 422: password_too_common — x"), "auth.password_too_common");
  assert.equal(passwordChangeErrorKey("API 401: change_token_invalid"), "auth.change_step_expired");
});

test("the client's first check of a new password mirrors the policy", () => {
  assert.equal(newPasswordProblem("short", "short"), "auth.password_too_short");
  assert.equal(newPasswordProblem("x".repeat(129), "x".repeat(129)), "auth.password_too_long");
  assert.equal(newPasswordProblem("jane.trader-forever", "jane.trader-forever", "jane.trader"), "auth.password_contains_username");
  assert.equal(newPasswordProblem("a calm long phrase", "a calm long phrasE"), "auth.password_mismatch");
  assert.equal(newPasswordProblem("a calm long phrase", "a calm long phrase", "jane"), null);
  for (const key of ["auth.password_too_short", "auth.password_mismatch", "auth.change_title"]) {
    assert.ok(en[key] && zh[key], key);
  }
});

test("Admin -> Users uses the shared primitives and shows the one-time password once", () => {
  const panel = source("components/AccessUsers.tsx");
  for (const primitive of ["<DataGrid", "<Dialog", "<Field", "<Button"]) assert.ok(panel.includes(primitive), primitive);
  // The secret lives only in the dialog's state and is never written to storage.
  assert.doesNotMatch(panel, /localStorage|sessionStorage/);
  assert.match(panel, /kind: "secret"/);
});

test("a VIEWER-only identity does not issue the review read its role floor refuses", async () => {
  const { workspaceReadNeeded } = await import("../src/stores/workspaceReadScope.ts");
  const viewer = { roles: ["VIEWER"], role: "VIEWER", permissions: ["review.read", "market.read", "portfolio.read"] } as never;
  const reviewer = { roles: ["REVIEWER"], role: "REVIEWER", permissions: ["review.read", "review.record"] } as never;
  assert.equal(workspaceReadNeeded("reviewDecisions", viewer), false);
  assert.equal(workspaceReadNeeded("reviewDecisions", reviewer), true);
});

test("QA-R-03: trader plus risk is granted with a segregation-of-duties warning, before and after saving", () => {
  assert.deepEqual(segregationConflict(["VIEWER", "REVIEWER", "ANALYST"]), ["ANALYST", "REVIEWER"]);
  assert.deepEqual(segregationConflict(["analyst", "reviewer"]), ["ANALYST", "REVIEWER"]);
  assert.equal(segregationConflict(["VIEWER", "REVIEWER"]), null);
  assert.equal(segregationConflict(["ANALYST"]), null);
  for (const key of ["access.users.sod_title", "access.users.sod_body", "access.users.sod_badge"]) {
    assert.ok(en[key], key);
    assert.ok(zh[key], key);
  }
  const form = source("components/AccessUsers.tsx");
  // Before saving: from the roles ticked, in both the Add and the Edit dialog.
  assert.equal(form.match(/<SegregationNotice roles=\{segregationConflict\(chosenRoles\)\}/g)?.length, 2);
  // After saving: the server's own warning, on the user's row and with the one-time password.
  assert.match(form, /user\.segregation_warning &&/);
  assert.match(form, /sod: user\.segregation_warning\?\.roles/);
});
