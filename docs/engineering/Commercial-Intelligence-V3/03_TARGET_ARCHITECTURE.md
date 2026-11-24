# 03 Target architecture

The platform stays a modular monolith on PostgreSQL and FastAPI (ADR Decisions 2 and 4;
AGENTS.md rule 5). A message broker, Kubernetes or a service split comes only with an ADR
and a measured need. This page separates what exists on the branch from what is planned.

## The continuous loop

```text
 source publishes ──► ingestion run / importer / desk entry ──► market event (outbox row)
                                                         │
                                       pg_notify at commit (wake-up only)
                                                         ▼
                      worker claims due deliveries (priority, FOR UPDATE SKIP LOCKED)
                                                         │
             ┌───────────────────────────┬───────────────┴────────────┬──────────────────────┐
             ▼                           ▼                            ▼                      ▼
  opportunity impact (built)   staleness / alerts (M6)    realised value (M9)     digital twin rebalance (later)
  re-run only the evaluators   from outbox lag and        outcome ledger          capacity net of outages
  whose opportunities depend   dead letters
  on the event's keys
```

## Components

| Component | State | Where |
| --- | --- | --- |
| Canonical event model (identity, content hash, revision decision, timeline, priority) | Built | `src/eurogas_nexus/domain/market_events/` |
| Outbox tables `market_events`, `market_event_deliveries` | Built | `alembic/versions/0077_market_event_outbox.py`, `db/models/market_events.py` |
| Publish, process, drain, replay, status, staleness, timeline | Built | `src/eurogas_nexus/application/market_events.py` |
| Producers: ingestion runs, firm marks | Built | `scripts/ops/run_dataops_scheduler.py`, `api/routes/public/assumptions.py` |
| Consumer: opportunity impact (targeted re-evaluation) | Built | `OpportunityImpactConsumer` in `application/market_events.py` |
| Producers: settlements, FX fixings, REMIT messages (change capture over the store) | Built (M5) | `src/eurogas_nexus/application/market_event_capture.py`, scheduler, `scripts/ops/import_settlements.py`, `scripts/ops/import_fx_fixings.py` |
| FX cross reach (a EUR fixing reaches stored cross pairs) | Built (M5) | `_fx_crosses` in `application/market_events.py` |
| Operations CLI (status, staleness, timeline, capture, drain, replay, listen) | Built | `scripts/ops/market_events.py` |
| Producers: contract and assumption edits | Planned (M5b) | contract and assumption services |
| Consumer: monitoring alerts from staleness and dead letters | Planned (M6) | monitoring worker |
| New engine to alerts and stream; legacy engine retired | Planned (M7) | notifications, `/api/stream/opportunities` |
| Outcome ledger | Planned (M9) | new tables, ADR first |

## Delivery guarantees

- **At least once, idempotent per row.** A delivery is one row per consumer and event; its
  status moves pending -> processed, or failed -> (retry) -> processed, or dead after five
  attempts. A consumer's writes run in a savepoint, so a failure leaves nothing behind.
- **Ordering.** Within a consumer, due deliveries are taken by priority (outages first,
  then contract, limit and mark changes, then prices, tariffs and capacity, then the rest)
  and by sequence. Order across priorities is not promised.
- **Supersession.** A new revision marks the undelivered rows of the previous one
  `superseded`, so a consumer never works on a figure that has already been corrected.
- **Replay.** Re-arms or creates deliveries for the current revision of each matching event
  (by sequence, time or id). Replaying twice gives the same result.
- **Concurrency.** Two workers never claim the same delivery (skip-locked, tested on
  PostgreSQL). Two publishers racing on one event write it once (unique key and a retried
  savepoint, tested on PostgreSQL).
- **Wake-up.** `LISTEN/NOTIFY` on channel `market_events` only shortens latency; the
  scheduler's drain after each cycle is the guarantee.

## Scaling limits and when to revisit

The outbox serves one PostgreSQL primary. Revisit (with an ADR) if sustained publication
passes what one primary handles with headroom, if events must cross installations (the
UK primary and China installation of Decision 22), or if an external party must subscribe.
A broker would then be fed from the outbox, which stays the source of truth.

## Boundaries that do not change

Decision support only (Decision 11): no consumer places an order, nominates or settles.
Outputs are proposals, alerts and signed handoff packages.
