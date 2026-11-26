# Eurogas Nexus: security review (CISO-office pre-onboarding assessment)

Reviewer angle: AppSec code review, security architecture and threat model, IT risk/compliance (DORA, NIS2, ISO 27001, SOC 2), penetration-test planning, insider-threat and market-abuse controls.
Scope: `/home/user/EurogasNexus-merge` @ `3a1f81a`; live demo probed read-only with the demo accounts (logins and GETs only, nothing written, no load).
Labels: **CONFIRMED** means I verified it in code and, where marked, on the live demo. **SUSPECTED** means the code points that way but I did not prove it end to end.

---

## 1. Verdict (five sentences)

The engineering hygiene is well above what we usually see from a single-vendor tool. It has scrypt passwords, uniform login refusal with per-account back-off, an HttpOnly/Secure/SameSite session with an origin-and-token CSRF guard, RS256-pinned OIDC, the desktop app using RFC 8252 with tokens held in memory, hash-pinned Python locks, SHA-pinned base images, pip-audit/cargo-audit, an SBOM, build attestations, and external LLMs hard-disabled in `release`.
The weak layer is **authorisation and data segregation**. Book/entity isolation is **off by default**, several commercial read families sit outside the commercial-data boundary, the route registry ignores the HTTP method for path families (so write safety depends on each handler remembering a check), and one static deployment token resolves to an OPERATOR with `*` scope over every book and every licensed dataset.
Governance controls exist as application conventions rather than enforced controls. The audit trail is "append-only" only by convention: the app's database user owns it and an operator can prune it. One administrator can switch off four-eyes. There is no MFA and no SIEM export.
A regulated trading house could run it today on an isolated network for a single desk with SSO in front. It is **not acceptable** for multi-desk or multi-entity use, for Chinese-wall separation, or for licensed Trayport/ICE/EEX data until the High findings below are closed.
Most fixes are code-sized (days). Audit immutability, the database role split, MFA and key management are architectural controls and need an ADR.

---

## 2. Threat model summary

**Assets (ranked):**
1. Positions, contracts, books, credit lines, trader mandates, hedge bands and firm marks. This is MNPI-adjacent, commercially secret data.
2. Licensed market data (Trayport/ICE/EEX). Redistribution breaches the licence.
3. Decision cases and AI findings. They reveal trading intent.
4. Integrity of prices and marks that traders act on.
5. Identity store, API keys and provider credentials (Fernet-encrypted under one master key).
6. The audit trail as regulatory evidence (REMIT record-keeping, MAR surveillance support).
7. Personal data: names, e-mails, IP addresses, session telemetry.

**Actors:**
- A curious or malicious insider in another desk or entity (Chinese-wall breach).
- A platform administrator or IT operator who should not see commercial data.
- An ops or source-operations engineer holding OPERATOR.
- A holder of a leaked static token (CI logs, SDK scripts, `.env` files).
- An external attacker on the corporate network.
- A poisoned upstream source (news feeds, REMIT UMM text, contract PDFs) aimed at the AI features or at CSV exports.
- A compromised supply-chain component.

**Trust boundaries:**
- Browser or desktop to Caddy/uvicorn.
- API to PostgreSQL. A single superuser credential is used for everything.
- API to external sources and the LLM provider.
- API to the SMTP relay.
- SDK, CLI and MCP using static tokens.
- Gateway (SAML/Kerberos) headers into the API, held by a shared secret.

**Top abuse cases:**
- (A1) A trader at entity NL reads entity UK's books, credit exposure and mandates. **Works today; CONFIRMED on the demo.**
- (A2) A platform admin, who per the design must not see commercial data, reads decision cases and analysis snapshots. **CONFIRMED.** The admin can also route every open alert, including limit breaches, to an external e-mail address. **CONFIRMED in code.**
- (A3) A holder of the deployment token reads everything and performs OPERATOR acts under any actor name they type.
- (A4) An OPERATOR or token holder injects quotes labelled `Trayport`/`EEX`/`ICE_OCM`, which traders then read as screen prices.
- (A5) An administrator disables four-eyes, edits limits through a colluding account, then prunes or edits the audit rows.
- (A6) A poisoned counterparty, contract or news string in a CSV export executes a formula on an analyst's PC.
- (A7) An authenticated user exhausts the single uvicorn process with SSE streams, chunked uploads or optimisation runs.

