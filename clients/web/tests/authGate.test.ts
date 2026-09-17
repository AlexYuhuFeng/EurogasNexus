import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  AUTHENTICATED_AUTH_STATE,
  UNAUTHENTICATED_AUTH_STATE,
  UNRESOLVED_AUTH_STATE,
  identityDeniedWorkspaceReset,
  isIdentityDeniedMessage,
  isIdentityGateOpen,
  isUnauthenticated,
  loadWorkspaceEndpoint,
  resetIdentityScopedCaches,
  workspaceLoadHasIdentityDenial,
} from "../src/stores/workspaceLoading.ts";
import {
  IDENTITY_SIGNAL_NAME,
  PROTECTED_CONTEXT_QUERY_KEYS,
  authStatusSnapshot,
  bootstrapStartState,
  credentialFreeEntryUrl,
  devLoginCurrentUser,
  devLoginErrorKey,
  devLoginOffered,
  identityFailureKey,
  identitySignalPayload,
  oidcSignInErrorKey,
  resolveIdentity,
  shouldScrubEntryUrl,
} from "../src/stores/authGate.ts";
import {
  SELECTION_CONTEXT_QUERY_KEYS,
  TRADER_CONTEXT_QUERY_KEYS,
} from "../src/app/context/contextUrl.ts";
import { workspaceTaskSearch } from "../src/workspaceNavigation.ts";

