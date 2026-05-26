# Domain Contract

## Purpose

`src/eurogas_nexus/domain` owns pure domain concepts for Eurogas Nexus.

## Domain Areas

- `market`
- `operations`
- `relationships`
- `topology`
- `assets`
- `economics`
- `route_cost`
- `netback`
- `feasibility`
- `allocation`
- `resources`
- `strategy_lab`
- `weather`
- `nowcast`
- `monitoring`
- `reporting`

## Rules

- Domain code must be deterministic and side-effect free unless a contract says
  otherwise.
- Domain code must not import FastAPI, SQLAlchemy sessions, HTTP clients, live
  connectors, or app entrypoints.
- Domain models must distinguish internal analysis from official trading
  recommendations.
- Analysis outputs must include assumptions, missing inputs, warnings, source
  references, lineage, `research_only`, and `human_review_required` where
  relevant.

## Bootstrap State

Only package boundaries are created. No business logic is implemented.