---

## 3. Findings

### HIGH

**H1. Book/entity isolation is off by default. Any principal with `portfolio.read` sees every book, including VIEWER and OPERATOR.** CONFIRMED (code and demo).
- Evidence (code): `security/portfolio_scope.py`. Isolation only applies with `EUROGAS_NEXUS_PORTFOLIO_ISOLATION=true`, and "With isolation off (the default ...) every caller sees every book".
- Evidence (demo):
  - `test_nl_trader` gets `GET /api/portfolio/books` → both `demo-nl-ttf` (NWG-NL) and `demo-uk-nbp` (NWG-UK).
  - `test_ops` (OPERATOR, a source-operations role) gets 200 on `/api/portfolio/books`, `/api/portfolio/credit-exposure` and `/api/market/firm-marks`.
  - `test_finance` (VIEWER) gets 200 on `/api/portfolio/mandate-usage`.
- The scope is **opt-in per query** (`restrict()`), and `current_scope()` returns `None` (unrestricted) outside a request context. A new query, a worker, a stream or an AI path that forgets the helper therefore fails **open**. Examples with no scope reference: `application/opportunity_reads.py:150`, `limits_service.py:293` and `lng_disruption.py:1198`, which reads all `TraderMandateRecord` rows.
- Exploit: an analyst in a regulated affiliate reads another legal entity's positions and credit lines. That is an information-barrier breach and, for a vertically integrated utility, potentially an unbundling or REMIT inside-information issue.
- Fix:
  - Make isolation default-on, refusing to start with it off unless `single_book_firm=true` is declared.
  - Enforce scope at the ORM layer (a `do_orm_execute` event or row-level security in PostgreSQL), not per call site.
  - Fail closed outside a request: no scope means no rows.
  - Remove `portfolio.read` from OPERATOR and VIEWER unless granted explicitly.
- Type: code fix, plus an architectural control (RLS).

**H2. The commercial-data boundary has holes. A platform ADMIN with no commercial role reads decision cases and analysis snapshots; there is no object-level check at all.** CONFIRMED (code and demo).
- Evidence (code): `COMMERCIAL_DATA_PREFIXES` in `security/permissions.py` omits `/api/decision-cases`, `/api/analysis-snapshots` and `/api/data-products`.
- Evidence (handlers):
  - `get_decision_case` (`api/routes/public/decision_cases.py:135`) loads any `case_id` with no owner, book or scope check.
  - `list_analysis_snapshots` and `get_analysis_snapshot` (`data_platform.py:164-245`) likewise.
- Evidence (demo): `test_admin` (permissions: identity/audit/source only) gets 200 on `GET /api/decision-cases/case-demo-review-haldor`. The response holds the objective ("Haldor supply ... open on the NBP book; cover tomorrow on NBP day-ahead or from storage?"), alternatives, evidence, `ai_findings` and the pack. `test_portfolio/books` gives the same admin a 403, which shows the boundary is meant to exist.
- A VIEWER can also obtain an HMAC-**signed** ERP hand-off for any decided case: `GET /api/decision-cases/{id}/handoff` is READ.
- Exploit: IT administration staff learn trading intent ahead of execution (front-running or leakage risk). Users can read other desks' cases.
- Fix:
  - Add these prefixes to the commercial boundary.
  - Add `book_id`/`created_by`/team visibility to cases and snapshots and filter on read.
  - Make the hand-off REVIEW and owner-or-approver only.
  - Add a CI test that enumerates every GET and asserts that an admin-only principal gets 403 unless the path is allow-listed.
- Type: code fix.

