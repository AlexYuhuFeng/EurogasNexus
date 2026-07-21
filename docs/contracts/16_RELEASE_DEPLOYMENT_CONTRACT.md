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
- Server owns PostgreSQL, migrations, API, HTTPS gateway, and ingestion workers.
- AllInOne owns a loopback-only PostgreSQL/API runtime and desktop Client on one
  Windows evaluation workstation.
- Deployment tooling detects Docker/Compose but never installs it silently.
- Simulated price ingestion is explicit and retains `_Sim` provenance.
- Every Release publishes separate, unambiguous Windows assets for `Client-only`
  and `AllInOne` installation.
- The AllInOne NSIS package embeds the desktop Client and API image. It requires
  Docker Compose v2 but does not require a source checkout, Python, Node.js,
  Rust, Git, a local PostgreSQL installation, or a TLS certificate.
- AllInOne binds the API and PostgreSQL host ports to `127.0.0.1` only.
- Normal AllInOne uninstall preserves its named PostgreSQL volume. Data deletion
  requires a separate explicit purge confirmation.

## Implemented State

The Windows role bootstrapper, containerized server runtime, and one-click
AllInOne NSIS packaging are implemented.
Enterprise signing, customer certificate issuance, firewall policy, offline
image import, backup scheduling, and managed upgrades remain operator-owned
release gates.

