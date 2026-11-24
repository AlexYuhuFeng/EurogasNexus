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

## M5 tests

| Suite | Tests | Result |
| --- | --- | --- |
| `tests/integration/test_market_event_capture.py` | 15: period mapping (9 cases), builder keys and identities, capture once then a correction reaching only `sell_down`, REMIT versions as revisions, FX cross reach, importer transaction, scheduler capture | 15 pass (SQLite) |
| `tests/integration/test_opportunity_schedule_race.py` | a change noted while the scheduled evaluation runs stays pending | Pass; fails on the old `run_due` |
| `tests/integration/test_market_event_outbox_postgres.py` | 6: the 4 M4 tests, capture writes each figure once, the scheduled evaluation keeps a change noted while it runs | 6 pass on PostgreSQL 16; the last fails on the old `run_due` |
| `tests/integration/test_market_event_outbox.py` | scheduler hook now reports `captured` | 11 pass |

```bash
RUNTIME_STORE_DATABASE_URL=postgresql+pg8000://postgres@127.0.0.1:55432/egn_m4 \
  python -m pytest -q tests/integration/test_market_event_outbox_postgres.py \
  tests/integration/test_market_event_outbox.py tests/integration/test_market_event_capture.py
```

On the demo seed, the first capture publishes the settlements that map to canonical periods,
the 8 FX fixings and the 2 REMIT messages; delivering that history re-runs no evaluator,
because no stored opportunity reads those keys. A second capture writes nothing.

M5 full suite (SQLite, `python -m pytest -q tests`, 2026-11-24): 7,049 passed, 241 skipped, 0 failed in 38 min 27 s.

## M5b, M6 and LNG-1 (2026-11-24)

| Run | Command | Result |
| --- | --- | --- |
| M5b desk capture and outbox | `pytest tests/integration/test_desk_event_capture.py tests/integration/test_market_event*.py tests/domain/test_market_events_model.py` | passed (part of the 141 below) |
| M6 alerts and freshness | `pytest tests/integration/test_feed_and_outbox_alerts.py` plus dataops, scheduler and freshness suites | 141 passed; monitoring suite 112 passed |
| PostgreSQL 16 | `RUNTIME_STORE_DATABASE_URL=postgresql+pg8000://... pytest tests/db tests/integration/test_market_event*.py` after `alembic upgrade head`, `downgrade -1`, `upgrade head` to 0078 | 137 passed, 2 skipped |
| LNG-1 domain, API, SDK | `pytest tests/domain/test_lng_in_transit.py tests/api/test_lng_cargo_plan_api.py tests/sdk/test_lng_cargo_plan_client.py` | 12 + 5 + 2 passed |
| Contract, security, release, SDK | `pytest tests/contract tests/security tests/release tests/sdk` | 1,873 passed, 35 skipped |
| Affected suites (migrations, outbox, LNG, db) | as listed in 10 | 1,921 passed after the census and reachability fixes |
| Web client types | `npx tsc --noEmit -p clients/web` | clean |
| Lint | `ruff check .` | clean |
| API census | `app.openapi()` | 282 paths / 315 operations (+4 / +4) |

## F1 and DOC (2026-11-24)

| Run | Command | Result |
| --- | --- | --- |
| Pre-push gate on `dcbb498` | `scripts/ci/pre_push_check.sh` | 4,598 passed, 81 skipped; web types and tests clean |
| SDK, database URL, reference | `pytest tests/sdk tests/integration/test_db_config.py tests/contract/test_sdk_reference_current.py tests/contract/test_db_foundation.py tests/unit/test_database_url_mapping.py` | 294 passed |
| SDK examples against a local demo server | `pytest tests/docs/test_sdk_examples.py` with the two example variables set | 12 passed |
| Links | `python scripts/ci/check_markdown_links.py` | 441 files, all local links resolve |

## AIR stage 1: suggestions through support reports (2026-11-24)

| What | Command | Result |
| --- | --- | --- |
| AIR-1 a suggestion is P4, `FB-` id, low-severity notification, unknown category refused | `pytest tests/api/test_support_api.py` | 4 passed |
| AIR-2 suggestion mode, composition in diagnostics, EN and ZH labels | `node --test tests/supportReport.test.ts` (in `clients/web`) | 4 passed; full client suite 1,307 passed, 3 skipped; `tsc --noEmit` clean |
| No path or operation added; contract and docs gates | `pytest tests/contract tests/docs` | 607 passed, 12 skipped (with the support tests) |

## GOV-1 governance (2026-11-24, branch `wip/gov`)

