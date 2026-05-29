# R6: Research Workflow Models Report

**Milestone ID:** R6
**Status:** COMPLETE
**Date:** 2026-05-29

## Evidence

- 11 research workflow dataclass models with required metadata:
  RouteCostResult, IndicativeNetbackResult, FeasibilityResult,
  AllocationScenarioResult, MonitoringAlert, NowcastResult, BacktestResult,
  CandidateRanking, ShadowRunResult, LlmMarketAnalysis, ResearchBrief.
- All models inherit research_only=True, human_review_required=True,
  assumptions, missing_inputs, warnings, source_references, lineage.
- CandidateAction enum restricted to research-only semantics (no execute,
  place_order, submit_nomination, approve_trade).
- 10 workflow API routes: route-cost, netback, feasibility, allocation,
  monitoring, nowcast, backtest, shadow-run, llm-analysis, brief.
- 2 glossary routes: list terms, get term — English and Mandarin (zh-CN)
  definitions for 15 gas/energy terms.
- All routes return research metadata envelope.
- All data is synthetic fixtures.
- App import DB-free (44 routes).
- Default tests DB-free.

## Files Created / Modified

- `src/eurogas_nexus/workflows/__init__.py`
- `src/eurogas_nexus/workflows/models.py` — 11 dataclass models + enums
- `src/eurogas_nexus/api/routes/v1/workflows.py` — 10 workflow routes
- `src/eurogas_nexus/api/routes/v1/glossary.py` — 2 glossary routes (en/zh)
- `src/eurogas_nexus/api/route_registration.py` — +2 routers
- `.agent/plans/V1_R6_RESEARCH_WORKFLOW_MODELS_EXECPLAN.md`
- `data/release_v1/r6_research_workflow_models_report.md`
- `tests/contract/test_workflow_models.py` (11 tests)
- `tests/api/test_workflows_api.py` (15 tests)

## DB Impact

None. Pure dataclass models with synthetic fixtures.

## API Impact

12 new routes. Route count: 32 → 44.

## Validation

- ruff: All checks passed
- pytest: 239 passed (was 204; +35 new tests)
- app: import ok, 44 routes

## Next Milestone

R7: Route Cost and Indicative Netback (first live research workflow)
