# Release Deployment Contract

## Purpose

Release and deployment assets are organized under:

- `release/v1`
- `dist/releases`
- `infra/docker`
- `infra/nginx`
- `infra/systemd`
- `infra/postgres`
- `infra/deployment`
- `docs/release`
- `docs/operations`
- `deploy/runtime`
- `scripts/install/windows`

## Rules

- Release artifacts must be reproducible from committed source.
- Deployment templates must not include secrets.
- Production defaults must avoid exposing development-only API surfaces.
- Release tests belong under `tests/release`.
- Customer delivery exposes exactly three device roles: `Server`, `Client`, and
  `AllInOne`.
- Client devices receive an HTTPS API URL, never PostgreSQL credentials.
- Server and AllInOne roles own PostgreSQL, migrations, API, HTTPS gateway, and
  ingestion workers.
- Deployment tooling detects Docker/Compose but never installs it silently.
- Simulated price ingestion is explicit and retains `_Sim` provenance.

## Implemented State

The Windows role bootstrapper and containerized server runtime are implemented.
Enterprise signing, customer certificate issuance, firewall policy, offline
image import, backup scheduling, and managed upgrades remain operator-owned
release gates.

