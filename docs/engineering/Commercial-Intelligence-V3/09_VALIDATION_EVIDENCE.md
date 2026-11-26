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
| GOV1-5, GOV1-6 licensed data use and file export decisions (P6) | `pytest tests/unit/test_licensed_use.py tests/api/test_licensed_use_api.py` | 20 passed |
| Migration `0079_licensed_data_use` and the pinned schema head | `pytest tests/unit/test_licensed_use.py::test_migration_0079_matches_the_model_up_and_down` and the seven migration tests that pin `DB_SCHEMA_REVISION` | passed on SQLite; the PostgreSQL-marked tests were not run (no PostgreSQL role or driver available to this worktree) |
| Licence register shows 30-day use (web) | `npx tsc --noEmit -p .`; `npm test` (in `clients/web`) | clean; 1,307 passed, 3 skipped |
| Regression after GOV-1 slices 1 to 3 | `pytest tests/api tests/security tests/contract tests/docs tests/evals tests/db` with the migration, entitlement and report-file unit tests | 2,319 passed, 14 skipped |

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

## LNG-2 a cargo change reaches each role (2026-11-24, branch `wip/lng2`)

The owner's scenario as the acceptance test runs it: cargo SAB-0420 (Aurora, 1,000 GWh loaded)
due at Gate on Friday 27 November 09:00, slot 26 November to 6 December at 100 GWh/d, hedged
month by month to the plan; the vessel feed (KPLER, AIS ETA, low confidence) reports it on
Tuesday 1 December 09:00. What each role's channel receives:

| Role | Severity | Title | Body (summary) |
| --- | --- | --- | --- |
| Trader | critical | Hedges no longer match Aurora (SAB-0420): buy 383,333 MWh TTF 2026-11 at short notice; sell 379,373 MWh TTF 2026-12 | Per month "physical + hedge = net"; Nov has stopped trading (short notice); Dec sale due before 28 Nov 00:00 UTC; 3,960 MWh more boil-off; nothing is traded; confirm the AIS ETA before acting |
| Scheduler | warning | Renominate 10 gas day(s) for Aurora (SAB-0420) | Berth Fri 27 Nov 09:00 → Tue 01 Dec 09:00; each gas day's send-out before and after (27 Nov 83,333 → 0 MWh, …) with the cut-off it hits (nominate by Thu 26 Nov 13:00 UTC, …) |
| Risk | critical | Mandate breach from Aurora (SAB-0420) | TTF 2026-11 net 0 → −383,333 MWh; 2026-12 0 → +379,373 MWh; LNG desk mandate 98 % watch → 126 % breach |
| Desk head | critical | Material cargo change: Aurora (SAB-0420) | Net exposure 383,333 MWh in one month; hedge actions 762,706 MWh; mandate breach; threshold 100,000 MWh (desk standard, no approved `lng.material_change_mwh`) |

Each body ends with the inputs' line ("Inputs: ETA from KPLER (the ETA declared in AIS, low
confidence), stored …; slot gate-1 from ETRM, …; hedges recorded by lng.trader, …; plan rebuilt
… from cargo.changed revision 2") and "For: <owner>. If not acted on: <escalation>."

Latency, ETA import committed to every role's notification in the outbox, PostgreSQL 16, the
listen worker as its own process (`scripts/ops/market_events.py listen --poll-seconds 0.05`),
`tests/integration/test_lng_cargo_change_postgres.py`, 8 runs (plus 9 earlier runs of the
first change only, 0.62 to 0.83 s):

| Change | n | Median | Min | Max |
| --- | --- | --- | --- | --- |
| First change after the worker starts (loads the cargo modules) | 8 | 0.66 s | 0.61 s | 0.75 s |
| Next change in the same worker (ETA corrected back: four withdrawals) | 8 | 0.11 s | 0.09 s | 0.16 s |
| Outbox to the channel sender (dispatch) | 8 | +0.02 s | | |

In the worker's report the `cargo_roles` batch is drained before the `opportunities` batch
for the same event. Profiled on SQLite, the consumer's time is mostly the mandate re-check's
ladder read (`ladder_inputs`, about 0.1 to 0.15 s per cargo on the test desk).

```bash
createdb egn_lng2; RUNTIME_STORE_DATABASE_URL=postgresql+pg8000://postgres@127.0.0.1:55432/egn_lng2 alembic upgrade head
RUNTIME_STORE_DATABASE_URL=postgresql+pg8000://postgres@127.0.0.1:55432/egn_lng2 \
  python -m pytest -q -s tests/integration/test_lng_cargo_change_postgres.py
```

Migration `0080_lng_eta_basis` on PostgreSQL: `alembic upgrade head`, `downgrade -1`, `upgrade
head`, all clean; the four columns are nullable.

