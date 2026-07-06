# Documentation Consistency Audit

Date checked: 2026-07-06

This audit reviews whether repository documentation matches the current product
reality. Eurogas Nexus should be described as a commercial European gas
intelligence and decision-support workspace. It is not merely a research-only
sandbox, and it is also not an execution venue, nomination system, settlement
system, legal-advice tool, or ETRM replacement.

## Executive Summary

The cleanup standard is:

1. **Product identity**: use "European gas intelligence workspace" or
   "decision-support workspace" instead of "research-only".
2. **Release language**: use normal release-line language such as
   `v0.5-preview`, "current release line", "current release-candidate scope", or
   "current product boundary". Avoid treating "V1" as the product identity.
3. **Boundary language**: the product supports commercial analysis, route
   economics, portfolio/resource-pool optimization, market positioning, strategy
   evaluation, LLM-assisted explanation, and reporting. The boundary is
   non-execution and human-reviewed, not research-only.
4. **Resource terminology**: use `Resource Terms` for the user-facing workspace
   that captures EFET-style resource assumptions. Keep `contracts` and
   `upstream-contracts` only as technical/API compatibility identifiers.

## Completed Cleanup

- Added a root `LICENSE` file with proprietary source-visible terms.
- Rewrote `CONTRIBUTING.md` as a human contributor guide and removed
  research-only positioning.
- Removed the local machine path from `PROJECT_DIRECTORY.md`.
- Normalized `docs/api/API_PATH_POLICY.md` so `/api` is the documented public
  path and `/api/v1` is hidden compatibility.
- Renamed `docs/release/V1_RELEASE_READINESS.md` to
  `docs/release/RELEASE_READINESS.md`.
- Added `docs/release/PRODUCTION_READINESS_BACKLOG.md`.
- Added neutral runtime validation and release-build entrypoints.
- Added `docs/operations/LIVE_POSTGRESQL.md` and reduced the old
  `LIVE_POSTGRESQL_V1.md` file to a compatibility pointer.
- Stabilized CI/release workflow action versions and default release behavior.
- Renamed the user-facing `Order Records` surface to `Market Positioning` while
  keeping the technical `orders` workspace id for compatibility.
- Introduced grouped workspace navigation and added
  `docs/clients/WORKSPACE_NAVIGATION_SPEC.md`.
- Productized `Contracts` as the user-facing `Resource Terms` workspace in
  README, Web client spec, client docs, and Web i18n overrides while keeping the
  technical `contracts` workspace id and API field names for compatibility.

## Remaining High-Priority Items

### DOC-001 Compatibility wrappers still contain `v1` in filenames

The following files remain intentionally as compatibility wrappers or link
pointers:

- `scripts/ops/validate_v1_runtime_db.py`
- `scripts/release/build_v1_release.sh`
- `scripts/release/build_v1_release.ps1`
- `docs/operations/LIVE_POSTGRESQL_V1.md`

Preferred replacements are:

- `scripts/ops/validate_runtime_db.py`
- `scripts/release/build_release.sh`
- `scripts/release/build_release.ps1`
- `docs/operations/LIVE_POSTGRESQL.md`

These compatibility files can be removed later after CI, docs, release notes, and
user habits have moved to the neutral names.

### DOC-002 Product boundary should be durable

The non-execution boundary should not be written as if it only applies to one
release. The durable product-level boundary is:

- no order entry;
- no order routing;
- no order amendment or cancellation;
- no nomination submission;
- no settlement/accounting;
- no official approvals;
- no legal advice;
- no official trading recommendation;
- no auto-trading;
- no ETRM replacement behavior.

### DOC-003 "Trading cockpit" can sound executable

The map-first cockpit is useful, but the phrase "trader cockpit" may imply an
execution terminal. Prefer:

- map-first decision cockpit;
- map-first gas intelligence workspace;
- commercial decision-support cockpit;
- route and portfolio decision cockpit.

When "trader" is retained, pair it with "decision support" and "human review
required".

### DOC-004 "Live monitor" and "live strategy" need careful wording

Strategy pages may monitor live or near-live observations, but should not imply
automated action or official recommendations. Recommended wording:

- live signal monitoring;
- paper monitor;
- shadow-run monitor;
- candidate action for human review;
- source freshness and warning state.

### DOC-005 README still needs actual visuals

The README contains a Product Visuals section, but screenshot files are not yet
committed. Add synthetic/sanitized visuals for:

1. Network map cockpit;
2. Scenario and route economics;
3. Review and report.

These should use preview or synthetic PostgreSQL-backed data and must not contain
restricted vendor, customer, or strategy material.

### DOC-006 API path policy must remain single-source-of-truth

The repository states `/api` as the public path and `/api/v1` as hidden
compatibility. Future docs, SDK snippets, UI mocks, tests, and README examples
should follow `docs/api/API_PATH_POLICY.md`.

Add a doc-hygiene CI check later to flag public prose that contradicts this
policy.

### DOC-007 Production readiness should become managed work

`docs/release/PRODUCTION_READINESS_BACKLOG.md` is the tracked backlog, but it is
still a markdown file. Convert each item into GitHub issues or milestones when
issue automation is available.

Recommended first issue set:

- GOV-003 Add sanitized product visuals;
- OPS-001 Ingestion scheduling, retry, and monitoring;
- OPS-002 Provider live-test matrix;
- SEC-001 Auth, audit, entitlement, and export governance;
- SEC-002 Role model and external secure configuration integration;
- SEC-003 CI safety and doc-hygiene checks;
- WF-001 Persist EFET-style resource workflow through backend APIs;
- RUN-001 Backup, migration, incident, and rollback runbooks.

## Medium-Priority Consistency Recommendations

### Naming and UX

- Prefer "Network" or "Decision Cockpit" over "Trader Cockpit" in user-facing
  titles.
- Use "Market Positioning" for the read-only imported observation and PnL
  workspace. Keep `orders` only as a technical compatibility id until route
  migration is explicitly planned.
- Use "Resource Terms" for the EFET-style resource-assumption workspace. Keep
  `contracts` only as a technical compatibility id until route migration is
  explicitly planned.
- Use "candidate", "option", "signal", "warning", "human review" consistently.

### Data-state language

Every UI and report surface should distinguish live, delayed, preview, simulated,
stale, unavailable, partial, access-not-configured, and unsupported states. The
application should never silently replace missing runtime data with invented
client-side values.

### LLM language

LLM output should be described as structured-data explanation and report support,
not as trading advice. Standard badges: decision support, human review required,
source references available, missing inputs, warning state, and provider/model
metadata.

## Suggested Follow-Up Commits

1. `Add README product visuals`
   - commit synthetic/sanitized screenshots under `docs/assets/readme/`.

2. `Add doc-hygiene checks`
   - detect local machine authority paths;
   - detect public-doc API path drift;
   - detect product-boundary language drift.

3. `Migrate compatibility route ids`
   - optional later migration from technical workspace ids `contracts` and
     `orders` to `resource-terms` and `market-positioning`, with backward
     compatibility.

## Current Product Statement

Use this wording as the default public-facing description:

> Eurogas Nexus is a PostgreSQL-first European gas intelligence workspace for
> infrastructure visibility, source operations, route economics, resource-pool
> optimization, market positioning, strategy evaluation, and trader-reviewed
> decision support. It does not execute trades, route orders, submit nominations,
> replace an ETRM, provide legal advice, or issue official trading
> recommendations.
