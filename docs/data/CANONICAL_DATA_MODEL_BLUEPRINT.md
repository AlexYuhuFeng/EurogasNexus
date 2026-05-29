# Canonical Data Model Blueprint

## Purpose

This document defines the target data model families for Eurogas Nexus. It is a
blueprint for DB-first implementation and does not create tables by itself.

## Source Of Truth

PostgreSQL is the runtime source of truth. Alembic owns schema changes.

Local files may be import templates, raw/canonical archives, fixtures, or
reports. Trial and release modes must not silently use local files as runtime
truth.

## Required Metadata For Durable Records

Every durable runtime record should include or link to:

- canonical ID;
- source reference;
- lineage;
- schema version;
- observation timestamp where applicable;
- retrieval timestamp where applicable;
- load timestamp;
- freshness state;
- data quality state;
- entitlement/export state;
- audit metadata where applicable.

## Core Entity Families

### Source And Lineage

Entities:

- `SourceSystem`
- `SourceDataset`
- `SourceReference`
- `LineageEvent`
- `IngestionJob`
- `IngestionRun`
- `NormalizationResult`
- `DataQualityResult`

Purpose:

- prove where data came from, how it was transformed, and whether it is usable.

### Geometry, Topology, And Market Mapping

Entities:

- `PhysicalGeometry`
- `TopologyNode`
- `TopologyEdge`
- `Facility`
- `MarketHub`
- `MarketArea`
- `RouteCorridor`
- `GeometryTopologyMapping`
- `TopologyMarketMapping`

Rules:

- geometry is map display only until mapped;
- topology is operational/commercial structure;
- market abstraction is trading/research context;
- mapping records carry confidence and eligibility;
- strategy/research eligibility requires approved mapping.

### Market Observations

Entities:

- `MarketVenue`
- `MarketProduct`
- `MarketObservation`
- `FxObservation`
- `UnitConversionRule`
- `MarketSignal`

Fields:

- price/value;
- unit;
- currency;
- period;
- observation time;
- source reference;
- freshness and quality.

### Physical Flow, Capacity, Outage

Entities:

- `FlowObservation`
- `CapacityObservation`
- `OutageEvent`
- `Direction`
- `InterconnectionPoint`
- `CapacityContract`
- `CapacityAvailability`
- `RouteEligibility`
- `ContractExposure`

Purpose:

- represent physical and operational context without assuming tradability.

### LNG And Storage

Entities:

- `LngTerminal`
- `LngObservation`
- `StorageSite`
- `StorageObservation`
- `RegasCapacityObservation`

Purpose:

- support LNG/regas and storage context in scenarios and monitoring.

### Weather And Demand Context

Entities:

- `WeatherLocation`
- `WeatherObservation`
- `HddCddMetric`
- `DemandProxyObservation`
- `WeatherMarketMapping`
- `WeatherSignal`

Purpose:

- support weather-adjusted demand, supply, and price-pressure nowcast.

### Resource And Commercial Context

Entities:

- `ResourcePool`
- `SupplySource`
- `ContractAnchor`
- `DeliveryPoint`
- `VolumeProfile`
- `CostAssumptionSet`

Purpose:

- define scenario input context without becoming an ETRM or trade-capture
  system.

### Route Cost And Netback

Entities:

- `RouteCandidate`
- `RouteLeg`
- `CostComponent`
- `TariffReference`
- `RouteCostRun`
- `RouteCostResult`
- `NetbackRun`
- `NetbackResult`

Purpose:

- produce indicative research economics with explicit assumptions and warnings.

### Feasibility And Allocation

Entities:

- `Scenario`
- `ScenarioInput`
- `FeasibilityRun`
- `FeasibilityResult`
- `AllocationRun`
- `AllocationCandidate`

Purpose:

- test plausibility and allocation choices without creating nominations,
  bookings, trades, or approvals.

### Monitoring, Nowcast, Strategy

Entities:

- `MonitoringRule`
- `ResearchAlert`
- `AnomalyCandidate`
- `NowcastRun`
- `NowcastResult`
- `StrategyHypothesis`
- `BacktestRun`
- `BacktestResult`
- `ShadowRun`
- `ShadowRunObservation`
- `MarketMovementAnalysisRun`
- `AnalysisCitation`

Purpose:

- support research monitoring, near-term pressure views, backtesting, and paper
  shadow runs.

### Research Output And Reporting

Entities:

- `ResearchOutput`
- `ResearchCandidate`
- `ResearchWarning`
- `MissingInput`
- `Assumption`
- `ResearchBrief`
- `ReportExportEvaluation`
- `GlossaryTerm`

Required output metadata:

- assumptions;
- missing inputs;
- warnings;
- source references;
- lineage;
- freshness;
- data quality;
- `research_only`;
- `human_review_required`.

### Governance And Audit

Entities:

- `EntitlementDecision`
- `ExportPolicyDecision`
- `AuditEvent`
- `AccessPolicy`
- `DataScope`

Rules:

- unknown commercial data fails closed;
- export requires explicit policy decision;
- audit must record sensitive runtime actions.

## Naming And ID Policy

Canonical IDs should be stable, lowercase, and scoped:

```text
<scope>:<source-or-domain>:<natural-key-or-slug>
```

Examples:

```text
hub:market:ttf
facility:synthetic:lng-terminal-a
route:synthetic:nbp-ttf-corridor-a
```

Synthetic IDs must be visibly synthetic.

## Table Implementation Rule

Do not create all tables at once. Each milestone should add only the tables
needed for the selected slice, with:

- migration revision;
- required table registry update;
- repository tests;
- API/SDK/CLI/client impact notes;
- rollback notes.