| Run | Command | Result |
| --- | --- | --- |
| LNG-2 tests | `pytest tests/domain/test_lng_consequences.py tests/integration/test_lng_cargo_change_roles.py tests/integration/test_lng_cargo_change_postgres.py tests/unit/test_lng_positions_import.py tests/unit/test_lng_eta_basis_migration.py tests/api/test_lng_cargo_plan_api.py` | 20 passed, 1 skipped (the PostgreSQL test, run separately above: 1 passed) |
| Related suites (outbox, alerts, notifications, monitoring, limits, Today, assumptions, LNG) | 105 files under `tests/api`, `tests/integration`, `tests/unit`, `tests/domain`, `tests/sdk`, `tests/security` | API 193 passed; integration 76 passed, 2 skipped; unit, domain, SDK and security 811 passed; 0 failed |
| PostgreSQL-only tests on the same database | outbox, acknowledgement, opportunity alerts, live trigger and the LNG-2 worker test, `-k "postgres or listen"` | 12 passed, 3 skipped |
| Contract and docs | `pytest tests/contract tests/docs` | 605 passed, 12 skipped |
| Lint | `ruff check src tests scripts` | All checks passed |
| Markdown links | `python scripts/ci/check_markdown_links.py` | All local links resolve |
| Web | `npx tsc --noEmit -p .`; `npm test` | clean; 1,366 tests, 1,363 passed, 3 skipped, 0 failed |

## P-17 maker-checker on limits and reference data (2026-11-24, branch `wip/p17`)

| Run | Command | Result |
| --- | --- | --- |
| P-17 tests | `pytest tests/api/test_maker_checker_api.py tests/unit/test_maker_checker.py` | 10 passed |
| Writes now proposed and approved (limits, segregation, governed audit, assumptions and marks, outbox, scheduling, LNG cargo economics) | `pytest tests/api/test_risk_limits_api.py tests/api/test_risk_segregation_api.py tests/api/test_governed_audit_api.py tests/api/test_assumptions_api.py tests/integration/test_market_event_outbox.py tests/integration/test_opportunity_scheduling.py tests/integration/test_lng_cargo_economics_api.py` | 40 passed |
| API, security and DB suites | `pytest tests/api tests/security tests/db` | 1,437 passed, 2 skipped |
| Integration suite (SQLite) | `pytest tests/integration` | 205 passed, 161 skipped, 3 failed: `test_demo_planted_cases.py` (L1, W1, quiet), which fail the same way on the base commit `e772502` (an extra `S` item on the demo seed), not caused by this slice |
| Unit, domain, SDK and eval suites | `pytest tests/unit tests/domain tests/sdk tests/evals` | 3,858 passed, 46 skipped (after updating `tests/unit/test_freight_route_migration.py`, whose model match now allows the `change_id` that 0081 adds; 3,857 passed and that 1 failed before) |
| Migration `0081_change_requests` on PostgreSQL 16 | `alembic upgrade head`, `downgrade -1`, `upgrade head` on a fresh database | all clean |
| PostgreSQL tests on that database | `pytest tests/integration/test_maker_checker_postgres.py tests/integration/test_schema_matches_models_postgres.py`; `pytest tests/integration -k postgres` | 2 passed; 147 passed, 16 skipped |
| Contract and docs | `pytest tests/contract tests/docs` | 605 passed, 12 skipped (census 288 paths / 323 operations) |
| Lint | `ruff check src tests scripts` | All checks passed |
| Markdown links | `python scripts/ci/check_markdown_links.py` | All local links resolve |
| Web (P17-9) | `npx tsc --noEmit -p .`; `npm test`; `node scripts/cssTokenLint.mjs` (in `clients/web`) | clean; 1,373 tests, 1,370 passed, 3 skipped, 0 failed; the new stylesheet has no raw values |

## DATA-1 data integration (2026-11-24, branch `wip/data1`)

