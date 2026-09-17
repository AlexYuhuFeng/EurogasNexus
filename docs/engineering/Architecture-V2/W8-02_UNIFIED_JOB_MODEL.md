# W8-02 — Unified Job Model

Status: **delivered (Wave 8, job lifecycle + API)**. Authority:
[08_DECISION_APPLICATION_AI.md](08_DECISION_APPLICATION_AI.md) section 5,
[03_TARGET_PLATFORM_ARCHITECTURE.md](03_TARGET_PLATFORM_ARCHITECTURE.md) section 3 and
[02_ARCHITECTURE_CONSTITUTION.md](02_ARCHITECTURE_CONSTITUTION.md) rule 36.

## 1. What the wave requires

Ingestion, dataset builds, optimisation, backtests, reporting and governed agent runs each grew
their own run model. Architecture V2 converges them on one lifecycle with one set of fields, so a
user, an operator, the job telemetry and the error surface all read the same thing.

## 2. Delivered

| Layer | Module | Content |
|---|---|---|
| Contract | `src/eurogas_nexus/domain/operations/jobs.py` | `JobState` (`QUEUED`, `RUNNING`, `WAITING_FOR_INPUT`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `EXPIRED`), `JobKind` (ingestion, dataset build, optimisation, backtest, report, agent run, snapshot), the transition table and the `Job` value object with every field V2 names |
| Persistence | `db/models/jobs.py`, `db/repositories/jobs.py`, `alembic/versions/0036_job_records.py` | `job_records` (expand-only migration), create/start/progress/finish/fail/cancel/get/list, each outcome writing an audit event in the same transaction |
| Tracking seam | `src/eurogas_nexus/application/jobs.py` | `track_job()` context manager: creates the job, records produced artefacts, fails it with a stable code and **re-raises the original exception untouched** |
| API | `api/routes/public/jobs.py` | `GET /api/jobs` (filter by status/kind/principal), `GET /api/jobs/{job_id}`, `POST /api/jobs/{job_id}/cancel` |
| Client contract | `clients/web/src/api/client.ts` | `JobDTO` plus `jobs()`, `job(id)`, `cancelJob(id)` |
| Activity surface | `clients/web/src/components/JobTimeline.tsx`, `clients/web/src/app/model/jobTimelineModel.ts` | The activity list on the Administration surface: active work first, states from the payload, cancellation offered only where the backend would accept it, failure codes rendered through the product error taxonomy, and the correlation id shown so a user can quote it |
| First wired path | `api/routes/public/research_data.py` | a dataset build is tracked, so `/api/jobs` shows what the deployment actually ran, its artefacts and its failure code |

## 3. Rules

1. **A terminal job stays terminal.** A late progress write, a second finish or a cancel attempt after
   completion raises `job_already_finished` instead of resurrecting the row.
2. **Progress never moves backwards**, and only a cancellable, non-terminal job may be cancelled.
3. **A failure carries a stable code** from the product error taxonomy (`W8-01`), taken from the
   exception when it declares one and otherwise from the status fallback.
4. **Tracking never changes behaviour.** The job row is written in the caller's session, so a job
   cannot claim an outcome the surrounding transaction did not commit; a failure inside the tracker
   never masks the real error; and a deployment without a runtime store runs the work untracked
   rather than refusing it.
5. **The payload is telemetry-safe**: identifiers, states, counts, hashes and correlation id - no
   secret, no stack trace, no licensed value.

## 4. Compatibility

- Additive: three new public paths, pinned in `tests/contract/test_api_surface_stability.py`,
  recorded in `docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md` and counted in the security
  acceptance bound (178).
- Migration `0036_job_records` is expand-only: one new table and its indexes, no change to anything
  existing, safe to apply while serving. `DB_SCHEMA_REVISION` reports `0036_job_records` and the
  release-metadata test asserts it equals the real Alembic head.
- The dataset-build endpoint keeps its payload, status codes and validation; the only behaviour change
  is that a validate-only build now commits its job record (nothing else is written on that path).

## 5. Adopted run paths

The seam only earns its keep when existing work registers into it, so the paths V2 names now do:

| Path | Seam | Artefact it cites |
|---|---|---|
| Dataset build (`POST /api/research/datasets`) | `track_job()` in the handler's own session | the dataset snapshot it built |
| Resource-pool optimisation (`POST /api/route-cost/resource-pool/optimize`) | `run_tracked_job()` (the work has no session of its own) | none: the run persists no artefact, so its `output_refs` are honestly empty rather than invented |
| Strategy backtest (`POST /api/strategy-runs`, `run_type=BACKTEST`) | `track_job()` inside the existing `_db_session()` | `strategy_run:<run_id>`, committed with the run rows it describes |
| Portfolio report (`POST /api/reports/portfolio`) | `run_tracked_job()` | `generated_report:<report_id>`, and **only** when the report really was persisted |
| Governed agent research (`POST /api/agent/research`) | `track_job()` in the run's own session, committed after the tracker wrote the terminal outcome | `agent_run:<run_id>` plus every artefact that carries an id (`strategy_version:`, `backtest:`, `review-pack:`); the orchestrator's bare artefact labels are not dressed up as references |
| Ingestion runs (`execute_claimed_runs`, the worker path) | `track_job()` per claimed run, with the outcome stated on the handle because the runtime reports failure in its return value rather than by raising | `ingestion_run:<run_id>` on a successful run; a failed run records the run's own error code and cites no artefact |

