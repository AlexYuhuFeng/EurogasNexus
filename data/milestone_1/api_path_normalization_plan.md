# Milestone 1 API Path Normalization Plan

## Decision

Use `/api/v1` as the preferred stable API prefix. Keep `/v1` as a bootstrap
compatibility prefix while repository and client contracts stabilize.

## Current Implementation

- `GET /v1/health` remains available.
- `GET /api/v1/health` is added as a low-risk alias using the same handler and
  response model.
- Internal route profile paths use `/api/internal`.
- Development route profile paths use `/api/dev`.

## Client Guidance

SDK and CLI code should target `/api/v1` for stable routes. New tests and docs
should prefer `/api/v1`, while compatibility tests continue to cover
`/v1/health`.

## Migration Steps

1. Preserve `/v1/health` through the V1 bootstrap phase.
2. Add any new stable routes only under `/api/v1`.
3. Update SDK/CLI clients to use `/api/v1`.
4. Document any future `/v1` deprecation in a release milestone before removal.

## Risks

- Duplicate health paths may appear in OpenAPI during development profile.
  This is acceptable for Milestone 1 because the alias preserves behavior and
  release profile hides OpenAPI.
- Existing scripts that call `/v1/health` remain compatible.

## Acceptance

Both `/v1/health` and `/api/v1/health` return the same health payload without
requiring a DB URL, external API, or live connector.
