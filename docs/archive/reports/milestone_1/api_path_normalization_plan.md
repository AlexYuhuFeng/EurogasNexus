# Milestone 1 API Path Normalization Plan

## Decision

Use `/api` as the preferred stable API prefix. Keep `/v1` as a bootstrap
compatibility prefix while repository and client contracts stabilize.

## Current Implementation

- `GET /api/health` remains available.
- `GET /api/health` is added as a low-risk alias using the same handler and
  response model.
- Internal route profile paths use `/api/internal`.
- Development route profile paths use `/api/dev`.

## Client Guidance

SDK and CLI code should target `/api` for stable routes. New tests and docs
should prefer `/api`, while compatibility tests continue to cover
`/api/health`.

## Migration Steps

1. Preserve `/api/health` through the V1 bootstrap phase.
2. Add any new stable routes only under `/api`.
3. Update SDK/CLI clients to use `/api`.
4. Document any future `/v1` deprecation in a release milestone before removal.

## Risks

- Duplicate health paths may appear in OpenAPI during development profile.
  This is acceptable for Milestone 1 because the alias preserves behavior and
  release profile hides OpenAPI.
- Existing scripts that call `/api/health` remain compatible.

## Acceptance

Both `/api/health` and `/api/health` return the same health payload without
requiring a DB URL, external API, or live connector.
