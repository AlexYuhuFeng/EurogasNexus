# Data Status and Provenance

Eurogas Nexus separates research state from current market state.

## Where evidence is shown

- Source and freshness columns on market/route/strategy cards.
- Warnings and missing-input lists on every analytical result.
- Evidence packs in Review.
- Source Center for credential/certification/runtime state per source.

## Status vocabulary

- `FRESH/LATE/STALE/MISSING/NOT_EXPECTED`: backend-owned freshness evaluation.
- `BLOCKED`: a required input is missing or unknown; the calculation did not
  proceed.
- `UNAVAILABLE`: the data or service cannot currently provide evidence.
- `_Sim`: simulated preview data; never live licensed evidence.
- `research_only` / `human_review_required`: decision-support guardrails.

If a value looks surprising, check the gas day/product context, the source,
the freshness timestamp, and the warning register before interpreting it.