The report path needed one honesty fix before it could be tracked: `_persist_report_if_db` swallowed
every failure, so a job would have cited a report the store does not hold. Persistence is still
best-effort - a store that refuses the write must not fail a report the user asked for - but it now
reports whether it stored the report. A configured store that refuses the write adds
`REPORT_NOT_PERSISTED` to the response warnings and the job records no artefact; a deployment with no
runtime store at all is a declared posture (the envelope already reports
`runtime-db-not-configured`), not a failed write, so it adds no warning and invents no job.

## 6. Retention: bounded, operator-controlled, and never automatic

The job table grows one row per tracked run, so Wave 8 owes a supported way to bound it. The
mechanism follows the audit-retention pattern, and the *policy* stays the operator's:

- `application/job_retention.py` holds `prune_expired_job_records(session, retention_days=...,
  dry_run=True)`. There is deliberately **no default window**: audit retention has one because a
  stated policy set it (R32, 365 days), and no equivalent decision exists for job records, so the
  caller states one. The bounds (1–3650 days) only reject values that cannot be meant.
- **Only terminal rows are eligible**, whatever their age. A `QUEUED`, `RUNNING` or
  `WAITING_FOR_INPUT` row is work that has not finished, and it is the row
  `POST /api/jobs/{job_id}/cancel` acts on. Rows past the window that are still active are
  **counted and reported**, with `scripts/ops/recover_stale_jobs.py` named as the path to resolve
  them - a retention pass is not the place to decide that a long backtest is dead.
- **Pruning removes bookkeeping, never work.** The reports, strategy runs, dataset snapshots and
  agent runs a job's output references name are separate records the prune does not touch.
- `scripts/ops/prune_job_records.py` is dry-run by default, requires `--retention-days`, and prints
  rows deleted, rows eligible, active rows retained and the oldest instant still represented.
- No route exposes it. Bounding operational bookkeeping is an operator action on the deployment;
  the audit endpoints are served because an auditor needs a served, audited path, and mirroring
  that for jobs is a deliberate step if an operator asks for it.

Job *replay* stays deferred: re-running a recorded job is not a retention question, and it needs
its own answer about authority and idempotence before any surface offers it.

## 7. Deferred

- Job *replay* (re-running a recorded job) is a future operations decision: it needs an authority
  and idempotence answer before a surface offers it. Retention is delivered - see section 6. The
  activity list shows the most recent 25 records and refreshes on demand.

Every run family V2 names is now tracked: ingestion, dataset builds, optimisation, backtests,
reporting, agent runs and snapshots. The ingestion path needed one addition to the seam - work that
reports its outcome in a return value rather than by raising can state it on the handle
(`JobHandle.mark_failed`), so the job records the run's real outcome instead of the mere fact that the
worker did not throw. Tracking there also degrades to untracked when a store cannot accept a job row,
because a missing job row is an operational gap while a skipped ingestion is lost data.

## 7. Verification

- `tests/unit/test_job_contract.py` — the state/kind vocabularies, the success path with duration,
  terminal immutability, monotonic progress, cancellation bounds, the required failure code, the
  waiting-job transition rules and the telemetry payload shape.
- `tests/unit/test_job_retention.py` — retention as a bounded operator action: a dry run counts and
  changes nothing, only terminal rows past the window are deleted, active rows survive however old
  they are and are reported, the pass is idempotent and leaves the work its rows referenced, the
  window is required with nonsense refused, and the script refuses to run without a window or a
  database and reports the stale active rows it kept.
- `tests/api/test_jobs_api.py` — a tracked job records outcome, deduplicated outputs, input hash and
  correlation id; a failing tracked job stores the stable code and re-raises; cancellation is refused
  for a finished job and accepted for a running one; 404 for an unknown job; authentication required.
- `clients/web/tests/jobTimeline.test.ts` — active/finished separation, payload-driven cancellation and
  retry, progress and duration formatting without invented values, timeline ordering and summary
  counts, stable label keys, the shared badge primitive (including that the existing variants are
  unchanged), the mount on the administration surface, failure explanation through the taxonomy, and
  bilingual vocabulary.
- `tests/api/test_report_jobs_api.py` — a stored report registers a `REPORT` job that cites the report
  under its stored id; a configured store that refuses the write warns `REPORT_NOT_PERSISTED` and the
  job cites no artefact; a deployment without a store adds no warning and invents no job.
- `tests/api/test_agents_api.py` — a governed research run registers an `AGENT_RUN` job attributed to a
  principal the identity vocabulary accepts, citing the run and every id-bearing artefact, with no bare
  artefact label among its output references.
- `tests/unit/test_dataops_runtime.py` — one claimed ingestion run is one tracked job: a failed run is
  a FAILED job with the run's own error code and no artefact, a successful run cites
  `ingestion_run:<run_id>`, and the job is scoped to its source.
- `tests/api/test_projections_api.py`, `tests/api/test_route_cost_adjacent_api.py` and
  `tests/api/test_backtest_api.py` — the adopted paths' own behaviour is unchanged by tracking.
- Full suites: `python -m pytest tests -q --ignore=tests/integration` and the client suite; results are
  recorded in the execution checkpoint.