**H3. The static deployment token is a firm-wide super-credential with self-asserted attribution.** CONFIRMED (code).
- Evidence:
  - `security/identity.py::legacy_public_token_principal` gives role OPERATOR with `data_scopes=("*",)`.
  - `api/dependencies/route_permission.py`: OPERATOR routes accept any `X-Eurogas-Principal` string as the actor.
  - `ai_authority.py` explicitly accepts the token for AI calls.
  - The token is also accepted as the `?api_key=` query parameter (`public_auth.py`), which uvicorn's default access log writes to disk.
  - The token sits in the environment of every container (`deploy/runtime/compose.yaml`, including the healthcheck command line, which is visible in `docker inspect`).
- The internal profile adds `EUROGAS_NEXUS_INTERNAL_API_TOKEN`. With it plus a typed principal name, a caller can create identities, mint keys, disable users and prune audit (`api/routes/internal/identity_admin.py`).
- Exploit: anyone with the `.env` file or a CI log reads all books and all licensed data, and acts under someone else's name. The audit then attributes the act to the forged name.
- Fix:
  - Retire the token for anything but health and readiness.
  - Require per-person API keys (already implemented: `/api/me/api-keys`, scoped and expiring) and per-service principals stored in the database.
  - Drop the query-string channel and use a short-lived signed SSE ticket instead.
  - Mark actor attribution derived from a header as "unverified" in audit.
- Type: code fix and configuration.

**H4. Price-integrity: OPERATOR (or the token) can inject quotes under licensed exchange families.** CONFIRMED (code); not exercised.
- Evidence: `("/api/market/ticks", Permission.OPERATOR)`. `application/market_ticks.py` accepts the `EEX`/`ICE_OCM`/`Trayport` families from an HTTP caller. Only plausibility and jump checks apply. The rows then drive marks, strategy tracking and alerts.
- Exploit: a person in operations, with no trading role, makes a TTF or NBP print appear on traders' screens as a Trayport price, triggering alerts and strategy signals. For a market-abuse control owner this is a falsified-data vector, and it breaches AGENTS.md rule 17 in spirit.
- Fix:
  - Bind each licensed family to a dedicated service principal (feed adapter) with a signed or mTLS channel.
  - Refuse human principals.
  - Show "manually injected" provenance in the UI.
  - Alert compliance on any tick write outside the adapter.
- Type: code fix plus an architectural control.

**H5. The audit trail is not tamper-evident, and it can be pruned by an operator.** CONFIRMED (code).
- Evidence:
  - `db/repositories/audit.py` says "append-only", but no trigger, `REVOKE UPDATE/DELETE`, hash chain or WORM export exists in `alembic/versions`.
  - The application connects as the database owner (`POSTGRES_USER` in `RUNTIME_STORE_DATABASE_URL`, `deploy/runtime/compose.yaml`).
  - `POST /api/internal/audit/prune` takes `retention_days` ≥ 30, gated by the internal token plus a typed principal.
  - Audit writes outside "governed actions" are best-effort (`try/except: return` in `api/dependencies/identity.py::_audit_auth_failure`).
  - There is no syslog/SIEM forwarder and no trusted time source beyond the host clock.
- Regulatory impact: DORA Art. 9/12 (logging, protection of ICT data), ISO 27001 A.8.15/A.8.17, SOC 2 CC7.2. REMIT and MAR record-keeping expect at least 5 years of retention; a 30-day floor is incompatible.
- Fix:
  - Use separate DB roles: migration owner, an app role with `INSERT`-only on `audit_events`, and a read-only reporting role.
  - Add a per-row hash chain with periodic anchoring (signed daily digest).
  - Stream to the firm's SIEM.
  - Raise the minimum retention to 5 years (configurable upward only), with pruning under four-eyes.
- Type: architectural control (ADR).

