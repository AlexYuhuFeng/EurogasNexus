# Gate 0: Release Blockers Remediation ExecPlan

Audit source: Sol 5.6 preview-hardening review (P0-1..P0-4, GasDay, resource-pool
status semantics, SSE cursor). This plan implements the Gate 0 release blockers
plus two high-value correctness items. It does NOT implement full user
authentication, data-lineage archives, or exact-algorithm replacement of every
optimizer; those remain Gate 1-4 and are called out in Non-goals.

## 1. Goal

Remove the four release-blocking defects and the GasDay inconsistency so the
product can honestly continue as a private-network preview:

1. P0-3 — EUR and GBP are never silently mixed again in route/resource-pool
   economics; conversion, when performed, uses as-of FX observations and is
   recorded in the payload.
2. P0-4 — TSO access and capacity use explicit three-state semantics
   (CONFIRMED/DENIED/UNKNOWN and KNOWN/NOT_REQUIRED/UNKNOWN); UNKNOWN fails
   closed for cross-zone routes.
3. P0-2 — external LLM provider invocation is disabled in trial/release
   profiles and entitlement evaluation fails closed before any provider call.
4. P0-1 — release API profile requires an API token on all public routes and
   declares the security scheme in OpenAPI.
5. GasDay — backend GasDay computation follows the CAM rule (05:00 UTC winter /
   04:00 UTC during DST) through one shared helper.
6. Resource-pool — allocation uses an exact min-cost-flow solver instead of the
   greedy heuristic; status never claims SUCCESS with unallocated volume.
7. SSE — events carry an `id:` cursor and honour `Last-Event-ID` so rows with
   identical timestamps are never permanently skipped.

## 2. Non-goals (deferred to later gates)

- Full user authentication, roles, SSO/OIDC, and row-level entitlement (Gate 1).
- Ontology Semantic Kernel v1 / GasDayRef / Measure / Money value objects (Gate 2).
- DB migrations for new columns (this plan changes no DB schema).
- Web evidence-pack review redesign (Gate 1/3).
- Real PostgreSQL CI, dependency pinning, backup/restore drills (Gate 4).

## 3. Product boundary

Decision support only; no trade execution. All economic outputs remain
`research_only=True` and `human_review_required=True`. Fail-closed behaviour
must never fabricate market data; unavailable inputs produce BLOCKED/PARTIAL
with explicit blockers.

## 4. Files to create/modify

Create:
- `src/eurogas_nexus/domain/market/gas_day.py` — CAM gas-day calendar helper.
- `src/eurogas_nexus/security/public_api.py` — public API token guard.
- `docs/archive/agent-plans/GATE0_RELEASE_BLOCKERS_EXECPLAN.md` (this file).

Modify:
- `src/eurogas_nexus/ingestion/simulated_market_prices.py` — use shared gas-day helper.
- `src/eurogas_nexus/ingestion/public_sources.py` — use shared gas-day helper for GIE periods.
- `src/eurogas_nexus/domain/constraints/access.py` — three-state TSO access.
- `src/eurogas_nexus/domain/route_cost/route_optimizer.py` — capacity three-state + access three-state.
- `src/eurogas_nexus/domain/route_cost/resource_pool.py` — currency fields, capacity status, exact min-cost-flow solver, status semantics.
- `src/eurogas_nexus/api/routes/public/route_cost.py` — as-of FX conversion in resource-pool option composition.
- `src/eurogas_nexus/core/config.py` — `llm_external_provider_enabled` (fail-closed in trial/release).
- `src/eurogas_nexus/api/routes/public/analysis.py` — profile gate + entitlement check before provider call.
- `src/eurogas_nexus/api/dependencies/entitlement.py` — fail closed when governance unavailable.
- `src/eurogas_nexus/api/route_profiles.py` — `require_auth` flag.
- `src/eurogas_nexus/api/app.py` — enforce auth dependency + OpenAPI security scheme.
- `src/eurogas_nexus/api/routes/public/streaming.py` — SSE `id:` cursor + `Last-Event-ID`.
- `clients/web/src/components/ScenarioWorkspace.tsx` — honest currency label.
- `clients/web/src/components/ReviewWorkspace.tsx` — honest currency label.
- `docs/ontology/gap-report.md` — remove stale "no typed ontology" claim.

