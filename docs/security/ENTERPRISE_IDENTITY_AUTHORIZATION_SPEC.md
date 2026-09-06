# Enterprise Identity and Authorization Specification — CR-10

Status: normative for the CR-10 security milestone. Repository behavior is
the authority; this document records the audited current state and the
architecture accepted by DSH Pro for single-organization enterprise security.

## 1. Scope and deployment model

Target: **one enterprise organization, many authenticated professionals**,
with one or more approved OIDC identity providers. No customer tenants,
billing accounts, public signup, SCIM provisioning, cross-tenant SaaS
abstractions, or execution/approval permissions are introduced. Future tenant
extension remains possible but is deliberately not paid for now.

## 2. Current-state audit (2026-09-07)

### 2.1 Principal model

`identity_principals` already stores local USER/SERVICE principals with
`principal_id`, `name`, `display_name`, one `role`, `status`, `data_scopes`,
timestamps. Gaps: no email, no identity source, no plural roles, no last login.

### 2.2 Local identity model

Local principals are real rows, not pseudo-users. Keys are owned by
principals (`identity_api_keys.principal_id` FK).

### 2.3 API-key model

Bearer format `nexus_<key_id>_<secret>`; plaintext returned once; SHA-256 hash
stored. Keys support create/list/rotate/revoke/expire. Gaps: no `scopes`
field, no `created_by`, no public admin surface (internal token only).

### 2.4 Current OIDC capabilities

`security/oidc.py` validates RS256 access tokens with issuer, audience, exp,
nbf, `sub`, kid, JWKS discovery, 300s cache and signature verification. It is
a machine-to-machine bearer path only. **No authorization-code flow, PKCE,
state, nonce, token exchange, browser session, logout, or desktop callback.**

### 2.5 Authorization mechanism

`security/permissions.py` maps every public path to a coarse permission:
PUBLIC/READ VIEWER+, GOVERNED ANALYST+, OPERATOR OPERATOR+. Role checks are
centralized in one dependency. Gap: no fine-grained permissions, no
REVIEWER role, no ADMIN-only identity surface in the public API.

### 2.6 Role definitions

VIEWER, ANALYST, OPERATOR, ADMIN exist. Missing REVIEWER. Roles are a single
string; data scopes are already separate JSON.

### 2.7 Data-scope behavior

CR-09 propagates row/derived-result filtering across market, physical,
storage, LNG, route candidates, strategy/shadow evidence and reports.
Principal data scopes are backend-owned and fail closed for unknown families.

### 2.8 Frontend auth state

The Web client stores the deployment API token and operator principal in
`localStorage` and sends them as headers. This is the anti-pattern this
milestone replaces for human users. Context/settings localStorage use remains
for non-secret preferences.

### 2.9 Desktop auth behavior

Tauri shell has no login flow. It reads a deployment JSON and talks to the
backend over `/api`; authentication is the same localStorage token path.
Capabilities are already minimal (`core:default`), CSP has no `unsafe-eval`.

### 2.10 SSE auth

`EventSource` uses `?api_key=` query channel because it cannot set headers.
The channel is documented and the token is never logged by the application.
Gap: no session-cookie streaming path and no principal status/scope
revalidation inside the stream.

### 2.11 Credential-write security

Provider credential routes are OPERATOR-gated in release. Plaintext keys are
write-only, Fernet-encrypted at rest with redacted previews. No plaintext
return.

### 2.12 Missing audit coverage

Audit exists for identity lifecycle, review decisions, policy denials, LLM
calls, source ingestion and CR-09 operator actions. Gaps: login/logout,
session revocation, authorization denials, strategy freeze/retire,
shadow lifecycle, explicit `permission`/`correlation_id`/`client_type`
columns.

### 2.13 Insecure token/storage patterns

- Web stores long-lived deployment API token in localStorage.
- No human session model.
- No CSRF/origin guard for future cookie authentication.

### 2.14 Current production blockers

- No interactive SSO; users are either a shared deployment token or a
  machine identity.
- No REVIEWER role.
- No admin access center.
- No session/revocation/de-provisioning lifecycle.

## 3. Principal model

`identity_principals` is extended, never replaced:

```text
Principal
  principal_id, principal_type (USER|SERVICE), name, display_name,
  email (nullable), status (ACTIVE|DISABLED|LOCKED), identity_source
  (LOCAL|OIDC), roles (list, effective), data_scopes (list),
  created_at_utc, updated_at_utc, last_login_at_utc
```