**H6. No MFA. Local accounts are on by default whenever OIDC is absent.** CONFIRMED (code).
- Evidence: no TOTP, WebAuthn or MFA code anywhere in `src`. `local_accounts_policy.py` sets `auto` to on when OIDC is unset.
- Sessions use a 12 h idle and 24 h absolute TTL (`db/repositories/security.py:21-22`), and personal API keys live up to 365 days.
- For admin and risk roles this fails the usual vendor questionnaire (privileged access requires MFA) and NIS2 Art. 21(2)(j).
- Fix:
  - Require SSO for release (local accounts only as break-glass, with a hardware key).
  - Add WebAuthn for local admin accounts.
  - Make idle timeout configurable, defaulting to 30 min.
  - Cap personal keys at 90 days for privileged roles.
- Type: feature.

**H7. Segregation of duties: one administrator can neutralise the maker-checker and self-provision commercial access.** CONFIRMED (code).
- Evidence:
  - `PUT /api/settings/organisation` (ADMIN only, `api/routes/public/preferences.py`) can set `four_eyes` to false for credit lines, mandates, hedge bands and firm marks. Changing the control is not itself under four-eyes.
  - Self-grant is blocked (`access.py:381`), but an admin can create a second local account with ANALYST/REVIEWER and `*` scope. They can also reset a user's password and sign in as that user first (temporary password).
  - The maker-checker distinguishes approver from proposer only by `principal_id` (`maker_checker.py::approve_change`).
- Exploit: one person changes a trader mandate, then approves it from a sock-puppet account.
- Fix:
  - Put dual control on role and scope grants, the four-eyes setting and admin password resets.
  - Forbid any principal created by X from approving X's proposals.
  - Send a compliance notification on every privileged change.
  - Add a break-glass account with sealed credentials and alerting.
- Type: code fix and process.

### MEDIUM

**M1. Notification channels bypass entitlement, book scope and the admin boundary.** CONFIRMED (code).
- `application/notifications.py::mirror_monitoring_alerts` queues **every** open alert, including the `limits` category, to every enabled channel. Channels are arbitrary e-mail lists set by ADMIN, with no domain allow-list.
- `smtp.starttls()` is called without an SSL context, so the relay certificate is not verified.
- Fix:
  - Filter alerts by recipient principal (map addresses to principals) and refuse addresses outside approved domains.
  - Call `starttls(context=ssl.create_default_context())`.

**M2. The route permission registry is method-blind for path families, so writes depend on in-handler checks.** CONFIRMED (code).
- `permission_for_path` only consults `METHOD_ROUTE_PERMISSIONS`. Otherwise `/api/portfolio/` and `/api/contracts/` resolve to READ for POST and PUT too.
- A static scan of the decorators shows writes landing at the VIEWER floor: `PUT /api/portfolio/hedge-approvals/{id}`, `POST /api/portfolio/lng-cargo-bid`, `/sell-down-plan`, `/desk-replay`, `PUT /api/opportunities/{id}/state`. These are protected today by handler checks (`_require_risk_function`, `_require(..., PORTFOLIO_READ)`), but one missed check would be a privilege escalation.
- Fix: make every non-GET default to at least WRITE/GOVERNED and fail CI on any unmapped non-GET.

**M3. OIDC role mapping trusts generic claim names, including the OAuth `scope` string, and puts token `entitlements` straight into data scopes.** CONFIRMED (code: `security/oidc.py:292-333`).
- A user holding a realm-wide Keycloak role named `admin`, `ops` or `operator` used by *another* application, or a client scope named `admin`, becomes ADMIN or OPERATOR here.
- OIDC access-token principals are not persisted, so they cannot be disabled locally and are bounded only by token lifetime.
- The gateway mapper's rank list also omits SCHEDULER.
- Fix: map only via the explicit `GROUPS_ROLE_MAP` with an app-specific prefix, drop the alias table, and provision OIDC subjects in the database.

**M4. CSV exports are not neutralised against formula injection.** CONFIRMED (code).
- `api/csv_export.py::_cell` writes the raw string. Values from external sources (counterparty names, news titles, REMIT text, imported files) beginning with `= + - @` execute in Excel.
- The XLSX path is safe because it writes `inlineStr`.
- Fix: prefix such cells with `'`, per OWASP guidance.

