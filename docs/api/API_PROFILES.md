# API Profiles

Eurogas Nexus separates API routes by profile and package.

## Stable V1

Package: `src/eurogas_nexus/api/routes/public`

Purpose: stable public API routes intended for clients.

Current routes:

```text
GET /api/health
GET /api/health
```

Stable clients and SDKs should target `/api`. `/v1` remains available for
bootstrap compatibility.

## Internal

Package: `src/eurogas_nexus/api/routes/internal`

Purpose: future service-internal routes. These must be profile-gated and must
not expose business actions without authorization, audit, and governance
contracts.

Current prefix: `/api/internal`

## Development

Package: `src/eurogas_nexus/api/routes/dev`

Purpose: future development-only diagnostics. These must not be enabled in
release profile.

Current prefix: `/api/dev`

## Current Profiles

| Profile | Docs | OpenAPI | V1 | Internal | Dev |
| --- | --- | --- | --- | --- | --- |
| `development` | enabled | enabled | enabled | disabled | enabled |
| `internal` | disabled | disabled | enabled | enabled | disabled |
| `release` | disabled | disabled | enabled | disabled | disabled |

No DB connection, external API, secret, or live connector is required to import
the app.

## Milestone 1 Path Normalization

- Preferred stable prefix: `/api`.
- Bootstrap compatibility prefix: `/v1`.
- Internal prefix: `/api/internal`.
- Development prefix: `/api/dev`.
