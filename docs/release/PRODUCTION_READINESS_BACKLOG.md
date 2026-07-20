# Production Readiness Backlog

This backlog turns the production gaps listed in `docs/release/RELEASE_READINESS.md` into actionable work items. It does not expand the current product boundary: Eurogas Nexus remains a decision-support platform requiring human review.

## Milestone A: Repository Governance and Public Presentation

### GOV-001 Add and maintain proprietary license notice

- Status: started
- Priority: P0
- Scope: keep `LICENSE`, README license text, and public repository warnings aligned.
- Acceptance:
  - `LICENSE` exists at repository root.
  - README links to `LICENSE`.
  - CONTRIBUTING explains that the repository is source-visible but proprietary.

### GOV-002 Keep contribution and agent instructions separate

- Status: started
- Priority: P0
- Scope: `CONTRIBUTING.md` remains human-facing; agent execution plans remain in `AGENTS.md` and `.agent/`.
- Acceptance:
  - human setup exists for Windows and macOS/Linux.
  - architecture boundary rules are still explicit.
  - no local machine paths are used as authority references.

### GOV-003 Maintain visual product evidence

- Status: planned
- Priority: P1
- Scope: add screenshots or safe mockups for the map-first cockpit, scenario workflow, and review/report screen.
- Acceptance:
  - README contains a Product Visuals section.
  - screenshot files are synthetic or sanitized.
  - no licensed vendor data, customer data, or real strategy parameters appear in visuals.

## Milestone B: Runtime Ingestion Operations

### OPS-001 Production ingestion scheduling, retry, and monitoring

- Status: planned
- Priority: P1
- Scope: define and implement scheduler, retry policy, job state, failure classification, and operator-visible status for ingestion workflows.
- Acceptance:
  - ingestion jobs expose last run, next run, retry count, failure reason, and freshness state.
  - operator runbook documents restart, backfill, and degraded-source handling.
  - test coverage validates failure visibility without leaking credentials.

### OPS-002 Provider live-test matrix

- Status: planned
- Priority: P1
- Scope: validate provider-specific integrations after customer credential and entitlement approval.
- Provider families:
  - EEX
  - ICE OCM
  - Trayport
  - Kpler
  - Platts
  - ICIS
  - Argus
  - brokers
  - weather
  - LLM providers
- Acceptance:
  - each provider has a live-test plan, entitlement requirement, and expected degraded/offline UI state.
  - tests are gated so CI never requires real credentials.

## Milestone C: Security, Entitlement, and Governance

### SEC-001 Strengthen authentication, audit, entitlement, and export governance

- Status: planned
- Priority: P1
- Scope: define role-aware access, auditable actions, source entitlement states, and export restrictions.
- Acceptance:
  - every sensitive operation has an actor, timestamp, scope, and audit record.
  - export-disabled states explain restrictions without legal advice.
  - UI displays entitlement and freshness state for live-source panels.

### SEC-002 Multi-user role model and secret-manager integration

- Status: planned
- Priority: P1
- Scope: replace single-operator assumptions with role model and external secret-manager integration.
- Acceptance:
  - roles and permissions are documented.
  - secrets are write-only from client forms and not returned to clients.
  - local development still supports deterministic test mode without live provider calls.

### SEC-003 Add CI secret scanning and static safety checks

- Status: planned
- Priority: P1
- Scope: add automated checks for committed secrets, local absolute paths, and public-doc API path drift.
- Acceptance:
  - CI detects obvious credential-like material.
  - CI rejects tracked `C:\Users\` or `/Users/` authority paths in docs.
  - CI flags public docs that contradict `docs/api/API_PATH_POLICY.md`.

## Milestone D: Business Workflow Persistence

### WF-001 Persist EFET-style customer contract and resource workflow through backend APIs

- Status: planned
- Priority: P1
- Scope: move customer contract/resource workflow from preview/testing shape into auditable backend-backed APIs.
- Acceptance:
  - contracts, resources, pricing basis, settlement terms, capacity terms, and provenance are persisted through API boundaries.
  - clients do not store contract truth locally.
  - outputs remain decision-support and human-review-required.

## Milestone E: Operational Runbooks

### RUN-001 Backup, migration, incident, and rollback runbooks

- Status: planned
- Priority: P1
- Scope: document operator procedures for database backup, Alembic migration, incident response, release rollback, and degraded-source operation.
- Acceptance:
  - runbooks cover normal operation and failure recovery.
  - migration rollback limitations are clearly stated.
  - no secrets or deployment-specific confidential values are included.

## Milestone F: Deployment Packaging and Discoverability

### DEP-001 Make deployment roles and release assets unambiguous

- Status: planned
- Priority: P0
- Scope: align GitHub Release asset names, release notes, deployment documentation, and installer behavior so operators can distinguish the standalone desktop Client installer from the Server and AllInOne deployment bundle before downloading or installing anything.
- Acceptance:
  - the standalone NSIS asset is labeled as `Client only` in its filename or adjacent release description.
  - release notes identify the exact asset required for `Server`, `Client`, and `AllInOne` roles.
  - the deployment bundle is published as a separate, clearly named asset containing `Deploy-EurogasNexus.ps1`, server runtime scripts, Compose configuration, gateway configuration, and operating instructions.
  - installing the standalone desktop Client does not imply that PostgreSQL, API, migrations, or ingestion workers were installed.
  - first launch and Settings clearly show the configured API endpoint and a diagnostic state when no reachable backend exists.
  - automated release tests verify the expected role-specific asset set and reject ambiguous or missing asset names.
  - English and Mandarin deployment documents contain the same role and asset guidance.

## Non-goals

The backlog does not authorize:

- order entry;
- order routing;
- order amendment or cancellation;
- trade capture;
- nomination submission;
- official approvals;
- settlement/accounting;
- legal advice;
- official trading recommendations;
- auto-trading;
- ETRM replacement behavior.