Tests (new/updated):
- `tests/unit/test_gas_day.py` (new)
- `tests/unit/test_constraints_access.py`
- `tests/unit/test_resource_pool_optimization.py`
- `tests/unit/test_route_cost_route_recommendation.py`
- `tests/unit/test_route_cost_market_price_selection.py` (or new currency/FX test)
- `tests/api/test_analysis_api.py` / new LLM gate test
- `tests/api/test_api_profiles.py` / new release-auth test
- `tests/api/test_streaming_api.py`
- `tests/security/test_public_api_auth.py` (new)

## 5. Dependency policy

No new third-party dependencies. `zoneinfo` (stdlib) for DST; existing pydantic
and FastAPI features only. No GPL-family licenses introduced.

## 6. Data policy

- PostgreSQL remains the runtime source of truth; no local fallback for
  trial/release.
- FX conversion uses `fx_observations` rows as-of the market observation time
  (fallback to latest row is explicit and warns `FX_AS_OF_APPROXIMATED`).
- Unknown entitlement or unknown TSO/capacity data fails closed.

## 7. API impact

- `GET/POST /api/*` in release profile: require `Authorization: Bearer <token>`
  or `X-Eurogas-Api-Key`; 401 missing/invalid, 403 invalid (hmac mismatch),
  503 token not configured (fail-closed).
- `POST /api/analysis/query`, `POST /api/reports/portfolio`: when the profile
  disables external providers, `provider_status` returns
  `LLM_PROVIDER_DISABLED_IN_PROFILE` and no provider call occurs; entitlement
  denial returns `ENTITLEMENT_DENIED:<source>`.
- `GET /api/route-cost/resource-pool/options`: sale options now carry
  `sale_price_currency`, `sale_price_unit`, and FX provenance fields
  (`fx_converted_from`, `fx_rate_used`, `fx_observation_id`, `fx_value_date`);
  options that cannot be converted are excluded with a blocker.
- SSE endpoints: events include `id:`; server honours `Last-Event-ID`.
- OpenAPI (development profile only): documents `ApiKeyAuth` security scheme.

## 8. DB impact

No schema changes. FX reads use the existing `fx_observations` table. Migration
head stays at 0018.

## 9. Tests

- Unit: gas-day boundaries (DST transitions), access three-state, capacity
  three-state, currency mismatch fail-closed, exact-solver counterexample
  (greedy 2000 vs optimal 3700), FX conversion provenance.
- API: release auth 401/403/503; analysis provider disabled; streaming cursor
  resume; resource-pool options currency fields.
- Existing suite must stay green except tests that encoded the old fail-open
  behaviour (those are updated deliberately and noted in the diff).

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance criteria

- No code path mixes EUR and GBP without conversion + provenance.
- `tso_access_status(required, None)` returns UNKNOWN; UNKNOWN blocks cross-zone routes.
- Capacity `None` never means unlimited; only explicit NOT_REQUIRED does.
- `invoke_provider=true` in trial/release never reaches an external LLM.
- Release profile rejects unauthenticated requests.
- Simulated/GIE gas-day boundaries match CAM at DST transitions.
- Resource pool returns the exact optimum for the documented counterexample and
  never SUCCESS with unallocated volume.
- SSE resumes exactly (no lost rows) when >200 rows share one timestamp.

## 12. Rollback notes

All changes are additive or locally scoped. Rollback = revert this plan's
commits; no DB migration involved. The old greedy solver remains in git
history; the new solver is deterministic and unit-tested, so a regression would
surface in `tests/unit/test_resource_pool_optimization.py`.
