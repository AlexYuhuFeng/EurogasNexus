# Streaming Kafka Contract

## Purpose

`src/eurogas_nexus/streaming` is reserved for future streaming contracts.

## Bootstrap State

Kafka is optional and a planned boundary only. No Kafka dependency, broker
configuration, consumer, producer, schema registry, or background streaming
service is present. Streaming must never be the runtime source of truth.

## Future Rules

- Message contracts must be documented before producers or consumers are added.
- Streaming code must be optional for API import.
- Consumer side effects must be idempotent.
- Replay and dead-letter behavior must be specified before production use.

## Forbidden In Bootstrap

- Kafka client libraries.
- Background consumers.
- Live producers.
- Broker-specific configuration.

## Milestone 12 Additions

- Added dependency-free `StreamingEnvelope` shell type for future optional streaming integration.
- Contract tests enforce no Kafka dependencies and preserve non-authoritative streaming policy.

## Market event outbox (2026-11-24)

Market events are delivered from PostgreSQL by a transactional outbox, not by a broker:
see [Decision 28](ARCHITECTURE_DECISION_RECORD.md#decision-28-market-events-go-through-a-postgresql-transactional-outbox-not-a-broker).
The bootstrap rules above still hold. The outbox already meets the "future rules": the event
contract is documented, consumers are idempotent per delivery row, and replay and
dead-letter behaviour are specified and tested. A broker would be an optional relay fed
from the outbox, never the source of truth.

## Market change v1 (CODEX-1, 2026-11-25)

`MarketChangeV1` in `src/eurogas_nexus/streaming/contracts.py` is the versioned,
transport-neutral form of one market change. It adds no broker, consumer, producer or
dependency. The source of truth stays the PostgreSQL outbox (ADR Decision 28); clients outside
the monolith read it through the DATA-1 change feed (`GET /api/market/changes`).

- **Fields.** Exactly the change feed's digest columns without the feed cursor: event id and
  key, type, operation, revision, superseded event, subject, source, input class, dependency
  keys, content hash and the market, published and ingested times (UTC). Never a value:
  extra fields are refused, so a price or a contract term cannot ride along.
- **Dispatch metadata.** `kind` (`market.change`) and `schema_version` (1) travel in the value.
  A consumer decodes a named version and refuses any other.
- **Key.** `event_key`, the event's identity across revisions, so every revision of one fact
  lands in one partition in order; `(event_key, revision)` deduplicates a redelivery.
- **Tests.** `tests/streaming/test_market_change_contract.py` builds envelopes from the real
  outbox and feed and holds the envelope's fields equal to the feed's columns.

The research branch proposed a run-level `opportunity.input.invalidated` notice
(`IngestionInvalidationV1`) wired into the scheduler. It is not built: the outbox already
records each ingestion run that changed rows as a `source.ingested` event (identity
`run:<run_id>`, source, input class) with revisions, replay and dead letters, and the
scheduler's pending input classes stay as they are. A broker remains subject to the revisit
conditions of
[15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md](../engineering/Commercial-Intelligence-V3/15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md)
section 4 and an ADR.
