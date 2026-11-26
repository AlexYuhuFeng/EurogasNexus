# Security hardening (2026-11): what an installation notices

For the customer's IT lead. These changes close the findings of the 2026-11 security review
([remediation record](../../security/SECURITY_REVIEW_REMEDIATION_2026-11.md)). Read this before
upgrading: several defaults are stricter, and a release server now refuses to start on some
configurations it used to accept.

## The server may refuse to start

A `trial` or `release` server now stops with a message naming the setting when:

- no sign-in is configured: set up company SSO, or set `EUROGAS_NEXUS_LOCAL_ACCOUNTS=on`
  (local accounts are no longer switched on automatically);
- `EUROGAS_NEXUS_PORTFOLIO_ISOLATION=false` without `EUROGAS_NEXUS_SINGLE_BOOK_FIRM=true`;
- `EUROGAS_NEXUS_DUAL_CONTROL=off`;
- the deployment token is given the ADMIN role or a `*` scope.

An unset `EUROGAS_NEXUS_ENV` in the release profile now means `release` (it meant
`development`).

## Access changes

- **Book isolation is on.** People see the books their `BOOKS:` data scopes name; a person
  with no `BOOKS:` scope sees no position. Give head office `BOOKS:*` and regional staff
  `BOOKS:ENTITY:<entity>` before upgrading. `*` still means everything.
- **Credit, mandates, hedge bands and firm marks** need `risk.limits.read` (ANALYST and
  REVIEWER hold it); operations and finance get it only with the data scope
  `PERM:risk.limits.read`.
- **OPERATOR no longer reads positions**; grant `PERM:portfolio.read` where needed.
- **Platform administrators** no longer read analysis snapshots, data products, LNG cargoes or
  capacity bookings without a commercial role, nor any new path family.
- **The signed ERP hand-off** needs the review floor and a party to the decision.
- **SSO roles** come only from `EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP`: map your directory groups
  explicitly (for example `{"eurogas-nexus-analysts": "ANALYST"}`) before upgrading, or everyone
  signs in as VIEWER. A token's scope claim is read only when `EUROGAS_NEXUS_OIDC_SCOPE_CLAIM`
  is set, and never grants `*`.

## The deployment token

In trial and release the token is a service principal (default VIEWER, public sources only) and
cannot name who acts. Move scripts to personal API keys; set
`EUROGAS_NEXUS_PUBLIC_API_TOKEN_ROLE` and `_SCOPES` for what remains, or, temporarily,
`EUROGAS_NEXUS_PUBLIC_API_TOKEN_MODE=legacy_operator`. The token in a URL (`?api_key=`) is
refused everywhere. See [DEPLOYMENT_TOKEN.md](../../security/DEPLOYMENT_TOKEN.md).

## Second administrator

Creating accounts, changing roles or scopes, issuing service keys, resetting passwords or
second factors, switching four eyes off, switching an AI use on, changing alert recipients and
pruning the audit trail answer 409 `dual_control_required` with a change id. A second
administrator approves it; the requester repeats the call with `X-Eurogas-Dual-Control`. An
installation with one administrator uses break-glass (`X-Eurogas-Break-Glass: <reason>`),
which is audited at critical severity. Approval is an API call in this release; the web
client shows the message.

## Sign-in

Local accounts above VIEWER and SCHEDULER must set up a second factor (TOTP) at their next
sign-in in trial and release (`EUROGAS_NEXUS_MFA_REQUIRED`). Sessions end after 30 minutes idle
and 10 hours in all (`EUROGAS_NEXUS_SESSION_IDLE_MINUTES`, `_ABSOLUTE_HOURS`).

## Audit trail

Audit rows are hash-chained; `GET /api/audit/verify` and
`scripts/ops/verify_audit_chain.py` check the chain. Pruning keeps at least
`EUROGAS_NEXUS_AUDIT_RETENTION_DAYS` (default five years) and needs a second administrator; the
internal token can no longer delete audit rows. Run `deploy/runtime/database_roles.sql` to give
the application an INSERT-only audit role ([DATABASE_ROLES.md](../../security/DATABASE_ROLES.md)).
`EUROGAS_NEXUS_AUDIT_SINK` forwards audit rows to your SIEM.

## Other defaults

- No model provider is configured by default: set `EUROGAS_NEXUS_LLM_BASE_URL`. In trial and
  release an on-premises endpoint may be enabled.
- Alert e-mail needs `EUROGAS_NEXUS_ALERT_EMAIL_DOMAINS` in trial and release; the relay's TLS
  certificate is verified.
- Price ticks under a licensed venue's label are accepted only from that venue's connector key
  (`PUBLISH:<family>` scope on a service identity); screen exports are labelled as file imports.
- CSV and XLSX exports neutralise cells that a spreadsheet would run as a formula.
- Security headers on every API answer; local origins only in development.
- Per-person quotas on changes (300 a minute) and heavy computations (30 a minute), five open
  streams per person.
- The containers run read-only, without capabilities, and receive only their own settings.
- `EUROGAS_NEXUS_SECRET_KEY_PREVIOUS` and `scripts/ops/rotate_secret_key.py` rotate the
  deployment key.

## The hosted demo

The demo start-up gives each tester explicit scopes on every start: traders see their own
entity's books, data operations and the platform administrator see none, finance reads books
but not limits. The demo runs as `development`, where dual control, the second factor and the
quotas are off by default; set `EUROGAS_NEXUS_DUAL_CONTROL=on` and `EUROGAS_NEXUS_MFA_REQUIRED`
to try them. AI on the demo now names its endpoint when the operator supplies a model key.
