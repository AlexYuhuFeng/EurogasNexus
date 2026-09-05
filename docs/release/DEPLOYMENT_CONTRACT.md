# Release Deployment Contract

## Purpose

Committed release and deployment source/configuration is organized under:

- `dist/releases/` (tracked release-output placeholder)
- `infra/docker`
- `infra/nginx`
- `infra/systemd`
- `infra/postgres`
- `infra/deployment`
- `docs/release`
- `docs/operations`
- `deploy/runtime`
- `scripts/install/windows`

Generated output is separate from committed source:

- `release-assets/` is the CI staging directory used to assemble GitHub Release
  assets;
- Tauri bundles are generated under
  `clients/desktop/src-tauri/target/release/bundle/`;
- `dist/releases/` receives locally generated release files while preserving its
  tracked `.gitkeep` placeholder.

## Rules

- Release artifacts must be reproducible from committed source.
- Deployment templates must not include secrets.
- Production defaults must avoid exposing development-only API surfaces.
- Release tests belong under `tests/release`.
- Customer delivery exposes two device roles: `Server` and `Client`.
- Client devices receive an HTTPS API URL, never PostgreSQL credentials.
- Server owns PostgreSQL, migrations, API, HTTPS gateway, and ingestion workers.
- Server owns the backend runtime. Client is separate and reaches Server through
  the configured HTTPS API.
- Deployment tooling detects Docker/Compose but never installs it silently.
- Simulated price ingestion is explicit and retains `_Sim` provenance.
- Every Release publishes a separate Client-only Windows NSIS asset and a Server
  operator ZIP asset.
- The Server operator ZIP contains deployment scripts, runtime configuration,
  and operating documentation. It is not a Server NSIS installer and does not
  embed the desktop Client or API image; the target Server supplies its approved
  Docker/Compose runtime and images.
- Server binds the API and PostgreSQL host ports to `127.0.0.1` only.
- Normal Server uninstall preserves its named PostgreSQL volume. Data deletion
  requires a separate explicit purge confirmation.

## Implemented State

The Client-only Windows NSIS packaging, Server operator ZIP packaging, and
containerized server runtime are implemented. The Server operator ZIP is an
operator toolkit, not an embedded desktop/API-image installer.
Enterprise signing, customer certificate issuance, firewall policy, offline
image import, backup scheduling, and managed upgrades remain operator-owned
release gates.
