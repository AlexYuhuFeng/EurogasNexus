# clients

Future user-facing API consumers live here.

## Components

- `web/`: future browser workspace.
- `desktop/`: future Windows client package.
- Python SDK lives under `src/eurogas_nexus/sdk` now and later
  `packages/python-sdk`.
- CLI lives under `src/eurogas_nexus/cli`.

## Rule

Clients consume `/api/v1`. They must not read PostgreSQL, backend local files,
raw vendor data, or credentials directly.

Backend implementation comes first. Start client coding only when the user
explicitly selects the web or Windows phase.

## Design Docs

Read before adding client code:

- `docs/clients/README.md`
- `docs/clients/CLIENT_DELIVERY_MILESTONES.md`
- `docs/clients/CLIENT_API_CONTRACT.md`
- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`
- `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`
- `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
