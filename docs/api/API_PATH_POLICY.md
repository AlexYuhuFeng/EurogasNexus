# API Path Policy

## Decision

The preferred stable API prefix is `/api/v1`.

Bootstrap compatibility may preserve `/v1` while clients migrate. SDKs, CLIs,
and new clients should target `/api/v1`.

## Route Families

| Route family | Prefix | Audience |
| --- | --- | --- |
| Stable V1 | `/api/v1` | SDK, CLI, and stable backend clients |
| Bootstrap compatibility | `/v1` | Existing bootstrap checks only |
| Internal | `/api/internal` | Profile-gated service/operator routes |
| Development | `/api/dev` | Development-only diagnostics |

## Rules

- Do not remove `/v1/health` during Milestone 1.
- Add new stable V1 routes under `/api/v1`.
- Internal routes must be registered only in the `internal` profile.
- Development routes must be registered only in the `development` profile.
- Release profile must not expose internal or development routes.
- SDK and CLI code should call backend API paths, not internal domain modules.

## Current Compatibility Alias

`GET /api/v1/health` is an alias for the existing `GET /v1/health` health
handler. This is low risk because it does not change response shape, dependency
requirements, or runtime DB behavior.
