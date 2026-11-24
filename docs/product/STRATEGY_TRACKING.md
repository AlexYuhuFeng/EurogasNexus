# Strategy tracking, the intraday path and the prompt market

Status: built 2026-11-19 (branch `strategy-audit`). Decision support only: nothing here places,
routes or nominates an order (AGENTS.md rule 8). Every fill is a paper fill on an order intent
that is never sent.

## 1. What existed before this change (measured on the demo stack)

| Question | Answer |
|---|---|
| How do quotes arrive? | Operator CSV import of the customer's own screen export (`scripts/ops/import_market_quotes.py`, `--watch N` re-imports a changed file every N seconds); the licensed connectors (EEX, ICE, Trayport) are manifest shells with no client (`implemented=False`); the demo seeds one board snapshot a day. No push API. |
| Cadence it accepts | One file import: 400 quotes in 2.2 s wall including process start; the import then runs the route-opportunity scan. |
| Does anything evaluate a strategy on a new quote? | No. Spreads backtested daily closes only; the old shadow runtime evaluates component strategies (`OCM_VS_DAY_AHEAD`, …) on a timer over persisted evidence, not on a quote and not on a StrategySpec. |
| What reaches the screen? | `GET /api/stream/quotes` (SSE) polls PostgreSQL every 1.5 s, 200 rows a poll per connection; the Prices board and monitoring poll every 10 s (`MARKET_REFRESH_INTERVAL_MS`); Today's age words tick every 60 s and the strip reads every 120/300 s. |
| Booked trades to position | ETRM extract by CLI (`scripts/ops/import_etrm_trades.py`), on demand; no schedule in the product. A loaded trade is in the position at the next read. |
| Market data beyond price | Quotes held bid/ask/last and top-of-book sizes only. No trade prints, VWAP, volume, OHLC, settlement or open interest. |

## 2. Decision: one store for tracks, the existing engines, no second runtime

- **Reuse assessed.** The shadow runtime (`application/shadow_runtime.py`, tables
  `strategy_shadow_*`) evaluates frozen strategy *versions* built from component types through the
  backtest engine's evidence pools on an interval schedule. A StrategySpec spread with a z-score
  or an intraday rule is not one of its component types; reusing it meant a new component in the
  backtest engine plus versioning/freezing a spec that changes in the workbench: a second engine
  in disguise.
- **Chosen.** A thin store, `strategy_tracks` and `strategy_track_events` (migration
  `0072_strategy_tracks_and_trades`), holding the StrategySpec, the rule and the paper book's
  state. Daily tracks re-run the *same* spread-history function the Spreads page uses
  (`application/spread_history.py`); intraday tracks run `domain/research/intraday_strategy.py`.
- **Old routers.** Nothing here depends on `strategy_registry`, `shadow`, `strategy_lab` or the
  backtest-experiment routers: the clean-up worker may defer all of them.
- **Permissions.** Reading needs `strategy.read`, saving or stopping `strategy.shadow.manage`
  (ANALYST and OPERATOR hold it; a persona grants nothing). A track is its owner's alone; its
  prices are read under the owner's current data scopes, and it pauses when the owner is no
  longer active. Delivering ticks needs `source.run` (OPERATOR floor).

## 3. The intraday path (seconds to minutes)

1. **Ingestion** `POST /api/market/ticks` (`application/market_ticks.py`): a licensed feed adapter
   (or the demo simulator) delivers a batch of quotes and trade prints; stored under the source
   family (`market_quotes` with the new session fields, `market_trades`). A licensed label
   (`EEX`, `ICE_OCM`, `Trayport`) is accepted only from a key whose data scopes name that
   family: issue the feed adapter its own key scoped to it; a `*` key is refused with
   `source_not_granted`. Every tick is checked before anything is stored, and one bad tick
   returns the whole batch with the reason (`ticks_invalid`): prices outside the plausible
   band for the hub's quotation and product (forward months may not go below zero), an
   exchange time more than two minutes after receipt, and a mid more than three times (or a
   third of) the previous quote for the instrument (`domain/market/feed.py`).
