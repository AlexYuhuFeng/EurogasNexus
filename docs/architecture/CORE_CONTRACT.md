# Core Contract

## Purpose

`src/eurogas_nexus/core` contains shared primitives that are safe for every
layer to import.

## Allowed

- Side-effect-free settings models.
- Common exception classes.
- Shared API response models.
- Small constants and type aliases.

## Forbidden

- Database engines, sessions, or migrations.
- HTTP clients that call external systems.
- Business workflow behavior.
- Domain calculations requiring market, asset, or route semantics.
- Secrets retrieval from remote providers.

## Current Shell

- `Settings.from_env()`
- `get_settings()`
- `EurogasNexusError`
- `ConfigurationError`
- `HealthResponse`