**M5. Security headers are absent in the customer deployment.** CONFIRMED (code).
- `SecurityHeadersMiddleware` is installed only when the API serves the web client (the demo). The customer `deploy/runtime/Caddyfile` adds none: no HSTS, `nosniff`, frame or CSP headers on `/api`. Demo headers are good.
- The CSP `connect-src 'self' https:` and `img-src https:` (web and Tauri) allow exfiltration to any HTTPS host if XSS ever lands.
- Fix: set headers in the API unconditionally and narrow `connect-src` to the configured API origin.

**M6. CORS and the CSRF origin allow-list always include `http://localhost`, `http://127.0.0.1` and the Tauri origins, with credentials, in every profile.** CONFIRMED (code: `api/app.py::_cors_origins`, `origin_csrf.py`).
- Any local process serving port 80 on a user's PC can make credentialed requests.
- Fix: add these origins only in development, or only when desktop clients are enabled.

**M7. DoS and cost controls are thin.** SUSPECTED for exploitability; the absence is CONFIRMED.
- Only the auth and admin routes have a process-local limiter (`security/rate_limit.py`). There are none on optimisation, backtests, report generation, LLM routes or SSE.
- `/api/contracts/intake` checks `Content-Length`, then `await request.body()`, so a chunked body is read into memory before the 20 MB check.
- The customer image runs a single uvicorn process with no `--limit-concurrency`.
- Fix:
  - Per-principal token buckets and concurrency caps.
  - A streaming body limit.
  - A cap on SSE streams per principal.
  - Per-user and per-day LLM budgets.

**M8. Container and runtime hardening.** CONFIRMED (code).
- `postgres:16-alpine` and `caddy:2-alpine` are tag-only, not pinned by digest.
- There is no `read_only`, `cap_drop: [ALL]`, `no-new-privileges` or resource limits.
- `chown -R eurogas /app` makes the runtime user able to rewrite application code.
- Every service, including ingestion workers, receives every secret: OIDC client secret, internal token, master key.
- One DB superuser is used for migrate and runtime.
- `FORWARDED_ALLOW_IPS=172.16.0.0/12` trusts X-Forwarded-For from any container on any Docker network.
- Fix: per-service env sets, a read-only root filesystem, a non-writable `/app`, digests, and a narrow trusted-proxy CIDR.

**M9. Key management.** CONFIRMED (code).
- A single `EUROGAS_NEXUS_SECRET_KEY` both HMACs API keys and Fernet-encrypts provider credentials.
- There is no `MultiFernet` or rotation path; the preflight itself warns it "cannot be rotated deliberately".
- Without the key, API-key hashes fall back to unkeyed SHA-256.
- Secrets live in environment variables, not a vault or KMS.
- Fix: separate keys, use MultiFernet rotation, and add a KMS/Vault integration (`*_FILE` already exists for some providers).

**M10. LLM provider defaults and data flow.** CONFIRMED (code).
- The default endpoint is `https://api.deepseek.com` (`llm/provider.py`).
- In `release`/`trial` all external LLM calls are hard-off (`core/config.py:137`). That is a good control, but it also disables a firm's own on-prem vLLM.
- In `development`/`internal`, prompts containing books and decision context go to a provider outside the EU or EEA with no adequacy decision (GDPR Ch. V; confidentiality of commercial data).
- Prompt injection via news, REMIT and PDF text is mitigated by read-only, role-allow-listed tools (`domain/ai/register.py`, `NEVER_MODEL_TOOLS`). The residual risk is manipulated summaries shown to traders.
- Fix:
  - No default provider.
  - Allow-list the endpoint per installation.
  - Allow private endpoints in release.
  - Label untrusted-source spans in prompts and show "AI-generated, sources: ..." with links.

### LOW

