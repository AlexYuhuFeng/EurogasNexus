# ML Readiness Report (CR-14 / P13)

## Purpose

Make future forecasting work possible without shipping training
infrastructure in this milestone. CR-14 delivers a leakage-safe, versioned,
provenance-complete, semantically unambiguous multivariate European-energy
dataset foundation.

## Ready now

| Capability | Where |
|---|---|
| Versioned energy ontology and canonical entities | `domain/research/ontology.py`, `energy-ontology/v1` |
| Point-in-time source mappings | `canonical_entities`, `source_entity_mappings` |
| observed/available/ingested temporal semantics | `domain/research/temporal.py` |
| Forecast vintages and actual/forecast/assessment/simulated kinds | `forecast_observations`, `ObservationKind` |
| Versioned feature registry with dependency closure | `domain/research/features.py`, `feature_definitions` |
| Versioned target registry and target-never-feature gate | `domain/research/targets.py`, `target_definitions` |
| Bounded resampling (no unlimited ffill) | `domain/research/resampling.py` |
| Declarative DatasetSpec and immutable snapshots | `domain/research/datasets.py`, `dataset_snapshots` |
| Leakage validation with blockers/warnings | `domain/research/leakage.py` |
| Time-based splits with embargo/gap | `DatasetSplit` |
| Quality report and content hashing | `DatasetBuildResult.as_metadata()` |
| Parquet/CSV export with entitlement gate | `domain/research/export.py` |
| Lineage and reproducibility | snapshot metadata + dependency tables |
| Typed agent capability contracts (MCP-free) | `domain/research/capabilities.py` |
| Catalog/build/quality/export APIs | `/api/research/*` |

## Deliberately not ready

- No model training, no GPU, no training jobs.
- No MCP adapter; capability contracts are transport-neutral and become the
  input to CR-15 (`Agent-Native Capability Layer`).
- No direct DB exposure to agents: agents call typed capabilities, never SQL.
- No execution/order/nomination semantics.

## Known limitations

- UAT price feeds are simulated; the representative snapshot uses
  `EXPLORATORY` mode and labels simulated targets explicitly.
- Runtime feature computers currently cover builtin spread/route-margin
  transforms; new transforms require a versioned `transformation` reference
  and tests.
- Official historical availability timestamps must be certified by sources
  before production `STRICT` datasets can be claimed.

## Next milestone

CR-15 / P14: Agent-Native Capability Layer, unless a blocker is found.
