# API Path Policy

## Decision

The preferred stable API prefix is `/api`.

SDKs, CLIs, Web, Windows, Linux, and customer integrations must target `/api`.
Version numbers are not part of the current public URL surface.

## Route Families

| Route family | Prefix | Audience |
| --- | --- | --- |
| Stable public API | `/api` | SDK, CLI, Web, Windows, Linux, and customer integrations |
| Hidden legacy compatibility | `/api/v1`, `/v1/health` | Existing bootstrap checks only; not documented for customer use |
| Internal | `/api/internal` | Profile-gated service/operator routes |
| Development | `/api/dev` | Development-only diagnostics |

## Rules

- Public docs, SDKs, clients, tests, and examples must use `/api`.
- Add new stable public routes under `/api`.
- Internal routes must be registered only in the `internal` profile.
- Development routes must be registered only in the `development` profile.
- Release profile must not expose internal or development routes.
- SDK and CLI code should call backend API paths, not internal domain modules.

## Hidden Compatibility

The app factory rewrites legacy `/api/v1/*` requests to `/api/*` and
`/v1/health` to `/api/health`. This compatibility is intentionally hidden from
OpenAPI and customer-facing documentation.
