# Documentation Consistency Audit

Date checked: 2026-07-06

This audit reviews whether the repository documentation matches the current
product reality. Eurogas Nexus should be described as a commercial European gas
intelligence and decision-support workspace. It is not merely a research-only
sandbox, and it is also not an execution venue, nomination system, settlement
system, legal-advice tool, or ETRM replacement.

## Executive Summary

The repository is technically well structured, but several docs still carry older
milestone language and overly restrictive wording. The cleanup standard is:

1. **Product identity**: use "European gas intelligence workspace" or
   "decision-support workspace" instead of "research-only".
2. **Release language**: use normal release-line language such as
   `v0.5-preview`, "current release line", "current release-candidate scope", or
   "current product boundary". Avoid treating "V1" as the product identity.
3. **Boundary language**: the product supports commercial analysis, route
   economics, portfolio/resource-pool optimization, market positioning, strategy
   evaluation, LLM-assisted explanation, and reporting. The boundary is
   non-execution and human-reviewed, not research-only.

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
- Updated README positioning, visuals guidance, documentation links, and
  release-line language.
- Added neutral runtime validation and release-build entrypoints:
  - `scripts/ops/validate_runtime_db.py`
  - `scripts/release/build_release.sh`
  - `scripts/release/build_release.ps1`
- Kept old `v1` script names as compatibility wrappers, not preferred entrypoints.
- Added `docs/operations/LIVE_POSTGRESQL.md` and reduced the old
  `LIVE_POSTGRESQL_V1.md` file to a compatibility pointer.
- Updated CI/release workflow action versions to currently valid major versions.

## High-Priority Remaining Inconsistencies

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

### DOC-002 "Research-only" wording is too narrow

The project is not only for research. It supports commercial desk workflows such
as route economics, resource-pool optimization, market positioning, strategy
shadow runs, imported screen observations, and reporting. Docs should say
"decision support" or "commercial decision-support" instead.

Recommended wording:

> Eurogas Nexus is a European gas intelligence and decision-support workspace.
> Outputs require human review and are not execution instructions, official
> approvals, legal advice, settlement records, or ETRM records.

Avoid:

> research-only platform

unless describing a specific demo, test, or historical milestone.

### DOC-003 Product boundary should be durable, not milestone-specific

The non-execution boundary should not be written as if it only applies to one
release. The better product-level boundary is:

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

This should be the durable product boundary unless a future formal product
decision changes it.

### DOC-004 "Trading cockpit" can sound executable

The map-first cockpit is useful, but the phrase "trader cockpit" may imply an
execution terminal. Prefer:

- map-first decision cockpit;
- map-first gas intelligence workspace;
- commercial decision-support cockpit;
- route and portfolio decision cockpit.

When "trader" is retained, pair it with "decision support" and "human review
required".

### DOC-005 "Live monitor" and "live strategy" need careful wording

Strategy pages may monitor live or near-live observations, but should not imply
automated action or official recommendations. Recommended wording:

- live signal monitoring;
- paper monitor;
- shadow-run monitor;
- candidate action for human review;
- source freshness and warning state.

Avoid wording that implies live trading, automated allocation, or immediate
execution.

### DOC-006 Order Records naming can imply trade capture

The current "Order Records" surface is read-only imported observation context.
To reduce ETRM confusion, consider renaming the page to one of:

- Screen Observations;
- Imported Observations;
- Market Positioning;
- Imported Order/PnL Context.

If "Order Records" is retained, every page and component must clearly say it is
read-only imported context and not trade capture.

### DOC-007 Contracts page can imply an ETRM

The Contracts surface is valuable but should be framed as contract assumptions,
resource terms, and portfolio-resource context for decision support. It should
not suggest official contract capture, contract lifecycle management, settlement,
or ETRM replacement.

Recommended labels:

- Resource Terms;
- Contract Assumptions;
- EFET-style Resource Terms;
- Resource Contract Library for decision support.

### DOC-008 README still needs actual visuals

The README now contains a Product Visuals section, but screenshot files are not
yet committed. Add synthetic/sanitized visuals for:

1. Network map cockpit;
2. Scenario and route economics;
3. Review and report.

These should use preview or synthetic PostgreSQL-backed data and must not contain
restricted vendor, customer, or strategy material.

### DOC-009 API path policy must remain single-source-of-truth

The repository now states `/api` as the public path and `/api/v1` as hidden
compatibility. Future docs, SDK snippets, UI mocks, tests, and README examples
should follow `docs/api/API_PATH_POLICY.md`.

Add a doc-hygiene CI check later to flag public prose that contradicts this
policy.

### DOC-010 Production readiness should become managed work, not static prose

`docs/release/PRODUCTION_READINESS_BACKLOG.md` is now the tracked backlog, but it
is still a markdown file. Convert each item into GitHub issues or milestones when
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
- Prefer "Market Positioning" over "Order Records" if the page is read-only.
- Prefer "Resource Terms" or "Contract Assumptions" if the page is not an ETRM.
- Use "candidate", "option", "signal", "warning", "human review" consistently.

### Data-state language

Every UI and report surface should distinguish:

- live;
- delayed;
- preview;
- simulated;
- stale;
- unavailable;
- partial;
- access not configured;
- unsupported.

The application should never silently replace missing runtime data with invented
client-side values.

### LLM language

LLM output should be described as structured-data explanation and report support,
not as trading advice. Standard badges:

- decision support;
- human review required;
- source references available;
- missing inputs;
- warning state;
- provider/model metadata.

## Suggested Follow-Up Commits

1. `Rename read-only market-positioning workspace`
   - decide whether `Order Records` should become `Imported Observations` or
     `Market Positioning` in UI and docs.

2. `Rename contract assumptions workspace`
   - decide whether `Contracts` should become `Resource Terms` or
     `Contract Assumptions` in UI and docs.

3. `Add README product visuals`
   - commit synthetic/sanitized screenshots under `docs/assets/readme/`.

4. `Add doc-hygiene checks`
   - detect local machine authority paths;
   - detect public-doc API path drift;
   - detect product-boundary language drift.

## Current Product Statement

Use this wording as the default public-facing description:

> Eurogas Nexus is a PostgreSQL-first European gas intelligence workspace for
> infrastructure visibility, source operations, route economics, resource-pool
> optimization, market positioning, strategy evaluation, and trader-reviewed
> decision support. It does not execute trades, route orders, submit nominations,
> replace an ETRM, provide legal advice, or issue official trading
> recommendations.