| What | Command | Result |
| --- | --- | --- |
| DATA1-1 as-of reads (P1) | `pytest tests/api/test_data1_as_of_reads.py` | 12 passed |
| DATA1-2 change feed (P2) | `pytest tests/api/test_data1_change_feed.py` | 8 passed |
| DATA1-3 Power Query refreshable reads (P7) | `pytest tests/api/test_data1_refreshable_reads.py` | 5 passed |
| DATA1-4 ETRM and ERP import contracts | `pytest tests/api/test_data1_import_contracts.py` | 10 passed |
| DATA-1 on PostgreSQL 16 (migration 0082 with `erp_references`) | fresh store: `alembic upgrade head`, `downgrade 0080_lng_eta_basis`, `upgrade head`; columns and indexes of `market_events` and `erp_references` match the models; `scripts/ops/import_contract_file.py --commit` twice each for counterparties, invoices and the cargo schedule (created 1, then unchanged 1); `pytest tests/integration/*postgres*.py tests/unit/test_postgres_native_schema_pipeline.py tests/db` with `RUNTIME_STORE_DATABASE_URL` and `EUROGAS_NEXUS_TEST_POSTGRES_URL` set | clean; 247 passed, 16 skipped |
| Imports, migrations and pins with DATA1-1 to DATA1-4 | `pytest tests/api/test_data1_*.py tests/unit/*migration*.py` and the schema-pin, release-metadata, licensed-use, LNG, gas-day and integration-export suites, `tests/docs`, `tests/sdk`; `tests/contract tests/security` | 414 passed, 12 skipped; 1,136 passed; ruff clean |
| Reads, files and licence metering with DATA1-1 to DATA1-3 | `pytest` the three DATA-1 API suites, `tests/api/test_licensed_use_api.py`, `tests/api/test_market_fx_api.py`, `tests/api/test_one_price_across_screens.py`, `tests/api/test_research_data_api.py`, `tests/api/test_error_envelope.py`, the CSV and report API tests, `tests/security/test_public_api_auth.py`, `tests/security/test_identity_row_entitlement.py`, `tests/contract`, `tests/docs`, `tests/sdk`; `ruff check src tests scripts` | 934 passed, 12 skipped; ruff clean |
| DATA1-2 never skips a committed event (PostgreSQL 16) | `alembic upgrade head`, `downgrade 0080_lng_eta_basis`, `upgrade head` on a fresh store; `RUNTIME_STORE_DATABASE_URL=postgresql+pg8000://... pytest tests/integration/test_change_feed_postgres.py tests/integration/test_market_event_outbox_postgres.py` | migration up, down, up clean; 9 passed |
| Migration 0082 and the schema pins | `pytest tests/unit/*migration*.py tests/db tests/api/test_release_metadata_api.py tests/unit/test_reliability_ops.py tests/unit/test_runtime_db_validation.py tests/unit/test_backup_restore_readiness.py tests/unit/test_migration_preflight.py` | 158 passed, 2 skipped |
| Related suites with DATA1-1 and DATA1-2 | `pytest` the DATA-1 tests, the pinned migration tests, `tests/sdk`, `tests/contract`, `tests/docs`; `ruff check src tests scripts` | 897 passed, 13 skipped; ruff clean |
| Market, price and SDK reads unchanged otherwise | `pytest tests/api/test_one_price_across_screens.py tests/api/test_trader_desk_api.py tests/api/test_market_fx_api.py tests/api/test_projections_api.py tests/api/test_context_api.py tests/api/test_market_normalisation_api.py tests/api/test_research_data_api.py tests/api/test_error_envelope.py tests/sdk tests/security/test_public_api_auth.py tests/security/test_identity_row_entitlement.py tests/security/test_platform_admin_commercial_boundary.py tests/unit/test_demo_desk_seed.py tests/unit/test_projections_application.py tests/contract tests/docs` (with the DATA1-1 tests) | 1,018 passed, 12 skipped |

## TAR-1 public tariffs and capacity windows (2026-11-25, branch `wip/tar1`)

| What | Command | Result |
| --- | --- | --- |
| TAR1-1 to TAR1-6 (model, versions, status, registry, freshness, notices, reads) | `pytest tests/domain/test_tariff_book_domain.py tests/unit/test_tariff_book.py tests/unit/test_tariff_book_migration.py tests/api/test_tariffs_api.py tests/integration/test_tariff_book_postgres.py` | 38 passed, 2 skipped (the PostgreSQL tests, run below) |
| TAR-1 on PostgreSQL 16 (migration 0083) | fresh store: `alembic upgrade head`, `downgrade 0082_data1_integration` (both tables gone), `upgrade head`; `pytest tests/integration/*postgres*.py tests/unit/test_postgres_native_schema_pipeline.py tests/db` with `RUNTIME_STORE_DATABASE_URL` and `EUROGAS_NEXUS_TEST_POSTGRES_URL` set | migration up, down, up clean; 250 passed, 16 skipped |
| TAR1-4 latency (PostgreSQL 16, one host) | `pytest -s tests/integration/test_tariff_book_postgres.py`, 8 runs | read to version and event committed median 12.5 ms (11 to 14 ms); first write in a fresh process median 166 ms (160 to 205 ms); commit to the opportunities consumer having processed it median 5.5 ms (5 to 7 ms). An earlier set of 8 runs on the same host: 18 ms, 244 ms, 10.5 ms. Row in [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) section 8 |
| Full capture at the size of the ENTSOG register (PostgreSQL 16, 12,670 rows, the count measured on 2026-11-19) | `capture_tariffs` once on an empty book, then again | first pass 77 s (12,670 versions and events: a one-off backfill), unchanged pass 2.3 s; hence the per-minute signature check with a full pass hourly |
| Operator script | `scripts/ops/tariff_book.py sync --commit` twice on the fresh store | the CAM NC standard auctions: 18 created, then 18 unchanged; no register rows, so no versions |
| Contract, census, permissions, reachability, docs and security gates | `pytest tests/contract tests/docs tests/security` | 1,136 passed, 12 skipped |
| Related suites (tariff registers, ENTSOG ingestion, route cost, valuation, opportunities, outbox and capture, monitoring and routing, scheduler, migrations and schema pins) | `pytest` every test file that imports a tariff register, the ENTSOG tariff ingestion, the valuation snapshot, the capture, alert routing, the scheduler or the monitoring service, `tests/unit/*migration*.py`, `tests/db`; `ruff check src tests scripts` | 1,348 passed, 38 skipped (130 files); ruff clean |
| Web: tariff book view, client, EN and ZH text | `npx tsc --noEmit -p .`; `npm test` (clients/web) | clean; 1,379 tests, 1,376 passed, 0 failed |

