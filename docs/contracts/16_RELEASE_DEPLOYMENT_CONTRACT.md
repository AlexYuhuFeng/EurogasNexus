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

## Rules

- Release artifacts must be reproducible from committed source.
- Deployment templates must not include secrets.
- Production defaults must avoid exposing development-only API surfaces.
- Release tests belong under `tests/release`.

## Bootstrap State

Only directories are present. No deployment runtime is implemented.