`role` remains the highest effective role for backward compatibility and is
maintained transactionally whenever `roles` changes. Authorization consumes
`roles`; data entitlement consumes `data_scopes`. A role string never encodes
a data scope.

## 4. External identity link

New `identity_external_ids` maps OIDC identities to local principals:

```text
ExternalIdentity
  identity_id, principal_id FK, issuer, subject, provider_id,
  email, display_name, created_at_utc, last_seen_at_utc
```

Canonical key is **unique(issuer, subject)**. Email is metadata only and may
change. A subject is never re-bound to another principal while an active link
exists.

## 5. Provisioning policy

Default: **PRE-PROVISIONED**. A verified OIDC identity with no local link is
denied with `external_identity_not_provisioned`.

Optional JIT is allowed only when both:

- `EUROGAS_NEXUS_OIDC_PROVISIONING_MODE=approved_domain`;
- the token email domain is in `EUROGAS_NEXUS_OIDC_APPROVED_DOMAINS`.

JIT-created principals get **VIEWER and no commercial scopes**; optional
explicit group mappings may add roles/scopes. Unknown groups grant nothing.
Local explicit grants always take precedence over group mappings. This is the
documented resolution order:

```text
local explicit grants
  > explicit local revocations
  > approved external group mappings
  > deny
```

## 6. OIDC provider configuration

Provider-neutral environment configuration:

```text
EUROGAS_NEXUS_OIDC_ISSUER            https (discovery required)
EUROGAS_NEXUS_OIDC_CLIENT_ID         public client id
EUROGAS_NEXUS_OIDC_AUDIENCE          optional; defaults to client id
EUROGAS_NEXUS_OIDC_CLIENT_SECRET     optional; only for confidential token endpoint
EUROGAS_NEXUS_OIDC_ALLOW_HTTP        false in production
EUROGAS_NEXUS_OIDC_ROLE_CLAIM        default roles
EUROGAS_NEXUS_OIDC_SCOPE_CLAIM       default entitlements
EUROGAS_NEXUS_OIDC_PROVISIONING_MODE preprovisioned | approved_domain
EUROGAS_NEXUS_OIDC_APPROVED_DOMAINS  comma separated, required only for JIT
EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP   JSON {"group-name": "ROLE"}
EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP  JSON {"group-name": ["EEX", ...]}
EUROGAS_NEXUS_OIDC_REDIRECT_URI      backend callback; defaults to /api/auth/oidc/callback
```

Secrets are deployment-managed and never returned to clients.

## 7. Token validation

Every OIDC token (access token for machine clients, ID token for interactive
login) is validated for signature, RS256 only, `kid`, issuer, audience,
expiry, nbf, non-empty `sub`. JWKS is fetched from provider discovery,
cached for 300 seconds, and refreshed on unknown `kid`. `alg=none`, HS256, or
mismatched issuer/audience fail closed. No provider-specific core logic.

## 8. Interactive login: Authorization Code + PKCE

Browser flow:

1. `GET /api/auth/oidc/login` creates a one-time authorization state in
   PostgreSQL (`oidc_authorization_states`), stores a hashed PKCE verifier
   and a nonce, then redirects to the provider authorization endpoint.
2. Provider redirects to `GET /api/auth/oidc/callback` with `code` and
   `state`. The state row is consumed exactly once (SKIP LOCKED/unique
   semantics), TTL is 5 minutes, and state mismatch is terminal.
3. Backend exchanges `code + code_verifier` at the token endpoint.
4. ID token is validated against the same issuer/audience/RS256 rules and
   `nonce`.
5. External identity (issuer + subject) resolves to an ACTIVE local
   principal; otherwise provisioning policy applies.
6. A random 256-bit session token is generated; only its SHA-256 digest is
   persisted in `user_sessions`. The browser receives an
   `HttpOnly; SameSite=Lax; Path=/; Secure` session cookie.
7. `GET /api/me` returns safe capability information.

No refresh tokens or access tokens are stored in browser storage. No client
secret is embedded in the Web client. Logout revokes the current session and
clears the cookie.

## 9. Web authentication design

Chosen: **backend-managed session cookie** for interactive Web use. The
existing deployment API key remains available in Settings for controlled
operational/service access and SDK/CLI compatibility, but human login does
not depend on it. The Web client sends cookies with `credentials:"include"`
and no longer places human OIDC tokens in localStorage.

