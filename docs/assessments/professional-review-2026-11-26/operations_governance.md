# Eurogas Nexus: operations, service management and governance review

Reviewer angle: the people who keep a trading-floor system running and governed after go-live. Tree reviewed:
`/home/user/EurogasNexus-merge` (1.0.0-beta.1, Alembic head 0091). Demo walked as `test_admin`
(Admin → Data Sources, Runtime: Health / Release checks / Governance / Problem reports). Read-only.

## 1. Verdict

An IT service manager, DBA and market-data manager at a European trading house would find a better
governance core than most in-house desk tools have. It has a licence register with display and
non-display use, seat counting and usage metering, a "Report a problem" path that attaches diagnostics,
deterministic per-dataset freshness, signed releases with SHA256SUMS, and a fail-closed dependency licence
audit. They would not take it into production support as it stands. The operating model behind it (on-call,
status communication, scheduled backups, alert routing to a monitoring stack, environments, retention) is
written for a single-host preview: the documents say so themselves ("not contractual SLAs", "PITR out of scope
until a production deployment is authorized", "error budgets … production milestone"). Procurement and
internal audit would stop at continuity: of 889 commits, 821 are by Claude and 65 by Codex, which leaves a
bus factor of one human. The buyer's own acceptance record (`docs/release/acceptance/01_BUYER_ACCEPTANCE.md`
L10, A9) lists the missing escrow and the missing second maintainer as open conditions. Adoption is blocked
by service-management and continuity gaps rather than by features. Most of the fixes are configuration,
documentation and contracts, not code.

## 2. Per persona

### 2.1 IT service manager / application support lead (ITIL)
**Day:** triage overnight alerts before the 06:00 gas-day nomination window. Work the L1/L2 queue, chase
vendors on feed outages, and post user notices.
**Works:** the in-product **Report a problem** flow (`api/routes/public/support.py`: P1–P4, categories
including `wrong_figure`; it captures client diagnostics with correlation ids and the server's
failing sources *at the time*; take, then resolve with a mandatory note; audited; email to an IT-desk
channel). `docs/user/manual/IT_DESK.md` is a clear L1 guide with screenshots. Severity definitions are
consistent between `INCIDENT_RESPONSE.md` and `guides/SUPPORT_AND_UPDATES.md`, and the latter rightly says
"a misleading valuation can be more urgent than a cosmetic defect".
**Gaps.**
- *Must:* a support model with tiers. Nothing defines L1 (firm IT desk), L2 (product admin) and L3 (vendor
  engineering), or the hand-offs between them. Response and restore targets are deferred to "the agreed
  support arrangement" (`SUPPORT_AND_UPDATES.md`). No support hours cover the gas day (06:00–06:00 CET) or
  weekend and holiday within-day trading. "On-call" appears in no runbook.
- *Must:* integration with the firm's ITSM (ServiceNow/Jira SM). Problem reports live only in the product
  database and in email. They need an outbound ticket (webhook or e-mail-to-ticket with a stable id) so they
  join the firm's incident record.
- *Should:* problem management and a known-error database. There is no "problem", "known error" or
  "workaround" entity, and a resolved report cannot be linked to a recurring cause. The terms appear in no
  document.
- *Should:* user communication during an outage. There is no service banner, no maintenance notice and no
  status page. A trader who opens the app during an outage sees per-slice freshness badges but no "we know,
  ETA 10:30" message.
- *Nice:* report SLAs and an ageing view in Problem reports.

