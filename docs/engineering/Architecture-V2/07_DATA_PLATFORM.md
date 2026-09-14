# Unified Data Platform Specification

## 1. Core decision

Data Source shall not belong to a client, workspace or persona.

The target is one governed Data Platform.

```text
External/Internal Sources
EEX · ICE · ICIS · Kpler · Fluxys · ENTSOG · GIE · Weather · Internal Data
                         │
                         ▼
                    CONNECTORS
                         │
                         ▼
                  LANDING / RAW
                         │
                         ▼
                 NORMALISATION
                         │
                         ▼
                  CANONICAL DATA
                         │
                         ▼
                 SEMANTIC LAYER
                         │
                         ▼
                    DATA PRODUCTS
                         │
          Workspace · Research · AI · Reports
```

## 2. Separate concepts

### Provider Connection
Operational integration:
- endpoint;
- credential reference;
- quota;
- health;
- scheduler;
- ingestion;
- certification.

### Data Product
Business-facing data contract:
- NBP Day-Ahead Market Context
- TTF Forward Curve
- European Physical Flow
- Capacity Availability
- Storage Context
- Weather Context
- Portfolio Position
- Route Cost Inputs

A Data Product may combine several sources and derived calculations.

### Data Entitlement
Controls:
- view;
- calculate;
- export;
- redistribute;
- external-LLM usage.

## 3. User-facing data posture

Normal users see:
- value;
- time basis;
- source/provenance summary;
- as-of;
- freshness;
- quality/confidence;
- entitlement limitations.

They do not see:
- API keys;
- secret values;
- scheduler internals;
- retry traces.

## 4. Operator posture

Data operators may see:
- connection state;
- credential state/expiry metadata;
- ingestion history;
- latency;
- freshness breach;
- DQ issues;
- quota/circuit-breaker;
- backfill/retry/test actions.

## 5. Storage

Default:
- PostgreSQL for canonical relational/time-series state, governance, metadata and moderate research data.

Future optional:
- object storage for raw archives, Parquet, large immutable dataset/report/model artefacts.

Add only when there is a concrete size/performance/retention requirement.

## 6. Analysis Snapshot

Snapshot descriptor should include:
- snapshot_id
- as_of
- gas day/time basis
- market data versions
- network/capacity version
- portfolio version
- contract/resource versions
- tariff/FX
- weather/demand assumptions
- manual assumptions
- model/calculation versions
- entitlement context

Scenario, optimisation, strategy, report and AI evidence should reference snapshot_id.

## 7. Access path

Allowed:

`Application API -> Data Product/Semantic Service -> Repository/Provider Adapter`

Forbidden:
- UI -> EEX directly
- Strategy -> ICIS directly
- Agent -> Kpler directly
- Scenario -> arbitrary table reads
