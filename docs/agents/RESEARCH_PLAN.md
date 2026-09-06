# ResearchPlan (CR-15)

Source: `src/eurogas_nexus/domain/agents/research_plan.py`.

## Required structure

`research_plan_id`, `objective`, `question`, `market_scope`, `entities`,
`product`, `horizon`, `hypotheses_to_test`, `required_evidence`, `analyses`,
`data_quality_requirements`, `statistical_requirements`,
`strategy_generation_allowed`, `stopping_conditions`.

## Validation

`validate_research_plan` checks entity existence, series availability,
history coverage, temporal provenance, entitlement, horizon syntax, and
analysis support. It never substitutes a fake series.

Blocker codes: `ENTITY_NOT_FOUND`, `SERIES_UNAVAILABLE`,
`INSUFFICIENT_HISTORY`, `TEMPORAL_PROVENANCE_INSUFFICIENT`,
`ENTITLEMENT_MISSING`, `INVALID_ANALYSIS`, `HORIZON_INVALID`, `DATA_MISSING`.

## Offline deterministic planner

`deterministic_plan` creates a conservative plan without a live LLM. It
names NBP/TTF and FX evidence requirements but never invents market values.
