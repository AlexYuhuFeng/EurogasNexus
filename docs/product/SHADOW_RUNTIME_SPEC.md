# Shadow Runtime Specification — CR-06

Status: accepted CR-06 architecture. This document owns the production-grade
shadow research runtime: monitor lifecycle, scheduler, evidence/freshness
policy, candidate decisions, risk checks, outcome maturation, shadow
indicative PnL, baseline/drift, alerts, recovery and no-execution guarantees.

## 1. Scope and audit

Pre-implementation audit:

- Legacy `/api/research/shadow-run` computes simple signal statistics from
  client-supplied signals; it is a research calculation, not scheduled
  runtime.
- `/api/strategy-lab/evaluate` and CR-03 `EVALUATION` runs are single
  operator-triggered evaluations; they are not scheduled and consume
  caller-supplied observations.
- CR-04 backtest engine owns as-of evidence selection, shared
  `StrategyEvaluator`, economic model, decision events, metrics, and run
  persistence.
- The frontend Shadow task is currently a truthful shell
  (`SHADOW_MONITORING_NOT_CONFIGURED`) with no fake scheduler.
- `monitoring_service` and `monitoring_alerts` provide generic infrastructure
  alerts; they are not strategy-shadow alerts.
- `streaming.py` provides existing SSE heartbeat/delta patterns; no
  production strategy scheduler, cron, lease, or background worker exists.
- `cost_source_refresh` and ingestion connectors are scheduler-friendly but
  are data acquisition, not strategy evaluation.

CR-06 therefore adds a new persistence/runtime layer on top of CR-04, sharing
the same evaluator; it does not create a second strategy engine.

## 2. Monitor lifecycle

`ShadowMonitor` state:

- `DRAFT` — persisted preflight object, not yet active;
- `ACTIVE` — future scheduled evaluations are eligible;
- `PAUSED` — no future evaluations scheduled; history and open alerts kept;
- `DEGRADED` — still active but recent evaluations consistently warn/fallback;
- `BLOCKED` — structural/data blocker or configured consecutive-failure
  threshold reached; no new evaluation until resumed;
- `RETIRED` — terminal, no future evaluation.

Lifecycle state is separate from latest evaluation outcome
(`SCHEDULED`, `RUNNING`, `COMPLETED`, `COMPLETED_WITH_WARNINGS`, `BLOCKED`,
`FAILED`, `CANCELLED`).

Activation prerequisites: frozen version, valid typed schedule, supported
component types, defined resource/economic assumptions, explicit baseline
backtest, and no structural blockers. A partially functioning monitor is
never started.

## 3. Scheduler architecture

DB-backed monitor definitions + a single synchronous scheduler process:

- `run_due_shadow_evaluations(session_factory, now, limit)` scans due
  monitors and evaluates them in-process.
- A standalone `scripts/ops/run_shadow_scheduler.py` runs one scan; CI/dev
  may invoke it on cadence. No Kafka/Celery/Redis is introduced.
- Restart-safe: all truth is in PostgreSQL; the next-run calculation is
  deterministic from persisted `next_evaluation_at`.
- Idempotent: every evaluation has unique `(shadow_monitor_id, scheduled_for)`.
- No browser timer is a production scheduler.

## 4. Locking / idempotency

PostgreSQL-safe claim: due monitors are selected with
`SELECT ... FOR UPDATE SKIP LOCKED`, and evaluation rows are inserted with
unique `(shadow_monitor_id, scheduled_for)`. If two workers claim the same
logical event, one insert succeeds and the other receives the existing
canonical evaluation (integrity-error path), so duplicates are impossible.
SQLite tests exercise the same repository contract sequentially; the
PostgreSQL lock path is the documented production mechanism.

Stale `RUNNING` rows (worker died) are recovered by `recover_stale_evaluations`
only after `stale_after_seconds`; their original records are never mutated
to fake a completed result, they are marked `FAILED` with
`OPERATIONAL_FAILURE:STALE_EVALUATION`.

## 5. Schedule semantics

Typed schedule only:

- `INTERVAL` — every `interval_seconds` from `activated_at`;
- `DAILY_AT` — daily at `HH:MM` UTC.

`missed_policy` is explicit: `SKIP` (default), `RUN_LATEST_ONLY`, or
`CATCH_UP_LIMITED` with `catch_up_limit`. Missed intervals produce a
`MISSED_SCHEDULE` monitor audit note and are never silently replayed as if
live.

## 6. Decision-time semantics

Every evaluation persists four separate timestamps:

- `scheduled_for`;
- `started_at`;
- `decision_time` — evidence eligibility cutoff;
- `completed_at`.

Worker start time and DB insert time are never substituted for decision
time. Gas-day fields use the shared `EU-CAM-UTC-2025` calendar.

## 7. Evidence acquisition

Shadow evaluation reads persisted PostgreSQL evidence only. Ingestion
pipeline remains the only data acquisition path. For each evaluation the
runtime loads the same normalized pool used by CR-04
(`load_backtest_evidence_pool`) bounded to `decision_time` and creates a
CR-03 `strategy_data_snapshots` row. Price/FX/resource/cost refs and source
systems are persisted on the evaluation.

## 8. Freshness policy

For each required evidence family the evaluation records:

- `FRESH`, `STALE`, `MISSING`, `RESTRICTED`, `UNAVAILABLE`.

Hard requirements block the evaluation. Soft/degraded requirements emit
warnings and mark the evaluation `COMPLETED_WITH_WARNINGS`. Approved fallback
sources use the CR-04 `USE_APPROVED_FALLBACK_SOURCE` policy and persist
`SOURCE_FALLBACK_USED` lineage. No silent fallback.

