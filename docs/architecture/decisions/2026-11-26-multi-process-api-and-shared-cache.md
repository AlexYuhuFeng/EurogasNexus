# DRAFT ADR: Several API processes, one live-update poller per process, and a shared cache

**Status:** DRAFT, awaiting owner review (2026-11-26). Proposed in
[ARCHITECTURE_V3_PLAN.md](../ARCHITECTURE_V3_PLAN.md) sections 3.6 and 3.10. On acceptance it is
appended to [ARCHITECTURE_DECISION_RECORD.md](../ARCHITECTURE_DECISION_RECORD.md). It adds one
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