## Demo planted cases after P-11 (2026-11-24, branch `wip/fix-planted`)

`test_demo_planted_cases` failed on every day after P-11 (first bad commit `07abf30`): two
must-act sell-down items, `NBP · long` (UK book, +5,171.4 MWh) and `TTF · short` (NL book,
-1,912.5 MWh), were listed daily. The residuals were checked line by line on a 2 Dec seed
(the BBL export at TTF and import at NBP net; Haldor capped to 18/70, Kestrel to 31/40 over
22 h) and are correct: the demo schedule did not balance. It now balances each book on every
gas day except the planted S1 days (18 to 20 of each month).

| Run | Command | Result |
| --- | --- | --- |
| Planted cases (L1, W1, quiet, new S1 day) | `pytest tests/integration/test_demo_planted_cases.py` | 6 passed |
| Integration | `pytest tests/integration` | 209 passed, 160 skipped |
| Sell-down, gas day, daily balance, Today, demo seed and market | 16 files under `tests/api`, `tests/domain`, `tests/sdk`, `tests/unit` | 139 passed |
| Contract and docs | `pytest tests/contract tests/docs` | 605 passed, 12 skipped |
| Lint | `ruff check src tests scripts` | All checks passed |

## MAP-1 the map (2026-11-24, branch `wip/map1`)

| What | Command | Result |
| --- | --- | --- |
| MAP1-1 to MAP1-4 site figures, flow days, ETA basis and entitlement | `pytest tests/unit/test_map1_assets.py tests/api/test_map_situation_api.py` | 4 new unit tests and 1 new API test pass; with the existing map tests, 59 passed |
| API contract and docs with the additive fields | `pytest tests/contract tests/docs tests/unit/test_map1_assets.py`; `ruff check src tests scripts` | 609 passed, 12 skipped; ruff clean. Census unchanged (no route added) |
| MAP1-1 to MAP1-6 map models (layers, estimates, flow orientation, scrubber, reduced motion, colours, cards) | `node --test --experimental-strip-types tests/mapScene.test.ts` (in `clients/web`) | 16 passed |
| Web client | `npx tsc --noEmit -p .`; `npm test`; `node scripts/cssTokenLint.mjs` | clean; 1,389 tests, 1,386 passed, 3 skipped (baseline 1,373, 1,370 passed); token lint unchanged (the new stylesheet is clean) |
| Bundle (`npm run build`), against `333254d` | `index-*.js` 2,215.21 kB (gzip 616.73) from 2,181.64 (606.88): +33.6 kB, gzip +9.9; `index-*.css` 392.37 kB (gzip 60.38) from 389.52 (59.84): +2.9 kB, gzip +0.5; `vendor-map` 1,037.39 kB and the MapLibre worker 507.72 kB unchanged | No npm package added |
| Frame behaviour | Not measured: this environment has no browser. The map writes the p95 frame interval of the flow animation to `data-map-scene-frame-p95` on `.gas-map`, summarised by `app/mapSceneFrames.ts` (tested) | To be read in a browser on the desk's reference machine |

## SCHED-1 why trades, confirmations and nominations disagree (2026-11-25, branch `wip/sched1`)

Worked example, the demo's R1 gas day 2026-12-11 read at 23:00 UTC: the UK book sold
Aldermoor 6,000 MWh at NBP and nominated it out; Aldermoor nominated 4,800 and the TSO
confirmed the lesser: 6,000 − 4,800 = 1,200 MWh cut (40,946 th, 50,000 kWh/h), the book long
1,200 MWh, indicative cash-out 1,200 × 1.20 GBP/MWh = 1,440 GBP, three hours to the last
renomination at 02:00 UTC (due soon). On 2026-12-02 the reconciliation has no break.

