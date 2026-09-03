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
