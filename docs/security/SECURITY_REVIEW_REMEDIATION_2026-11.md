# Security review 2026-11: remediation

The independent security review of 2026-11 (CISO-office pre-onboarding assessment) reported
seven High, ten Medium and five Low findings. This page records, per finding, how it arose,
what changed, where else the same class was found, and what remains. Behaviour changes an
installation notices are collected in
[the release note](../release/notes/SECURITY_HARDENING_2026-11.md).

Detailed pages: [book isolation and the commercial boundary](BOOK_ISOLATION.md),
[the deployment token](DEPLOYMENT_TOKEN.md), [database roles and the audit trail](DATABASE_ROLES.md),
[local accounts and the second factor](LOCAL_ACCOUNTS.md).

## High

**H1 Book isolation off by default, applied filter by filter.** Cause: isolation was designed
for a single office and added per query through a helper; a forgotten call failed open.
Fixed: on by default; enforced in the ORM layer for every session (`db/book_scope.py`), with a
deny-all scope until the caller is identified; writes into another book refused; refused off in
trial/release unless `EUROGAS_NEXUS_SINGLE_BOOK_FIRM=true`. `risk.limits.read` gates credit,
mandates, hedge bands and firm marks (in the limits service, so every reader follows it);
OPERATOR no longer reads positions by role; `PERM:` scopes grant either explicitly. Inventory
and two-entity leak tests over every GET route. Same class: decision cases, analysis snapshots,
credit lines (entity), mandates (books), hedge bands and deliveries (contract), cargo hedges
(cargo) are now scoped by explicit rules. Not done: PostgreSQL row-level security as a second
layer (planned with the database role split, Architecture V3 plan); outside a request
(workers) the system still sees every book.

**H2 Commercial boundary holes; no object checks.** Cause: the boundary was a deny-list of path
families. Fixed: default-commercial (`PLATFORM_PATH_PREFIXES` allow-list); decision cases and
snapshots scoped per object (book, author, citing case); the signed ERP hand-off needs the
review floor and a party to the decision. Test: every commercial GET as an admin-only principal
is refused.

**H3 Static deployment token as a super-credential.** Fixed: never read from a URL (the web
client streams through fetch with a header); `service` mode by default in trial/release (a
service principal with a configured role, never ADMIN, and scopes, never `*`;
`X-Eurogas-Principal` ignored); `legacy_operator` deprecated and logged; claimed names recorded
as `public-api@<name>` / `internal-api@<name>`; a previous token accepted during rotation; the
token and the internal token removed from every container but the API. Same class: the internal
profile's token.

**H4 Licensed venue labels writable by operators.** Fixed: only a SERVICE identity with its own
key and a `PUBLISH:<family>` scope writes a venue's label; people, sessions and the deployment
token never do; file imports are labelled `<venue> (file import)` with the importer; every tick
batch and every refusal is audited.

**H5 Audit trail not tamper-evident; prunable.** Fixed: hash chain in an insert-only link table,
verification endpoint and command, signed checkpoints, SIEM forwarding, guard triggers, role SQL
(application INSERT-only), retention floor (`EUROGAS_NEXUS_AUDIT_RETENTION_DAYS`, default five
years, at least one) and dual-controlled, audited pruning that keeps the chain verifiable. Not
done: daily write-once export to object storage (the checkpoint and SIEM stream are the hooks);
trusted time source.

**H6 No MFA; local accounts on by default.** Fixed: TOTP with recovery codes and an
administrator reset under dual control; a policy setting with an enrolment-only session;
configurable idle and absolute session lifetimes with shorter production defaults; no automatic
local accounts in production and a start-up error without a sign-in method; an unset
environment in the release profile is `release`, never `development` (the customer image also
sets it). Not done: WebAuthn/hardware keys; a 90-day cap on privileged personal API keys.

**H7 One administrator could neutralise maker-checker.** Fixed: dual control
(`api/dual_control.py`) on account creation, role and scope grants, service-key issue, password
and second-factor resets, four-eyes switched off, AI uses switched on, alert recipients and
audit prunes; the approver may not be the requester, nor an account the requester created or
granted within the cooling period (also enforced in the existing maker-checker); break-glass
with a stated reason, audited at critical severity. Not done: the web client has no approval
screen yet (approval is an API call; the client shows the 409 message); compliance notification
beyond the audit/SIEM stream.

## Medium

- **M1** Alert e-mail: approved domains required in production, limits alerts only to people
  who may read every book's limits, channel changes under dual control, STARTTLS verifies the
  relay certificate.
- **M2** Non-GET routes must be declared with their method or exact path; a write through a
  read family is refused (deny by default). Contract test over the route table.
- **M3** SSO roles come only from `EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP`; generic role names and
  the OAuth `scope` string grant nothing; a scope claim is read only when configured and never
  grants `*` or `PERM:`; SCHEDULER added to the gateway's rank list. Not done: provisioning OIDC
  access-token subjects as database principals.
- **M4** Formula-injection neutralisation in the CSV report export, research dataset export and
  XLSX cells (`core/csv_safety.py`).
- **M5** Security headers on every API answer in every deployment and at the customer gateway;
  the web CSP names the tile service instead of any HTTPS host. Not done: the desktop (Tauri)
  CSP, which must reach a configurable server.
- **M6** Local origins allowed only in development; desktop origins as CORS origins only
  (`EUROGAS_NEXUS_DESKTOP_CLIENTS`), never cookie origins in production.
- **M7** Per-principal quotas on writes and heavy computations (production defaults), at most
  five open streams per person, a streaming body limit on PDF intake, a gateway body limit.
  Not done: LLM per-day budgets; a cross-process limiter.
- **M8** Containers: non-root without write access to the application, read-only root
  filesystem with a private `/tmp`, no capabilities, no privilege escalation, per-service
  settings, a fixed gateway address as the only trusted proxy. Not done: image digests for
  PostgreSQL and Caddy (pin them in the operator's registry).
- **M9** `EUROGAS_NEXUS_SECRET_KEY_PREVIOUS` with MultiFernet decryption and API-key checks;
  `scripts/ops/rotate_secret_key.py` re-encrypts stored secrets. Not done: separate keys per
  purpose; a KMS/Vault integration.
- **M10** No default model provider; an on-premises endpoint may be enabled in trial/release.

## Low

- **L1** An exception's class name reaches operators only (one rule in the error envelope).
- **L2** The CSRF token is an HMAC of the session, no longer a prefix of the stored hash.
- **L3** See H6 (release environment never defaults to development).
- **L4, L5** Not changed (OIDC library choice; GDPR records of processing).
