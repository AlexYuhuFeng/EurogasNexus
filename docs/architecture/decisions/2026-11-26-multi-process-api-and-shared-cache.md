# ADR: Several API processes, one live-update poller per process, and a shared cache

**Status:** Accepted 2026-11-26 (owner). Implemented on branch `p1-A` (phase 1, work package
P1-A); see "Implementation" below. Proposed in
[ARCHITECTURE_V3_PLAN.md](../ARCHITECTURE_V3_PLAN.md) sections 3.6 and 3.10. On acceptance it is
appended to [ARCHITECTURE_DECISION_RECORD.md](../ARCHITECTURE_DECISION_RECORD.md) (Decision 40). It adds one
small component (Valkey); it keeps Decision 28 (outbox, no broker).

**Context.** The API runs as one uvicorn process (`deploy/runtime/Dockerfile.api`; the demo pins
`--workers 1`). 376 of 381 route handlers are synchronous and share one thread pool. Each open
live-update stream runs synchronous database queries inside an `async` generator every poll
interval (`api/routes/public/streaming.py`, lines 92 to 164), which blocks the event loop for
every user. With a handful of concurrent reviewers the demo measured 4 to 6 seconds mean per
route group, 1.5 seconds on `/api/health`, 11 of 12 pool connections in use and 502 errors after
20 seconds (technology review, gap 1). Warm views (`application/warm_views.py`), the rate limiter
(`security/rate_limit.py`) and HTTP metrics live in process memory, so a second process would
recompute every view, enforce limits per process and report partial metrics. That is the
measured need AGENTS.md rule 5 asks for.

**Decision.**

1. **Live updates**: each API process runs one background poller per topic, woken early by
   PostgreSQL `LISTEN/NOTIFY` and authoritative by polling (as Decision 28 already states for
   workers). It reads new rows once, applies the per-caller entitlement filter in memory and fans
   them out to that process's open streams. All database work runs in a worker thread, never on
   the event loop. Streams per person are capped.
2. **Several processes**: the API runs 4 to 8 processes per server and at least two servers in
   production behind the customer's load balancer. No sticky sessions are required.
3. **Shared cache: Valkey** (BSD-3-Clause, the community fork of Redis 7.2), replicated, for
   (a) warm views, keyed by the view and the caller's scope rather than the principal where the
   scope is the same, (b) per-principal rate limits and concurrency caps, (c) session revocation
   and the SSE ticket store. A single-process installation (development, demo) keeps the
   in-memory implementation behind the same interface, so Valkey is optional there.
4. **Not Redis 7.4 or later** (its licence is refused by the dependency policy), and no other
   use of Valkey (it is not a message bus or a store of record; losing it loses only cached
   work).
5. **Driver**: `pg8000` stays for now (BSD). psycopg 3 is LGPL, which
   `scripts/ci/audit_dependencies.py` refuses. After the serving fix, a profile decides: if the
   driver exceeds 30 % of request time on the main reads, take a reviewed licence exception for
   psycopg 3 (as was done for `r-efi`), or move the hot read paths to asyncpg (Apache-2.0).

**Alternatives.** (a) Sticky sessions and per-process caches only: four to eight recomputations
of each warm view, limits that a user escapes by reconnecting, and partial metrics. (b) PostgreSQL
as the cache (unlogged tables) and rate limiter: adds write load to the one component the whole
product depends on, and three pieces of bespoke code. (c) A message broker for fan-out: not
needed, since each process polls once. (d) An asynchronous rewrite of all 376 handlers: a large
change with no gain where the thread pool suffices.

**Consequences.** One more small service to operate (two 2-vCPU, 8-GB instances, or co-located on
the application servers). The serving fix itself is independent of Valkey and comes first.
Metrics become per-process and are aggregated by the scraper (see the operations section of the
plan).

**Migration.** (1) Shared poller and off-loop database work in one process, measured. (2) Cache
and limiter behind an interface with an in-memory implementation (no behaviour change). (3) Valkey
implementation, switched by configuration. (4) Several processes, load test, then several
servers.

**Measured acceptance.** A load test of 50 users with three tabs each, including live streams,
meets a 95th-percentile budget of 1 second on the main reads and keeps the event loop's lag under
100 ms; repeated with two servers and Valkey on.

## Implementation (2026-11-26, phase 1 work package P1-A)

What was built, against the decision's points:

1. **Live updates.** `api/stream_hub.py`: one poller thread per API process. Each poll opens
   one session, lets every open stream say what it needs, reads each source once from the
   oldest cursor any stream holds (`application/live_topics.Reads`: newest-first notice
   sources, oldest-first row streams, the outbox, jobs, revocation notes), and lets each stream
   take the rows after its own cursor and apply its own caller's rule in memory. The caller's
   books are read once per poll per distinct caller. Events reach each connection through an
   in-memory queue owned by its event loop; a stream that falls 200 batches behind is ended
   (it resumes from its last event id). Streams per person: one cap,
   `EUROGAS_NEXUS_MAX_STREAMS_PER_PRINCIPAL` (from the security review; 8 since the web client
   holds one stream per tab, 2026-11-26), counted across
   processes through the shared cache (expiring slots), 429 past it. The stream's entitlement now takes the firm-level test and the
   opportunity read rule from the caller's own scopes, not from the request context a poller
   thread does not have. **Not built: the `LISTEN/NOTIFY` early wake.** The driver (pg8000)
   delivers a notification only on a round trip, so waking early would need its own
   sub-second query loop on a dedicated connection, costing what the 1.5 s poll already costs;
   polling stays authoritative and is the only mechanism. Revisit if the poll interval must
   drop below a second.
2. **No database work on the event loop.** Identity resolution (keys, sessions, OIDC key
   fetches, gateway directory sync, failure audits), contract intake, import validation,
   entitlement denial audits and the lifespan's sweep and disposal run in threads; credentials
   on their own two threads so they never queue behind busy request threads;
   `/api/health` and `/api/health/live` answer on the loop. `tests/contract/
   test_no_blocking_db_on_event_loop.py` scans every `async def` under `api/`.
3. **Several processes.** `UVICORN_WORKERS` (default 1); `deploy/runtime/compose.scale.yaml`
   runs 4 with a Valkey; the preflight refuses more than one process without a shared cache.
   The schedulers, the market-events listener and the monitoring worker were already separate
   services; the API process starts none of them (only per-process helpers: the stream poller
   and the warm views' keeper).
4. **Shared cache.** `core/shared_cache.py`: `MemoryCache` (default) and `ValkeyCache`
   (`EUROGAS_NEXUS_SHARED_CACHE_URL`), a fast failure for 2 s after an outage. Used for (b) the
   sign-in and administration rate limits and the per-address sign-in throttle (each process
   counts for itself while Valkey is down) and (c) session revocation notes read by open streams
   every poll. The database remains the authority on sessions: every request re-reads its
   session row, and a stream now also re-reads its session every `REAUTH_SECONDS`, so a cache
   that is down delays the end of a revoked stream to at most 30 s and never lets a revoked
   request through; the decision did not ask for a refusal when the cache is down, and none is
   made. There is no separate SSE ticket store in this codebase (streams authenticate with the
   session like every other request). For (a) warm views: the **write signal** is shared (a write
   through any process makes every process's entries due and the writer's own unservable; with
   the signal unreadable a process drops what it holds and computes every read), and nine
   audited reader-independent views are kept **by scope rather than by person**
   (`ViewSpec(shared_by_scope=True)`); the seven views that read per-person state (saved hubs,
   mandates, strategy-shared trades, per-section availability) stay per person. **Not built:
   the views' values in Valkey** (each process still computes its own copy, so 4 processes may
   compute a view 4 times); it needs a serialisation of every view's payload and was not needed
   for correctness.
5. **Driver.** pg8000 stays; no profile has yet shown it above 30 % of request time.

Pool sizing per process (`db/session.py`, `docs/operations/API_SERVING_AND_SHARED_CACHE.md`):
processes x (pool + overflow) + workers + 5 <= `max_connections` - 3; request threads = pool +
overflow - 5; API statements time out after 30 s (`EUROGAS_NEXUS_DB_STATEMENT_TIMEOUT_MS`,
workers unaffected); pool checkouts, waits, timeouts and wait time, and the poller's counters,
are `prometheus_client` counters in the shared multi-process directory (P1-C's
`application/process_metrics.py`), so `/metrics` and `/api/runtime/metrics` return the sum over
the processes.

New runtime dependency: `valkey` 6.2.0 (valkey-py, MIT, pure Python), with `async-timeout`
5.0.1 (Apache-2.0) on Python below 3.11.3 only; hash-pinned in `requirements-runtime.lock` and
`requirements.lock` by `uv pip compile` without `--upgrade` (no other pin moved);
`THIRD_PARTY_NOTICES.md` regenerated; licence line in `docs/legal/DEPENDENCY_LICENSE_REVIEW.md`.

Measured acceptance: see the results in
[API_SERVING_AND_SHARED_CACHE.md](../../operations/API_SERVING_AND_SHARED_CACHE.md#results-2026-11-26).
The two-server repetition was not run (one machine).
