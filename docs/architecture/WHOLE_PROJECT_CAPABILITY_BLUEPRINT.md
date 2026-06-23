# Whole Project Capability Blueprint

## Product Definition

Eurogas Nexus is an internal European gas research and decision-support system.
It connects market prices, physical flows, LNG/regas, storage, weather, asset
topology, capacity/contract context, cost assumptions, live source posture,
LLM-assisted market analysis, and strategy research outputs into one governed
backend-led product.

The product may produce research trading ideas, candidate rankings, explanations,
data gaps, and risk warnings. These are decision-support outputs for human
review. They are not official trading recommendations, order instructions,
nomination instructions, execution instructions, legal advice, or ETRM records.

## Source Of Truth

PostgreSQL is the runtime source of truth.

Clients, SDK, and CLI consume the backend API. They do not read PostgreSQL,
backend files, raw vendor data, or historical project files directly.

## Product Surfaces

Eurogas Nexus has five deliverable surfaces:

1. Backend/API service.
2. Python SDK.
3. CLI.
4. Web client.
5. Windows client.

Each surface has a separate implementation milestone path. Codex should
execute one surface milestone at a time.

## Capability Families

### Foundation And Governance

Purpose:

- make the repository safe for systematic DB-first development;
- keep secrets and real data out of the public repository;
- define import boundaries, route profiles, DB URL policy, migrations, and
  validation commands.

Primary docs:

- `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md`
- `docs/operations/LIVE_POSTGRESQL_V1.md`
- `docs/contracts/00_CONTRACT_INDEX.md`

### Runtime Store And Data Governance

Purpose:

- persist canonical runtime records in PostgreSQL;
- track source references, lineage, freshness, quality, entitlement, and audit
  metadata.

Required before real source data:

- runtime store repository contracts;
- Alembic migrations;
- no trial/release local-file fallback;
- entitlement/export policy;
- audit event model.

### Market-Physical-Commercial Relationship Mapping

Purpose:

- connect three layers without conflating them:
  - physical geometry;
  - commercial/operational topology;
  - market abstraction.

Rules:

- geometry does not prove commercial connectivity;
- topology does not prove tradable spread eligibility;
- market relevance requires explicit mapping and review;
- mappings carry confidence, source references, and eligibility flags.

Reference evidence:

- archived `THREE_LAYER_GRAPH.md`;
- historical map-centric client demo and QA reports.
- `docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md`;
- `docs/api/API_SURFACE_BLUEPRINT.md`;
- `docs/product/RESEARCH_WORKFLOW_BLUEPRINT.md`.

### Data Ingestion And Normalization

Purpose:

- bring external or manual source data into governed canonical forms.

Pipeline:

```text
connector -> raw archive -> normalization -> quality checks -> PostgreSQL -> API
```

Rules:

- connectors fetch only;
- normalizers transform;
- repositories persist;
- application/domain services analyze;
- live connectors require explicit credential, entitlement, and export review.

### Market, Flow, LNG, Storage, Weather, And Asset Context

Purpose:

- store and expose the source context required for research workflows.

Future datasets:

- market prices and spreads;
- ECB FX observations;
- EEX, Trayport, and ICE OCM venue/product context where licensed;
- FX and unit conversions;
- ENTSOG physical flows, capacity, outages, and interconnection context where
  permitted;
- LNG sendout and regas terminal context;
- GIE storage and LNG context where permitted;
- weather HDD/CDD and demand proxies;
- capacity contracts, route eligibility, and contract exposure context;
- asset topology and route/corridor metadata.

No real vendor/operator data should be committed. Synthetic fixtures are allowed
for tests and UI mocks.

### Path Cost And Indicative Netback

Purpose:

- evaluate route and delivery economics under explicit assumptions.

Route cost inputs:

- topology route candidate;
- route legs and direction;
- tariffs, fees, fuel, losses, regas/storage costs;
- volume and timing assumptions;
- compatibility flags.

Indicative netback inputs:

- market price context;
- FX and unit conversion;
- route cost result;
- resource/portfolio assumptions;
- source freshness and entitlement state.

Outputs:

- indicative result;
- cost stack;
- assumptions;
- missing inputs;
- warnings;
- source references;
- lineage;
- `research_only`;
- `human_review_required`.

### Feasibility And Allocation Scenario

Purpose:

- test whether candidate routes, volumes, timing, and resources are plausible
  under physical, commercial, and data-quality constraints.

Outputs:

- feasible, infeasible, or unknown status;
- blocking constraints;
- missing inputs;
- allocation candidates;
- sensitivity notes;
- source and quality warnings.

No nomination, booking, or official approval workflow is allowed.

### LLM-Assisted Market Analysis And Glossary

Purpose:

- explain market movements, route changes, weather signals, and conflicting
  data using structured backend context and cited source references.

Rules:

- LLM providers are never the source of truth;
- LLM routes consume backend snapshots and return cited explanations;
- outputs preserve assumptions, missing inputs, warnings, model/provider
  metadata, prompt/template version, `research_only`, and
  `human_review_required`;
- glossary terms are backend-served so SDK, CLI, web, and Windows clients share
  consistent definitions.

No LLM output may create official recommendations, orders, nominations,
execution instructions, legal advice, or uncited market claims.

### Monitoring, Alerts, And Anomaly Detection

Purpose:

- surface changes in market, flow, LNG, storage, weather, topology, and source
  health that matter to research workflows.

Outputs:

- alert events;
- anomaly candidates;
- data freshness warnings;
- source health status;
- affected scenarios or research outputs.

Alerts are research flags, not execution instructions.

### Weather-Adjusted Nowcast

Purpose:

- combine weather-demand context, supply context, market price context, and
  available netback artifacts into a near-term pressure view.

Outputs:

- demand pressure;
- supply tightness;
- price-pressure direction;
- confidence and missing-input state;
- source references and lineage.

This is not production forecasting and must be labeled as research-only.

### Strategy Backtest And Shadow Run

Purpose:

- evaluate research hypotheses against historical or observed states.

Backtest:

- uses historical canonical observations;
- records assumptions and evaluation metrics;
- does not call live sources during tests.

Shadow run:

- reads approved local/runtime observations;
- produces paper evaluation state;
- creates no orders, trades, nominations, or execution records.

Outputs:

- hypothesis ID;
- run mode;
- result metrics;
- warnings;
- source snapshots;
- human-review state.

### Research Brief And Reporting

Purpose:

- combine structured outputs into a human-review research brief.

Required statement:

```text
This report is a research decision-support output and not a trading
recommendation, order instruction, execution instruction, official approval, or
official risk decision.
```

Reports must preserve source references, lineage, assumptions, data gaps, and
warnings. Missing source data is not inferred.

## Delivery Principle

Build foundation first, then one narrow capability slice at a time:

1. DB/runtime foundation.
2. Runtime store and governance.
3. Reference network and relationship mapping.
4. Ingestion control plane.
5. Market/context observations.
6. Live-source posture, capacity/contract context, and weather signals.
7. Route cost.
8. Indicative netback.
9. Feasibility/allocation.
10. Monitoring/nowcast.
11. Strategy backtest/shadow run.
12. LLM-assisted analysis and glossary.
13. Reporting.
14. SDK/CLI expansion.
15. Web workspace.
16. Windows packaging.

Any milestone that lacks a DB impact, API impact, data policy, test plan,
validation command, and rollback note is not ready for runtime implementation.
