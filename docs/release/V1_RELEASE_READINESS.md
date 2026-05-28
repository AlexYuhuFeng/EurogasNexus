# V1 Release Readiness

This bootstrap is not a production release. It creates the structure needed for
future release work.

## Required Before Release

- Dependency review completed.
- DB foundation milestone completed. (DONE — M2)
- Release profile validated.
- No development-only routes enabled in release profile.
- No silent local file fallback in trial or release mode.
- Entitlement/export policy fail-closed behavior tested.
- Security and contract tests passing.

## Current Status

`PARTIAL`: repository structure, policy documents, and DB foundation exist.
Local PostgreSQL is available via Docker Compose with migrations applied.
Runtime release packaging, deployment templates, auth, audit, and governance
enforcement are deferred.

## Rollback

This bootstrap can be rolled back by removing structural files and directories.
No runtime data migration is required.



## Validated Gates (Current)

- Release API profile disables docs/openapi endpoints (contract-tested).
- Required release-policy statements are present in this readiness document.
- DB foundation: import-safe engine/session factories, Alembic scaffolding,
  local PostgreSQL via Docker Compose.

## Still Deferred

- Runtime release packaging automation.
- Auth/audit/governance enforcement runtime.
- Deployment templates and rollout playbooks.
- CI/CD pipeline with Dockerized PostgreSQL test containers.
