# Milestone 1 Remaining Gaps

## Runtime DB

- No live PostgreSQL runtime DSN was supplied or tested.
- Required table presence was tested through registry behavior, not a live
  deployed database.
- Alembic migration execution remains an operator action and was not run.

## Governance

- Security reporting channel details need repository-owner confirmation.
- Branch protection and required GitHub checks need repository settings outside
  the codebase.

## API

- `/v1/health` compatibility remains in place. Future removal needs a release
  milestone and client migration notice.
- Other future SDK and CLI routes must continue to use `/api/v1` for stable
  APIs.

## Auth, Audit, and Entitlement

- Vendor entitlement and export policy remain contract-only.
- Auth/audit runtime enforcement is deferred.

## Data and Business Domains

- No business domain features were added.
- No live connectors, external APIs, market data providers, or LLM providers
  were called.

## Review Flags

- `research_only`: true
- `human_review_required`: true