| What | Command | Result |
| --- | --- | --- |
| SCHED1-2, SCHED1-3 each break kind, hand-worked | `pytest tests/domain/test_nomination_reconciliation.py` | 15 passed |
| SCHED1-1, 3 to 6, 8 on the demo desk, imports, alerts, Today, API | `pytest tests/integration/test_gas_day_reconciliation.py tests/api/test_gas_day_reconciliation_api.py tests/integration/test_demo_planted_cases.py` | 9 + 1 + 9 passed (the planted cases L1, W1, S1 and quiet unchanged; R1 added) |
| SCHED1-4 migration 0085 up and down | `pytest tests/unit/test_gas_day_nominations_migration.py`; on PostgreSQL 16 `alembic upgrade head`, `alembic downgrade 0082_data1_integration`, `alembic upgrade head` | passed; head `0085_sched1_nomination_matching` |
| SCHED1-5 on PostgreSQL, and the schema against the models | `EUROGAS_NEXUS_TEST_POSTGRES_URL=… pytest tests/integration/test_gas_day_reconciliation_postgres.py tests/integration/test_schema_matches_models_postgres.py tests/integration/test_demo_seed_postgres.py tests/db/test_entsog_native_rate_schema.py` | 12 passed; one alert pass 0.026 to 0.036 s (median 0.031 s, 6 runs) |
| Related suites (gas day, checklist, my gas day, Today, demo, notifications, monitoring, LNG) | `pytest tests/unit/test_{demo_*,desk_today,gas_day*,my_gas_day,nomination_window_occurrence,notifications,monitoring_service,lng_*,strip_alerts,limit_monitoring,storage_nomination_composition}.py` with the SCHED-1 tests | 270 passed |
| API contract, docs and the related API and integration suites | `pytest tests/contract tests/docs tests/api/test_data1_import_contracts.py tests/api/test_data1_refreshable_reads.py tests/api/test_gas_day_status_api.py tests/api/test_monitoring_api.py tests/api/test_trader_desk_api.py tests/integration/test_lng_cargo_change_roles.py tests/integration/test_feed_and_outbox_alerts.py tests/integration/test_opportunity_alerts.py …` | 705 passed, 13 skipped; census 293 paths / 328 operations |
| Lint | `ruff check src tests scripts` | All checks passed |
| SCHED1-7 web: Reconciliation row, What needs me, role composition | `npx tsc --noEmit -p .`; `npm test`; `node scripts/cssTokenLint.mjs` (in `clients/web`) | clean; 1,394 tests, 1,391 passed, 3 skipped (5 new in `tests/reconciliationModel.test.ts`); token lint unchanged (the new rules are clean) |

## NEWS-1 news and events (2026-11-25, branch `wip/news1`)

| What | Command | Result |
| --- | --- | --- |
| NEWS1-1 to NEWS1-7 registry, feeds, tagging, ingest, outage link, relevance, routing, note | `pytest tests/unit/test_news_sources_feeds_tagging.py tests/unit/test_news_ingest.py tests/unit/test_news_relevance_routing_note.py tests/unit/test_news_items_migration.py tests/api/test_news_api.py` | 53 new tests pass (fixtures constructed, no network) |
| NEWS1-8 grounding evaluation set and the AI gate | `pytest tests/evals/test_news_note_evals.py tests/evals/test_ai_gate.py tests/unit/test_ai_register.py`; `python scripts/ai/ai_gate.py --record` | 36 cases, 36 correct (pass rate 1.0 at threshold 1.0), recorded for `news_note`; gate and register tests pass |
| NEWS1-9 API census and reachability | `pytest tests/contract tests/docs` | pass; census 295 paths / 330 operations (292 / 327 before) |
| NEWS1-11 migration on PostgreSQL 16 | `alembic upgrade head`, `downgrade -1`, `upgrade head` on a fresh database; `pytest tests/integration/test_news_postgres.py` and the outbox, change-feed, alert and LNG change integration tests | upgrade and downgrade clean; 55 passed, 3 skipped |
| Wider suites | `pytest tests/unit tests/api tests/evals tests/contract tests/docs tests/db`; `ruff check src tests scripts` | 4,684 passed, 60 skipped, 0 failed; ruff clean |
| NEWS1-10 web | `npx tsc --noEmit -p .`; `npm test`; `node scripts/cssTokenLint.mjs` (in `clients/web`) | clean; 1,394 tests, 1,391 passed, 3 skipped (5 new); token lint: the new stylesheet is clean |
| Bundle (`npm run build`) | `index-*.js` 2,226.70 kB (gzip 619.97), `index-*.css` 394.47 kB (gzip 60.66) | +11.5 kB JS and +2.1 kB CSS against MAP-1's figures; no npm package added |
| Live feeds | Not run: the build environment had no outbound network, so no feed was read live and no feed address was confirmed | The first operator poll confirms GOV.UK's address; the others are to be recorded |

## LNG-3 a disruption re-optimises the portfolio (2026-11-25, branch `wip/lng3`)

The owner's scenario (06, "LNG-3 a disruption re-optimises the portfolio"), judged 20 January
2027 09:00 UTC; every figure illustrative. Two days late (ETA 28 Jan), EUR against the plan:

