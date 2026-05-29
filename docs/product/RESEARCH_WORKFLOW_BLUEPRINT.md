# Research Workflow Blueprint

## Purpose

This document defines the research workflow semantics for Eurogas Nexus. It
translates the product ambition into safe, buildable backend slices.

## Output Language

Allowed:

- research idea;
- candidate;
- ranking;
- scenario;
- indicative result;
- data gap;
- risk warning;
- human review required.

Forbidden:

- official trading recommendation;
- order;
- execution instruction;
- nomination instruction;
- trade capture;
- approval;
- legal advice;
- auto-trading.

## Common Workflow Envelope

Every workflow output must include:

- input summary;
- assumptions;
- missing inputs;
- warnings;
- source references;
- lineage;
- freshness;
- data quality;
- entitlement/export state;
- `research_only: true`;
- `human_review_required: true`.

## Workflow 1: Relationship Mapping

Question:

- how do physical assets, operational topology, and market abstractions relate?

Inputs:

- physical geometry records;
- topology nodes/edges;
- market hubs/areas;
- explicit mapping records.

Outputs:

- display-eligible relationships;
- strategy/research-eligible relationships;
- confidence;
- rejected/unreviewed mappings;
- warnings.

## Workflow 2: Route Cost

Question:

- what is the indicative cost stack for a route candidate?

Inputs:

- route candidate;
- route legs;
- cost components;
- tariff references;
- unit/FX assumptions;
- timing and volume.

Outputs:

- segment-level cost breakdown;
- total indicative route cost if compatible;
- incompatible or missing components;
- assumptions and warnings.

## Workflow 3: Indicative Netback

Question:

- under explicit assumptions, what indicative netback does a candidate produce?

Inputs:

- market price context;
- route cost result;
- resource/contract assumptions;
- FX/unit conversion;
- source freshness state.

Outputs:

- indicative netback;
- sensitivity notes;
- missing price/cost/source inputs;
- warnings and lineage.

## Workflow 4: Feasibility

Question:

- is the scenario plausible under known physical, commercial, and data-quality
  constraints?

Outputs:

- feasible, infeasible, or unknown;
- blocking constraints;
- missing inputs;
- warnings;
- source references.

Unknown is a valid result when data is insufficient.

## Workflow 5: Allocation Scenario

Question:

- how could available resources be allocated across candidate markets or routes
  for research comparison?

Outputs:

- allocation candidates;
- rationale;
- constraints;
- unallocated volume;
- missing inputs and warnings.

No booking, nomination, or execution action is created.

## Workflow 6: Monitoring And Alerts

Question:

- what changed in market, physical, source, weather, or topology context that
  deserves research review?

Outputs:

- research alerts;
- anomaly candidates;
- affected scenarios;
- source/freshness warnings.

Alerts are not trade signals.

## Workflow 7: Weather-Adjusted Nowcast

Question:

- what near-term demand, supply, and price-pressure state is implied by current
  weather and market/physical context?

Outputs:

- demand pressure;
- supply tightness;
- price-pressure direction;
- confidence;
- missing inputs and warnings.

This is not production forecasting.

## Workflow 7A: Live Market Movement Analysis

Question:

- what changed across price, FX, flow, capacity, LNG, storage, weather, and
  source posture, and why might it matter for research?

Inputs:

- structured backend observations from approved sources;
- source/freshness/quality/entitlement metadata;
- route and capacity/contract context where relevant;
- optional LLM analysis provider configured through backend only.

Outputs:

- market movement summary;
- cited source references;
- conflicting signal notes;
- missing inputs;
- route or market areas affected;
- research-only explanation;
- no official recommendation.

## Workflow 8: Strategy Backtest

Question:

- how did a research hypothesis behave over historical canonical observations?

Outputs:

- hypothesis performance metrics;
- input window;
- assumptions;
- missing data periods;
- warnings.

## Workflow 9: Shadow Run

Question:

- how does a research hypothesis behave in paper mode over approved observed
  state?

Outputs:

- paper state;
- candidate actions for review;
- warnings;
- source snapshots.

Shadow run creates no orders, trades, nominations, execution records, or official
recommendations.

## Workflow 9A: Glossary And Explanation

Question:

- what does a gas, LNG, storage, venue, capacity, route economics, weather, or
  data-governance term mean in this product context?

Outputs:

- term definition;
- category;
- related terms;
- reviewed timestamp;
- source/reference note where applicable.

## Workflow 10: Research Brief

Question:

- what should a human reviewer know from the latest structured outputs?

Outputs:

- key findings;
- ranked research candidates;
- data gaps;
- risk warnings;
- source references;
- lineage;
- required disclaimer.

Required disclaimer:

```text
This report is a research decision-support output and not a trading
recommendation, order instruction, execution instruction, official approval, or
official risk decision.
```

## Implementation Rule

Each workflow must be implemented as:

```text
API route -> application workflow -> domain logic -> runtime store -> DB
```

SDK, CLI, web, and Windows clients call the API. They must not call domain logic
or runtime stores directly.
