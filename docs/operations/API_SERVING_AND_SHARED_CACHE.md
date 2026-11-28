# Serving: several API processes, the live-update poller and the shared cache

For operators. What changed on 2026-11-26 (decision record
[2026-11-26-multi-process-api-and-shared-cache.md](../architecture/decisions/2026-11-26-multi-process-api-and-shared-cache.md)),
how to run the API as several processes, how to size the database pool, what to watch, and how
the load test is run.

## In one paragraph

The API can now run as several processes on one server, and on several servers behind the
firm's load balancer (no sticky sessions). Each process keeps one live-update poller that reads
the database once per 1.5 seconds for every open browser tab and hands each tab only what its
user may see. The processes agree on rate limits, on "a write happened" (so nobody is answered
from before their own change) and on sign-outs through a small shared cache, **Valkey**. One
process with no Valkey stays the default, and the demo keeps running that way.

## Topologies

| Shape | API processes | Shared cache | How |
| --- | --- | --- | --- |
| Demo, development, evaluation | 1 | none (in the process) | `deploy/demo/compose.yaml`, `deploy/runtime/compose.yaml` as shipped |
| One production server | 4 (one per core, up to 8) | Valkey on the same server | `deploy/runtime/compose.yaml` + `compose.scale.yaml` |
| Production, two or more servers | 4 to 8 per server | one Valkey (or a replicated pair) all servers reach | the firm's load balancer in front; every server's `EUROGAS_NEXUS_SHARED_CACHE_URL` names the same Valkey |

The preflight (`config-check`) refuses more than one process without a shared cache: without
it, another process could answer a user from before their own change, and every rate limit
would be multiplied by the number of processes.

### Start the one-server production shape

1. In the deployment's environment file (kept outside the repository) set a long random
   `VALKEY_PASSWORD`.
2. Start: `docker compose -f compose.yaml -f compose.scale.yaml --env-file .env up -d`.
3. Check: `docker compose ps` shows `valkey` and `api` healthy; `GET /api/runtime/metrics`
   shows `eurogas_stream_connections` and the `eurogas_db_pool_*` counters.

Valkey keeps nothing on disk and evicts nothing. Restarting it loses counters and notes only:
rate-limit windows start again, every process drops its kept views once and recomputes them,
and open streams fall back to the database check for sign-outs (see below).

### Several servers

* Run Valkey once for all servers (two 2-vCPU, 8 GB instances with replication, or on the
  application servers). Use Valkey or Redis 7.2 or earlier; later Redis versions carry a
  licence the product does not accept.
* Prefer TLS between the servers and Valkey: `valkeys://:<password>@valkey.internal:6380/0`.
* Run the workers (ingestion scheduler, market-events listener, monitoring) once per
  installation, not once per API server: they are separate services, not part of the API
  process. The API process starts no scheduler and no feed.

## Sizing the database pool

Every API process has its own pool: `EUROGAS_NEXUS_DB_POOL_SIZE` connections kept open plus up
to `EUROGAS_NEXUS_DB_MAX_OVERFLOW` more.

```
API connections   = servers x processes per server x (pool size + overflow)
total connections = API connections + workers' pools + 5 for operators and migrations
total connections <= PostgreSQL max_connections - superuser_reserved_connections (3)
```

Example: one server, 4 processes, pool 8 + 4: 48 API connections; the three workers use about
15; with 5 spare that is 68 of PostgreSQL's default 100. Two servers with 4 processes each at
8 + 4 need 96 for the API alone: raise `max_connections` to 150 or lower the pool to 6 + 2.

Inside a process, the request threads are sized from the pool: pool size + overflow - 5 (one
connection for the live-update poller, two for the warm views' background refreshes, two for
the identity threads that check sessions and keys), so a request waits for a free thread rather
than failing after `EUROGAS_NEXUS_DB_POOL_TIMEOUT` for lack of a connection.
`EUROGAS_NEXUS_API_THREADS` overrides it; keep it at or below that figure. Credentials are
checked on their own two threads, so a sign-in, a session check or a live stream's opening
never waits behind request threads that are busy with a long computation.