2. **Evaluation on arrival** in the same transaction through one hook,
   `application/market_inputs.notify_inputs_changed(session, instruments, *, at, replay=False)`;
   subscribers register with `subscribe_inputs_changed(name, handler)` where
   `handler(session, instruments: frozenset[str], at: datetime, replay: bool) -> dict`. Instrument
   keys are `"HUB|product"` (`"TTF|within-day"`). The tracked strategies subscribe as
   `strategy_tracks`; the prompt opportunity evaluators may subscribe the same way.
3. **Signal** (debounced per track): z-score of the spread mid on a rolling window (mean and
   deviation from earlier ticks only), reversion from the session VWAP, or a breakout of the
   window range; gated on two-sided quotes with size, quote age and a screen trade in the last N
   minutes. Each signal carries the instant computed, the age of each quote it used, the edge net
   of the spread crossed and an **actionable-until** time: the earlier of its time-to-live and
   the hub cut-off (WD: last renomination, three hours before the gas day ends; DA: the 13:00 UTC
   nomination deadline; network-code defaults, stated). A signal is shown only while actionable;
   at its cut-off, on a stale quote or a gated market it is withdrawn and logged as **missed**.
4. **Order intent and paper fill**: the signal writes an order intent (legs with instrument and
   side, size, limit, reason, checks passed, `sent: false`), the record a later order-ticket
   hand-off would carry; the paper fill takes the quote on the screen (buy at the offer, sell at
   the bid), limited to the quoted size, top of book only, plus stated slippage; no size, no fill.
   An open position is marked at the price it could be closed at; a contract change closes it at
   the old contract's last price.
5. **Advice**: the changed, still actionable signal appears on Today's "What needs me" as a
   sentence with entry level, bid/offer, edge and validity, ending "Not an instruction".
6. **Reads**: `GET /api/research/strategy-tracks[/{id}]` (state, intents, blotter, signals with
   missed ones, equity) and `GET /api/market/prompt` (live WD/DA screen with size, last, VWAP,
   volume, trades, settlement; the WD − DA spread; today's booked prompt trades against VWAP, the
   DA settlement and the mid at trade time, slippage against the touch, running day P&L, missed
   signals). Today's gas-day view (position to balance, deadlines, imbalance) is another worker's
   and calls `application/prompt_market.prompt_market` in-process.

## 4. Market data beyond price (licensed feeds)

`domain/market/feed.py` defines what a tick may carry and why a desk uses it: top of book with
sizes, last trade price and size, session open/high/low, VWAP, volume and number of trades
(screen prints only; block, OTC-cleared and auction prints are kept but not in the screen VWAP),
settlement and prior settlement, open interest (exchange futures; not spot WD/DA), trade type,
aggressor, venue and broker (Trayport), exchange and receipt time. Only what the customer's own
licensed feed delivers is stored, under that source family's entitlement; nothing is fetched,
inferred or redistributed (AGENTS.md rule 18). Used by: the VWAP-reversion rule and the liquidity
gates (no signal on a quote without size, or without a screen trade in N minutes), the size limit
of the paper fill, the prompt market read and post-trade performance.

## 5. Measurements (one API worker, demo stack, PostgreSQL 16 in a local container)

Throughput, one client posting batches as fast as it can, three active intraday tracks:

| batch | ticks/s | call p50 / p95 (ms) | evaluation latency p50 / p95 (ms) |
|---:|---:|---:|---:|
| 1 | 70 | 13 / 21 | 20 / 37 |
| 10 | 482 | 19 / 31 | 25 / 39 |
| 50 | 950 | 48 / 87 | 56 / 93 |
| 200 | 958 | 192 / 347 | 201 / 394 |
| 1000 | 1195 | 821 / 1170 | 822 / 1133 |