CSRF protection: state-changing requests from a cookie-authenticated browser
must pass an origin/referrer check (browser-origin header must match the
request origin) plus the same-site cookie. `/api/me` also returns a
session-bound CSRF token which the client sends as `X-Eurogas-CSRF` on
mutations. GET/SSE are exempt from the CSRF token but not from authentication
or entitlement.

## 10. Desktop/Tauri authentication design

Chosen: **system browser + loopback redirect + backend token exchange**.
The Tauri shell opens the provider login in the system browser with a
loopback `redirect_uri` (`http://127.0.0.1:<port>/callback`), listens for the
authorization code on a local TCP socket, closes the listener after exactly
one callback, then calls `POST /api/auth/oidc/desktop/token` with
`code + code_verifier + expected redirect_uri`. The backend validates the
one-time state/PKCE and returns a **short-lived opaque access token**.
The desktop frontend holds that token in memory only (never localStorage)
and sends it as a bearer header. Logout drops the in-memory token.

Windows and Linux both use loopback; no custom URI scheme registration is
required. The Tauri command never exposes filesystem/shell access beyond the
existing deployment-config command, and the loopback listener is bound to
`127.0.0.1` with a single-use timeout.

## 11. Session/token model

`user_sessions`:

```text
session_id, principal_id FK, session_token_hash, created_at_utc,
last_seen_at_utc, expires_at_utc, revoked_at_utc, client_type,
client_label (bounded, non-secret)
```

Session lifetime default 12 hours, idle timeout 2 hours, absolute max 24
hours. Every authenticated request checks: session exists, not expired, not
revoked, owner ACTIVE. Last-seen is updated at most once per 60 seconds.
Logout revokes the current session; disabling a principal revokes all
sessions immediately. Session secrets are never returned after creation and
never logged.

## 12. API-key/service credential model

`identity_api_keys` is extended with `scopes` (explicit permission list),
`created_by`, and `key_prefix` remains the only visible secret prefix.
Service principals remain the intended owner. Rules:

- plaintext shown exactly once at creation/rotation;
- only SHA-256 digest persisted (existing compatibility policy; ASVS mapping
  marks key hashing PARTIAL pending keyed-hash migration);
- expiration and revocation stop authentication immediately;
- a disabled owner stops every key immediately even if the key row is not
  revoked;
- full secret is never returned, exported, logged, or audited.

## 13. Authorization model

RBAC for job function + data scopes for commercial entitlement. New
permissions include:

```text
market.read, portfolio.read, portfolio.write, strategy.read,
strategy.create, strategy.edit, strategy.freeze, strategy.retire,
strategy.shadow.manage, scenario.create, optimization.run,
review.read, review.record, source.read, source.run, source.backfill,
source.credentials.write, source.certification.manage, runtime.read,
identity.read, identity.manage, api_keys.manage, audit.read, me.read
```

`security/authorization.py` is the single evaluator. Route enforcement uses
the existing coarse registry for role floors and fine-grained permission
checks on sensitive handlers. Unknown permission, role, scope, or principal
fails closed.

## 14. Role/permission matrix

| Permission | VIEWER | ANALYST | REVIEWER | OPERATOR | ADMIN |
|---|---|---|---|---|---|
| market.read | ✓ | ✓ | ✓ | ✓ | ✓ |
| portfolio.read | ✓ | ✓ | ✓ | ✓ | ✓ |
| strategy.read | ✓ | ✓ | ✓ | ✓ | ✓ |
| review.read | ✓ | ✓ | ✓ | ✓ | ✓ |
| runtime.read | ✓ | ✓ | ✓ | ✓ | ✓ |
| portfolio.write | | ✓ | | ✓ | ✓ |
| strategy.create/edit/freeze | | ✓ | | | ✓ |
| strategy.shadow.manage | | ✓ | | ✓ | ✓ |
| scenario.create | | ✓ | | | ✓ |
| optimization.run | | ✓ | | | ✓ |
| review.record | | | ✓ | | ✓ |
| source.run/backfill/credentials/certification | | | | ✓ | ✓ |
| identity.read | | | | | ✓ |
| identity.manage/api_keys.manage/audit.read | | | | | ✓ |
| me.read | ✓ | ✓ | ✓ | ✓ | ✓ |

ADMIN does **not** automatically receive every commercial data scope; data
scopes are assigned separately. No TRADER_EXECUTOR or TRADE_APPROVER exists.

## 15. Data-scope model

