# Product Boundary Policy

Eurogas Nexus V1 is research-only decision support for European gas resource
analysis. It is not an execution, trading, legal, approval, nomination, or ETRM
system.

## Allowed In V1

- Backend API service shell.
- Future worker and scheduler boundaries.
- PostgreSQL-backed persistence once approved by a DB milestone.
- API-backed Python SDK and CLI once approved by SDK/CLI milestones.
- Research data ingestion and normalization once approved by ingestion
  milestones.
- Dry-run tests and fixture-based development.

## Not Allowed In V1 Without Explicit Scope Change

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
- Frontend or desktop implementation.

## Required Language For Future Analysis Outputs

Where relevant, analysis outputs must include:

- assumptions;
- missing inputs;
- warnings;
- source references;
- lineage;
- `research_only`;
- `human_review_required`.

