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

## Opportunity invalidation v1

The scheduled ingestion path uses `IngestionInvalidationV1` from
`src/eurogas_nexus/streaming/contracts.py` when a mapped source run succeeds and
changes rows. Its payload is a data-free hint with `event_type` set to
`opportunity.input.invalidated`, `schema_version` set to 1, a source ID and run
ID, a named input class, and a UTC scheduler notice time. The pair
`(source_id, run_id)` identifies a notice regardless of delivery mechanism.
A notice cannot represent individual observation publication or delivery time.
The current consumer coalesces work by input class in PostgreSQL and retains
its existing full-evaluation debounce. No broker or durable event-level
deduplication is active. The existing `StreamingEnvelope` shell is unaffected.