| What | Command | Result |
| --- | --- | --- |
| GOV1-1 to GOV1-3 audit with the change | `pytest tests/api/test_governed_audit_api.py tests/unit/test_governed_audit.py tests/unit/test_audit_service.py` | 11 passed |
| Governed-write modules unchanged in behaviour otherwise | `pytest tests/api/test_assumptions_api.py tests/api/test_lng_cargo_plan_api.py tests/api/test_opportunities_api.py tests/api/test_risk_limits_api.py tests/api/test_risk_segregation_api.py tests/security/test_access_self_grant.py tests/security/test_enterprise_access_api.py tests/security/test_identity_admin_api.py tests/security/test_local_accounts_api.py tests/security/test_personal_api_keys.py tests/security/test_platform_admin_commercial_boundary.py tests/unit/test_error_taxonomy.py tests/contract/test_error_vocabulary_coverage.py` | 111 passed |
| GOV1-4, AIR-3 to AIR-7 AI controls stage 2 | `pytest tests/unit/test_ai_register.py tests/evals/test_ai_gate.py tests/api/test_ai_controls_api.py` | 34 passed |
| AI evaluation gate, offline | `python scripts/ai/ai_gate.py` (record written by `--record`: 11 uses, default model `deepseek-v4-flash`) | AI gate passes |
| AI uses unchanged in behaviour otherwise | `pytest tests/evals tests/unit/test_mcp_capability_adapter.py tests/unit/test_explain.py tests/unit/test_desk_ask.py tests/unit/test_spreads_workbench.py tests/api/test_preferences_api.py tests/unit/test_settings_preferences.py tests/api/test_monitoring_api.py tests/security/test_ai_authority.py` with the report, monitoring, agent and analysis modules | 531 passed |

## Targeted re-evaluation, shown on the demo desk

With `scripts/demo/seed_demo_desk.py` seeded (37 `hedge_gap` and 3 `sell_down`
opportunities), one `price.updated` event for `hub:TTF:2026-11-18` re-runs only
`sell_down`, and one `contract.changed` event for `contract:demo-haldor-24` re-runs only
`hedge_gap`, each recorded as an evaluation with trigger `outbox`
(`test_an_event_re_evaluates_only_the_evaluators_that_read_its_key`).

## M7 live pipeline (2026-11-24)

Latency from a price input committed to the opportunity change visible, measured with
`scripts/ops/measure_live_latency.py` on a local PostgreSQL 16 with the demo desk
(`seed_demo_desk.py`, evaluated twice), API (`uvicorn apps.api.main:app`) and listen worker on
the same host. Each sample saves the firm's TTF mark for the next gas day (alternating about 44
and 40 EUR/MWh, so the event-exposure opportunities move by more than the 20 % material-change
threshold) with its `mark.changed` event in one transaction; the clock starts when the commit
returns.

| Mode | Measure | n | Median | Min | Max |
| --- | --- | --- | --- | --- | --- |
| before (script plays the 60 s tick, ten-batch cap, no listen worker) | commit to evaluation committed | 6 | 29.5 s | 16.6 s | 57.1 s |
| before | of which waiting for the tick | 6 | 22.0 s | 10.8 s | 50.8 s |
| before | evaluation | 6 | 6.4 s | 5.8 s | 7.8 s |
| before | change on `/api/stream/opportunities` | 6 | never (legacy rows only; the page showed it on reload) | | |
| after (listen worker, stream) | commit to `opportunity` event received | 12 | **6.6 s** | 6.0 s | 12.7 s |
| after | commit to evaluation committed | 12 | 5.7 s | 5.3 s | 12.3 s |
| after | evaluation | 12 | 5.5 s | 5.2 s | 6.5 s |

The 12.7 s sample waited for the one-minute full sweep holding the evaluation lock. An earlier
"before" run with an exchange settlement as the input (5 samples) gave the same shape: commit
to evaluation committed median 17.4 s (7.2 to 48.4 s), evaluation 3.7 to 4.7 s; it changed no
opportunity, because the firm caller holds no licence for that family on this store and the
demo board outranks a simulated settlement.

Outbox transport alone (`measure_live_latency.py throughput`, a consumer that does no work,
one process): 1,000 events published at 219/s and delivered at 1,308/s; 5,000 events at 236/s
and 1,889/s. The test events are deleted afterwards.

Found and fixed during the measurement: `publish_firm_marks` gave no publication time, so a mark
set back to an earlier value was refused as a replay and waited for the full sweep (about 20 s
per sample in the run before the fix) (`test_a_mark_set_back_to_an_earlier_value_is_published_again`).
A key whose latest stored revision predates the fix still refuses a return to an older value
once; the next distinct value publishes normally.

| Run | Command | Result |
| --- | --- | --- |
| M7 slices, SQLite | `pytest tests/integration/test_live_trigger.py tests/integration/test_opportunity_alerts.py tests/api/test_opportunity_stream.py tests/security/test_stream_entitlement.py` | 24 passed, 2 skipped (the PostgreSQL-only tests) |
| M7 PostgreSQL-only tests | the same with `RUNTIME_STORE_DATABASE_URL` on PostgreSQL | 3 passed (`-k postgres`: the sweep lock, and two workers queueing and sending once) |
| Contract and docs | `pytest tests/contract tests/docs` | 603 passed, 12 skipped |
| Web | `npx tsc --noEmit -p .`; `npm test` | clean; 1,308 passed, 3 skipped |

## Not yet evidenced

- Latency under sustained load: the M7 figures are single changes on an idle desk; the outbox
  transport rate is measured, sustained mixed load is not.
- Live quotes are not captured (R14, accepted). The cargo plan has no screen yet.
- CI on GitHub for the branch: `ci.yml` runs on pushes to `main` and on pull requests
  only, so pushing this branch starts no CI run. It runs if a pull request is opened, or by
  hand through `workflow_dispatch`.