With no debounce (every tick evaluates all three tracks): 29 ticks/s at batch 1, 181 at batch 10;
one track evaluation costs about 10 ms (two quote reads, a last-trade read, the state write).

What breaks first: (1) per-track evaluation cost × tracks × un-debounced ticks (the state holds
up to 4000 window samples as JSON and is rewritten each evaluation); (2) row inserts at about
0.8 ms per tick beyond ~1000 ticks/s; (3) the browser sees a change at the next poll (2 s on the
prompt and track panels, 10 s on the board), so the screen, not the server, sets the latency.

A 20-minute real-time simulated session (bursty, batches every 250 ms, three tracks, a booked
trade every 45 s): 2 629 ticks, 1 210 evaluations; tick receipt → signal computed p50 31 ms, p95
67 ms; one evaluation p50 15 ms, p95 28 ms; ingestion call p50 77 ms, p95 205 ms.

To the screen (Playwright, Chromium, one API worker, Vite dev server):

| path | n | p50 | p95 | note |
|---|---:|---:|---:|---|
| tick posted → DA bid on Prices → Prompt | 20 | 1.42 s | 2.14 s (5.09 s on the first read after opening the view) | panel reads every 2 s |
| tick posted → signal line on Spreads → Track | 6 | 1.84 s | 1.90 s | panel reads every 2 s |

So "is it actionable": a signal is on screen within about two seconds of the tick and carries its
own validity (default five minutes, never past the hub's cut-off).

## 6. Capability statement for a WD/DA desk

- **Can**: accept a licensed feed's quotes and prints in batches at ~1000 ticks/s on one worker;
  evaluate tracked strategies within tens of milliseconds of a tick's arrival; show the live
  WD/DA screen with size, last, VWAP and volume, a signal with its validity and edge, the paper
  intent and fill, and the performance of booked trades against VWAP, settlement and decision mid.
- **Cannot**: send, route or manage an order; see the customer's order book or own fills unless
  the ETRM extract (or a future fill feed) delivers them; price imbalance without a connected
  cash-out source; react faster than the screen's poll (2 s) without a push to the client.
- **Needs** for more: the customer's own streaming licence through its entitlement and a feed
  adapter posting batches; a second API worker (or a dedicated ingestion worker on the same
  PostgreSQL) above ~1000 ticks/s; the quote SSE stream wired to the panels to remove the poll.

## 7. Daily backtest corrections (strategy audit)

See the commit "Spreads backtest: next-close execution, roll and delivery sizing…": execution at
the next close by default, roll moves of month and longer contracts excluded, P&L sized by the gas
days of the contract held, cost from the held bid/offer (else zero, stated), the rule reading the
net-of-tariff spread by gas year, an assumptions line, worst trade, drawdown, out-of-sample split
and a "too few trades" warning. Results change materially and on purpose; the audit table is in
the hand-back.

## 8. Interfaces agreed with other work

- **Inputs-changed hook** (for the prompt opportunity evaluators):
  `eurogas_nexus.application.market_inputs.subscribe_inputs_changed(name, handler)` with
  `handler(session, instruments: frozenset[str], at: datetime, replay: bool) -> dict`; raised by
  `notify_inputs_changed(session, instruments, *, at, replay=False)` from the tick ingestion,
  inside its transaction, each subscriber in a savepoint (one failing hides only itself).
- **Prompt market for Today**: `eurogas_nexus.application.prompt_market.prompt_market(session,
  caller, hub, *, now=None)` (and `GET /api/market/prompt`): live WD/DA quote with size, last
  trade, VWAP, volume, trades and age, the WD − DA spread and today's prompt performance.
- **Who writes today's WD/DA quotes in the demo**: the demo exchange feed while it runs
  (`EUROGAS_NEXUS_DEMO_EXCHANGE_FEED`, default on); the roll-forward's daily prompt snapshot
  should write only when it is off.
