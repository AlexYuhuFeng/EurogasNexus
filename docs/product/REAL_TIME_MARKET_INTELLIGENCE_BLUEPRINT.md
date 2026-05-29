# Real-Time Market Intelligence Blueprint

## Purpose

This document defines the V1 target for map-focused live market intelligence,
capacity/contract context, strategy shadow runs, weather signals, glossary, and
LLM-assisted analysis.

It is implementation guidance for backend, SDK, web, and Windows milestones.
It does not authorize unmanaged live connector calls, credential leakage, or
automated trading.

## Product Intent

Eurogas Nexus should help a human gas analyst see where European gas market
conditions are changing and which route/resource candidates deserve review.

The primary experience is a map-first workspace:

```text
live sources -> ingestion/governance -> PostgreSQL -> /api/v1 -> SDK/API clients -> map workspace
```

The map must show infrastructure, contracts/capacity, market prices, physical
flows, LNG, storage, weather, route options, warnings, and research candidates
in one coherent visual workflow.

## Required Live Source Families

V1 should support connector contracts and, where credentials/entitlements are
provided, live or near-real-time ingestion for:

- ECB: FX reference rates and currency context.
- ENTSOG: transparency data for flows, capacity, nominations-related public
  context where permitted, outages, and interconnection points.
- GIE: AGSI/ALSI storage and LNG context.
- EEX: exchange market products, prices, curves, and settlement/reference
  context where licensed.
- Trayport: venue/market data context where licensed and technically available.
- ICE OCM: within-day/OCM market context where licensed and technically
  available.
- Weather providers: temperatures, forecasts, HDD/CDD, demand proxies, and
  forecast deltas.

Internet required: yes for current external API documentation, credentials,
entitlement review, live endpoint verification, package/license checks, and live
connector smoke tests.

Fallback if offline: implement connector interfaces, source registry records,
schemas, mocked transports, synthetic fixtures, entitlement gap reports, and
client states. Do not call live sources or claim live readiness.

## Connector Rules

Connectors fetch only. They do not analyze, rank, recommend, or calculate route
economics.

Each connector must declare:

- source system;
- dataset/product;
- entitlement scope;
- credential requirements;
- polling or request mode;
- freshness expectation;
- raw retention policy;
- normalization target;
- data-quality checks;
- failure modes;
- export restrictions.

Credentials must be operator-provided and never committed. Unknown commercial
entitlement fails closed.

## Capacity And Contract Management

V1 client workflows must represent capacity and contract context without
becoming an ETRM, order-entry, nomination, or trade-capture system.

Allowed:

- capacity contract inventory for research and operational context;
- booked/available capacity metadata;
- route eligibility and tenor/expiry context;
- tariff, fee, fuel, loss, regas, storage, and transport cost assumptions;
- contract exposure views linked to routes and assets;
- alerts for expiring or constrained capacity;
- scenario use of contract/capacity assumptions.

Forbidden:

- official booking;
- nomination submission;
- order entry;
- trade capture;
- official approval workflow;
- settlement or ETRM record creation.

## Map Intelligence Requirements

The web and Windows clients must make the map the primary decision surface.

Map layers:

- hubs and market areas;
- pipelines, corridors, interconnectors, and route legs;
- LNG terminals and regas capacity;
- storage sites and stock/injection/withdrawal indicators;
- beach delivery points;
- flow, capacity, outage, and constraint overlays;
- price, spread, FX, and venue/product overlays;
- weather/HDD/CDD and demand-pressure overlays;
- contract/capacity exposure overlays;
- research route candidates and warning states.

Route option display:

- show candidate route geometry or corridor sequence;
- show market/source/destination pair;
- show cost stack and indicative netback where available;
- show missing inputs and stale data warnings;
- show source references and entitlement state;
- show `research_only` and `human_review_required`;
- never show an order, nomination, or execution instruction.

## Research Trading Ideas

The product may surface:

- research trading ideas;
- candidate route rankings;
- spread movement explanations;
- route economics;
- congestion and bottleneck warnings;
- candidate actions for human review in shadow-run mode.

Use this language in UI and API:

- `research_candidate`;
- `candidate_ranking`;
- `research_signal`;
- `candidate_action_for_review`;
- `human_review_required`.

Do not use this language for released outputs:

- official recommendation;
- execute;
- place order;
- submit nomination;
- approve trade;
- book trade;
- guaranteed profit.

## Strategy Shadow Run

V1 must support strategy shadow run as paper evaluation.

Inputs:

- strategy hypothesis;
- source/product universe;
- route/capacity constraints;
- risk and missing-input rules;
- observation window;
- market/physical/weather context.

Outputs:

- paper state;
- candidate actions for review;
- hypothetical PnL or score where supported by licensed data;
- route and source snapshots;
- missed/blocked candidate reasons;
- warning stack;
- no orders, trades, nominations, or execution records.

## Weather Signals

Weather requirements:

- HDD/CDD by relevant market area;
- forecast delta versus normal and prior runs;
- temperature anomaly;
- demand-pressure proxy;
- weather-to-market mapping;
- confidence and missing-input status.

Weather outputs must remain research-only and carry source/freshness metadata.

## LLM-Assisted Analysis Layer

V1 may include an LLM-assisted analysis layer for explanation and synthesis, not
for source-of-truth data or autonomous decisions.

Allowed LLM tasks:

- summarize market movements from structured backend data;
- explain why a route or spread changed;
- draft research brief language from cited data;
- generate glossary explanations;
- identify missing inputs and conflicting signals;
- produce analyst questions for human review.

Forbidden LLM tasks:

- create official trading recommendations;
- decide orders, nominations, or execution;
- call live market sources directly;
- bypass entitlement/export policy;
- hide missing inputs or uncertainty;
- generate uncited market claims.

LLM outputs must include:

- structured input snapshot ID;
- citations/source references from backend data;
- assumptions;
- missing inputs;
- warnings;
- model/provider identifier when available;
- prompt/template version;
- `research_only: true`;
- `human_review_required: true`.

Internet required: yes for live LLM provider use and current provider
documentation. Offline fallback: implement provider interface, prompt templates,
mock responses, tests, and gap report. Do not call an LLM provider.

## Glossary

V1 must include a glossary surface for gas, LNG, storage, trading venue,
capacity, route economics, weather, and data-governance terms.

Glossary entries should be backend-served so SDK, CLI, web, and Windows clients
use consistent definitions.

Fields:

- term;
- category;
- short definition;
- detailed explanation;
- related terms;
- source/reference note where applicable;
- last reviewed timestamp;
- review status.

## Client Requirements

Web:

- map-first workspace;
- live source posture and warnings visible;
- contract/capacity overlay;
- route option comparison;
- strategy shadow-run review;
- weather signal panel;
- LLM analysis panel with citations;
- glossary drawer.

Windows:

- package or launch the same map-first web workspace;
- configurable backend URL;
- no local secrets;
- no direct connector calls;
- no direct DB access;
- desktop-safe runtime/source status.

SDK:

- typed clients for released route groups;
- preserve source, lineage, warnings, missing inputs, research metadata, and LLM
  citation metadata.

CLI:

- inspect source posture, route candidates, shadow runs, glossary terms, and
  analysis outputs through SDK/API.

## Acceptance Requirements

The capability is release-ready only when:

- live connector behavior is gated by entitlement and credentials;
- offline tests use mocks/synthetic fixtures;
- API routes expose source/freshness/quality metadata;
- clients reach data through SDK/API only;
- map shows route options and warnings clearly;
- LLM outputs cite backend source references and are marked research-only;
- no execution, order, trade-capture, nomination, or official recommendation
  behavior exists.