| Option | Expected | Worst | Cost | Spare MWh | Moved MWh | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Borrow in tank | -20,000 | -158,000 | 20,000 | 1,000,000 | 0 | Default, score -89,000 |
| Swap with GATE-1 | +95,800 | -330,200 | -35,000 | 1,000,000 | 1,000,000 | Frontier (score -617,200) |
| Buy send-out | -36,000 | -249,000 | 36,000 | 1,000,000 | 0 | Dominated by borrow |
| Divert to Dunkerque | -247,400 | -347,600 | 247,000 | 0 | 0 | Dominated by borrow |
| Wait and absorb | -279,000 | -417,000 | 79,000 | 800,000 | 0 | Dominated by borrow |
| Swap with HUE-1 | | | | | | Infeasible: Cepsa 50,000 MWh short on 24 Jan |

Four days late (30 Jan): the default flips to borrow and buy (-182,000 / -395,000, score
-288,500); frontier {borrow and buy, divert (-152,000 / -508,000)}; the swap with GATE-1 is
infeasible (storage at Gate). Through the store with no boil-off (1,000,000 MWh lands), the
same scenario gives the same borrow and borrow-and-buy figures; the swap is +35,000 (no
boil-off saved) and divert -187,000. The flip is told once to the trader, scheduler and desk
head (3 notices per run, 6 in all); re-running the same inputs tells no one.

Latency (in process, the development container; 12 ETA changes; [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) section 8):

| Store | Commit to run row and notices (median, max) | Options read | Engine alone |
| --- | --- | --- | --- |
| PostgreSQL 16 | 0.052 s, 0.260 s | 0.050 s | 12 ms |
| SQLite | 0.028 s, 0.153 s | 0.025 s | 12 ms |

The engine is about 2 ms per option (112 options in 0.22 s; the 256 cap about 0.5 s).

