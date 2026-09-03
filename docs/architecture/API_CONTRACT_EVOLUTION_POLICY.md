# API Contract Evolution Policy

Chinese companion: [API_CONTRACT_EVOLUTION_POLICY-CN.md](API_CONTRACT_EVOLUTION_POLICY-CN.md)

## Purpose

The public `/api` surface is a shared product contract consumed by five
surfaces: Web, Python SDK, CLI, Windows/Linux desktop shells, and the
bilingual operator documentation. Every consumer is a thin client of the same
contract, so the contract changes only through a deliberate, tested process.

This document is the single policy for evolving that contract. It closes
roadmap problem D (no evolution strategy for the stable unversioned `/api` and
five hand-maintained surfaces).

## Principles

1. **Stable unversioned `/api`.** The public surface keeps the unversioned
   `/api` prefix. Operator-only and development-only routes keep their
   profile-gated `/api/internal` and `/api/dev` prefixes. No `/v1` or
   `/api/v1` aliases are ever served.
2. **Additive-only by default.** New endpoints and new optional response
   fields are the normal evolution path. Existing paths, parameters, and
   field meanings do not change silently.
3. **Breaking changes are a major event.** Removing, renaming, or re-typing a
   path, parameter, or response field requires a written migration plan
   (deprecate → dual-run → remove across at least one release) and an
   ExecPlan review. There is no in-place breaking change.
4. **Deprecation is explicit.** A deprecated path or field must carry
   `deprecated=True` in its OpenAPI operation, a `meta.warnings` entry in its
   runtime envelope, and a removal date in this document's deprecation table.
   Deprecated surfaces remain functional until removal.
5. **Backend is the only owner of normalization.** Derived fields (FX
   conversion, tenor, hub, spreads) are computed by the backend; clients must
   consume them instead of re-implementing domain logic.

## Compatibility Gates

These tests fail CI loudly on contract drift:

| Gate | File | What it pins |
|---|---|---|
| Surface stability | `tests/contract/test_api_surface_stability.py` | the exact set of public paths; no `/v1` aliases; declared prefixes only |
| Documented counts | `tests/contract/test_architecture_alignment.py` | alembic head, table count, documented route count |
| SDK parity | `tests/contract/test_sdk_backend_parity.py` | SDK DTOs versus backend payload contracts |
| Realtime contracts | `tests/contract/test_realtime_contracts.py` | SSE/streaming semantics, no Kafka/Redis tokens |
| Validation consistency | `tests/contract/test_validation_consistency.py` | the canonical validation commands in documentation |

## Change Process

1. Write an ExecPlan under `docs/archive/agent-plans/` listing API impact and rollback.
2. For a new path: add it to `PINNED_PUBLIC_PATHS` in
   `tests/contract/test_api_surface_stability.py`, update the documented
   route count (`RELEASE_READINESS.md` and the
   `test_architecture_alignment.py` assertion) in the same change.
3. For a deprecated path: mark it `deprecated` in the router, add the
   envelope warning, and record it in the deprecation table below.
4. Add API, SDK, and contract tests before the implementation is considered
   complete.
5. Run the full validation command set from `AGENTS.md`.

## Declared Additive Paths

| Path | Declared in | Contract |
|---|---|---|
| `POST /api/optimization/portfolio-network` | R31 (`V1_R31_DB_PORTFOLIO_NETWORK_EXECPLAN.md`) | DB-only `RUNTIME_DECISION`; accepts decision metadata only, never client network/tariff/capacity/price facts |
| `POST /api/optimization/storage-dispatch` | R34 (`V1_R34_STORAGE_NOMINATION_CLIENT_WORKFLOWS_EXECPLAN.md`) | assessment-only storage dispatch; RUNTIME_DECISION composes PostgreSQL masters/observations |
| `POST /api/optimization/nomination-window` | R34 | assessment-only nomination windows; RUNTIME_DECISION loads DB window masters; no submission action |

## Deprecation Table

| Surface | Deprecated since | Removal planned | Status |
|---|---|---|---|
| `/api/workflows/*` (10 legacy shells) | 0.5.x (S4.3) | after Web/SDK/CLI migrate to the domain-specific `/api` endpoints | removed in 0.5.x after Web/SDK/CLI migration; legacy paths now return 404 |

## Non-Goals

- URL versioning (`/v1`, `/v2`): rejected; the unversioned contract evolves
  additively.
- Generated client stubs: SDK DTOs remain hand-written and are guarded by
  parity tests.