**Remove or relabel:** the Governance tab shows raw booleans ("Decision Support Guardrail true", "Human Review
Required true"). These are engineering assertions, not something support acts on.
**Organise as:** Admin → *Service* with four parts: Incidents and reports, Known issues, Notices to users,
Health.

### 2.2 Release and change manager
**Works:** SemVer with channels (`RELEASE_CHANNELS.md`), a version-consistency gate, a Keep-a-Changelog
`CHANGELOG.md` plus customer-facing release notes (`docs/release/notes/1.0.0-beta-RELEASE_NOTES.md`, written
for desk leads, which is good). The release-integrity chain is in place: SHA256SUMS, manifest, digest
promotion in `CONTAINER_PROMOTION_PLAN.md`. A client/server compatibility blocking screen enforces
`/api/runtime/release`. `RELEASE_ROLLBACK.md` states the correct golden rule: no binary rollback across a
destructive migration.
**Gaps.**
- *Must:* migrations run unconditionally on start. `deploy/runtime/compose.yaml` service `migrate` runs
  `alembic upgrade head` on every `up`, gated only by `check_config.py`. No change window or approval step
  exists, and no backup is taken first. A change manager needs "backup, then preflight, then approve, then
  migrate" as an enforced sequence.
- *Must:* downgrade truth. Downgrades exist for most revisions, but `0040_strategy_owner_sharing` and
  `0042_national_gas_actual_demand` raise "cannot be downgraded", and `0091_hub_one_identity` downgrade is
  `pass` ("Nothing to undo … which rows were written GTF or VTP is not kept"). The release notes do not
  publish a per-release reversibility statement. Change approval needs it.
- *Must:* defined environments. The documents mention staging only in release-engineering terms. No
  dev/test/UAT/prod topology exists, no promotion of *data* (reference data, licence register, user roles)
  between environments, and no rule that UAT uses a production-like copy with masked books.
- *Should:* an upgrade path for a customer several versions behind (0.8 to 1.0 crosses 0040/0042). Only
  "upgrade head" is documented. Supported skip-versions and an N-2 compatibility window are not.
- *Should:* feature flags. There is one passing mention (`Architecture-V2/09_…`) and no runtime flag
  mechanism, so a new evaluator cannot be dark-launched to one desk.
- *Should:* a deprecation policy for API and SDK (`docs/sdk`) consumers. Deprecations appear in audit notes
  only.
- *Desktop:* `UPDATE_POLICY.md` says the Tauri updater is not shipped, with "no forced update possible".
  That is acceptable for managed SCCM/Intune rollout. Minimum-version blocking through the compatibility
  screen is the de-facto forced update and should be documented as such.

### 2.3 Database administrator
**Works:** PostgreSQL 16 only, one migration chain (92 revisions), required-table registry,
`migration_preflight.py`, read-only `validate_runtime_db.py`, `backup_runtime.py` and an automated
`backup_restore_drill.py` that restores into a scratch database and smoke-tests the API. Keyset and
time indexes exist (`0048`, `0061`). The capacity study (`Commercial-Intelligence-V3/19_…`) is
unusually good. It measures that the raw page archive is about 91 % of growth (about 107 MB a day today,
about 3.2 GB a day with hourly ENTSOG), sets partition triggers at 50 M rows, and correctly rejects
TimescaleDB on Timescale-licence grounds (TSL) in favour of native partitions plus Parquet. This makes the
"optional TimescaleDB extension" moot: none exists in code.
**Gaps.**
- *Must:* backups are manual and logical only. No backup service runs in compose, no schedule, no WAL
  archiving and no PITR (`BACKUP_RESTORE.md`: "taken offline or during low-write windows"). RPO is
  24 h (`DISASTER_RECOVERY.md`). For a desk with hand-entered decisions, approvals and audit, that means
  losing a trading day. The only recorded restore evidence is a 161,798-byte dump restored in 2.8 s (CR-11)
  and a 319 KB dump in the operations acceptance. The 30-minute RTO has never been measured on a realistic
  (tens of GB) store.
- *Must:* migrations on large tables. `0048` creates indexes on four observation tables without
  `CONCURRENTLY`. `alembic/env.py` sets no `lock_timeout` or `statement_timeout` (only prose in
  `0037`/`0038` recommends one). On a year of ENTSOG data that is a write-blocking lock during the gas day.
  No migration run-time estimate is published for a large store.
- *Must:* no replication or standby is shipped (single `postgres:16-alpine`). The capacity doc recommends a
  primary plus hot standby, but nothing implements or documents failover.
- *Should:* retention and archival are not scheduled. `application/retention.py` deletes market quotes after
  **30 days** and observations after 90, and `prune_audit_events.py` defaults to 1,827 days. All are manual
  scripts that nobody schedules, so tables grow without limit, or an operator who does run them destroys
  price history that risk and compliance need. There is no archive-before-delete (the Parquet tier is
  design only).
- *Should:* no PostgreSQL tuning profile (shared_buffers, autovacuum per large table, connection limits
  against the per-DSN pool) and no `pg_stat_statements` guidance. Autovacuum is mentioned once, in the
  capacity doc.

### 2.4 Monitoring and observability engineer
**Works:** liveness and readiness are separated (`/api/health/live` never touches the DB). Per-dataset
freshness contracts live in connector manifests (`DATA_FRESHNESS.md`, `application/freshness_contract.py`)
with weekday-aware ageing. Ingestion runs and issues are recorded with consecutive-failure counts. Scheduler
heartbeats exist. Monitoring alerts are routed with owner and escalation (`alert_routing`, SMTP).
**Gaps.**
- *Must:* the metrics endpoint cannot be scraped. `/api/runtime/metrics` returns Prometheus text *inside a
  JSON envelope* (`source_operations.py:440`), needs an authenticated READ principal and a DB, and the HTTP
  counters are process-local, with a defined `_LATENCY_BUCKETS` that is never used (sum only, so no
  percentiles). Prometheus cannot ingest it as is. The operations acceptance also logged an invalid sample
  value (OPS-06).
- *Must:* no SLO alerting. `SLO.md` lists "error budgets and burn-rate alerts" as a non-goal. Nothing pages
  when ENTSOG is stale at 05:30 CET or the scheduler heartbeat stops. The demo shows the failure mode:
  Health reports "Dataops scheduler: Not known yet, no heartbeat recorded", Release checks show "Data
  operations scheduler Blocked, 0/42 scheduled sources", and 68 open alerts sit unattended.
- *Should:* structured JSON logs and tracing. The container runs bare `uvicorn` with default text logs
  (`Dockerfile.api` CMD). There is no log formatter, no OpenTelemetry (only roadmap mentions) and no log
  shipping guidance. Correlation ids exist, which is the right foundation.
- *Should:* alert hygiene. Every GIE and ENTSOG source reads "Succeeded with warnings". When everything warns,
  nothing does. Warnings need classes and suppression.
- *Should:* capacity planning tied to telemetry. The capacity study is a design, and no table-size or
  row-count metric is exported to show when a trigger is reached.

### 2.5 Market-data and vendor manager
**Works (the strongest area):** the `market_data_licences` register (vendor, family,
`DISPLAY | NON_DISPLAY | DISPLAY_AND_NON_DISPLAY`, ENTERPRISE/office/NAMED_USER with seat counting and a
"all N seats assigned" block, validity dates, redistribution flag, contract reference). Grants of a licensed
scope are checked against it (`domain/market_data/licences.py`). Automated risk calculations run only on
families with a current non-display licence (`application/caller.py`). Per-request usage metering records
day, principal, family and surface, with exports marked (`governance/usage.py`,
`application/licensed_use.py`). File exports are fail-closed for unknown families. The admin screen captures
LNG terminal operators' reuse terms ("Needs the firm's terms" with Record permission).
`docs/legal/DATA_SOURCE_TERMS.md` is a real register.
**Gaps.**
- *Must:* vendor usage reporting. Usage is shown as a 30-day count beside each licence. ICE, EEX and Trayport
  declarations need a monthly per-user, per-product, per-office report with an export and sign-off, plus a
  history of seat assignment over time for vendor audits.
- *Should:* derived-data rules. The register has no "derived data allowed / derived redistribution" field,
  and spreads, curves and netbacks built from licensed prices inherit no tag. Vendor audits (ICE, Platts)
  focus on exactly this.
- *Should:* an onboarding workflow for a new source (request, legal review, register entry, certification,
  activation). The pieces exist (`SOURCE_CERTIFICATION.md`, `approve_public_source.py`) but there is no
  single checklist owned by the vendor manager.
- *Nice:* licence expiry alerts. `valid_to` exists, but no alert fires 60 days before it.

### 2.6 Data governance and data quality owner
**Works:** backend-owned freshness states, `data_quality_report.py`, `DATA_REVISIONS.md`, a raw payload
archive for lineage (`0021`), point-in-time datasets (`docs/research/POINT_IN_TIME_DATASETS.md`), and
manual entry labelled as entered by hand (AGENTS rule 19).
**Gaps.**
- *Must:* a golden-source matrix. `DATA_POLICY.md` says only "PostgreSQL is the runtime source of truth". The
  product both *imports* ETRM trades (`import_etrm_trades.py`) and *creates* contracts and books in-product,
  so no rule says which system masters trades, positions, counterparties or curves. Without one, two masters
  diverge.
- *Must:* reconciliation with the ETRM. The only reconciliation is gas-day nomination
  (`/api/desk/gas-day/{d}/reconciliation`). No position, P&L or trade-count reconciliation exists between
  this store and Endur or Allegro, and no break workflow either.
- *Should:* quality rules and an exception workflow. `data_quality/contracts.py` is a 25-line protocol
  "shell". Rules (spike, gap, negative flow, unit mismatch) need owners, thresholds and an exceptions queue,
  not only a report.
- *Should:* reference-data stewardship. Hubs, points and calendars change by migration and script (`0091`
  hub identity, `audit_reference_topology.py`). There is no steward role, no change request and no effective
  dating visible to users.
- *Should:* a retention schedule per data class, aligned to REMIT, MiFID and EMIR record-keeping (5–7 years)
  and GDPR (see 2.3).

### 2.7 Procurement, legal and internal audit
**Works:** a fail-closed dependency licence audit (Python 45, npm 103, Rust 434 packages, 0 copyleft;
`docs/legal/DEPENDENCY_LICENSE_REVIEW.md`), `THIRD_PARTY_NOTICES.md`, `CODING_STANDARDS.md`,
`CONTRIBUTING.md`, RFC and ADR process, 789 test files, and recorded acceptance reports, including an
operations acceptance that re-ran every command (`docs/release/acceptance/04_…`, "CONDITIONAL hand-over").
**Gaps.**
- *Blocker:* continuity. One human, two AI agents, a personal repository, no legal entity, no escrow and no
  second maintainer (`VENDOR_REMEDIATION_ACCEPTANCE.md` B7). About 250 k lines of Python and 142 k of web
  client, plus about 80 k lines of documentation across 434 files, much of it in Chinese and English pairs
  or historical. A new team would struggle to find the current truth. Required: escrow with release
  triggers, a named second maintainer with commit rights, and a maintained onboarding path that a human
  engineer can follow in a week.
- *Must:* SLA, support contract and BCP templates. None exist. Container CVE scanning is still
  `TOOL_UNAVAILABLE`, and the documents themselves say this blocks a stable release.
- *Should:* test evidence an auditor can consume per release (traceability from requirement to test to
  result). The evidence exists but is scattered across acceptance notes.

### 2.8 Training and change management
**Works:** role manuals (`docs/user/manual/TRADER|RISK|ADMIN|IT_DESK.md` with screenshots), role guides in
English and Chinese, in-product tips and "See an example", a Commercial UAT plan and trader UAT script
(`docs/uat/`), and a demo-desk dataset.
**Gaps.**
- *Must:* a training or sandbox environment separate from production. A "demo marks" toggle exists in the
  same store (`caller.py`). Training on the production instance pollutes audit and books.
- *Should:* manual currency control. Screenshots are not versioned per release, and the governance tab in the
  demo already shows Alembic 0086 against a 0091 tree.
- *Should:* a desk onboarding pack: a role checklist, licence seat assignment, and sign-off.

### 2.9 Business continuity
**Works:** the product is decision support with no execution (rule 8), so an outage is not a market-access
event. Polling fallback for SSE, readiness separation, and CSV, XLSX and PDF report exports.
**Gaps.**
- *Must:* a desk fallback procedure. No document says what the trader uses when Nexus is down: Trayport
  and Joule for prices, TSO portals for flows, the ETRM for positions, plus a last-known-good snapshot.
  The desktop client needs the server and has no read-only cached last view.
- *Should:* a bulk "export everything" for exit and lock-in (books, contracts, decisions, audit) in a
  documented format. Only `personal_data_export.py` (GDPR) and per-report exports exist.

## 3. Cross-cutting gaps

| # | Gap | Why a firm needs it | Evidence | Severity | Fix size |
|---|---|---|---|---|---|
| 1 | No continuity arrangement (escrow, second maintainer, entity) | Third-party risk policy, DORA-style ICT outsourcing review | `01_BUYER_ACCEPTANCE.md` L10; git shortlog 821/65/3 | Blocker | Contract and organisation |
| 2 | No scheduled backup, no WAL/PITR, RTO untested at scale | Losing a day of decisions and audit breaches record-keeping | `BACKUP_RESTORE.md`; compose has no backup service | Blocker | Configuration |
| 3 | Unattended alerting: metrics not scrapable, no SLO alerts, no on-call | Stale data before nomination deadlines goes unnoticed | `source_operations.py:440`; `SLO.md` non-goals; demo scheduler "no heartbeat", 68 open alerts | Major | Feature (small) |
| 4 | Migration on start, no change gate, irreversible migrations unflagged | Change Advisory Board approval; safe rollback | `compose.yaml` `migrate`; `0040`, `0042`, `0091` | Major | Configuration and documentation |
| 5 | No golden-source matrix or ETRM reconciliation | Dual-master positions mislead risk | `DATA_POLICY.md`; only gas-day reconciliation | Major | Feature |
| 6 | Retention destructive and unscheduled (quotes 30 d) | REMIT, MiFID and EMIR 5–7 year records; storage growth | `application/retention.py` | Major | Configuration plus archive feature |
| 7 | No environments model (UAT, training, prod) | Change control, training, UAT on real-shaped data | Only release-engineering staging | Major | Deployment |
| 8 | No ITSM integration, problem management or user notices | Incidents must be in the firm's record; users need outage notices | `support.py` local only | Major | Feature (small) |
| 9 | Vendor usage reporting and derived-data tagging | Vendor audit exposure (ICE, EEX, Platts back-billing) | 30-day count only; no derived field | Major | Feature |
| 10 | Large-table migration safety (locks) | Gas-day write outages during upgrade | `0048` without `CONCURRENTLY`; no `lock_timeout` in `env.py` | Minor now, major at scale | Configuration |
| 11 | Plain-text logs, no tracing | Forensics across API, worker and scheduler | `Dockerfile.api` CMD | Minor | Configuration |
| 12 | No desk BCP or fallback guide | Desk must keep working | absent | Major | Documentation |

## 4. Structural limits

- **Single-host, single-process deployment.** One `postgres:16-alpine` and one `uvicorn` process (no workers,
  no replica, process-local metrics). High availability for a 24×7 gas day needs a standby database, at least
  two API replicas and externalised metrics. The capacity study already plans this, so it is an
  implementation gap, not a redesign.
- **Scheduled operations live outside the product.** Tariffs, deliveries, notification retries, pruning and
  backups are "cron or Windows task scheduler" jobs (`IT_DESK.md`), outside compose and outside the
  scheduler's heartbeat. Operability depends on the customer's IT rebuilding the job plan correctly.
- **Self-hosted, single organisation, customer-operated.** There is no vendor-run service, so every SLA term
  falls on the customer's IT, while L3 rests on one person.
- **The data-licensing model is sound but customer-dependent.** Commercial connectors need the firm's own
  entitlement, so vendor compliance reporting must be produced *by* the product for the firm.
- **AI-built codebase velocity.** About 890 commits in about five months, 92 migrations and a very large
  documentation set mean a high change rate against a thin human review layer. Change management must slow
  promotion to production, whatever the development pace.

## 5. Top 10 changes, in priority order

1. Sign an escrow agreement with release triggers, name a second human maintainer with commit rights, and
   publish a one-week onboarding path for a new engineering team.
2. Add a backup service to the runtime compose (nightly `pg_dump` plus WAL archiving to off-site object
   storage) and run a quarterly restore drill on a realistic store, recording the measured RTO.
3. Make metrics scrapable: plain `text/plain` with its own scrape token, real histogram buckets, and
   freshness and heartbeat gauges. Ship Prometheus alert rules for scheduler heartbeat, per-dataset stale
   state before the gas-day deadlines, and consecutive failures.
4. Gate migrations: remove auto-migrate from `up`; run backup, then preflight, then an approved migrate; add
   `lock_timeout` in `env.py` and `CONCURRENTLY` for indexes on large tables; print a reversibility statement
   per release.
5. Write the support model: L1/L2/L3, gas-day and weekend coverage hours, response targets per P1–P4, an
   SLA template, and an ITSM webhook from Problem reports.
6. Publish a golden-source matrix (ETRM masters trades and counterparties, Nexus masters decisions and
   analytics) and build a daily position and trade-count reconciliation against the ETRM import, with a
   breaks queue.
7. Replace the destructive 30- and 90-day prune with a retention schedule per data class (5–7 years for
   prices and audit), archive-before-delete to Parquet, and schedule it inside the product scheduler.
8. Define the environments: separate UAT and training instances, a seeding and masking procedure, and
   promotion of reference data and the licence register.
9. Add a monthly vendor usage report (per user, family, office and display or non-display, exportable), a
   seat history, licence expiry alerts, and derived-data tagging on licensed-input analytics.
10. Write a desk BCP: a fallback sources card per role, a read-only last-known-good snapshot in the desktop
    client, user-facing service notices in the top bar, and a documented full-data export for exit.