function source(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function json(relativePath: string): Record<string, string> {
  return JSON.parse(source(relativePath)) as Record<string, string>;
}

test("no protected read is possible while identity is unresolved or denied", () => {
  assert.equal(isIdentityGateOpen(UNRESOLVED_AUTH_STATE), false);
  assert.equal(isIdentityGateOpen(UNAUTHENTICATED_AUTH_STATE), false);
  assert.equal(isIdentityGateOpen(AUTHENTICATED_AUTH_STATE), true);
  assert.equal(isIdentityGateOpen("unknown"), false);
  assert.equal(isIdentityGateOpen("unauthenticated"), false);
  assert.equal(isIdentityGateOpen("authenticated"), true);

  // Only a finished denial scrubs the URL; a pending resolution is not a denial.
  assert.equal(isUnauthenticated(UNAUTHENTICATED_AUTH_STATE), true);
  assert.equal(isUnauthenticated(UNRESOLVED_AUTH_STATE), false);
  assert.equal(isUnauthenticated(AUTHENTICATED_AUTH_STATE), false);
});

test("identity resolution treats every non-success outcome as unauthenticated", () => {
  const success = resolveIdentity({ ok: true, value: { principal_id: "operator-1" } });
  assert.equal(success.authState, AUTHENTICATED_AUTH_STATE);
  assert.equal(success.failureReason, null);

  // A cold visit presents no credential: no error banner, just the sign-in screen.
  const noCredential = resolveIdentity({
    ok: false,
    error: {
      code: "request",
      message: "API 401: unauthenticated — No authenticated identity was presented.",
    },
  });
  assert.equal(noCredential.authState, UNAUTHENTICATED_AUTH_STATE);
  assert.equal(noCredential.failureReason, "identity_absent");
  assert.equal(identityFailureKey(noCredential.failureReason), null);

  // Any other denial means a session the operator actually lost.
  const revoked = resolveIdentity({
    ok: false,
    error: {
      code: "request",
      message: "API 401: identity_key_revoked — This identity key is revoked.",
    },
  });
  assert.equal(revoked.authState, UNAUTHENTICATED_AUTH_STATE);
  assert.equal(revoked.failureReason, "identity_denied");
  assert.equal(identityFailureKey(revoked.failureReason), "auth.error_session_expired");

  const notProvisioned = resolveIdentity({
    ok: false,
    error: {
      code: "request",
      message: "API 403: identity_not_provisioned — No active local identity principal matches.",
    },
  });
  assert.equal(notProvisioned.authState, UNAUTHENTICATED_AUTH_STATE);
  assert.equal(notProvisioned.failureReason, "identity_denied");

  const unreachable = resolveIdentity({
    ok: false,
    error: { code: "timeout", message: "Workspace endpoint timed out after 10000ms." },
  });
  assert.equal(unreachable.authState, UNAUTHENTICATED_AUTH_STATE);
  assert.equal(unreachable.failureReason, "identity_unreachable");
  assert.equal(
    identityFailureKey(unreachable.failureReason),
    "auth.error_identity_unreachable",
  );
  assert.equal(identityFailureKey(null), null);
});

test("bootstrapping identity keeps a confirmed session and re-resolves everything else", () => {
  assert.equal(bootstrapStartState(AUTHENTICATED_AUTH_STATE), AUTHENTICATED_AUTH_STATE);
  assert.equal(bootstrapStartState(UNAUTHENTICATED_AUTH_STATE), UNRESOLVED_AUTH_STATE);
  assert.equal(bootstrapStartState(UNRESOLVED_AUTH_STATE), UNRESOLVED_AUTH_STATE);
});

test("development sign-in is offered only when the deployment advertises it", () => {
  const configured = authStatusSnapshot({
    oidc_configured: true,
    session_cookie: true,
    profile: "corporate-oidc",
    dev_login: true,
  });
  assert.deepEqual(configured, {
    oidcConfigured: true,
    sessionCookiePresent: true,
    profile: "corporate-oidc",
    devLoginAvailable: true,
  });
  assert.equal(devLoginOffered(configured), true);

  const production = authStatusSnapshot({
    oidc_configured: true,
    session_cookie: false,
    profile: { issuer: "https://idp.example" },
    dev_login: false,
  });
  assert.equal(production.devLoginAvailable, false);
  assert.equal(devLoginOffered(production), false);
  assert.equal(production.profile, null);

  for (const malformed of [null, undefined, "not-an-object", 42, []]) {
    assert.equal(authStatusSnapshot(malformed).devLoginAvailable, false);
  }
  // A truthy string is not an advertised capability.
  assert.equal(authStatusSnapshot({ dev_login: "true" }).devLoginAvailable, false);
  assert.equal(authStatusSnapshot({ oidc_configured: "yes" }).oidcConfigured, false);
});

test("development login failures are localised by machine code, not by status text", () => {
  assert.equal(
    devLoginErrorKey("API 401: invalid_credentials — Username or password is incorrect."),
    "auth.error_invalid_credentials",
  );
  assert.equal(
    devLoginErrorKey("API 403: identity_not_provisioned — an administrator must provision it."),
    "auth.error_not_provisioned",
  );
  assert.equal(
    devLoginErrorKey("API 503: dev_login_disabled — not configured"),
    "auth.error_dev_login_disabled",
  );
  assert.equal(devLoginErrorKey("API 401: Unauthorized"), "auth.error_invalid_credentials");
  assert.equal(devLoginErrorKey("API 403: Forbidden"), "auth.error_not_provisioned");
  // An ambiguous 503 (runtime DB down) must not claim development login is disabled.
  assert.equal(devLoginErrorKey("API 503: runtime_db_unavailable — DB down"), "auth.error_generic");
  assert.equal(devLoginErrorKey("TypeError: Failed to fetch"), "auth.error_generic");
  assert.equal(oidcSignInErrorKey("API 503: oidc_not_configured"), "auth.sso_unavailable");
  assert.equal(oidcSignInErrorKey("Desktop login callback was incomplete."), "auth.error_sso_failed");
});

test("the provisional development identity never carries a credential", () => {
  const permissions = ["market.read"];
  const user = devLoginCurrentUser({
    authenticated: true,
    principal_id: "dev-operator-1",
    display_name: "Development Operator",
    role: "trader",
    permissions,
  });

  assert.equal(user.principal_id, "dev-operator-1");
  assert.equal(user.name, "Development Operator");
  assert.equal(user.display_name, "Development Operator");
  assert.equal(user.role, "trader");
  assert.deepEqual(user.roles, ["trader"]);
  assert.deepEqual(user.permissions, ["market.read"]);
  assert.equal(user.email, null);
  assert.equal(user.csrf_token, null);
  assert.equal(user.auth_method, "dev_login");
  assert.equal(user.identity_source, "dev-credentials");

  // The projection must not alias the backend payload.
  permissions.push("identity.manage");
  assert.deepEqual(user.permissions, ["market.read"]);
});

test("losing an identity clears every identity-scoped slice and returns to sign-in", () => {
  const reset = resetIdentityScopedCaches({ open_count: 0 });

  assert.equal(reset.authState, UNAUTHENTICATED_AUTH_STATE);
  assert.equal(reset.currentUser, null);
  assert.deepEqual(reset.nodes, []);
  assert.deepEqual(reset.marketQuotes, []);
  assert.deepEqual(reset.intradayOpportunities, []);
  assert.equal(reset.loading, false);
  assert.equal(reset.dataStatus, "unavailable");

  const denied = identityDeniedWorkspaceReset(
    [
      { key: "referenceNodes", outcome: { ok: true, value: "retained" } },
      {
        key: "marketQuotes",
        outcome: { ok: false, error: { code: "request", message: "API 401: unauthenticated" } },
      },
    ],
    { open_count: 0 },
  );
  assert.ok(denied);
  assert.equal(denied.authState, UNAUTHENTICATED_AUTH_STATE);
  assert.equal(denied.currentUser, null);
  assert.deepEqual(denied.nodes, []);
});

test("a scope-only 403 keeps the session, a 401 anywhere fails it closed", () => {
  assert.equal(workspaceLoadHasIdentityDenial([]), false);
  assert.equal(
    workspaceLoadHasIdentityDenial([
      { key: "referenceNodes", outcome: { ok: true, value: "retained" } },
      {
        key: "resourcePoolOptions",
        outcome: { ok: false, error: { code: "request", message: "API 403: forbidden" } },
      },
    ]),
    false,
  );
  assert.equal(
    workspaceLoadHasIdentityDenial([
      { key: "referenceNodes", outcome: { ok: true, value: "retained" } },
      {
        key: "marketQuotes",
        outcome: { ok: false, error: { code: "request", message: "API 401: unauthenticated" } },
      },
    ]),
    true,
  );
  assert.equal(
    identityDeniedWorkspaceReset(
      [
        {
          key: "resourcePoolOptions",
          outcome: { ok: false, error: { code: "request", message: "API 403: forbidden" } },
        },
      ],
      { open_count: 0 },
    ),
    null,
  );
});

test("an unauthenticated entry URL is rewritten without protected context", () => {
  const href =
    "https://nexus.example/terminal?workspace=market&task=review&gasDay=2026-09-14" +
    "&product=day-ahead&hub=NBP&route=route-1&resource=res-1&run=run-1" +
    "&strategy=strategy-1&version=version-1&theme=dark#section";
  const scrubbed = credentialFreeEntryUrl(href);

  for (const key of PROTECTED_CONTEXT_QUERY_KEYS) {
    assert.equal(new URL(scrubbed).searchParams.has(key), false, key);
  }
  assert.equal(scrubbed.includes("#"), false);
  assert.equal(new URL(scrubbed).searchParams.get("theme"), "dark");
  assert.equal(new URL(scrubbed).pathname, "/terminal");
});

test("a cold anonymous visit keeps its deep link while a lost session drops it", () => {
  // A plain anonymous visit: no error, no notice - the URL must survive so the
  // requested deep link is honoured after sign-in.
  assert.equal(shouldScrubEntryUrl(UNAUTHENTICATED_AUTH_STATE, null, null), false);
  // A session that was lost while in use, and an explicit sign-out, both scrub.
  assert.equal(
    shouldScrubEntryUrl(UNAUTHENTICATED_AUTH_STATE, "auth.error_session_expired", null),
    true,
  );
  assert.equal(
    shouldScrubEntryUrl(UNAUTHENTICATED_AUTH_STATE, null, "auth.notice_signed_out"),
    true,
  );
  // An authenticated session and an unresolved check never scrub.
  assert.equal(shouldScrubEntryUrl(AUTHENTICATED_AUTH_STATE, null, null), false);
  assert.equal(shouldScrubEntryUrl(UNRESOLVED_AUTH_STATE, null, null), false);

  // The navigation hook must use that decision rather than scrubbing on any
  // unauthenticated state.
  const navigation = source("app/hooks/useWorkspaceNavigation.ts");
  assert.match(navigation, /shouldScrubEntryUrl\(authState, authErrorKey, authNoticeKey\)/);
});

test("a real 401 through the endpoint loader reads as an anonymous visit", async () => {
  // Regression guard: the loader used to build its message with String(error),
  // which prefixes "Error: " and made every "API 401:" classifier miss - a cold
  // visit was then reported as an unreachable backend instead of a plain
  // sign-in, and the entry URL lost its deep link.
  const denied = await loadWorkspaceEndpoint<never>(
    () => {
      throw new Error("API 401: unauthenticated — No authenticated identity was presented.");
    },
    { retries: 0 },
  );

  assert.equal(denied.ok, false);
  assert.ok(!denied.ok);
  assert.match(denied.error.message, /^API 401\b/);
  assert.equal(isIdentityDeniedMessage(denied.error.message), true);
  assert.deepEqual(resolveIdentity(denied), {
    authState: UNAUTHENTICATED_AUTH_STATE,
    failureReason: "identity_absent",
  });
  // A cold anonymous visit therefore shows no error banner and keeps its URL.
  assert.equal(identityFailureKey("identity_absent"), null);
  assert.equal(shouldScrubEntryUrl(UNAUTHENTICATED_AUTH_STATE, null, null), false);

  const unreachable = await loadWorkspaceEndpoint<never>(
    () => {
      throw new TypeError("Failed to fetch");
    },
    { retries: 0 },
  );
  assert.ok(!unreachable.ok);
  assert.deepEqual(resolveIdentity(unreachable), {
    authState: UNAUTHENTICATED_AUTH_STATE,
    failureReason: "identity_unreachable",
  });
});

test("the scrubbed entry URL covers workspace, trader and selection context keys", () => {
  const covered = new Set(PROTECTED_CONTEXT_QUERY_KEYS);
  for (const key of Object.values(TRADER_CONTEXT_QUERY_KEYS)) assert.equal(covered.has(key), true, key);
  for (const key of Object.values(SELECTION_CONTEXT_QUERY_KEYS)) assert.equal(covered.has(key), true, key);

  const workspaceSearch = new URLSearchParams(workspaceTaskSearch("", "review", "review"));
  for (const key of workspaceSearch.keys()) assert.equal(covered.has(key), true, key);
});

test("the desktop identity signal stays non-secret and stable", () => {
  const resolvedAtUtc = "2026-09-14T10:00:00.000Z";
  const authenticated = identitySignalPayload("authenticated", "operator-1", resolvedAtUtc);
  assert.deepEqual(authenticated, {
    schemaVersion: 1,
    state: "authenticated",
    principalId: "operator-1",
    resolvedAtUtc,
  });

  const denied = identitySignalPayload("unauthenticated", "operator-1", resolvedAtUtc);
  assert.equal(denied.principalId, null);
  assert.equal(denied.state, "unauthenticated");
  assert.equal(identitySignalPayload("unknown", null, resolvedAtUtc).state, "unknown");

  const serialized = JSON.stringify(authenticated).toLowerCase();
  for (const banned of ["token", "cookie", "password", "secret"]) {
    assert.equal(serialized.includes(banned), false, banned);
  }
  assert.equal(IDENTITY_SIGNAL_NAME, "eurogas:identity");
});

test("the shell mounts no workspace surface before the backend confirms identity", () => {
  const shell = source("app/shell/AppShell.tsx");

  assert.match(shell, /if \(api\.authState !== "authenticated"\) \{/);
  assert.match(shell, /<SignInScreen/);
  // The auth gate sits after the release-compatibility blocker and before the shell.
  assert.ok(
    shell.indexOf("isBlockingCompatibility") < shell.indexOf('api.authState !== "authenticated"'),
  );
  assert.ok(shell.indexOf("<SignInScreen") < shell.indexOf("<WorkspaceTopBar"));
  assert.ok(shell.indexOf("<SignInScreen") < shell.indexOf("<WorkspaceRenderer"));
  // The shell mounts no surface of its own any more: every page composes through the
  // renderer, which sits behind the gate (conflicting register C9).
  assert.equal(shell.includes("<NetworkWorkspace"), false);
  // The sign-in screen is wired to store actions only.
  assert.match(shell, /onOidcSignIn=\{\(\) => void api\.signIn\(\)\}/);
  assert.match(shell, /onDevLogin=\{\(username, password\) => void api\.login\(username, password\)\}/);
  assert.match(shell, /onRetryIdentity=\{\(\) => void api\.bootstrapIdentity\(\)\}/);
});

test("every workspace loader, poll and stream is gated on the identity gate", () => {
  const store = source("stores/api.ts");

  // Eight gated entry points: six workspace loaders, the task-scoped Analysis Snapshot read the
  // reproducibility picker uses, and the snapshot *write*, which is gated the same way. The
  // count is asserted so a new loader or writer cannot be added without a gate.
  assert.equal(store.match(/isIdentityGateOpen\(get\(\)\.authState\)/g)?.length, 8);
  for (const action of [
    "fetchWorkspace: async",
    "retryFailedWorkspaceEndpoints: async",
    "refreshMarketData: async",
    "refreshMonitoring: async",
    "fetchReviewContext: async",
    "fetchAnalysisSnapshots: async",
    "recordAnalysisSnapshot: async",
    "subscribeDecisionStreams: () =>",
  ]) {
    assert.ok(store.includes(action), action);
  }
  // Identity resolves alone; it is not a workspace loader any more.
  assert.equal(store.includes('["me", api.me]'), false);
  assert.equal(store.includes('me: "currentUser"'), false);
  assert.equal(store.includes("currentUser: (slices.me"), false);
  assert.match(store, /bootstrapIdentity: async \(\) => \{/);
  assert.match(store, /loadWorkspaceEndpoint\(api\.me, \{/);
  assert.match(store, /loadWorkspaceEndpoint\(api\.authStatus, \{/);
  assert.match(store, /login: async \(username, password\) => \{/);
});

test("the runtime resolves identity first and never polls before authentication", () => {
  const runtime = source("app/hooks/useWorkspaceRuntime.ts");

  assert.match(runtime, /void bootstrapIdentity\(\)/);
  assert.equal(runtime.includes("void fetchWorkspace()"), true);
  assert.equal(runtime.match(/if \(!authenticated\) return;/g)?.length, 3);
  assert.match(runtime, /const authenticated = isIdentityGateOpen\(authState\);/);
  assert.match(runtime, /MARKET_REFRESH_INTERVAL_MS = 10_000/);
});

test("navigation and context restore nothing protected while unauthenticated", () => {
  const navigation = source("app/hooks/useWorkspaceNavigation.ts");
  const trader = source("app/context/useTraderContext.ts");
  const selection = source("app/context/useSelectionContext.ts");
  const controller = source("app/hooks/useAppController.ts");

  assert.match(navigation, /export function workspaceFromLocation\(\): WorkspacePageId \{/);
  assert.match(navigation, /if \(!isIdentityGateOpen\(useApiStore\.getState\(\)\.authState\)\)/);
  assert.match(navigation, /if \(!shouldScrubEntryUrl\(authState, authErrorKey, authNoticeKey\)\) return;/);
  assert.match(navigation, /credentialFreeEntryUrl\(window\.location\.href\)/);
  assert.match(navigation, /window\.history\.replaceState\(window\.history\.state, "", nextUrl\)/);
  assert.match(trader, /export function useTraderContext\(\) \{/);
  assert.match(selection, /export function useSelectionContext\(\) \{/);
  assert.match(trader, /if \(!isIdentityGateOpen\(useApiStore\.getState\(\)\.authState\)\)/);
  assert.match(selection, /if \(!isIdentityGateOpen\(useApiStore\.getState\(\)\.authState\)\)/);
  assert.match(controller, /useWorkspaceNavigation\(\)/);
  assert.match(controller, /useTraderContext\(\)/);
  assert.match(controller, /useSelectionContext\(\)/);
  assert.match(controller, /authState: api\.authState/);
});

test("logout clears client-stored credentials and keeps non-secret preferences", () => {
  const client = source("api/client.ts");
  const store = source("stores/api.ts");

  const clearBlock = /export function clearStoredAuth\(\): void \{[\s\S]*?\n\}/.exec(client)?.[0];
  assert.ok(clearBlock, "clearStoredAuth must exist");
  assert.match(clearBlock, /clearDesktopSession\(\)/);
  assert.match(clearBlock, /localStorage\.removeItem\(API_TOKEN_STORAGE_KEY\)/);
  assert.match(clearBlock, /localStorage\.removeItem\(PRINCIPAL_STORAGE_KEY\)/);
  for (const preserved of [
    "API_BASE_STORAGE_KEY",
    "saveApiBaseUrl",
    "theme",
    "language",
    "mapTile",
  ]) {
    assert.equal(clearBlock.includes(preserved), false, preserved);
  }

  assert.match(store, /signOut: async \(\) => \{[\s\S]*?clearStoredAuth\(\)/);
  assert.match(store, /resetIdentityScopedCaches\(DEFAULT_MONITORING_SUMMARY\)/);
  assert.match(store, /authNoticeKey: "auth.notice_signed_out"/);
  // Logout revokes server-side first, so stored auth is cleared only afterwards.
  assert.ok(store.indexOf("api.logout({ signal })") < store.indexOf("clearStoredAuth()"));
});

test("the sign-in screen is presentational and holds no hardcoded credential", () => {
  const screen = source("components/SignInScreen.tsx");

  assert.match(screen, /devLoginAvailable && \(/);
  assert.match(screen, /const devLoginAvailable = devLoginOffered\(authStatus\);/);
  assert.match(screen, /onOidcSignIn/);
  assert.match(screen, /onDevLogin\(username, password\)/);
  assert.match(screen, /authErrorKey && \(/);
  assert.match(screen, /role="alert"/);
  assert.equal(screen.includes("defaultValue"), false);
  assert.equal(screen.includes("dangerouslySetInnerHTML"), false);
  for (const banned of ["localStorage", "fetch(", "useApiStore", "api.", "process.env"]) {
    assert.equal(screen.includes(banned), false, banned);
  }
  for (const banned of ["WorkspaceTopBar", "NetworkWorkspace", "MarketTerminal", "WorkspaceTabs"]) {
    assert.equal(screen.includes(banned), false, banned);
  }
  assert.equal(screen.includes('role="tab"'), false);
});

test("auth strings exist in both locales, differ, and carry no placeholder characters", () => {
  const en = json("i18n/en.json");
  const zh = json("i18n/zh.json");
  const authKeys = Object.keys(en).filter((key) => key.startsWith("auth."));
  const referenced = new Set(
    [...source("components/SignInScreen.tsx").matchAll(/\bt\(\s*"([^"]+)"/g)].map(
      (match) => match[1],
    ),
  );

  assert.ok(authKeys.length >= 20, `expected the sign-in vocabulary, found ${authKeys.length}`);
  for (const key of authKeys) {
    assert.equal(typeof zh[key], "string", key);
    assert.ok(en[key].trim() && zh[key].trim(), key);
    assert.notEqual(en[key], zh[key], key);
    assert.equal(en[key].includes("?"), false, key);
    assert.equal(zh[key].includes("?"), false, key);
    assert.equal(zh[key].includes("\ufffd"), false, key);
  }
  for (const key of referenced) {
    assert.ok(key in en, `en is missing ${key}`);
    assert.ok(key in zh, `zh is missing ${key}`);
  }
  assert.equal(Object.keys(en).length, Object.keys(zh).length);
});

test("error keys produced by the gate are translation-backed", () => {
  const en = json("i18n/en.json");
  const keys = new Set([
    identityFailureKey("identity_denied"),
    identityFailureKey("identity_unreachable"),
    devLoginErrorKey("API 401: invalid_credentials — nope"),
    devLoginErrorKey("API 403: identity_not_provisioned — nope"),
    devLoginErrorKey("API 503: dev_login_disabled — nope"),
    devLoginErrorKey("TypeError: Failed to fetch"),
    oidcSignInErrorKey("API 503: oidc_not_configured"),
    oidcSignInErrorKey("boom"),
  ]);

  for (const key of keys) assert.ok(key && key in en, String(key));
  // A cold visit intentionally has no error banner.
  assert.equal(identityFailureKey("identity_absent"), null);
});

test("the desktop shell is only told to reveal the window after identity resolves", () => {
  const signal = source("app/hooks/useIdentitySignal.ts");
  const client = source("api/client.ts");
  const host = source("app/host/hostCapabilities.ts");

  // The signal hook stays silent while identity is unresolved, then reports once.
  assert.match(signal, /if \(authState !== "unknown"\)/);
  assert.match(signal, /notifyDesktopClientReady\(\)/);

  // The transport keeps the exported bridge, is desktop-only and fails soft...
  assert.match(client, /export async function notifyDesktopClientReady/);
  assert.match(client, /if \(!isDesktopShell\) return;/);
  assert.match(client, /tryHostCommand\(HOST_COMMANDS\.notifyClientReady\)/);

  // ...while the native command name, the desktop detection and the fail-soft
  // behaviour live in the single HostCapabilities boundary (Architecture V2).
  assert.match(host, /notifyClientReady: "notify_client_ready"/);
  assert.match(host, /"__TAURI_INTERNALS__" in window/);
  assert.match(host, /if \(kind !== "desktop" \|\| !isHostCommand\(command\)\) return null;/);
  assert.match(host, /catch \{\s*return null;\s*\}/);
});
