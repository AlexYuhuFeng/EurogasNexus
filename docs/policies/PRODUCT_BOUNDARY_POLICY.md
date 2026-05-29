# Product Boundary Policy

Eurogas Nexus V1 is research-only decision support for European gas resource
analysis. It is not an execution, trading, legal, approval, nomination, or ETRM
system.

## Allowed In V1

- Backend API service shell.
- Future worker and scheduler boundaries.
- PostgreSQL-backed persistence once approved by a DB milestone.
- API-backed Python SDK. The SDK is required for V1 and expands through SDK
  milestones after API contracts exist.
- API-backed CLI once approved by CLI milestones.
- API-backed web workspace once approved by web milestones.
- API-backed Windows client shell once approved by Windows milestones.
- Research data ingestion and normalization once approved by ingestion
  milestones.
- Dry-run tests and fixture-based development.

## Not Allowed In V1

- Trade execution.
- Order entry.
- Order routing.
- Trade capture.
- Nomination submission.
- Official approval workflow.
- Legal advice.
- Official trading recommendation.
- Auto-trading.
- ETRM replacement behavior.
- Company SSO/OIDC.

## Phase Restrictions

Backend foundation milestones must not add frontend, desktop, Node, Rust, or
Tauri runtime dependencies.

Web and Windows runtime implementation is allowed only when the selected
milestone is a web or Windows client milestone. Those clients must consume
`/api/v1` and must not read PostgreSQL, backend local files, raw vendor data, or
credentials directly.

## Required Language For Future Analysis Outputs

Where relevant, analysis outputs must include:

- assumptions;
- missing inputs;
- warnings;
- source references;
- lineage;
- `research_only`;
- `human_review_required`.

