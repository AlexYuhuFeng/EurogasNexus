/**
 * Authentication-first entry policy.
 *
 * Pure, dependency-free decisions shared by the API store, the shell and the
 * navigation guards. Nothing here inspects a credential or grants access: the
 * backend owns identity, the client only decides what may be mounted or
 * requested for a given identity state.
 */

import {
  AUTHENTICATED_AUTH_STATE,
  UNAUTHENTICATED_AUTH_STATE,
  isIdentityDeniedMessage,
  isIdentityGateOpen,
  type AuthState,
  type WorkspaceLoaderOutcome,
} from "./workspaceLoading.ts";

/** Safe, non-secret view of `GET /api/auth/status`. */
export interface AuthStatusSnapshot {
  oidcConfigured: boolean;
  sessionCookiePresent: boolean;
  profile: string | null;
  devLoginAvailable: boolean;
}

export const UNKNOWN_AUTH_STATUS: AuthStatusSnapshot = {
  oidcConfigured: false,
  sessionCookiePresent: false,
  profile: null,
  devLoginAvailable: false,
};

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/**
 * Normalise `GET /api/auth/status` data. Unknown or malformed fields degrade to
 * the safest reading: no SSO, no development sign-in.
 */
export function authStatusSnapshot(data: unknown): AuthStatusSnapshot {
  if (!data || typeof data !== "object") return UNKNOWN_AUTH_STATUS;
  const payload = data as Record<string, unknown>;
  return {
    oidcConfigured: payload.oidc_configured === true,
    sessionCookiePresent: payload.session_cookie === true,
    profile: text(payload.profile),
    devLoginAvailable: payload.dev_login === true,
  };
}

/**
 * Development credential sign-in is offered only when the deployment's own
 * `/api/auth/status` advertises it. No client-side environment check can enable it.
 */
export function devLoginOffered(status: AuthStatusSnapshot): boolean {
  return status.devLoginAvailable;
}

export type IdentityFailureReason =
  | "identity_absent"
  | "identity_denied"
  | "identity_unreachable";

export interface IdentityResolution {
  authState: AuthState;
  failureReason: IdentityFailureReason | null;
}

/**
 * A 401 carrying the backend's `unauthenticated` code means no credential was
 * presented at all: that is an ordinary cold visit to the sign-in screen, not a
 * session the operator lost.
 */
export function isNoCredentialMessage(message: string): boolean {
  return /^API 401\b/.test(message) && message.includes("unauthenticated");
}

/**
 * Decide the auth state from a `GET /api/me` outcome. A denial is an explicit
 * "unauthenticated"; any other failure also fails closed, because access must
 * never be inferred from a request that did not succeed.
 */
export function resolveIdentity(
  outcome: WorkspaceLoaderOutcome<unknown>,
): IdentityResolution {
  if (outcome.ok) return { authState: AUTHENTICATED_AUTH_STATE, failureReason: null };
  const message = outcome.error.message;
  if (!isIdentityDeniedMessage(message)) {
    return { authState: UNAUTHENTICATED_AUTH_STATE, failureReason: "identity_unreachable" };
  }
  return {
    authState: UNAUTHENTICATED_AUTH_STATE,
    failureReason: isNoCredentialMessage(message) ? "identity_absent" : "identity_denied",
  };
}

export const SESSION_EXPIRED_KEY = "auth.error_session_expired";
export const IDENTITY_UNREACHABLE_KEY = "auth.error_identity_unreachable";

/** `null` means the sign-in screen shows no error banner: a cold visit is not a failure. */
export function identityFailureKey(reason: IdentityFailureReason | null): string | null {
  if (reason === "identity_denied") return SESSION_EXPIRED_KEY;
  if (reason === "identity_unreachable") return IDENTITY_UNREACHABLE_KEY;
  return null;
}

/** Successful `POST /api/dev/auth/login` payload (development deployments only). */
export interface DevLoginIdentity {
  authenticated: boolean;
  principal_id: string;
  display_name: string;
  role: string;
  permissions: string[];
}

/**
 * Provisional identity projection used between a successful development login
 * and the authoritative `GET /api/me` read. It only fills display fields so the
 * shell has a name to show; it never grants access.
 */
