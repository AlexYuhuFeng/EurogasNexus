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
