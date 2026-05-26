# V1 Gap Report

This report records known gaps instead of inventing behavior.

## PARTIAL: Python Tooling Validation

The repository declares minimal Python dependencies, but validation depends on a
local environment with FastAPI, pytest, and Ruff installed.

Credential requirements: none.

Next action: install the project in a local virtual environment with
`pip install -e ".[dev]"`, then run the validation commands.

## PARTIAL: PostgreSQL Runtime

PostgreSQL is the intended runtime source of truth, but no DB configuration,
engine, session, models, repositories, or migrations are implemented in this
bootstrap milestone.

Credential requirements: future database URL or deployment secret reference.

Next action: create a dedicated DB foundation ExecPlan before adding runtime DB
code.

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

