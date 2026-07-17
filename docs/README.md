# Documentation Index

Mandarin companion: [README-CN.md](README-CN.md)

This index separates current implementation authority from historical plans.
Start with the first section for active development; do not treat every
blueprint or completed ExecPlan as an instruction to implement it again.

## Current status and queue

1. [Current pause point](architecture/CURRENT_PAUSE_POINT.md)
2. [Next development queue](architecture/NEXT_DEVELOPMENT_QUEUE.md)
3. [Project north star](architecture/PROJECT_NORTH_STAR.md)
4. [Production readiness backlog](release/PRODUCTION_READINESS_BACKLOG.md)

## Architecture and contracts

- [Target product architecture](architecture/TARGET_PRODUCT_ARCHITECTURE.md)
- [API contract](contracts/06_API_CONTRACT.md)
- [Database contract](contracts/04_DB_CONTRACT.md)
- [Runtime-store contract](contracts/05_RUNTIME_STORE_CONTRACT.md)
- [SDK and CLI contract](contracts/15_SDK_CLI_CONTRACT.md)
- [Resource-pool contract EN](contracts/21_RESOURCE_POOL_CONTRACT-EN.md)
- [Resource-pool contract CN](contracts/21_RESOURCE_POOL_CONTRACT-CN.md)

## Clients

- [Client documentation index](clients/README.md)
- [Web application architecture EN](clients/WEB_APPLICATION_ARCHITECTURE-EN.md)
- [Web application architecture CN](clients/WEB_APPLICATION_ARCHITECTURE-CN.md)
- [Workspace navigation](clients/WORKSPACE_NAVIGATION_SPEC.md)
- [UI/UX style guide EN](clients/UI_UX_STYLE_GUIDE-EN.md)
- [UI/UX style guide CN](clients/UI_UX_STYLE_GUIDE-CN.md)

## Operations and deployment

- [Local development](operations/LOCAL_DEVELOPMENT.md)
- [Validation](operations/VALIDATION.md)
- [Live PostgreSQL](operations/LIVE_POSTGRESQL.md)
- [Deployment roles EN](deployment/DEPLOYMENT_ROLES-EN.md)
- [Deployment roles CN](deployment/DEPLOYMENT_ROLES-CN.md)
- [Release readiness](release/RELEASE_READINESS.md)

## Document status rule

- `contracts/`, current architecture policies, and current operations guides
  are normative.
- `*-EN.md` and `*-CN.md` are language companions and must describe the same
  behavior.
- `.agent/plans/` records scoped implementation decisions and completion
  evidence; completed plans are historical.
- Files named `BLUEPRINT`, `REFERENCE`, or `AUDIT` provide context unless a
  current queue item explicitly activates them.
