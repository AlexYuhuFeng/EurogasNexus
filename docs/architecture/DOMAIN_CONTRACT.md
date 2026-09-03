# Domain Contract

## Purpose

`src/eurogas_nexus/domain` owns pure domain concepts for Eurogas Nexus.

## Implemented Domain Areas

- `analysis`
- `constraints`
- `identity`
- `ingestion`
- `market`
- `market_intelligence`
- `monitoring`
- `observations`
- `ontology`
- `research`
- `route_cost`
- `strategy_lab`

Additional domain areas are added when their first implementation is created,
not as empty placeholder packages.

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

## Current State

Implemented domain packages contain pure logic and calculations. Empty
placeholder directories are intentionally removed from the source tree.