`data_scopes` remain canonical source-family grants: `PUBLIC` baseline is
implicit for every active principal; `EEX`, `ICE_OCM`, `TRAYPORT`, `ICIS`,
`PLATTS`, `ARGUS`, `KPLER`, `BROKER_X` require explicit grants; `*` is an
explicit all-families grant. Provider names are values, not hard-coded
branches in authorization logic.

## 16. Derived-result entitlement enforcement

CR-09 filtering remains authoritative. Sensitive read surfaces derive source
requirements from persisted lineage (`manifest_json.evidence.source_systems`,
run `source_refs`, route `source_systems`) and never trust a client-supplied
list. Mixed-source results default to requiring all contributing restricted
families; no partial value redaction is implemented, so the result is hidden
or denied rather than partially exposed.

## 17. Deprovisioning/revocation

- Disabled principal: new OIDC login denied; sessions revoked; API-key
  authentication denied because owner status is checked on every request;
  writes denied immediately; audit/history rows preserved.
- Re-enable is explicit and does not restore revoked sessions.
- Historical `created_by`/actor strings remain.

## 18. Audit architecture

`audit_events` is extended with `permission`, `correlation_id`,
`client_type`, `before_summary`, `after_summary` (all non-secret JSON/text).
Audit is append-only through all public/internal application APIs; no update
or delete route exists. Admin may read bounded, filterable audit data.
Retention pruning remains operator-controlled and dry-run by default.

Audited actions: auth login/logout/revocation; identity enable/disable,
role/scope changes; API-key lifecycle; strategy/version/shadow lifecycle;
source run/backfill/credential/certification; review recording; sensitive
denials.

Audit never contains tokens, key secrets, provider credentials, raw licensed
payloads, or full financial contract content.

## 19. AI/LLM entitlement

Before any provider call the backend resolves the principal, checks the
`analysis.query` capability, computes source entitlement from the actual
snapshot, and applies the existing financial-field redaction. A denied
source blocks provider invocation with a generic error. LLM endpoints never
become an entitlement bypass.

## 20. SSE/streaming hardening

Streams accept the deployment API key via the documented EventSource query
channel or an existing session cookie with `withCredentials`. Each SSE
connection re-resolves principal status/scope at connection time and closes
on `DISABLED`/`REVOKED`. Query tokens are never logged.

## 21. CORS/CSRF/CSP

- Release CORS origins come from `EUROGAS_NEXUS_CORS_ORIGINS` plus local
  loopback/tauri origins; never `*` with credentials.
- Cookie-authenticated mutations require origin match plus session CSRF
  token.
- Tauri CSP keeps `script-src 'self'` without `unsafe-eval`; connect-src
  remains explicit.
- Development convenience is separated from release profile.

## 22. Tauri hardening

Capability file remains `core:default` only. No shell, fs, http, opener or
keychain plugin permissions are added. The new auth command is an internal
Rust command, not exposed as generic shell. CSP and deployment-config command
remain least privilege. System-browser launch and loopback listen are the only
new desktop behaviors.

## 23. Observability and abuse protection

Counters for login success/failure, OIDC verification failures,
authorization denials, entitlement denials, session revocations and API-key
usage are exposed through the CR-09 metrics endpoint. Login callback and
identity-administration endpoints get bounded in-memory rate limiting
(short-window fixed counter, no user-email labels). Normal analytical reads
are not rate limited.

## 24. Performance

Authorization context is one principal row per request (no external lookup
for local identities). OIDC discovery/JWKS is cached for 300 seconds.
`/api/me` performs one session+principal query. Audit insertion is one
appended row. Benchmark coverage is added in
`scripts/ops/security_benchmark.py`.

## 25. Accepted risk and limitations

- API keys retain SHA-256 hashing for compatibility; a keyed-hash migration
  is deferred and ASVS mapping marks it PARTIAL.
- OIDC live enterprise acceptance is pending until an approved IdP
  configuration is supplied; cryptographic local fixtures validate the flow.
- No SCIM. JIT is optional and off by default.
- Session revocation uses DB checks, not distributed cache invalidation.

## 26. Security documentation map

- `docs/security/ASVS_CONTROL_MAPPING.md` — implemented/partial/external/
  not-applicable mapping.
- Runbooks: `SSO_OIDC.md`, `USER_ACCESS.md`, `API_KEYS.md`,
  `SECURITY_AUDIT.md`, `ACCESS_REVOCATION.md`.
- `docs/architecture/AUTH_AUDIT_CONTRACT.md` updated from "SSO deferred" to
  current delivered scope.
