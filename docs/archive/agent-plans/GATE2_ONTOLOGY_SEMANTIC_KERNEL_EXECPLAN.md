# Gate 2: Ontology v0.3 — Semantic Kernel v1 + Binding Integrity — ExecPlan

## 1. Goal

1. Ship the Semantic Kernel v1 value objects (`CanonicalId`, `ExternalIdentifier`,
   `Measure`, `Money`, `PriceBasis`, `FxConversionRef`, `TimeInterval`,
   `GasDayRef`, `GasYearRef`, `EffectivePeriod`, `JurisdictionRef`,
   `RegulatoryInstrumentRef`, `SourceRef`, `LineageRef`, `OntologyVersion`,
   `MappingVersion`) with versioned regulatory instruments (715/2009 superseded
   by 2024/1789; REMIT amended by 2024/1106; CAM 2017/459; interoperability
   2015/703).
2. Split capacity-product semantics: `CapacityProductDuration`
   (yearly/quarterly/monthly/daily/within-day) vs `AuctionTiming`; WEEKLY marked
   as a non-standard extension.
3. Classify actions: `ActionKind` gains SYSTEM / ANALYTICAL /
   DECISION_CANDIDATE / EXTERNAL_ACTION categories.
4. Unify result statuses in the ontology: `StatusKind`
   (SUCCESS/PARTIAL/BLOCKED/UNKNOWN).
5. Make concept↔table bindings machine-checkable at slot level
   (`CONCEPT_SLOT_COLUMN_MAPS` + integrity test), and close the real gaps:
   `flow_observations.kind`, `capacity_profiles.capacity_product/scope`.

## 2. Non-goals

- RDF/OWL/graph DB (explicitly out of scope per audit).
- Hub/MarketArea migration to a DB reference master (next Gate 2 milestone).
- glossary `concept_id` migration.

## 3. Product boundary

Value objects and vocabulary only; no behavior changes in optimizers except
status string sources (Gate 3 wires them to `StatusKind`).

## 4. Files

Create:
- `src/eurogas_nexus/domain/ontology/semantic_kernel.py`
- `alembic/versions/0019_ontology_slots_and_optimization_runs.py`
- `tests/unit/test_semantic_kernel.py`
- `tests/unit/test_ontology_binding_integrity.py`

Modify:
- `src/eurogas_nexus/domain/ontology/vocabulary.py` (new enums)
- `src/eurogas_nexus/domain/ontology/actions.py` (action categories)
- `src/eurogas_nexus/domain/ontology/bindings.py` (slot→column maps)
- `src/eurogas_nexus/domain/ontology/concepts.py` (slot fixes for
  MarketObservation, FlowObservation, CapacityProfile)
- `src/eurogas_nexus/db/models/observation.py` (FlowObservationRecord.kind)
- `src/eurogas_nexus/db/models/route_cost.py` (CapacityProfileRecord product/scope)
- `src/eurogas_nexus/db/registry.py` (new required tables)

## 5. Dependency policy

stdlib only (`zoneinfo` already used by gas_day).

## 6. Data policy

Migration 0019 adds nullable columns with defaults; existing rows keep values.

## 7. API impact

None (payload shapes unchanged). `StatusKind` values equal current strings.

## 8. DB impact

Migration 0019: `flow_observations.kind` (default 'actual'),
`capacity_profiles.capacity_product`, `capacity_profiles.capacity_scope`,
plus `optimization_runs` (used by Gate 3 milestone).

## 9. Tests

- Semantic kernel: measure/money/effective-period/gas-day-ref/gas-year
  construction; jurisdiction registry contains 2024/1789 and 2024/1106 with
  correct effective dates; supersession 715/2009 → 2024/1789.
- Binding integrity: every bound concept has a slot→column map entry for every
  slot; every mapped column exists on the model; the check runs against
  `Base.metadata` without a DB connection.

## 10. Validation

```powershell
ruff check .
pytest -q tests/unit tests/contract tests/integration
alembic heads  # must report 0019_ontology_slots_and_optimization_runs
```

## 11. Acceptance criteria

- 20 bindings × all slots resolve to real columns; zero reported mismatches.
- Migration applies cleanly on SQLite/PostgreSQL in CI.
- Vocabulary exposes the four new enum families with documented values.

## 12. Rollback

Revert commits; migration downgrade drops only the new columns/table; the
slot maps are declarative and can be reverted without data impact.
