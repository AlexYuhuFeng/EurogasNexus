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

## Not yet evidenced

- Latency under sustained load: the M7 figures are single changes on an idle desk; the outbox
  transport rate is measured, sustained mixed load is not.
- Live quotes are not captured (R14, accepted). The cargo plan has no screen yet.
- CI on GitHub for the branch: `ci.yml` runs on pushes to `main` and on pull requests
  only, so pushing this branch starts no CI run. It runs if a pull request is opened, or by
  hand through `workflow_dispatch`.
