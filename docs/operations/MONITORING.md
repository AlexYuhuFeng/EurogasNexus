# Monitoring: metrics, alerts, logs and traces

How to watch a Eurogas Nexus installation with the firm's own Prometheus and Alertmanager,
read its logs, and (optionally) send traces. What to do when an alert fires is in
[ALERT_RESPONSES.md](ALERT_RESPONSES.md).

## What the product exports

`GET /metrics` on each API server returns the standard Prometheus text format. It is **closed
by default**: it answers only when the deployment configures who may scrape, and it is never
reachable through the public HTTPS gateway (the shipped gateways answer `/metrics` with 404).

| Family | What it tells you |
| --- | --- |
| `eurogas_http_request_duration_seconds` (histogram), `eurogas_http_requests_total` | Request latency and count per route group (`/api/market`, `/api/portfolio`, ...), method and status class (2xx, 4xx, 5xx) |
| `eurogas_db_pool_checked_out`, `eurogas_db_pool_size`, `eurogas_db_pool_overflow` | Database connections in use and available, summed over the API's worker processes |
| `eurogas_db_pool_checkouts_total`, `eurogas_db_pool_waits_total`, `eurogas_db_pool_timeouts_total`, `eurogas_db_pool_wait_seconds_total` | Connections handed out, checkouts that had to wait because the pool was exhausted, checkouts that gave up after the pool timeout, and the time spent waiting (all from the pool's own counts, `db/session.py`) |
| `eurogas_db_statement_timeouts_total`, `eurogas_db_connections_lost_total` | Statements the database cancelled after their time limit (answered 503 `runtime_db_timeout`), and connections dropped because the database stopped answering (`docs/operations/DB_RUNTIME_HARDENING.md`, Timeouts) |
| `eurogas_stream_connections{topic}` | Open live-update connections (quotes, alerts, opportunities ...) |
| `eurogas_stream_polls_total`, `eurogas_stream_poll_seconds_total`, `eurogas_stream_poll_failures_total`, `eurogas_stream_refused_total` | The live-update pollers (one per API process): polls, time spent in them, polls that could not reach the store, streams refused over the per-caller cap |
| `eurogas_source_freshness_seconds{source_id}`, `eurogas_source_stale_after_seconds{source_id}` | How old each enabled source's data is, and the age its own freshness rule calls stale |
| `eurogas_source_consecutive_failures`, `eurogas_source_stale`, `eurogas_source_enabled`, `eurogas_source_scheduler_overdue`, `eurogas_source_certification_state` | Per-source health |
| `eurogas_ingestion_runs_total`, `eurogas_ingestion_failures_total`, `eurogas_ingestion_failures_last_hour{source_id}` | Ingestion outcomes |
| `eurogas_scheduler_heartbeat_age_seconds{scheduler}` | Seconds since the data-operations (and shadow) scheduler last reported; `+Inf` when it never ran |
| `eurogas_scheduler_last_scan_age_seconds`, `eurogas_scheduler_sources_scheduled` | The scheduler's last scan and how many sources it has on a schedule |
| `eurogas_jobs_finished_last_hour{kind,status}`, `eurogas_jobs_active{kind}` | Job outcomes and running work |
| `eurogas_feed_last_quote_age_seconds{source_system}`, `eurogas_feed_receive_lag_seconds{source_system}` | Live price feeds: newest quote's age, and how far receipt lags the venue time |
| `eurogas_market_events_backlog{consumer}`, `eurogas_market_events_oldest_due_age_seconds{consumer}`, `eurogas_market_events_dead{consumer}` | The market-event outbox: waiting deliveries and how late the oldest is |
| `eurogas_metrics_database_up`, `eurogas_metrics_collector_up{collector}` | Whether the database metrics could be read at this scrape |

The database-derived families are computed at each scrape with aggregate queries; every API
server reports the same values (the alert rules take the maximum, so two servers do not alert
twice). The Runtime page keeps reading the same text through `/api/runtime/metrics` behind
sign-in.

**Several worker processes.** When the API runs more than one worker process, set
`PROMETHEUS_MULTIPROC_DIR` to an empty directory the workers share (the runtime compose file
mounts an empty `tmpfs` at `/run/eurogas-metrics`, emptied at every start). Each worker writes
its samples there and whichever worker answers a scrape adds them all up. Without it, each
process reports only its own requests, which is right only with a single worker. The preflight
(`config-check`) warns when `UVICORN_WORKERS` is above 1 and the directory is not set.

## Step 1: let Prometheus scrape

Choose one or both, in the deployment's environment file:

- **A scrape token.** Generate one (`openssl rand -hex 32`), set it as
  `EUROGAS_NEXUS_METRICS_SCRAPE_TOKEN`, and give Prometheus the same value in a file only it
  can read (`authorization.credentials_file`).
- **Allowed networks.** Set `EUROGAS_NEXUS_METRICS_ALLOWED_NETWORKS` to the monitoring
  servers' addresses or ranges, comma-separated (`10.20.0.15,10.20.1.0/24`).

With both set, a scrape needs both. Restart the API (`docker compose up -d api`). Check from
the monitoring server:

```sh
curl -s -H "Authorization: Bearer $(cat scrape-token)" http://api-1.internal:8000/metrics | head
```

401 means the token differs, 403 that the address is not allowed, 404 that neither setting
reached the API.

Scrape each API server directly on the internal network, not through the HTTPS gateway.
`deploy/monitoring/prometheus/prometheus.example.yml` is a starting configuration; a 30-second
scrape interval is enough.

## Step 2: load the alert rules

Copy `deploy/monitoring/prometheus/eurogas-nexus-alerts.yml` to Prometheus's rules directory,
list it under `rule_files:` and reload Prometheus. Check it first:

```sh
promtool check rules eurogas-nexus-alerts.yml
promtool test rules eurogas-nexus-alerts.test.yml   # the rules' own tests, beside them
```

Every alert carries `severity` (`critical` or `warning`) and `team` (`platform` or `data`)
labels for Alertmanager routing, and a `runbook_url` that points at its section of
[ALERT_RESPONSES.md](ALERT_RESPONSES.md). The alerts:

| Alert | Severity | Fires when |
| --- | --- | --- |
| EurogasSchedulerHeartbeatMissing | critical | no scheduler heartbeat for 5 minutes (2 minutes' grace) |
| EurogasSourceStale | warning | a source is older than its freshness rule for 10 minutes |
| EurogasSourceFailing | warning | a source failed 3 times in a row |
| EurogasFeedLagging | warning | a live feed lags the venue by more than 30 s for 5 minutes |
| EurogasJobFailures | warning | a job failed in the last hour |
| EurogasMarketEventsBacklog | warning | an event consumer is more than 10 minutes behind |
| EurogasApiDown | critical | an API server cannot be scraped for 2 minutes |
| EurogasMetricsDatabaseUnavailable | critical | the API cannot read the database for 5 minutes |
| EurogasDbPoolExhausted | critical | a pool checkout timed out, or over 10 % of checkouts waited, for 2 minutes |
| EurogasDbPoolNearlyExhausted | warning | over 90 % of the pool in use for 5 minutes |
| EurogasApiErrorRate | critical | over 5 % server errors for 10 minutes |
| EurogasApiSlowP95 | warning | p95 latency of a route group over 1 s for 15 minutes |
| EurogasMetricsCollectorFailing | warning | a group of database metrics fails for 15 minutes |

**Prove it works** (the phase-1 acceptance check): stop the scheduler
(`docker compose --profile public-ingestion stop public-ingestion-worker`); within about 7
minutes EurogasSchedulerHeartbeatMissing fires. Start it again and the alert clears.

## The scheduler: one active, the others standing by

The data-operations scheduler takes a PostgreSQL advisory lock when it starts. A second
scheduler against the same database (a second job server, an old container, a manual run)
does not ingest: it logs `scheduler.standby` every interval and takes over within a minute
when the active one stops. While active, the scheduler writes its heartbeat every 30 seconds,
also during long ingestions. The Runtime page's scheduler row shows the heartbeat: "Not
running" when no scheduler has ever reported, the age of the last report otherwise.

`run_dataops_scheduler.py --once` on a standby exits with code 3 without ingesting.

## Logs

Every process writes one JSON object per line to standard error (`EUROGAS_NEXUS_LOG_FORMAT`:
`json` by default in trial and release, `text` elsewhere; `EUROGAS_NEXUS_LOG_LEVEL`, default
`INFO`). The runtime compose file keeps at most five 20 MB files per container
(`docker compose logs`); ship them to the firm's log platform with its usual collector.

The API's live-update poller (`logger` `eurogas_nexus.api.stream_hub`) logs a poll that cannot
reach the store as an `error` record with `error_type` and `stack`, then at most once a minute
while the store stays unreachable, and one `info` record when it recovers.

Fields: `timestamp`, `level`, `logger`, `service`, `message`; while a request is served
`request_id` (the `X-Request-Id` response header) and, once the caller is known,
`principal_id`; each API request ends with one `eurogas_nexus.access` record with
`http_method`, `route` (the route template, never the actual path), `status` and
`duration_ms`. Health probes are not access-logged.

Not logged, by design: client addresses, user agents, headers, query strings, request and
response bodies, credentials. Values that look like credentials (a password in a URL, a
`Bearer` header, a field named like a token or secret) are replaced with `[REDACTED]`.

## Tracing (optional, off by default)

`EUROGAS_NEXUS_OTEL_ENABLED=1` makes each API request one OpenTelemetry server span
(`GET /api/market/curves/{hub}`, status code, request id) and adds `trace_id` to its log
lines. The OpenTelemetry packages are not part of the shipped image: install
`opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http` into a derived image (both
Apache-2.0) and set the standard `OTEL_EXPORTER_OTLP_ENDPOINT` (and `OTEL_SERVICE_NAME` if you
like). With the setting on and the packages missing, the API starts, logs one warning and
runs without traces.
