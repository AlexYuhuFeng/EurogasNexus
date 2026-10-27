# Decision Case and Decision Pack query batching acceptance

Task: `CASE-QUERY-BATCHING`. Scope is output-preserving read batching only. No
policy, schema, authorization, visibility, snapshot semantics, numeric result,
endpoint or migration change is included.

## Changed files

- `src/eurogas_nexus/db/repositories/decision.py`
- `src/eurogas_nexus/db/repositories/data_platform.py`
- `src/eurogas_nexus/application/decision_pack.py`
- `tests/db/test_decision_query_batching.py` (new)
- `docs/engineering/CASE_QUERY_BATCHING_ACCEPTANCE.md` (new)

## Changed behaviour

- `db/repositories/decision.py`: `list_decision_cases` keeps the existing case
  query, status filter, `updated_at_utc` descending order and `1..200` limit
  clamp. It then reads every decision record for the selected page in one
  `case_id IN (...)` query, ordered by `recorded_at_utc` ascending, and maps each
  case through the existing `_to_domain` domain/payload path. Empty pages issue
  no record query. Single-case reads keep their per-case query.
- `db/repositories/data_platform.py`: new
  `get_existing_analysis_snapshot_ids(session, snapshot_ids)` resolves candidate
  snapshot IDs with one ORM existence query. Duplicate candidates are
  deduplicated and an empty collection issues no query. Row visibility and
  payload semantics are unchanged; `get_analysis_snapshot` is unchanged.
- `application/decision_pack.py`: `load_decision_pack` replaces the per-distinct-
  snapshot `session.get` loop with one call to the batched existence resolver.
  Evidence entries, unresolved reporting, audit trail and content hash continue
  through the existing `build_decision_pack` path.

## Focused evidence added

`tests/db/test_decision_query_batching.py` uses real SQLAlchemy SQLite statement
counters and asserts:

- `list_decision_cases` sends exactly two SELECTs for both a one-case and a
  fifty-case page (case page plus one batched record read).
- Batched summaries equal the existing full single-case payload projection, and
  all decision records retain ascending `recorded_at_utc` ordering.
- Status filtering, the `limit=0` -> one-row clamp, descending page order and
  empty-page behaviour are preserved.
- `load_decision_pack` sends the same four SELECTs for one cited snapshot and for
  many cited snapshots, including duplicate and missing references.
- Duplicate evidence entries remain present, resolvable and unresolved snapshot
  states are reported, and pack history/decision ordering matches the full case.
- The snapshot-ID existence resolver deduplicates candidates and issues no query
  for an empty candidate collection.

## Validation status

The worker could not execute tests: the harness shell fails before command
execution with `CreateFileW failed (Win32 5)` on its ACL lock
(`...\dsh-acl-locks\...lock`). No test, Ruff or compile result is claimed here.

Root should run at minimum:

```text
python -m pytest tests/db/test_decision_query_batching.py tests/api/test_decision_cases_api.py tests/api/test_decision_pack_api.py tests/contract/test_data_platform_contract.py
ruff check src/eurogas_nexus/db/repositories/decision.py src/eurogas_nexus/db/repositories/data_platform.py src/eurogas_nexus/application/decision_pack.py tests/db/test_decision_query_batching.py
```

This slice is performance/query-shape evidence only. Reproducibility, signing,
access-policy and release acceptance remain separate root/reviewer decisions.

## Independent root verification

2026-10-28: focused actual SQLAlchemy query-count tests plus decision case/pack API
and data-platform contract selection: **30 passed**. Ruff passed on all changed
Python modules. This verifies output-preserving batching, not snapshot replay.
