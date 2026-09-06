# Dataset Architecture (CR-14)

Source: `src/eurogas_nexus/domain/research/datasets.py`, migration
`alembic/versions/0031_research_data_foundation.py`.

## Layers

1. Semantic registry: canonical entities, source mappings, series
   definitions, feature definitions, target definitions, resampling policies.
2. Declarative spec: `DatasetSpec` pins target/feature ids, window, origin
   frequency, history lookback, point-in-time policy, coverage floor, source
   restrictions, and entitlement envelope.
3. Builder: `build_dataset` emits an immutable `DatasetBuildResult` with rows,
   columns, quality report, leakage issues, lineage, warnings, and content
   hash.
4. Persistence: `dataset_snapshots` plus dependency, build-issue, and artifact
   child tables.
5. Export: Parquet (primary) and CSV (debug) adapters.

## Persisted tables (migration 0031)

- `canonical_entities`
- `source_entity_mappings`
- `series_definitions`
- `feature_definitions`
- `target_definitions`
- `resampling_policies`
- `dataset_specs`
- `dataset_snapshots`
- `dataset_snapshot_dependencies`
- `dataset_build_issues`
- `dataset_artifacts`
- `forecast_observations`
- `observation_temporal_metadata`

## DatasetSpec fields

- `dataset_spec_id`, `name`, `description`, `version`
- `target_ids` (required), `feature_ids`, `entity_ids`
- `start`, `end`, `history_lookback`, `forecast_origin_frequency`, `timezone`
- `point_in_time_policy`
- `resampling_policy_id`, `missing_data_policy`, `minimum_coverage`
- `source_restrictions`, `entitlement_envelope`, `split_specs`,
  `output_format`, `ontology_version`
- `content_hash()` and `qualified_version()` pin the exact spec.

## Builder guarantees

- Every origin computes features only from records eligible at that origin.
- Forecast series use the latest eligible vintage; actual rows never replace
  historical vintages.
- Target labels are computed strictly after `origin + horizon` and are never
  visible to feature construction.
- Row provenance lists the exact source references used for that row.
- `content_hash` covers spec version plus all rows, so rerunning the same
  spec and inputs reproduces the same snapshot id and hash.
- `STRICT` mode marks the snapshot `build_blocked` on temporal leakage
  blockers; `EXPLORATORY` mode records explicit warnings.

## Quality report

`rows`, `origins`, `observed_values`, `missing_values`,
`missing_percentage`, `coverage`, `minimum_coverage`, `temporal_integrity`,
`build_blocked`, `source_count`.

## Entitlement and export

- Each snapshot stores its `entitlement_envelope`; the export route returns
  `403` with `export_denied_entitlement` for any policy other than
  `EXPORT_ALLOWED`.
- `export_parquet`/`export_csv` enforce the same gate at the domain layer.
