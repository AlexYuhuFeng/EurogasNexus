# API Profiles

Eurogas Nexus separates API routes by profile and package.

## Stable Public API

Package: `src/eurogas_nexus/api/routes/public`

Purpose: stable public API routes intended for clients.

Current routes:

```text
GET /api/health
```

Stable clients and SDKs target `/api`. No versioned or bootstrap aliases are
exposed.

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

| Profile | Docs | OpenAPI | Public `/api` | Internal | Dev |
| --- | --- | --- | --- | --- | --- |
| `development` | enabled | enabled | enabled | disabled | enabled |
| `internal` | disabled | disabled | enabled | enabled | disabled |
| `release` | disabled | disabled | enabled | disabled | disabled |

No DB connection, external API, secret, or live connector is required to import
the app.

## Path Policy

- Preferred stable prefix: `/api`.
- Versioned and bootstrap aliases return `404`.
- Internal prefix: `/api/internal`.
- Development prefix: `/api/dev`.