export function devLoginCurrentUser(data: DevLoginIdentity) {
  return {
    principal_id: data.principal_id,
    name: data.display_name,
    display_name: data.display_name,
    principal_type: "user",
    role: data.role,
    roles: [data.role],
    email: null,
    identity_source: "dev-credentials",
    status: "active",
    data_scopes: [] as string[],
    permissions: [...(data.permissions ?? [])],
    auth_method: "dev_login",
    csrf_token: null,
  };
}

/**
 * Re-bootstrapping identity must not unmount a working terminal, so an existing
 * authenticated state is preserved; every other state is re-resolved.
 */
export function bootstrapStartState(current: AuthState): AuthState {
  return isIdentityGateOpen(current) ? current : "unknown";
}

const DEV_LOGIN_ERROR_KEYS: Record<string, string> = {
  invalid_credentials: "auth.error_invalid_credentials",
  identity_not_provisioned: "auth.error_not_provisioned",
  dev_login_disabled: "auth.error_dev_login_disabled",
};

/**
 * Localise a backend auth failure by its machine code. Codes are matched before
 * HTTP status so a 403 provisioning failure never reads as a bad password. An
 * unrecognised 503 stays generic: it may mean the runtime DB, not a disabled
 * development login.
 */
export function devLoginErrorKey(message: string): string {
  for (const [code, key] of Object.entries(DEV_LOGIN_ERROR_KEYS)) {
    if (message.includes(code)) return key;
  }
  if (/^API 401\b/.test(message)) return "auth.error_invalid_credentials";
  if (/^API 403\b/.test(message)) return "auth.error_not_provisioned";
  return "auth.error_generic";
}

/** Localise an SSO start failure; an unconfigured provider is not an error of the operator. */
export function oidcSignInErrorKey(message: string): string {
  if (message.includes("oidc_not_configured")) return "auth.sso_unavailable";
  return "auth.error_sso_failed";
}

/**
 * Query parameters that carry workspace, trader or selection context. They must
 * survive only an authenticated session: an unauthenticated entry point is
 * rewritten without them so browser history cannot restore a protected view.
 */
export const PROTECTED_CONTEXT_QUERY_KEYS: readonly string[] = [
  "workspace",
  "task",
  "route",
  "resource",
  "run",
  "strategy",
  "version",
  "gasDay",
  "product",
  "hub",
];

/** Rewrite an entry URL to a credential-free one, keeping unrelated parameters. */
export function credentialFreeEntryUrl(href: string): string {
  const next = new URL(href);
  PROTECTED_CONTEXT_QUERY_KEYS.forEach((key) => next.searchParams.delete(key));
  next.hash = "";
  return next.toString();
}

/**
 * Whether an unauthenticated entry must drop its protected context.
 *
 * Only a finished denial qualifies: an explicit sign-out (notice) or a session
 * that was lost while in use (error). A plain anonymous visit keeps its
 * `?workspace=`/`?task=` because nothing is mounted while the gate is closed,
 * and the requested deep link is then honoured once sign-in succeeds instead of
 * silently dropping the visitor on the default landing page.
 */
export function shouldScrubEntryUrl(
  authState: AuthState,
  authErrorKey: string | null,
  authNoticeKey: string | null,
): boolean {
  if (isIdentityGateOpen(authState)) return false;
  if (authState === UNAUTHENTICATED_AUTH_STATE) {
    return Boolean(authErrorKey || authNoticeKey);
  }
  // Unresolved identity: still checking, so nothing has been denied yet.
  return false;
}

export const IDENTITY_SIGNAL_NAME = "eurogas:identity";

/**
 * Desktop startup signal. The Tauri shell cannot see React state, so identity
 * resolution is published on `window.__EUROGAS_IDENTITY__` and re-emitted as the
 * `eurogas:identity` custom event after every resolution change. The payload
 * carries no credential and no token.
 */
export interface IdentitySignalPayload {
  schemaVersion: number;
  state: AuthState;
  principalId: string | null;
  resolvedAtUtc: string;
}

export function identitySignalPayload(
  state: AuthState,
  principalId: string | null,
  resolvedAtUtc: string,
): IdentitySignalPayload {
  return {
    schemaVersion: 1,
    state,
    principalId: isIdentityGateOpen(state) ? principalId : null,
    resolvedAtUtc,
  };
}
