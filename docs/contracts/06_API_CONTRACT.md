# API Contract

## Purpose

`src/eurogas_nexus/api` owns the FastAPI app factory, route registration, route
profiles, route modules, API services, and dependency providers.

## Current Routes

- `GET /v1/health`

## Route Profiles

- `development`: public V1 routes plus documentation and OpenAPI exposure.
- `release`: public V1 routes without documentation or OpenAPI exposure.
- Stable V1, internal, and development-only routes must remain separated by
  package and profile.

## Rules

- `apps.api.main` must expose `app`.
- API import must not require DB, network, or secrets access.
- Routes must delegate business orchestration to application services once
  those services exist.
- Development-only and internal routes must live under their route packages and
  be gated by route profiles.

## Forbidden In Bootstrap

- Trade execution and order routing endpoints.
- Nomination submission endpoints.
- Trade capture endpoints.
- Official approval endpoints.
- Legal advice or official recommendation endpoints.
- Live connector endpoints.


## Milestone 6 Additions

- Contract tests verify development profile exposes docs/openapi.
- Contract tests verify release profile hides docs/openapi.


## Milestone 14 Additions

- Route registration explicitly wires v1/internal/dev package routers via profile flags.
- Contract tests verify release excludes dev/internal paths and development currently exposes no dev/internal endpoints until added intentionally.
