# Runtime Store Contract

## Purpose

`src/eurogas_nexus/runtime_store` is reserved for future ephemeral runtime state
such as locks, caches, short-lived coordination records, and service heartbeat
metadata.

## Bootstrap State

No runtime store implementation is present.

## Rules

- Runtime store usage must be optional at app import.
- No Redis or distributed cache dependency is allowed in this bootstrap.
- Store interfaces must be declared before adapters are introduced.
- Runtime state must never be treated as the system of record.

## Milestone 13 Additions

- Added import-safe `RuntimeStore` protocol and `HeartbeatRecord` shell types.
- Added unit tests to enforce optional/ephemeral runtime-store contract usage.