- **L1.** `error_class` (the exception class name) appears in 503 bodies (`api/dependencies/identity.py`). This is minor information disclosure. CONFIRMED.
- **L2.** The CSRF token is `sha256(session)[:32]`, which is a prefix of the stored `session_token_hash`. Anyone with read access to the database can therefore compute it. Use an HMAC with a server key instead. CONFIRMED.
- **L3.** The demo-account boundary is sound. It has three layers:
  1. Start-up refusal outside the `demo` profile in a `development`/`test` environment (`local_accounts_policy.py`, `route_profiles.py`).
  2. A per-sign-in refusal of any `is_demo` credential unless the demo profile is active (`local_accounts.py:813`).
  3. Disabling of accounts that are no longer listed.

  The residual risk is that `EUROGAS_NEXUS_ENV` defaults to `development`. A customer who copies the demo image (the root `Dockerfile` runs `start_public_demo.py`) without setting the environment gets demo semantics, `/api/dev/auth/login` and simulated sources. Fix: make the default environment `release`. CONFIRMED.
- **L4.** The OIDC/JWT verification is hand-rolled, although sound (RS256 pinned, `aud`/`iss`/`exp`/`nonce`, `cryptography` for verification). Prefer a maintained library (`joserfc`/`authlib`) and add JWKS refresh on unknown `kid`.
- **L5.** Personal data inventory: identities, e-mail addresses, IP addresses in the audit trail, session telemetry and support reports. There is no record of processing, no erasure procedure (principals with audit history are never deleted, which is defensible but must be documented), and backup encryption is "deployment-owner policy" (`docs/operations/BACKUP_RESTORE.md:121`).

### What is done well (for the questionnaire)

- Hash-pinned Python and Rust locks.
- GitHub Actions pinned by SHA, with least-privilege `permissions:`.
- pip-audit and cargo audit in CI.
- SBOM and GitHub build-provenance attestations (`release.yml`).
- Authenticode and GPG signing paths.
- Customer image runs non-root.
- Parameterised SQL throughout (the one f-string query uses constant table names).
- XML parsing refuses DTDs.
- Map popups escape their content; no `dangerouslySetInnerHTML`.
- Report HTML is served with a strict CSP and escaped JSON.
- Uniform login refusal, 5-failure back-off and a per-address throttle.
- Change-token password flow with session revocation.
- Personal API keys: scoped, expiring, and creatable only from an interactive session.
- Desktop: in-memory session, loopback OIDC with PKCE, minimal Tauri capabilities.
- Four-eyes with stale-check and proposer ≠ approver.
- Work mode and job functions never grant authority (rule 7 holds: `capabilities.py` uses them for composition only).
- MCP is disabled in customer profiles.
- External LLM is off in release.
- Licensed-data export decision on files.

---

## 4. Controls a regulated trading firm expects that are absent

| Control | Status | Framework hook |
|---|---|---|
| MFA for all users, phishing-resistant for privileged users | absent | NIS2 21(2)(j), ISO A.8.5, SOC2 CC6.1 |
| Enforced information barriers (entity/desk, default-deny, DB-enforced) | opt-in, app-level | MAR Art. 9, REMIT, firm Chinese-wall policy |
| Immutable, hash-chained audit with SIEM export and ≥5y retention | absent | DORA Art. 12, ISO A.8.15, REMIT record-keeping |
| Privileged access management: dual control on grants, break-glass, quarterly access recertification report | partial (self-grant block only) | ISO A.5.18, SOC2 CC6.2/6.3 |
| Database role separation and least privilege | absent | ISO A.8.2/A.8.3 |
| Secrets in a vault or KMS with rotation | absent (env + single Fernet key) | ISO A.8.24, DORA Art. 9(4) |
| Per-user rate limits and resource quotas | absent | DORA operational resilience |
| DLP-style egress controls: export watermarking, e-mail domain allow-list, download logging per user | partial (export decision, usage meter) | insider risk, licence compliance |
| Data-feed authenticity (signed or mTLS adapters, no human tick injection) | absent | market-data integrity, MAR |
| GDPR RoPA, DPIA for the AI features, data residency statement, subprocessor list | absent | GDPR Art. 30/35, Ch. V |
| Pen-test report, ASVS L2 evidence, vulnerability-disclosure SLA, secure SDLC attestation | partial (ASVS mapping doc, SECURITY.md) | vendor questionnaire, DORA Art. 28 (ICT third-party) |
| Container runtime hardening and image scanning (Trivy/Grype) | partial | CIS Docker benchmark |
| Session idle timeout aligned to policy (15–30 min) | 12 h | firm policy |

