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

## 5. Deferred

- Wiring the remaining long-running paths onto `track_job()`: resource-pool optimisation, strategy
  backtests, report generation, agent runs and ingestion runs. The seam is ready; each is a small
  bounded change.
- Job *replay* and retention policy (how long records are kept) are future operations decisions. The
  activity list shows the most recent 25 records and refreshes on demand.

## 6. Verification

- `tests/unit/test_job_contract.py` — the state/kind vocabularies, the success path with duration,
  terminal immutability, monotonic progress, cancellation bounds, the required failure code, the
  waiting-job transition rules and the telemetry payload shape.
- `tests/api/test_jobs_api.py` — a tracked job records outcome, deduplicated outputs, input hash and
  correlation id; a failing tracked job stores the stable code and re-raises; cancellation is refused
  for a finished job and accepted for a running one; 404 for an unknown job; authentication required.
- `clients/web/tests/jobTimeline.test.ts` — active/finished separation, payload-driven cancellation and
  retry, progress and duration formatting without invented values, timeline ordering and summary
  counts, stable label keys, the shared badge primitive (including that the existing variants are
  unchanged), the mount on the administration surface, failure explanation through the taxonomy, and
  bilingual vocabulary.
- Full suites: `python -m pytest tests -q --ignore=tests/integration` and the client suite; results are
  recorded in the execution checkpoint.
