# DRAFT ADR: A feed-handler process for licensed live prices; two price sets

**Status:** DRAFT, awaiting owner review (2026-11-26). Proposed in
[ARCHITECTURE_V3_PLAN.md](../ARCHITECTURE_V3_PLAN.md) section 3.3. Prepared now, to be accepted on
the day a licensed live feed is contracted for a customer. It adds one process (a new service in
the sense of AGENTS.md rule 5); it keeps Decisions 6 (connectors fetch, they do not analyse),
20, 28 and 31.

**Context.** Every licensed connector (Trayport, EEX, ICE, Platts, Kpler, ICIS, Argus) is a
manifest with `implemented=False` (`domain/connectors/builtin/`). Licensed prices arrive as CSV
exports of a trader's screen (`ingestion/licensed_quote_import.py`) or through
`POST /api/market/ticks`, which an operator, or the holder of the static token, can call under an
exchange's name (security finding H4). Tick ingestion (`application/market_ticks.py`) runs a
duplicate check, one "previous price" query per instrument and the opportunity evaluation in the
same transaction, and refuses a whole batch for one implausible tick. Rows are about 888 bytes
with JSON metadata. A real Trayport or ICE feed sends thousands of top-of-book updates a second
across hundreds of instruments; the capacity study sizes scenario C at 3,000 to 5,000 rows a
second in bursts. One price resolver serves live screens and valuation alike, so a 10:20 tick
became the "close" behind a day's figure (middle-office review).

**Decision.**

1. **One feed-handler process** per installation (two if the vendor licenses two sessions), in
   the market-data network zone, reaching only the vendor or the customer's market-data
   platform and the database. It is a Python process in this repository, sharing the domain
   package; no business logic beyond checking and thinning.
2. **Vendor adapters** behind one interface (subscribe, receive, map to an instrument, report
   session state). First adapter: Trayport, or the customer's market-data platform (for
   example LSEG or Bloomberg) if the pilot customer has one. EEX and ICE Endex end-of-day
   settlements arrive earlier by file through the import contracts, not through this process.
3. **Per tick**: map to an instrument and price type; check plausibility against the last value
   in memory; drop and log a bad tick (never the batch); update the in-memory last value.
4. **Thinning**: every second, write changed last values to a `latest_prices` table (one row per
   instrument and price type, upserted) and `NOTIFY`; every minute, append one-minute bars
   (open, high, low, close, volume) to history. Every tick is kept only if the customer's
   non-display licence allows it and the TimescaleDB option is turned on (Decision 39).
5. **Identity**: the process authenticates as a service identity bound to the licensed
   families it may write. People cannot write licensed families; `POST /api/market/ticks`
   refuses them.
6. **Evaluation moves off the write path**: opportunity and strategy re-evaluation runs as an
   outbox consumer (Decision 28) on the one-second snapshots, not inside the tick transaction.
7. **Two price sets, never mixed**: the *live* set (latest valid price, for screens and
   what-ifs) and the *official* set (settlement, or the firm's policy snapshot at a stated time,
   for the close and every recorded figure). The resolver reports which set and which price type
   it used.
8. **Usage**: every read of a licensed family keeps going through the per-request meter
   (Decision 31); the feed handler adds the session and subscription counts the vendor's monthly
   declaration needs.

**Alternatives.** (a) Calling vendor APIs from the API process: blocks it and mixes concerns.
(b) A broker (Kafka) between the vendor and the store: one consumer only; thinned updates are a
few per second per instrument. (c) Storing every tick in PostgreSQL: licence and volume cost
without a use for a decision-support screen. (d) A compiled service (Rust, Java): not needed
until measured: the trigger is sustained updates above about 2,000 a second or a 99th-percentile
per-tick handling time above 50 ms in Python, and then only the checking step moves to a Rust
extension.

**Consequences.** One more process and server to operate, in its own network zone. Licensed
prices reach screens within about a second. The direct tick endpoint becomes a narrow,
service-only path. A recorded vendor session is needed for tests, since CI cannot reach a vendor.

**Migration.** (1) Settlement import by file and the `settlement_prices` table (plan phase 2).
(2) `latest_prices` and the live/official split in the resolver, fed by the existing tick
endpoint restricted to a service identity. (3) The process with one adapter, against a recorded
session. (4) Evaluation as a consumer. (5) The CSV screen-export import stays for customers
without a feed.

**Tests that make it observable.** Replay of a recorded session at the vendor's peak rate with
p99 under 50 ms per tick; a bad tick dropped without losing the batch; a human principal refused
on a licensed family; a close that never reads the live set.
