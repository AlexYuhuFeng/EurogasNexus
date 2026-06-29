# API Contract

## Purpose

`src/eurogas_nexus/api` owns the FastAPI app factory, route registration, route
profiles, route modules, API services, and dependency providers.

## Current Routes

- `GET /api/health`
- `GET /api/internal/health` in the internal profile only.
- `GET /api/dev/health` in the development profile only.

## Route Profiles

- `development`: stable public `/api` routes, `/api/dev` diagnostics,
  documentation, and OpenAPI exposure.
- `internal`: stable public `/api` routes plus `/api/internal` routes without
  documentation or OpenAPI exposure.
- `release`: stable public `/api` routes without documentation, OpenAPI, dev
  routes, or internal routes.
- Stable public, internal, and development-only routes must remain separated by
  package and route profile.

## Rules

- `apps.api.main` must expose `app`.
- API import must not require DB, network, or secrets access.
- Routes must delegate business orchestration to application services once
  those services exist.
- Development-only and internal routes must live under their route packages and
  be gated by route profiles.

## Forbidden Product Surfaces

- Trade execution and order routing endpoints.
- Nomination submission endpoints.
- Trade capture endpoints.
- Official approval endpoints.
- Legal advice or official recommendation endpoints.
- Live connector endpoints.

## Milestone 6 Additions

- Contract tests verify development profile exposes docs/openapi.
- Contract tests verify release profile hides docs/openapi.

## Path Policy

- Public client and SDK routes use `/api`.
- Hidden `/api/v1/*` and `/v1/health` compatibility rewrites may remain only
  for old health/bootstrap checks and must not be documented for customer use.
- Internal routes use `/api/internal`.
- Development routes use `/api/dev`.
- Route registration explicitly wires public/internal/dev package routers via
  profile flags.
- Contract tests verify release excludes dev/internal paths.
