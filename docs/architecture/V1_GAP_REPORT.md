# V1 Gap Report

This report records known gaps instead of inventing behavior.

## PARTIAL: Product North-Star Alignment

Historical local Eurogas Nexus implementations clarify the long-term product
goal: a governed, map-centric European gas decision-support workspace served by
DB-first backend APIs. The current repository now documents that north star, but
it intentionally remains a backend-only V1 bootstrap.

Credential requirements: none.

Next action: follow `V1_STEPWISE_DELIVERY_ROADMAP.md` and do not import
historical frontend, desktop, connector, LLM, or local-file runtime behavior
into V1 without a scoped milestone.

## PARTIAL: Python Tooling Validation

The repository declares minimal Python dependencies, but validation depends on a
local environment with FastAPI, pytest, and Ruff installed.

Credential requirements: none.

Next action: install the project in a local virtual environment with
`pip install -e ".[dev]"`, then run the validation commands.

## PARTIAL: PostgreSQL Runtime

PostgreSQL is the runtime source of truth. The current repository has an
import-safe DB foundation and live validation policy, but no live runtime DB has
been validated in this worktree and no business-domain schemas are approved.

Credential requirements: operator-provided database URL through
`RUNTIME_STORE_DATABASE_URL`, `DATABASE_URL`, or legacy
`EUROGAS_NEXUS_DB_DSN`. Do not commit or print the URL.

Next action: harden the DB runtime boundary in Milestone 2 using
`docs/operations/LIVE_POSTGRESQL_V1.md` without adding business features.

## PARTIAL: External Data Sources

No live external API, vendor connector, LLM provider, or credentialed source is
implemented.

Credential requirements: future connector-specific credentials and entitlement
documents.

Next action: create connector contracts, mocks, fixture policy, and credential
requirements before any live adapter.

## PARTIAL: Analysis Output Schema

The required analysis-output metadata fields are documented, but no business
analysis output model is implemented.

Next action: create an analysis-output contract and tests when the first
research workflow is approved.

