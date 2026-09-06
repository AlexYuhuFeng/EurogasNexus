# Scheduled Agent State

## Current run

- Current milestone: `M0-P0` — versioned CAM gas-day correction (no historical
  rewrite, no execution-boundary change).
- Last completed milestone: `M0-P0` (evidence below; committed in this run).
- Current branch/commit: `main`; M0-P0 commit recorded as the current `git log`
  HEAD (local commit, not pushed). `origin/main` remained
  `399be6aec931849e51379dbb6667c751ece5016a` at start of run.
- Model routing: DSH Pro (cross-subsystem domain, schema-adjacent semantics,
  strategy/data integrity).

## Baseline observed at start

- Working tree: ` M docs/clients/UI_CONTENT_STANDARDS.md` (pre-existing audit
  addition, preserved), `?? output/` (assessment evidence, not committed).
- `stash@{0}` preserved: `codex-strategy-wip-before-9f0652d`.
- CI config present: `ci.yml`, `ci-manual.yml`, `release.yml`. Live GitHub CI
  status was not queried this run; local validation gates are run below.
- Runtime API observed previously: development profile, PostgreSQL head
  `0024_cost_observations`, 46/46 required tables, 86 OpenAPI paths.

## Implementation plan for this run

1. Create and maintain `docs/product/*` governance files.
2. Add `EU-CAM-UTC-2025` corrected calendar version to
   `src/eurogas_nexus/domain/market/gas_day.py`; keep `EU-CAM-2025` frozen as a
   legacy reproducibility version; make corrected version the default for new
   computations.
3. Propagate corrected calendar and `calendar_version` metadata into new GIE
   AGSI/ALSI rows and simulated market rows (metadata only; no migration and no
   rewrite of historical rows).
4. Correct `GasDayRef` default and documentation in
   `src/eurogas_nexus/domain/ontology/semantic_kernel.py`.
5. Correct the web client duplicate constants in
   `clients/web/src/app/tradingContext.ts` and compute the displayed gas-day
   label from the corrected boundary.
6. Add focused Python and Node tests for legacy compatibility, corrected
   boundaries, DST anchors, metadata provenance, and client boundary logic.
7. Add `docs/product/GAS_DAY_CALENDAR_COMPATIBILITY.md` proposal and update
   normative release docs.
8. Run focused tests, then the broader Python/Node acceptance gates.
9. Update this file and backlog evidence; commit only files owned by this
   milestone. Leave pre-existing dirty `docs/clients/UI_CONTENT_STANDARDS.md`
   additions and untracked `output/` assessment uncommitted.

## Tests run

- `pytest -q tests` could not collect because local environment lacks `rdflib`
  (pre-existing environment gap; no dependency install performed).
- `pytest -q tests --ignore=tests/contract/test_ontology_grm_parity.py`:
  **1136 passed, 4 skipped**.
- Focused calendar/ingestion/ontology tests: **68 passed**.
- `npm --prefix clients/web run test`: **12 passed**.
- `npm --prefix clients/web run build`: **passed**.
- `ruff check .`: **passed**.
- `python scripts/ci/check_markdown_links.py`: **passed**.
- `python scripts/ops/load_smoke.py --requests 100 --concurrency 8 --p95-threshold-ms 1000`: **OK** (p50 6.9 ms, p95 541.2 ms, p99 550.9 ms).

## Known failures

- `tests/contract/test_ontology_grm_parity.py` cannot collect locally because
  `rdflib` is not installed in this local environment. Not caused by this
  milestone; CI installs the declared dependencies. Do not install new
  dependencies in this run.
- Live GitHub Actions status was not queried; local gates are green with the
  exclusion above.

## Unresolved architectural decisions

- Whether future persisted rows should carry a first-class `calendar_version`
  column in addition to `metadata_json` (requires Alembic migration; deliberately
  deferred until M0 evidence review).
- Recompute vs annotate policy for historical rows produced with
  `EU-CAM-2025`; must remain read-only until operator review.
- ENTSOG timezone contract (M1-P0) remains unproven.
- Gas-year official boundary (`GasYearRef`) remains unverified.

## Next recommended milestone

- `M1-P0` — ENTSOG timezone normalization contract and fixtures, then `M2-P1`
  information-architecture consolidation after acceptance of M0-P0.
