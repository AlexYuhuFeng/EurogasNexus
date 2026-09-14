# Target Platform Architecture

## 1. Logical platform model

```text
USERS
Trader · Analyst · HQ · Reviewer · Management · Research · Data Ops · Platform Admin
                                  │
                                  ▼
                         EXPERIENCE PLATFORM
 Functional Assignments · Work Modes · Navigation · Panels · Preferences · Active Context
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
         BUSINESS WORKSPACE   RESEARCH STUDIO      ADMINISTRATION
              └───────────────────┼───────────────────┘
                                  ▼
                        APPLICATION PLATFORM
 Decision Case · Analysis Snapshot · Projections · Reports · Unified Jobs · Errors
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
 DOMAIN / ANALYTICS          AI / AGENT              CONTROL SERVICES
 Market · Network            Capability Registry      Identity
 Portfolio · Contracts       Agent Runtime            Access/Entitlement
 Scenario · Optimisation     Strategy IR              Audit/Config
 Risk · Strategy             Research/Challenge       Provider Ops/Observability
         └────────────────────────┼────────────────────────┘
                                  ▼
                            DATA PLATFORM
 Connectors → Landing/Raw → Normalisation → Canonical → Semantic → Data Products
          Quality · Freshness · Lineage · Snapshot · Licence/Entitlement
                                  │
                                  ▼
                   PostgreSQL (+ object storage only if justified)
```

## 2. Physical default

```text
TLS / Reverse Proxy
      │
      ├── Web static assets
      │
      └── FastAPI Application
              │
              ├── Worker Runtime
              ├── Scheduler
              ├── PostgreSQL
              └── optional broker/cache only where justified
```

This remains intentionally simple.

## 3. Cross-cutting first-class concepts

### Active Context
Common context for:
- gas day / time basis;
- organisation;
- portfolio;
- hub/market;
- resource;
- route;
- scenario;
- Decision Case;
- Analysis Snapshot.

### Analysis Snapshot
Reproducible reference to:
- market data versions;
- network/capacity state;
- portfolio and contract versions;
- tariff/FX;
- weather/demand assumptions;
- manual assumptions;
- model/calculation versions;
- entitlement context.

### Decision Case
Container for:
- objective;
- context;
- assumptions;
- alternatives;
- scenarios;
- analytics;
- risks/constraints;
- evidence;
- AI challenge;
- human review;
- Decision Record.

### Data Product
Business-facing governed data contract independent of provider implementation.

### Job
Shared lifecycle for ingestion, dataset build, optimisation, backtest, agent work and reporting.

## 4. Application projection layer

Preserve current APIs for compatibility, but add coherent read models:

- MarketContext
- PortfolioSnapshot
- RouteDecisionContext
- ScenarioContext
- StrategyEvidence
- DecisionCaseProjection
- ReviewContext
- ManagementOverview
- ExperienceProfile

This reduces:
- frontend waterfalls;
- inconsistent time bases;
- duplicated client joins;
- business logic in React.

## 5. Portfolio semantic model

Portfolio must represent:
- Resources
- Contracts/Obligations
- Sales/Offtake
- Capacity Rights
- Storage
- LNG/Regas rights
- Physical Position
- Financial Exposure
- Capacity Exposure
- Delivery Obligations
- Optionality
- Commercial Constraints

## 6. Network model

Evolve Network into a **Physical Commercial Graph**:
- physical nodes/edges;
- capacity;
- tariffs/costs;
- market areas;
- portfolio rights;
- route feasibility;
- time-dependent state.
