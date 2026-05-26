# Data Quality Contract

## Purpose

`src/eurogas_nexus/data_quality` owns future validation, completeness, freshness,
schema, and reconciliation checks.

## Rules

- Quality checks must be deterministic for a given input.
- Checks must report failures without mutating source data.
- Quality results must be auditable when attached to workflows.
- API routes must not silently bypass quality failures once quality gates exist.

## Bootstrap State

No quality checks are implemented.

