# release/v1

V1 release blueprint documents live here.

## Current Scope

This directory is documentation-only until a release milestone activates it.

Full V1 release authority:

- `docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md`
- `docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md`
- `docs/release/V1_RELEASE_MILESTONE_BACKLOG.md`
- `docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md`
- `docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md`

## V1 Release Gate

A V1 release candidate must prove:

- every required backend, SDK, CLI, web, and Windows row in the acceptance
  matrix is complete or explicitly accepted as partial;
- app import works without DB connection side effects;
- live PostgreSQL validation is documented and operator-invoked;
- `/api/v1` client routes are stable for the released scope;
- `/api/internal` and `/api/dev` routes are profile-gated;
- SDK and CLI consume the API rather than internal modules;
- no secrets, raw vendor data, internal commercial data, contracts, or strategy
  parameters are included;
- research outputs include assumptions, missing inputs, warnings, source
  references, lineage, `research_only`, and `human_review_required` where
  relevant.

## Release Non-goals

V1 release does not include trade execution, order entry, order routing, trade
capture, nomination submission, official approvals, legal advice, official
trading recommendations, auto-trading, or ETRM replacement behavior.
