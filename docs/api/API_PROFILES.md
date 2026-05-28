# API Profiles

Eurogas Nexus separates API routes by profile and package.

## Stable V1

Package: `src/eurogas_nexus/api/routes/v1`

Purpose: stable public API routes intended for clients.

Current route:

```text
GET /v1/health
```

## Internal

Package: `src/eurogas_nexus/api/routes/internal`

Purpose: future service-internal routes. These must be profile-gated and must
not expose business actions without authorization, audit, and governance
contracts.

## Development

Package: `src/eurogas_nexus/api/routes/dev`

Purpose: future development-only diagnostics. These must not be enabled in
release profile.

## Current Profiles

| Profile | Docs | OpenAPI | V1 | Internal | Dev |
| --- | --- | --- | --- | --- | --- |
| `development` | enabled | enabled | enabled | disabled | enabled |
| `internal` | disabled | disabled | enabled | enabled | disabled |
| `release` | disabled | disabled | enabled | disabled | disabled |

No DB connection, external API, secret, or live connector is required to import
the app.



## Milestone 14 Note

Internal/dev routers are explicitly registered behind profile flags. They currently define no endpoints, so no `/internal/*` or `/dev/*` paths are exposed yet.
