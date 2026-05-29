# Project North Star

## Ultimate Goal

Eurogas Nexus is a research-only European gas decision-support platform. The
long-term product goal is an internal, governed workspace for pipeline gas, LNG
regas, storage, beach delivery, market-price context, route economics,
feasibility, allocation, strategy testing, nowcasting, monitoring, and research
reporting.

The current repository is the disciplined V1 foundation for that goal: a
DB-first, API-first, SDK-ready and SDK-required platform. It exists to make the
platform safe and systematic before adding broad product behavior.

## Current V1 Posture

- PostgreSQL is the runtime source of truth.
- Live local PostgreSQL validation is part of V1 runtime readiness when a safe
  DB URL is configured.
- FastAPI owns the HTTP API boundary.
- SQLAlchemy and Alembic own the DB access and migration boundary.
- SDK and CLI code must call the backend API.
- Clients access PostgreSQL-backed runtime data through SDK/API boundaries, not
  direct database connections.
- Local files are import templates, archives, reports, fixtures, or development
  fallback only.
- Analysis outputs must preserve assumptions, missing inputs, warnings, source
  references, lineage, `research_only`, and `human_review_required` when
  relevant.

No frontend runtime implementation belongs in the current backend foundation
milestones. SDK, CLI, web, and desktop clients are consumers of the API. The
Python SDK is required for V1. Web and Windows runtime implementation starts
only when their selected release milestones activate those surfaces. Their
designs are documented now under `docs/clients/` so client implementation is
deliberate instead of improvised.

## Product Boundary

Eurogas Nexus helps users research and evaluate European gas context. It must
not become a trade execution, order-entry, order-routing, trade-capture,
nomination, settlement, official approval, legal-advice,
official-trading-recommendation, auto-trading, or ETRM replacement system.

Reserved future interfaces may be documented only as reserved interfaces. They
must not imply that Eurogas Nexus can create, route, execute, book, approve, or
settle trades.

## Architecture Direction

The target system is built in this order:

1. Repository governance, import safety, DB foundation, and API path policy.
2. DB runtime hardening and explicit migration lifecycle.
3. Runtime store and repository contracts for DB-first reads and writes.
4. Canonical reference network, topology, asset, and market/fundamental models.
5. Governed ingestion, normalization, data quality, freshness, and lineage.
6. Research-only domain workflows exposed through stable `/api/v1` routes.
7. Auth, audit, governance, entitlement, release, and operations.
8. Required Python SDK expansion and CLI expansion.
9. Web and Windows clients that consume SDK/API-backed `/api/v1` contracts.

This sequence intentionally delays business features until source-of-truth,
lineage, entitlement, and route boundaries are testable.

## What Historical References Contribute

Historical local Eurogas Nexus projects clarify the ambition: a map-centric gas
research workspace with canonical gas-network data, market context, scenario
testing, governed data scopes, and API-backed clients.

They also show what to avoid: desktop-first drift, local-file runtime truth,
domain sprawl, premature live connector behavior, broad LLM/RAG surfaces,
frontends before backend contracts, and route/API expansion without a stable
source of truth.

The current repo should reuse the architecture lessons, vocabulary, guardrails,
and canonical-model ideas. It should not copy historical code, data artifacts,
secrets, vendor files, or generated reports.

## Engineering Standard

Every milestone should answer:

- What boundary is being made more true?
- What files are allowed to change?
- What data policy applies?
- What API and DB impact exists?
- What validation proves the milestone?
- What remains `PARTIAL` or `BLOCKED`?

If a requirement is unclear, create a gap report rather than invent behavior.
