# Alert responses

What each Eurogas Nexus alert means and what to do. The rules are in
`deploy/monitoring/prometheus/eurogas-nexus-alerts.yml`; setting up the monitoring is in
[MONITORING.md](MONITORING.md).

**Severity.** *Critical*: the desk is affected now or will be within minutes; act now, at
any hour the desk trades (gas day 06:00 to 06:00 CET, weekends included). *Warning*: something
is degrading; act the same working day.

**First look for any alert.** The Runtime page (Admin, Runtime) shows the database, the
schedulers' heartbeats and source health. The logs are one JSON object per line
(`docker compose logs api --since 30m`); every line of one request carries the same
`request_id`, which is also the `X-Request-Id` header a user can read from a failed page.

## EurogasSchedulerHeartbeatMissing

**Means.** The data-operations scheduler has not reported for more than 5 minutes (it reports
every 30 seconds while it runs). Nothing is read on schedule: prices, flows, storage and
outages stop updating and the freshness alerts follow. A value of "+Inf" means no scheduler
has ever run against this database.

**Do.**

1. Is the scheduler running? `docker compose --profile public-ingestion ps
   public-ingestion-worker`. If it is stopped or restarting, read its last lines:
   `docker compose logs public-ingestion-worker --tail 50`.
2. Start it if it is stopped: `docker compose --profile public-ingestion up -d
   public-ingestion-worker`.
3. If it runs but logs `scheduler.standby`, another scheduler holds the lock: only one may
   ingest. Find the other one (a second job server, an old container, a manual run). The one
   that holds the lock should be beating; if it is hung, stop it and the standby takes over
   within a minute.
4. If it logs `scheduler.lock.lost`, its database connection dropped; it retakes the lock by
   itself once the database answers. If the database is down, see
   EurogasMetricsDatabaseUnavailable.
5. When it beats again, the alert clears within 2 minutes and the sources catch up on their
   next scheduled runs.

## EurogasSourceStale

**Means.** A source has not succeeded for longer than its own freshness rule allows (each
source definition sets how old its data may get). Screens built on it show old data, marked
stale.

**Do.**

1. Look at the source on the Sources page: last success, last error, circuit state.
2. If EurogasSchedulerHeartbeatMissing is also firing, fix that first: every source goes stale
   when the scheduler stops.
3. If the source fails (EurogasSourceFailing is firing for it), follow that section.
4. If the source succeeds but its data is old, the provider has not published: check the
   provider's status page. Nothing to fix here; tell the desk which data is late.
5. A source that is no longer wanted can be switched off on the Sources page; the alert then
   stops for it.

## EurogasSourceFailing

**Means.** The scheduler's last three or more attempts for one source failed. After repeated
failures the source's circuit opens and retries slow down.

**Do.**

1. Read the error on the Sources page (the error category says the kind: credential, rate
   limit, provider unavailable, data quality, configuration).
2. Credential or entitlement: renew the key in Admin, Data sources (the firm's own key for
   ENTSO-E, EIA, GIE).
3. Rate limited or provider unavailable: usually clears by itself; if it lasts more than a
   few hours, check the provider's status.
4. Configuration (for example an ENTSOG window): see
   [PRODUCTION_SOURCE_OPERATIONS.md](PRODUCTION_SOURCE_OPERATIONS.md).
5. An operator can run the source once by hand from the Sources page after a fix.

## EurogasFeedLagging

**Means.** A live price feed delivers quotes more than 30 seconds after the venue time.
Live prices on Nexus lag the trading screen.

**Do.**

1. Tell the desk that live prices on Nexus lag; the trading screen remains the reference.
2. Check the feed handler's host and its connection to the provider (the provider's own
   status, the firm's network).
3. Check the database: a slow database delays every write (EurogasApiSlowP95 and
   EurogasDbPoolNearlyExhausted usually fire too).

## EurogasJobFailures

**Means.** Jobs (reports, optimisations, backtests, ingestion runs tracked as jobs) failed in
the last hour.

**Do.**