Every API statement is cancelled after 30 seconds (`EUROGAS_NEXUS_DB_STATEMENT_TIMEOUT_MS`;
`0` switches it off). The workers and migrations, which read the same environment file, are not
affected.

## What to watch

`GET /metrics` (for Prometheus, [MONITORING.md](MONITORING.md)) or `GET /api/runtime/metrics`
(the same text behind sign-in). All the API processes of one server write to the shared
`PROMETHEUS_MULTIPROC_DIR`, so one scrape returns the sum over them; the alert
EurogasDbPoolExhausted reads the waits and timeouts below.

| Metric | Healthy | Act when |
| --- | --- | --- |
| `eurogas_db_pool_waits_total` | flat or slow growth | it climbs steadily: the pool is too small for the load, or a slow read holds connections |
| `eurogas_db_pool_timeouts_total` | 0 | any growth: requests fail for lack of a connection; raise the pool (within the formula) or find the slow read |
| `eurogas_db_pool_checked_out` | below size + overflow | at the ceiling for minutes |
| `eurogas_db_statement_timeouts_total` | flat | growing: reads hit the 30 s statement timeout (a slow query or an overloaded database); users see 503 `runtime_db_timeout` and retry |
| `eurogas_stream_connections` (summed over `topic`) | about 1 to 3 per signed-in user | far above: a client reconnecting in a loop |
| `eurogas_stream_poll_seconds_total` / `eurogas_stream_polls_total` | well under 1.5 s per poll | close to 1.5 s: the poll cannot keep its interval; look for a slow source query |
| `eurogas_stream_poll_failures_total` | flat | growing: the poller cannot reach the database |
| `eurogas_stream_refused_total` | 0 | growing: someone opens more than `EUROGAS_NEXUS_MAX_STREAMS_PER_PRINCIPAL` (8: tabs, one stream each) streams across all processes |

## What happens when Valkey is down