| Run | Command | Result |
| --- | --- | --- |
| LNG-3 tests | `pytest tests/domain/test_lng_disruption.py tests/api/test_lng_disruption_api.py tests/unit/test_lng_disruption_migration.py tests/integration/test_lng_disruption_postgres.py tests/integration/test_demo_planted_cases.py` | 33 passed, 2 skipped (the PostgreSQL cases, run below) |
| PostgreSQL 16 (`egn_lng3`, `alembic upgrade head`, `downgrade -1`, `upgrade head`, all clean; dropped afterwards) | `EUROGAS_NEXUS_TEST_POSTGRES_URL=... pytest tests/integration tests/unit -k "postgres or listen"` | 75 passed, 106 skipped (other suites' own preconditions), including both LNG-3 PostgreSQL cases, the schema-matches-models check and the demo seed on PostgreSQL |
| Contract and docs (census 296 paths / 331 operations, surface reachability, policy EN and CN) | `pytest tests/contract tests/docs` | 605 passed, 12 skipped |
| API, security and DB | `pytest tests/api tests/security tests/db` | 1,478 passed, 2 skipped |
| Integration, unit and domain (SQLite) | `pytest tests/integration tests/unit tests/domain` | 3,644 passed, 212 skipped (PostgreSQL and other preconditions), 0 failed |
| Lint | `ruff check src tests scripts` | All checks passed |
| Markdown links | `python scripts/ci/check_markdown_links.py` | All local links resolve |
| Web | `npx tsc --noEmit -p .`; `npm test` (in `clients/web`) | clean; 1,394 tests, 1,391 passed, 3 skipped, 0 failed (5 new in `disruptionOptionsModel.test.ts`); token lint 43 of 44 stylesheets clean, baseline unchanged |

## CODEX-1 the Codex assessments reviewed (2026-11-25)

Verdicts in [18](18_CODEX_ASSESSMENT_REVIEW.md). Codex's own measurements on the research
branch, quoted and not re-run here (no model was called): the evidence-gated workflow costs
about 74 µs at the median over direct engine calls (92.34 µs against 18.09 µs, 3,000
iterations); the follow-up planner on two local models found a feasible follow-up in 3 of 9
cases, as fixed order did, against 9 of 9 for a deterministic purpose rule, at 1,157 ms and
2,254 ms median.

| Run | Command | Result |
| --- | --- | --- |
| CODEX-1 tests | `pytest tests/unit/test_codex1_runtime_controls.py tests/streaming tests/api/test_capability_invocation_api.py tests/api/test_agents_api.py tests/evals/test_agent_evals.py` | all passed (15 new runtime cases, 11 new streaming cases, 4 new agent-evaluation tests, 2 new route cases) |
| AI gate | `python scripts/ai/ai_gate.py` | passes; `agent_research` and `mcp_tools` re-recorded for the evaluation set (33 cases; prompts and fingerprints unchanged) |
| Evaluations | `pytest tests/evals` | 253 passed |
| Contract, docs and streaming (census 303 paths / 338 operations, unchanged) | `pytest tests/contract tests/docs tests/streaming` | 619 passed, 12 skipped |
| Full serial run | `pytest tests/unit tests/domain tests/security tests/evals tests/db tests/sdk tests/release tests/integration tests/api` | 6,263 passed, 253 skipped (PostgreSQL and other preconditions), 0 failed |
| Lint | `ruff check src tests scripts alembic` | All checks passed |
| Markdown links | `python scripts/ci/check_markdown_links.py` | All local links resolve |

No migration and no storage were added, so no PostgreSQL run was needed; the web client is
unchanged.

## TAR-2 contracted before public, tariff years and source precedence (2026-11-25)

| What | Command | Result |
| --- | --- | --- |
| TAR2-1 to TAR2-9 (status as of T, tariff years, new finals, bookings, the split, its uses, the resolver, the bank connector type, the reads) | `pytest tests/domain/test_tar2_tariff_year_and_precedence.py tests/unit/test_tar2_capacity_costs.py tests/api/test_tar2_api.py` | 25 + 16 + 6 passed |
| Worked example, pipeline | `test_long_term_capacity_covers_part_and_the_rest_is_priced_at_the_day_ahead_reserve`, `test_bookings_and_the_capacity_cost_read_name_layers_versions_and_sources` | ITP-1 exit, January 2027, 100 MWh/d: booking LT-7 (2,500 kWh/h = 60 MWh/d at 3.65 EUR/(kWh/h)/y = 0.416667 EUR per MWh/d a day) 1,860 MWh for 775.00 EUR; the other 40 MWh/d at the day-ahead reserve price (0.0125 EUR/(kWh/h)/d = 0.520833) plus 0.05 premium, final, GY 2026/27, 1,240 MWh for 707.83 EUR; total 1,482.83 EUR |
| Worked example, LNG slot | `test_a_slot_booked_at_auction_prices_before_the_first_come_first_served_rate` | slot SLOT-3 bought at auction for March 2027 at 450,000 EUR: a 12 March arrival costs 450,000 EUR (contracted); a 12 April arrival takes the first-come-first-served public rate, 520,000 EUR, final (reviewed), CY 2027, with the contracted tier `not_covering` |
| Tariff, capacity, route, contract-cost, optimiser, LNG, scheduler, import-contract and source suites, the demo planted cases | `pytest` the 85 files under `tests/unit`, `tests/domain`, `tests/api`, `tests/integration`, `tests/db` whose names hold tariff, capacity, optimi, lng, route, contract_cost, scheduler, tar2, spreads, desk_today, planted, import_contract or source (`tests/integration/test_demo_planted_cases.py` included) | 912 passed, 7 skipped |
| Full serial suite | `pytest tests/unit tests/domain tests/security tests/evals tests/db tests/sdk tests/release tests/integration tests/api` (no PostgreSQL URL) | 6,286 passed, 253 skipped, 3 failed: three registry counts that the new connector moves (43 sources; `BANK` in the fx category), fixed in `84b4988` and re-run (61 passed) |
| Contract, census, permissions, reachability and docs gates | `pytest tests/contract tests/docs` | 605 passed, 12 skipped; census 308 paths / 343 operations |
| TAR-2 on PostgreSQL 16 (migration 0088) | store at `0086_lng_disruption`: `alembic upgrade head` (table `capacity_bookings`, column `tariff_versions.tariff_year`), `downgrade -1` (both gone), `upgrade head`; `pytest tests/integration/*postgres*.py tests/unit/test_postgres_native_schema_pipeline.py tests/db` with `RUNTIME_STORE_DATABASE_URL` and `EUROGAS_NEXUS_TEST_POSTGRES_URL` set | migration up, down, up clean; 255 passed, 16 skipped, 1 failed: `test_lng_cargo_change_postgres.py::test_a_late_cargo_reaches_each_role_through_the_listen_worker` (each role also receives LNG-3's "Disruption cleared" message); it fails the same way at `85d59f1`, before TAR-2 |
| Web | `npx tsc --noEmit -p .`; `npm test` | clean; 1,416 tests, 1,413 passed, 0 failed (`capacityCostModel.test.ts` new; CSS token lint, locale and date-input gates pass) |
| Lint | `ruff check src tests scripts alembic` | clean |

## LNG-4 options with consequences, full cost, substitute supply, demurrage, REMIT (2026-11-26)

The owner's scenario at full cost (06, "LNG-4"), through the store on SQLite and PostgreSQL,
every figure illustrative. Two days late, EUR against the plan:

| Option | Expected | Direct | Opportunity | Flags | Rank |
| --- | --- | --- | --- | --- | --- |
| Borrow in tank | -20,000 | -20,000 | 0 | none | 1, recommended `clean` |
| Buy send-out | -36,000 | -36,000 | 0 | none | 2 |
| Stay, absorb | -279,000 | -279,000 | 0 | none | 3 |
| Divert to Dunkerque | -362,400 | -187,000 | 175,400 | none | 4 |
| Swap with GATE-1 | +35,000 | +35,000 | 0 | moves GATE-1 | 5, recommended `best_expected` |
| Swap with HUE-1, Cepsa covered with PVB gas | -215,000 | -215,000 | 0 | moves HUE-1 | 6 |
| Swap with HUE-1 | -215,000 | -215,000 | 0 | breaks Cepsa (50,000 MWh short on 24 Jan, penalty not held); moves HUE-1 | 7 |

The diversion's opportunity cost: the third-party carrier waits 48 h against 24 h of laytime
(65,000 EUR) and boils off 2,000 MWh at PEG 30.20 (60,400 EUR); the spare slot's release value
forgone (50,000 EUR). GATE-1's 77,000 USD/day at the ECB fix of 2027-01-19 is 70,000 EUR/day.
Demo D1 (24 December): the Huelva swap is listed with `contract_breach` (45,000 MWh short on
28 Dec, penalty not held), PVB hub gas covering it ranks just above it, the spot slot at
Montoir ranks first (+371,317 EUR), and Meridian's 76,000 USD/day converts at the simulated
demo rate (1.087, 2026-12-23) to 69,917 EUR/day only with demo marks on.

| Run | Command | Result |
| --- | --- | --- |
| Full serial suite (before `2bdd6e8`) | `pytest tests/unit tests/domain tests/security tests/evals tests/db tests/sdk tests/release tests/integration tests/api` | 6,283 passed, 254 skipped, 0 failed (45 min 16 s) |
| After `2bdd6e8` (the notice fix) | the same suites with `-k "lng or disruption or cargo or notification or outage or demo or market_event"` | 786 passed, 16 skipped, 0 failed |
| LNG-4 tests | `pytest tests/domain/test_lng_disruption.py tests/unit/test_lng_demurrage.py tests/unit/test_lng_substitutes.py tests/unit/test_pipeline_outages.py tests/unit/test_lng_disruption_migration.py tests/api/test_lng_disruption_api.py tests/api/test_data1_import_contracts.py tests/integration/test_lng_disruption_postgres.py tests/integration/test_demo_planted_cases.py` | 88 passed, 4 skipped (the PostgreSQL cases, run below) |
| Contract, docs and security (census 305 / 340, surface reachability, policy EN and CN) | `pytest tests/contract tests/docs tests/security` | 1,136 passed, 12 skipped |
| PostgreSQL 16 (`egn_fixlng`: `alembic upgrade head`, `downgrade -1`, `upgrade head`, all clean; dropped afterwards) | every test file gated on `RUNTIME_STORE_DATABASE_URL` (25 files) plus the LNG store and schema tests, with `RUNTIME_STORE_DATABASE_URL` and `EUROGAS_NEXUS_TEST_POSTGRES_URL` set (pg8000) | 148 passed, 0 skipped (106 of them skip without `RUNTIME_STORE_DATABASE_URL`) |
| PostgreSQL CI list | the pytest list of `scripts/ci/run_postgres_ci.sh` | 132 passed, 3 skipped (NumPy absent) |
| Lint | `ruff check src tests scripts alembic` | All checks passed |
| Markdown links | `python scripts/ci/check_markdown_links.py` | All local links resolve |
| Web | `npx tsc --noEmit -p .`; `npm test` (in `clients/web`) | clean; 1,418 tests, 1,415 passed, 3 skipped, 0 failed |

Found and fixed on the way (`2bdd6e8`): with `RUNTIME_STORE_DATABASE_URL` set, the LNG-2
listen-worker test showed a cargo four days late announced as "Disruption cleared" beside
LNG-2's message, because a run with no recommended option was titled cleared. Now that run is
"No workable option" and "cleared" follows only the end of an open disruption (LNG4-10).

Latency ([15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) section 8): the options read median
0.063 s on SQLite and 0.103 s on PostgreSQL; an outage event to its link and run median 0.071 s
and 0.114 s.

## Not yet evidenced

- TAR-2: the capacity cost panel and the tariff years view have not been walked in a browser;
  the time from ENTSOG republishing a reserve price to the version being held was not measured
  live (no outbound network), only bounded by the hourly job and the poll interval.

- NEWS-1 live feeds: no feed was read live (no outbound network in the build environment);
  end-to-end latency from publication to a role's alert not measured.

- MAP-1 frame rate: the flow animation and 3D columns have not been measured in a browser;
  read `data-map-scene-frame-p95` on the reference machine with every layer on.

- Latency under sustained load: the M7 figures are single changes on an idle desk; the outbox
  transport rate is measured, sustained mixed load is not.
- Live quotes are not captured (R14, accepted). The cargo plan has no screen yet.
- CI on GitHub for the branch: `ci.yml` runs on pushes to `main` and on pull requests
  only, so pushing this branch starts no CI run. It runs if a pull request is opened, or by
  hand through `workflow_dispatch`.
