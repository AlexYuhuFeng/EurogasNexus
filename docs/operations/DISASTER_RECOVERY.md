# Disaster Recovery

Engineering targets for the single-organization deployment model. These are
internal objectives, not contractual guarantees.

## RPO / RTO

| Asset | RPO target | RTO target | Evidence |
|---|---|---|---|
| PostgreSQL durable state | ≤ 24h (daily logical backup) | ≤ 30 min local restore | `scripts/ops/backup_restore_drill.py` actual drill |
| Application host | process supervisor restart | ≤ 5 min | Compose `restart: unless-stopped` |
| Scheduler jobs | no durable loss; stale rows recovered | next scheduler scan | `scripts/ops/recover_stale_jobs.py` |

Continuous WAL/PITR is not shipped at current scale; document it as the
production recommendation if continuous market ingestion is authorized.

## Failure scenarios

### Database loss

Detection: readiness 503, runtime `/api/runtime/db` unreachable.
Impact: all data routes unavailable; ingestion/shadow workers fail recorded.
Recovery: provision PostgreSQL, run `backup_restore_drill.py` target restore
or documented `pg_restore`, verify revision/required tables/API smoke.
Verification: `/api/health/ready` 200; representative business rows present.
Escalation: deployment owner if backup is missing or unreadable.

### Application host loss

Detection: liveness/readiness unavailable; supervisor restart loops.
Impact: interactive API down; PostgreSQL and persisted jobs remain.
Recovery: restore previous validated image/tag; rerun `smoke_release.py`.
Verification: live/ready 200; load smoke green.
Escalation: infrastructure owner if repeated crashes.

### Scheduler corruption / orphaned RUNNING jobs

Detection: missing scheduler heartbeat; RUNNING rows older than thresholds.
Impact: source freshness degrades; no duplicate claims are possible.
Recovery: `python scripts/ops/recover_stale_jobs.py --commit`; restart
scheduler workers.
Verification: heartbeat returns; source freshness recovers.
Escalation: data-operations owner if rows remain stuck.

### Bad deployment

Detection: release smoke fails; readiness path changes.
Impact: API/client mismatch.
Recovery: follow `RELEASE_ROLLBACK.md`; validate schema compatibility before
downgrade.
Verification: previous smoke suite passes; no data writes attempted.

### Bad migration

Detection: migration preflight fails or `alembic upgrade head` exits non-zero.
Impact: no partial revision is marked in the tested PostgreSQL transaction
path; API stays on previous head if migrate service is one-shot and fails.
Recovery: fix migration, rerun preflight, re-run upgrade.
Verification: revision equals expected head; required tables complete.
Escalation: engineering owner.

### Credential compromise

Detection: audit anomaly / provider auth failures.
Impact: data or identity boundary.
Recovery: revoke API key, disable principal, rotate provider credential, audit
retention.
Verification: revoked credential fails; audit row exists.
Escalation: security owner.

### Major provider outage

Detection: circuit state OPEN / freshness STALE.
Impact: only affected source surfaces degrade.
Recovery: wait for circuit recovery probe or operator retry.
Verification: source freshness FRESH/LATE per SLA.
Escalation: commercial-data owner for sustained outage.

### OIDC outage

Detection: login failures with `oidc_discovery_unavailable`.
Impact: new logins blocked; existing sessions continue until expiry.
Recovery: restore IdP/JWKS reachability; clear cache by process restart.
Verification: `/api/auth/status` and a login succeed.
Escalation: identity team.
