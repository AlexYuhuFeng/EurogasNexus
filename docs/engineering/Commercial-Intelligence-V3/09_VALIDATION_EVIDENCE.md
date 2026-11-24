# 09 Validation evidence

Every result below was produced on 2026-11-24 in the programme's build environment
(Linux, Python 3.11.12, PostgreSQL 16 for the PostgreSQL tests). Commands are given so the
results can be reproduced.

## Baseline (`main@6d21b89`, clean worktree)

| Check | Command | Result |
| --- | --- | --- |
| Full test suite | `python -m pytest -q -p no:cacheprovider tests` | **7006 passed, 235 skipped, 0 failed** (34 min 43 s) |
| Lint | `ruff check .` | All checks passed |
| API import and routes | `python -c "from apps.api.main import app; print(len(app.openapi()['paths']))"` | 278 paths |

The 235 skips are tests that need PostgreSQL, SciPy or other optional services; they are
the same tests CI runs in its PostgreSQL and scientific jobs.

## Branch (`innovation/continuous-commercial-intelligence`)

| Check | Command | Result |
| --- | --- | --- |
| Full test suite (before the two fixes below) | `python -m pytest -q -p no:cacheprovider tests` | 7031 passed, 239 skipped, 2 failed |
| The two failures | see below | Both fixed; re-run passes |
| Lint | `ruff check .` | All checks passed |
| API import and routes | as above | 278 paths (no route added) |
| Markdown links | `python scripts/ci/check_markdown_links.py` | Passes |
| Config contract | `python scripts/ci/check_config_contract.py` | Passes (no new environment variable) |
| Environment templates | `python scripts/ci/generate_env_template.py --check` | Passes |
| Toolchain versions | `python scripts/ci/check_toolchain_versions.py` | Passes |
| Pre-push gate | `scripts/ci/pre_push_check.sh` | Passes (run before the push) |

The two failures, both caught by existing gates and fixed without weakening them:

1. `test_domain_enum_ontology_gate`: the new `PublishKind` enum needed an ontology-review
   entry. It is an event-processing state like `FreshnessStatus`, so it got one (commit
   `429f51a`).
2. `test_markdown_links`: these documents linked to this page before it existed. Fixed by
   this page.

The 4 additional skips are the PostgreSQL outbox tests, which skip without a PostgreSQL URL
and are run separately below.

## M4 tests

| Suite | Tests | Result |
| --- | --- | --- |
| `tests/domain/test_market_events_model.py` | model, identity, revision decision, invalid events, timeline, staleness | Pass |
| `tests/unit/test_market_event_outbox_migration.py` | 0077 up and down on SQLite; tables match models | Pass |
| `tests/integration/test_market_event_outbox.py` | 11: idempotency, supersession, priority, retry/backoff/dead letter, savepoint rollback, replay, staleness, timeline, targeted re-evaluation, keyless events, scheduler hook, firm marks | 11 pass (SQLite) |
| `tests/integration/test_market_event_outbox_postgres.py` | 4: notify only at commit, skip-locked claims never overlap, store refuses a second copy of a revision, two racing publishers write once | 4 pass on PostgreSQL 16 |

PostgreSQL command (database migrated to head with `alembic upgrade head`):

```bash
RUNTIME_STORE_DATABASE_URL=postgresql+pg8000://postgres@127.0.0.1:55432/egn_m4 \
  python -m pytest -q tests/integration/test_market_event_outbox_postgres.py \
  tests/integration/test_market_event_outbox.py
# 15 passed
```

Migration on PostgreSQL: `alembic upgrade head` to `0077_market_event_outbox`, then
`alembic downgrade -1` and `alembic upgrade head` again, both clean.

## Targeted re-evaluation, shown on the demo desk

With `scripts/demo/seed_demo_desk.py` seeded (37 `hedge_gap` and 3 `sell_down`
opportunities), one `price.updated` event for `hub:TTF:2026-11-18` re-runs only
`sell_down`, and one `contract.changed` event for `contract:demo-haldor-24` re-runs only
`hedge_gap`, each recorded as an evaluation with trigger `outbox`
(`test_an_event_re_evaluates_only_the_evaluators_that_read_its_key`).

## Not yet evidenced

- Throughput and latency under sustained load: no load test yet (planned with M6).
- Producers other than ingestion runs and firm marks (M5).
- CI on GitHub for the branch: `ci.yml` runs on pushes to `main` and on pull requests
  only, so pushing this branch starts no CI run. It runs if a pull request is opened, or by
  hand through `workflow_dispatch`.
