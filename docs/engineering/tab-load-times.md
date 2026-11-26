# Tab load times: first open, before and after

What a main tab waits for the first time it is opened after sign-in, why, and what changed.
Measured 2026-11-26 on the shared 4-CPU development host.

## Method

- **Server**: one uvicorn worker per build, started from the worktree (`scripts/demo/start_public_demo.py`
  environment, no seeding, no migrations). Main builds read the shared demo database (Alembic 0076); the
  innovation builds read a private copy upgraded to 0086.
- **Harness** (HTTP, emulating the browser: 6 connections per origin). Sign in, run the sign-in batch the web
  client sends (about 32 reads), then open each of 14 main tabs in turn: issue that tab's first-open reads
  concurrently and record the tab's wall time (when its last read answered). Then a second pass over the tabs
  (revisit). Tab read lists come from a static inventory of each tab's `api.*` reads on mount.
- **Warm-up step** (innovation "after" only, and also run in the "before" so the two see the same requests):
  after the sign-in batch, the reads in `clients/web/src/app/data/warmUpSteps.ts` one at a time, as the web
  client does while idle; then the tabs.
- **Before/after on the same host load**: each pair ran back to back (main: base commit `a471bc2` against the
  fixes; innovation: the same build with `EUROGAS_NEXUS_WARM_VIEWS=off` against on). The host carried other
  agents' work (load average 9 to 19 on 4 CPUs), so single numbers move by tens of percent between runs;
  compare within a pair.
- **No browser**: a headless browser could not be installed here, so time-to-content in the page itself is
  not measured; the server time of the reads a tab waits for is.

## Causes found

1. Every heavy first-screen read is recomputed on every request; nothing on the server keeps a result.
   desk/today, forward balance, the spreads board, instruments, the report catalogue and the risk reads each
   took 1.5 to 11 s alone and 10 to 45 s with three users signing in at once, past the client's 10 s timeout.
2. Forward balance: the seasonal normal scanned the whole history for every forecast day (O(days × history)).
3. Date and timestamp columns decoded through pg8000's `strptime` path: about 1 s per 60 000 rows.
4. The report catalogue probed every section separately, repeating the same closes reads (5 daily-row reads,
   3 ladder-input reads).
5. The web client asks for a tab's reads only when the tab mounts, so the first open always waits for the
   computation.

## What changed

**Main branch** (`fix/tab-warm`, these areas are untouched by the innovation branch):

- The seasonal normal reads its days from a day-of-year index (same rule, same result; equivalence test).
- pg8000 connections decode DATE, TIMESTAMP and TIMESTAMPTZ with `fromisoformat` (7.7 µs to 0.23 µs a value),
  falling back to pg8000's converters.
- The catalogue's section probe runs under one book scope and one shared closes read.

**On top of innovation** (`fix/tab-warm-on-innovation`, cut from `innovation/continuous-commercial-intelligence`
at `85d59f1`):

- `application/warm_views.py`: heavy reads answer from the last good result computed for the same reader
  (the whole principal), database, UTC day and parameters. A new `market_events` outbox seq, or a write by the
  same principal (`api/middleware/warm_views.py`), makes it stale: the next read gets it at once marked
  `refreshing`, and one background refresh recomputes it in a copy of the first request's context (so alert and
  book scope are the same reader's). A failed refresh keeps the last good result. Results older than
  `max_stale` (10 minutes) are never served. Licensed-use families are noted on every serve.
- Every kept answer carries `meta.view = {state, computed_at_utc, max_age_seconds}`. The web names kept figures
  in the top bar ("Figures from 09:41, updating") while any answer on screen is being recomputed, and Today
  re-reads quietly a few seconds later to swap in the fresh figures. Kept figures never show without their time.
- After sign-in the web asks for the heavy reads of the user's tabs one at a time while idle, filtered by the
  user's permissions, so the first open of a tab finds them kept.
- Conditional reads ignore `meta.view`, so the map's revalidations still get 304.
- Market-context and review-context projections (whose monitoring slice follows `alert_visibility`) are not
  kept at all; desk/today's alert slices are kept per whole principal and refreshed as that principal.

## Main branch: per tab (ms, single user)

