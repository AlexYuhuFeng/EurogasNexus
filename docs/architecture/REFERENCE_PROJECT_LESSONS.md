# Reference Project Lessons

## Scope Of Review

Historical local Eurogas Nexus folders were reviewed as reference material only.
The review used repository structure and architecture/governance documentation.
It did not import `.env` values, vendor data, raw market data, internal business
data, contracts, generated reports, or source artifacts into this repository.

The `eurogas nexus.exe` Desktop demo is treated as a future Windows client UX
reference only. Its UI/UX may help explain the map-centric workspace idea, but
it is not an implementation target for V1 and should be redesigned before any
future client milestone. See `REFERENCE_EVIDENCE_LOG.md` for the local
executable artifact paths and archived QA references used during this pass.

## Useful Direction

The historical projects consistently point toward the same product ambition:

- a map-centric European gas research workspace;
- a dense terminal-style scenario and source-status surface;
- canonical network, topology, facility, route, cost, market, and scenario
  models;
- server-side ingestion and normalization;
- DB-first runtime truth;
- API-backed clients;
- SDK/CLI API client boundaries;
- explicit data scopes and governance;
- research output rather than execution behavior.

Those ideas are compatible with the current V1 bootstrap when introduced
step-by-step behind DB, API, governance, and test boundaries.

## Failure Patterns To Avoid

### Desktop-first drift

Pattern label: desktop-first drift.

The earliest implementation spent too much surface area on desktop packaging,
native runtime validation, local app acceptance, and UI workflow checks before a
stable backend source of truth existed. The current V1 should keep desktop as a
future client placeholder only.

### local-file runtime truth

Pattern label: local-file runtime truth.

Later implementations accumulated raw/canonical files, reports, snapshots, and
CSV-backed reads. Those files are useful as archives, import templates, and
fixtures, but they must not be production runtime truth. Trial and release modes
must fail closed when PostgreSQL is unavailable.

### domain sprawl

Pattern label: domain sprawl.

The broad Python implementation created many domain, readiness, hardening,
research, LLM, API, and service modules at once. That made ownership hard to
reason about. The current repo should introduce modules only when a milestone
gives them a tested boundary and a DB/API contract.

### live connector temptation

Pattern label: live connector temptation.

Historical docs and configs were close to live source integration. V1 must not
run live connector code, call external APIs, or imply entitlement for vendor or
operator data. Connectors should remain adapters with mocked tests until
credentials, licensing, lineage, and export policy are approved.

### LLM surface expansion

Historical LLM/RAG and provider-gateway surfaces were broader than the current
bootstrap should support. V1 may preserve future boundaries in docs, but it must
not call LLM providers or build production research-answering workflows until
governance, citation, data permission, and review requirements are approved.

### API surface expansion before source-of-truth

Many routes and service shells existed before the runtime store was clearly
DB-first. The current repo should prefer a small `/api` surface backed by
PostgreSQL repositories and explicit contracts.

### Governance as documentation only

Historical governance documents were valuable, but the current repo needs tests,
validation commands, fail-closed policies, and import boundaries to make those
rules enforceable.

## What To Reuse

- Product language: research-only, decision support, scenario output, risk
  simulation, market analysis, strategy evaluation.
- DB-first runtime policy.
- Canonical ID, lineage, freshness, source-reference, and scope ideas.
- API path/profile separation.
- Entitlement and export fail-closed posture.
- Map-centric product direction for future clients.
- The Windows demo's broad workspace concept, after redesign and only in a
  future client milestone.

## What Not To Reuse

- Historical `.env` files or credentials.
- Raw or canonical market/vendor data.
- Generated reports or snapshots as runtime truth.
- Frontend, desktop, Node, Rust, Tauri, Docker, Kafka, Redis, Celery, LLM, or
  live connector dependencies during V1 bootstrap.
- Over-broad service modules without a milestone, tests, and contracts.
- The existing Windows demo UI/UX as-is.