---

## 5. Penetration-test plan (5 days, grey box)

1. **Authorisation matrix (2 days):**
   - Enumerate every route from the router.
   - For 9 personas plus admin-only, token and anonymous callers, run GET, POST, PUT and DELETE and diff against the intended matrix. Use a non-production copy, because writes are needed.
   - Specifically probe object IDs across books and entities: decision cases, snapshots, reports, strategies (`/sharing`), opportunities, gas-day reconciliation and cargo plans.
2. **Identity:**
   - OIDC claim confusion (role names in `scope`, `realm_access`).
   - Gateway header spoofing with and without trusted-proxy CIDR.
   - Session fixation and revocation after disable or password reset.
   - Personal-key scope intersection.
   - Demo-account boundary under an unset `EUROGAS_NEXUS_ENV`.
3. **Injection:**
   - CSV formula payloads via imports and news.
   - Prompt injection through REMIT, news and contract PDFs into `/api/analysis/ask`, `/explain` and `/news/{id}/note`.
   - Malformed PDF fuzzing of `/api/contracts/intake` (memory and OCR timeouts).
4. **Integrity:** tick injection under licensed families, firm-mark changes with four-eyes toggled, the maker-checker sock-puppet path.
5. **Resilience (agreed window):** SSE connection exhaustion, chunked uploads, concurrent optimisation runs against a single-process deployment.
6. **Infrastructure:** container escape surface, Docker network trust (`FORWARDED_ALLOW_IPS`), secrets in `docker inspect`, TLS on the SMTP and PostgreSQL legs.

---

## 6. Prioritised remediation plan

| # | Action | Closes | Size |
|---|---|---|---|
| 1 | Default-on, fail-closed book isolation; add decision cases, snapshots and data products to the commercial boundary with owner/book filters; remove `portfolio.read` from OPERATOR and VIEWER | H1, H2 | code, 1–2 wk |
| 2 | Retire the static token for data access; per-service DB principals; drop `?api_key=` | H3 | code, 1 wk |
| 3 | Restrict `/api/market/ticks` for licensed families to the feed-adapter service principal; add injected-price provenance and a compliance alert | H4 | code, days |
| 4 | Database role split (owner / app / read-only); INSERT-only audit; hash chain; SIEM forwarder; ≥5y retention floor; prune under four-eyes | H5 | ADR + 2–3 wk |
| 5 | SSO-only in release; WebAuthn for break-glass admin; 30-min idle timeout | H6 | feature, 2 wk |
| 6 | Dual control on grants, the four-eyes setting and admin resets; creator ≠ approver | H7 | code, 1 wk |
| 7 | Method-aware default (non-GET ≥ WRITE) plus a CI authorisation-matrix test; OIDC explicit group mapping only | M2, M3 | code, days |
| 8 | Alert recipients filtered by principal entitlement; domain allow-list; verified STARTTLS | M1 | code, days |
| 9 | CSV neutralisation; unconditional security headers; prod-only CORS list; narrow CSP | M4–M6 | code, days |
| 10 | Rate limits and quotas, streaming body limit, SSE caps; container hardening and digests; per-service secrets; key rotation via Vault/KMS | M7–M9 | config + code, 2 wk |
| 11 | No default LLM provider; allow on-prem endpoints in release; DPIA and RoPA; subprocessor list | M10, L5 | docs + config |

**Gate for onboarding:** items 1–6 closed and re-tested by an independent pen test. After that the tool can sit beside Trayport and ETRM as a decision-support workstation on the firm network with SSO. Until then, restrict it to a single desk, a single entity and public data only.