| What | Behaviour while Valkey cannot be reached |
| --- | --- |
| Sign-in and administration rate limits, per-person write and heavy-computation quotas | each process counts for itself again (limits never disappear) |
| Open streams per person (`EUROGAS_NEXUS_MAX_STREAMS_PER_PRINCIPAL`) | each process counts its own new streams; slots already held in Valkey expire within 90 s |
| Per-address sign-in throttle | each process counts for itself; the per-account lockout is in the database and unaffected |
| Warm views | each process drops what it kept and computes every read until Valkey answers (slower pages, never an answer from before a user's own change) |
| Sign-out of an open live-update stream | the stream re-reads its session and identity from the database every 30 s, so it still ends within 30 s; with Valkey it ends at the next poll (1.5 s) |
| Every request's own session check | unaffected: it reads the database on every request |

The client stops asking Valkey for 2 seconds after a failure, so an outage costs one short
timeout, not one per request. A log line `shared cache unavailable` names the error class.

## The live-update poller

Each API process runs one thread, `nexus-stream-poller`, that polls the change sources (quotes,
outbox events, alerts, the map's inputs, jobs) once per interval for every open stream of that
process, in one database session, and hands each stream its own events through an in-memory
queue. Each stream keeps its own cursor and its own user's entitlement (licensed sources, book
scope, the opportunity and alert read rules). A stream opened with a session ends at the next
poll after a sign-out on any process. A user may hold `EUROGAS_NEXUS_MAX_STREAMS_PER_PRINCIPAL`
(8, security review M7; the demo 40) open streams in all; one more answers 429 `rate_limited`
(reason `stream_limit_reached`, `Retry-After: 30`). The web client holds ONE stream per browser
tab (`/api/stream/live` with every topic; the opportunity engine's events ride on it), so the cap
is tabs per person; a tab refused one says "Live updates paused" once and re-reads on a timer.
A stream's place is freed the moment its connection closes: the response closes its stream
however it ends (`CountedStreamingResponse`), a quiet stream sends a keepalive comment every
10 s so a closed connection is noticed at that write, and no error keeps a place. With Valkey
each stream holds a slot there (a 90-second lease renewed while the stream sends), so the cap
counts across every process and a process that dies frees its slots when the leases run out;
without Valkey each process counts its own.

The poller reads for every user it serves, so its own reads run in an explicit system scope
(`portfolio_scope.system_scope`, every book); nothing reaches a connection before that
connection's own guard has applied its user's book scope (default deny under isolation),
licensed data scopes and the commercial boundary (a user who loses every commercial role has
the stream ended at the next re-check, 30 s). `tests/security/test_stream_book_scope.py` runs
two legal entities on one poller.

## The load test

`scripts/ops/load_test_desk.py` signs in N users (default 50) through the API, opens three tabs
each (each tab: the desk pages' reads, one page after another with a think time, and one live
stream held for the whole run) and reports, per route group, the 50th/95th/99th percentile
latency, errors (5xx, timeouts) and refusals (4xx), and for the streams the time to the first
event.

### On a scratch stack seeded with the demo seed

1. A scratch PostgreSQL: `docker run -d --name loadtest-pg -e POSTGRES_PASSWORD=... -p
   127.0.0.1:55701:5432 postgres:16 -c max_connections=200`.
2. Seed it as the demo image does, with 50 load accounts copying the demo trader:
   `EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS='[{"username":"load_u01","password":"...","as":"demo.trader"}, ...]'`
   and `DATABASE_URL`, `EUROGAS_NEXUS_SECRET_KEY`, `EUROGAS_NEXUS_DEV_LOGIN_PASSWORD`,
   `EUROGAS_NEXUS_DEMO_LIVE_SOURCES=off`, then `python scripts/demo/start_public_demo.py serve`
   (it migrates, seeds, creates the accounts, starts the simulated exchange feed and serves).
3. Run the API with the shape to measure (for 4 processes and Valkey:
   `UVICORN_WORKERS=4 EUROGAS_NEXUS_SHARED_CACHE_URL=valkey://...`).
4. `LOAD_TEST_PASSWORD=... python scripts/ops/load_test_desk.py --base-url http://127.0.0.1:8091
   --users 50 --tabs 3 --duration 120 --json-out result.json --label "..."`.

Never run it against a production server without the owner's approval.

### Results (2026-11-26)

**Read this first: the machine.** The runs were made on one development machine with 4 vCPU
and 15 GB, **shared with other work** (other test suites and databases ran at the same time:
the load average before the runs was 4 to 8 and reached 14 to 23 during them). The load
generator, PostgreSQL 16 (scratch container, demo seed, the simulated exchange feed writing
quotes every 1 to 5 s) and the API all ran on it. Numbers between runs are therefore noisy; read
the structural differences, not the second decimal. Each run: 50 users signed in through the
API, 3 tabs each (150 live streams, the three desk pages' 13 reads in turn with a 3 to 10 s
think time), 120 s, every user starting cold (no view computed for them yet).

| Run | Main reads answered | p50 ms | p95 ms | Main-read timeouts | Health answered | Health p50 / p95 ms | Streams opened / broken | Stream events | All answered / all failed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Before: code before this work (`6ecc1ed`), 1 process | 5 | 18,577 | 21,660 | 1,938 | 1 of 5 | - | 49 / 101 | 230 | 7 / 2,291 |
| After, 1 process, no Valkey | 14 | 23,539 | 29,108 | 1,925 | 98 | 112 / 802 | 76 / 74 | 4,711 | 113 / 2,273 |
| After, 4 processes + Valkey | 45 | 20,351 | 26,569 | 1,883 | 114 | 28 / 166 | 143 / 7 | 3,830 | 165 / 2,225 |
| Reference: 1 user, 1 tab, 1 process | 118 | 48 | 2,290 | 0 | 89 | 5 / 35 | 1 / 0 | 74 | 228 / 0 |
| Rerun 2026-11-26 after the security merge and the socket-timeout fix, 1 process, no Valkey | 7 | 16,467 | 29,945 | 1,936 | 83 | 153 / 1,663 | 61 / 89 | 3,702 | 91 / 2,285 |
| Rerun, same build, 4 processes + Valkey | 31 | 16,453 | 24,516 | 1,911 | 110 | 50 / 376 | 150 / 0 | 7,697 | 146 / 2,257 |

(An earlier pass, before credentials got their own threads, gave on 4 processes 42 main reads,
health 59 / 269 ms, 150 streams opened and none broken, 6,273 events; on 1 process 18 main
reads, health 61 / 651 ms, 89 / 61 streams. Timeouts are the client's 30 s limit.)

**The rerun (after the security merge and the 5-second socket fix).** Same procedure and seed,
with the security settings a production deployment has where the demo profile allows them:
book isolation on (the 50 load accounts copy the demo trader's scopes, so each sees its own
entity's books), dual control on, the production write and heavy quotas (GETs are not
counted), the 5-stream cap per person (counted in Valkey on the 4-process run), 30-minute idle
sessions. The demo profile itself requires the `development` environment, so the second factor
stays off (it would put every load account into enrolment). The machine was otherwise idle this
time: load average about 1 before each run; during the 1-process run it stayed between 0.3 and
1.8 (one process computes on one core), during the 4-process run it rose from 0.5 to 9.5 (the
four processes and PostgreSQL saturating 4 cores). Every failure in both runs is the load
client's own 30 s limit; **the server answered no 5xx at all**, and its counters show
0 statements cancelled (`eurogas_db_statement_timeouts_total`), 0 connections lost and 0 pool
timeouts (on 4 processes, 3,046 of 5,680 checkouts waited for a connection: requests the client
had abandoned kept computing and holding one). Before the fix a read over 5 s on the database
ended in a client-side `TimeoutError` (500, a 502 behind the gateway); here reads of 16 to 24 s
were answered. The 4-process run holds every stream (150 opened, none broken, 7,697 events) and
answers health in 50 ms median. Main reads stay bound by the per-person cold computation
described below, not by serving: 31 answered on 4 processes against 7 on one.

What the numbers show:

* **The event loop is no longer blocked.** Before, the health check answered once in two
  minutes and the streams delivered 230 events; after, health answers every second (28 ms
  median on 4 processes) and the streams deliver thousands of events. On 4 processes nearly
  every stream opens and stays open (143 of 150, 7 breaks, against 49 and 101 before).
* **The main reads are bound by computation, not by serving.** Every user starts cold, and
  seven of the desk's heavy reads are computed per person (they depend on the person's
  book-shared trades, mandates or saved hubs), at 2 to 5 s of CPU each even on an idle
  process (the reference row's p95); 50 people opening three pages at once ask for roughly
  1,500 CPU-seconds before the first answer is warm. Four shared cores cannot give that in two
  minutes, whatever the serving, and 4 processes answer three times as many main reads as
  before (45 against 5 to 14). Once a view is warm a read is answered in about 50 ms (the
  reference's median).
* **Target: not shown on this machine.** The plan's budget (p95 under 1 s on the main reads at
  50 x 3) assumes the production hardware of plan section 7.2: two application servers of
  8 vCPU each running 4 to 8 API processes (16 cores for the API alone, not shared), the job
  servers taking the close and risk runs, and a 16-core database with a read replica. It also
  assumes the desk is warm: the per-person heavy reads are what phase 2 records once per close
  run instead of computing on read (plan root cause 1). Until then, the first open of the day
  by each person costs seconds on any hardware. Repeat this test on the pilot or production
  hardware, after a warm-up (each user opening each page once), before signing the exit
  criterion; the two-server repetition the decision asks for needs two servers.