| Tab | Before, first open | After, first open | Before, revisit | After, revisit |
|---|---:|---:|---:|---:|
| desk.today | 9238 | 5851 | 9302 | 3707 |
| desk.prices | 3910 | 1219 | 2957 | 1558 |
| desk.network | 6239 | 4148 | 7642 | 3375 |
| deals.opportunities | 147 | 130 | 129 | 57 |
| deals.contracts | 1311 | 1141 | 1168 | 539 |
| deals.review | 84 | 128 | 100 | 43 |
| book.position | 6791 | 3755 | 7560 | 3080 |
| book.limits | 3355 | 2176 | 2976 | 1660 |
| book.delivery | 1461 | 684 | 1847 | 320 |
| book.planning | 27 | 55 | 74 | 30 |
| research.fundamentals | 11326 | 9053 | 13658 | 5276 |
| research.spreads | 7186 | 5356 | 6408 | 3420 |
| research.cargo | 50 | 54 | 59 | 78 |
| research.reports | 11397 | 4397 | 33 | 48 |

Key reads, serial, three calls each (ms):

| Read | Before | After |
|---|---|---|
| desk/today | 6963, 6259, 4962 | 5657, 2486, 3729 |
| reports/catalogue | 11751, 15, 16 | 6154, 10, 14 |
| fundamentals/forward-balance | 5349, 5460, 5349 | 2879, 2525, 2344 |
| research/spreads/board | 4176, 5385, 5101 | 3374, 2655, 2477 |

## Innovation branch: per tab (ms, single user, after the idle warm-up)

| Tab | Before, first open | After, first open | Before, revisit | After, revisit |
|---|---:|---:|---:|---:|
| desk.today | 11242 | 1914 | 11913 | 427 |
| desk.prices | 4473 | 361 | 7488 | 95 |
| desk.network | 9294 | 3913 | 10026 | 108 |
| deals.opportunities | 138 | 1629 | 216 | 98 |
| deals.contracts | 1582 | 415 | 2638 | 69 |
| deals.review | 82 | 715 | 89 | 92 |
| book.position | 7045 | 506 | 10733 | 98 |
| book.limits | 6673 | 336 | 5254 | 115 |
| book.delivery | 2914 | 201 | 2910 | 96 |
| book.planning | 101 | 261 | 57 | 50 |
| research.fundamentals | 19189 | 1388 | 16958 | 206 |
| research.spreads | 13720 | 382 | 13322 | 158 |
| research.cargo | 100 | 246 | 105 | 90 |
| research.reports | 130 | 164 | 15961 | 58 |

The small tabs (opportunities, review, planning, cargo) read nothing heavy; their after numbers moved with host
load. desk.network was measured before the map's picture joined the warm-up. research.reports' "before" first
open was answered by the catalogue's own short-lived cache, which the warm-up had just filled; its revisit shows
the uncached cost.

Key reads at first open (ms; a read some tabs share is listed once per tab):

| Read | Before | After |
|---|---|---|
| desk/today | 11240, 9284, 7043 | 1520, 567, 421 |
| reports/catalogue | 121 (cached by warm-up), 15961 on revisit | 160 |
| fundamentals/forward-balance | 19179 | 427 |
| research/spreads/board | 13718 | 381 |

## Innovation branch: three users signing in at once

demo.trader, demo.risk and demo.manager signed in together, each running the warm-up and then the tabs.

| | Warm views off | Warm views on |
|---|---:|---:|
| Reads measured | 306 | 306 |
| Reads over the 10 s client timeout | 60 | 0 |
| Slowest read | 44975 ms | 4190 ms |
| desk/today, first open | 16410 to 41954 ms | 635 to 1818 ms |
| reports/catalogue, first open | 38236 to 42324 ms | 149 to 652 ms |
| fundamentals/forward-balance, first open | 16935 to 24032 ms | 382 to 766 ms |
| research/spreads/board, first open (demo.trader) | 19774 ms | 437 ms |
| desk.today tab | 23363 to 26331 ms | 889 to 2092 ms |
| research.fundamentals tab | 16939 to 24051 ms | 1050 to 1466 ms |

(demo.risk and demo.manager get 403 on the spreads board with either setting.)

## Limits

- Kept results live in the process: with several workers each keeps its own, and a restart starts cold.
- The warm-up adds about 20 sequential reads per sign-in; it runs only while the browser is idle and visible,
  and stops on sign-out.
- A kept result can be up to `max_age` old (60 to 300 s by view) while it is labelled fresh; a write that
  reaches the database without the outbox or this API is seen only when that age runs out.