## 9. Blocked / degraded behavior

`BLOCKED` is a valid persisted result. It records blocker codes, available
evidence refs, and creates no normal candidate and no normal-looking PnL.
`DEGRADED` evaluation state is used only for explicit permitted fallback and
records primary/fallback/reason/policy.

## 10. Candidate decision model

`ShadowCandidate` persists:

- candidate id, evaluation id, strategy version id, decision/gas-day;
- candidate type and market context;
- hypothetical direction and quantity;
- expected indicative margin;
- risk state and evidence state;
- explanation codes, warnings, blocker references.

Vocabulary is research-only: Candidate / Observation / Hypothetical
allocation. No order, trade, execution or nomination labels appear.

## 11. Risk checks

`RiskCheckResult` persists one row per meaningful control:

- `OCM_ALLOCATION_CLAMP`;
- `MIN_DAY_AHEAD_ALLOCATION`;
- `EXPECTED_MARGIN_FLOOR`;
- `SHADOW_STOP_LOSS`.

Each row has `observed_value`, `limit`, `state` (`PASS`/`WARN`/`BLOCK`) and
explanation. Risk is never reduced to one boolean.

## 12. Outcome maturation

Candidate decisions are immutable. Outcomes are separate rows with state:

- `OPEN`;
- `MATURED` — later eligible evidence exists for the delivery period;
- `UNRESOLVED` — maturation ran but evidence is insufficient;
- `INVALIDATED` — data correction/invalidation requires explicit invalidation.

No original candidate is overwritten.

## 13. Shadow indicative PnL

Initial outcome is `MARK_TO_MODEL`: same fill/economic assumptions as the
candidate, explicitly labelled mark-to-model. Maturation recomputes against
the latest eligible observation at or before delivery end and labels the
result `REALIZED_SHADOW_INDICATIVE` only when that evidence exists. Monitor
cumulative shadow PnL uses matured outcomes when available, otherwise
mark-to-model values, and always labels its basis.

## 14. Baseline backtest

`ShadowMonitor.baseline_run_id` is explicit and immutable after activation.
A new baseline requires a new monitor or an explicit documented change.
Drift compares only against this baseline; the system never silently follows
“latest backtest”.

## 15. Drift

Simple interpretable drift, no ML:

- **Data drift** — mean candidate market spread vs baseline average margin
  context;
- **Behavior drift** — candidate frequency vs baseline candidate rate;
- **Performance drift** — mean candidate margin vs baseline average margin;
- **Operational drift** — blocked rate and fallback rate vs baseline.

Snapshot state: `INSUFFICIENT_DATA` (<3 shadow evaluations),
`NORMAL`, `WATCH`, `MATERIAL`, with metric/baseline/current/explanation and
sample size. No green/red-only classification.

## 16. Alerts

`ShadowAlert` persists lifecycle state `OPEN`, `ACKNOWLEDGED`, `RESOLVED`,
severity `INFO`, `WARNING`, `CRITICAL`, occurrence count and deterministic
fingerprint:

```
monitor_id | alert_type | condition_key
```

Repeated condition increments occurrence and updates last-seen; condition
clears resolves; later recurrence creates a new episode. Acknowledgement
records actor/time and means “I saw this” only — never approval and never
bypasses risk blockers.

Initial alert types: `DATA_STALE`, `DATA_MISSING`, `SOURCE_FALLBACK`,
`EVALUATION_BLOCKED`, `RISK_WARNING`, `RISK_BLOCK`,
`SHADOW_LOSS_LIMIT`, `PERFORMANCE_DRIFT`, `BEHAVIOR_DRIFT`,
`OPERATIONAL_FAILURE`. Successful candidate observations are persisted but do
not create alerts.

## 17. Retry and recovery

Failure classes: `DATA_BLOCKER`, `DOMAIN_BLOCKER`,
`TRANSIENT_INFRASTRUCTURE`, `PERMANENT_CONFIGURATION`, `INTERNAL_ERROR`.
Only transient infrastructure errors retry with bounded backoff. Invalid
configuration is not retried endlessly.

Consecutive failures:

- 1 → warning;
- 3 → monitor `DEGRADED`;
- configured threshold (default 6) → monitor `BLOCKED`.

## 18. Observability

Each scheduler scan persists a heartbeat row with:

- last heartbeat/scan time;
- due/claimed/completed/blocked/failed counts;
- oldest overdue evaluation;
- active monitor count;
- duplicate claim count.

No credentials, licensed payload bodies, or private contract terms are ever
logged.

## 19. Security

Monitor create/pause/resume/retire and alert acknowledge are governed write
surfaces. Reads stay in the current read permission family. Row data remains
inside existing source entitlement boundaries.

## 20. No-execution guarantees

Shadow runtime imports no execution/order/nomination adapter. Candidate rows
have no external side effects and no venue-facing schema. Regression tests
assert that activation/evaluation/acknowledgement paths touch only research
tables and the shared evaluator.

## 21. Limitations

- Synchronous single-process scheduler is production-grade for current
  repository scale; multi-region/distributed scheduling is out of scope.
- Maturation is a mark-to-latest-eligible-observation model, not venue
  settlement data.
- Drift is operational/statistical, not ML.
- External notification channels are out of scope.
- Local PostgreSQL service is not reachable in this environment; migration
  contract is validated via Alembic/SQLAlchemy tests.