1. Open the Activity view: each failed job has an error code and, where it applies, a retry.
2. One failure is usually the input (a missing curve, a bad file): the job's owner retries.
3. The same kind failing repeatedly points at a dependency (database, a source): check the
   other alerts and the logs of the job's `request_id`.

## EurogasMarketEventsBacklog

**Means.** A consumer of market events (re-evaluation of opportunities, live notices) is more
than 10 minutes behind. Opportunity and alert updates on the desk are late; the figures
themselves stay correct when read.

**Do.**

1. Is the market-events worker running? `docker compose --profile public-ingestion ps
   market-events-worker`; start it if not. The scheduler also drains the outbox after each
   tick, so a stopped scheduler makes this worse.
2. If it runs and still lags, read its log for repeated failures of one consumer; events
   that fail too often are set aside ("dead") and stop blocking the others.

## EurogasApiDown

**Means.** Prometheus cannot read `/metrics` from an API server.

**Do.**

1. Open the product in a browser. If it does not answer, the API is down: `docker compose ps
   api`, `docker compose logs api --tail 100`, then `docker compose up -d api`.
2. If the product works, the scrape is refused: the scrape token
   (`EUROGAS_NEXUS_METRICS_SCRAPE_TOKEN`) and the token file Prometheus reads differ, or the
   monitoring server's address is not in `EUROGAS_NEXUS_METRICS_ALLOWED_NETWORKS`. A refused
   scrape gets 401 (token) or 403 (network); 404 means neither setting is in force.

## EurogasMetricsDatabaseUnavailable

**Means.** The API answers but cannot read the database.

**Do.**

1. Is PostgreSQL running? `docker compose ps postgres`, `docker compose logs postgres --tail
   50`.
2. Disk full is the most common cause on a single server: `df -h` on the database volume.
3. If the database runs, check the connection pool (EurogasDbPoolNearlyExhausted) and
   whether the database accepts connections (`max_connections`).
4. For a lost or damaged database follow [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md).

## EurogasDbPoolNearlyExhausted

**Means.** More than 90 % of an API server's database connections are in use for 5 minutes.
When none is left, requests wait and then fail with 503.

**Do.**

1. Look for slow statements: on PostgreSQL, `SELECT pid, now() - query_start, state, query
   FROM pg_stat_activity WHERE datname = current_database() ORDER BY 2 DESC;`.
2. A long report or export holding connections: let it finish or cancel it from the Activity
   view.
3. Sustained load: raise `EUROGAS_NEXUS_DB_POOL_SIZE` / `EUROGAS_NEXUS_DB_MAX_OVERFLOW` (within
   the database's `max_connections`), or add an API server.

## EurogasApiErrorRate

**Means.** More than 5 % of API requests fail with a server error for 10 minutes.

**Do.**

1. Read the errors: `docker compose logs api --since 15m | grep '"status": 5'`. Each line
   names the route and the `request_id`; the lines of that request show the cause.
2. Database errors: see EurogasMetricsDatabaseUnavailable and EurogasDbPoolNearlyExhausted.
3. After a release: if the errors started with the new version, roll back
   ([RELEASE_ROLLBACK.md](RELEASE_ROLLBACK.md)).

## EurogasApiSlowP95

**Means.** For 15 minutes, 5 % of the requests to one part of the API (the route group in the
alert) took more than one second, the phase-1 budget.

**Do.**

1. Note the route group: `/api/market`, `/api/portfolio` and the like.
2. Check the database first (slow statements, as for EurogasDbPoolNearlyExhausted).
3. Check the host: CPU and memory of the API and the database.
4. If one route group is slow after a release or a data load, record it as a problem report
   with the times; the logs carry `duration_ms` per request.

## EurogasMetricsCollectorFailing

**Means.** One group of database metrics (ingestion, sources, scheduler, jobs, feed, market
events) fails at every scrape, so the alerts built on it cannot fire.

**Do.**

1. Usually a schema older than the API (the upgrade was not run): run
   `python scripts/ops/upgrade_database.py check` ([DATABASE_UPGRADE.md](DATABASE_UPGRADE.md)).
2. Otherwise read the API log around a scrape for the database error and raise it with the
   vendor.
