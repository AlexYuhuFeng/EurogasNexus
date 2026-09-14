# Documentation, NFR, Testing and Long-Term Maintenance

## 1. Documentation system

The repository already has extensive documentation.
V2 should consolidate and classify, not create endless duplicates.

### User documentation
- Quick Start
- Market
- Portfolio
- Decision
- Research/Strategy
- Copilot
- Data status/provenance
- Glossary/FAQ

### Operator/Admin
- Installation
- Deployment prerequisites
- SSO/users
- Entitlements
- Providers/credentials
- Ingestion
- Upgrade
- Backup/restore
- DR
- Monitoring
- Diagnostics
- Incident response
- Troubleshooting

### Maintainer/Developer
- Architecture Constitution
- Target Architecture
- Module boundaries
- API/data contracts
- DB/migrations
- Frontend architecture
- Capability registry
- Testing
- ADR/RFC
- Contribution

### Delivery / Commercial IT
- Deployment profiles
- Infrastructure prerequisites
- Supported platforms
- Network/DNS/TLS
- Security baseline
- Provider/licence prerequisites
- Third-party notices
- Compatibility matrix
- Release notes
- Known issues
- Support/EOL
- Signing status

## 2. Deployment & Commercial Readiness Guide

Before GA, create one concise enterprise-IT handover document answering:
- required infrastructure;
- supported OS/runtime/database;
- ports/DNS/TLS;
- online/offline needs;
- IdP requirements;
- provider licences and customer credentials;
- storage/backup;
- expected scale;
- security responsibilities;
- included/excluded capabilities;
- upgrade/support model;
- known external dependencies.

## 3. Documentation-as-code

A change is incomplete if it materially changes:
- user workflow;
- API;
- data contract;
- config;
- deployment;
- migration;
- security;
- operating procedure;

without corresponding docs.

## 4. Non-functional requirements

Track:
- availability;
- latency/performance;
- scalability;
- security;
- recoverability;
- auditability;
- reproducibility;
- data freshness;
- data quality;
- accessibility;
- maintainability;
- portability;
- compatibility.

Do not invent final numeric SLOs without deployment/user-volume evidence.

## 5. Testing categories

Required:
- unit;
- domain/numerical;
- integration;
- API contract;
- authorisation/entitlement;
- DB migration;
- data quality;
- frontend component;
- E2E workflow;
- accessibility;
- i18n;
- performance/load;
- resilience;
- backup/restore;
- upgrade/rollback;
- packaging/install;
- UAT.

## 6. Golden analytical regression

Create versioned Golden Scenarios pinning:
- portfolio;
- gas day;
- market snapshot;
- capacity;
- tariffs/FX;
- assumptions;
- model version;
- expected outputs/tolerances.

Cover:
- route economics;
- min-cost flow;
- storage dispatch;
- exposure/PnL;
- scenario outputs;
- selected strategy/backtest results.

Numeric changes require explicit review.

## 7. Architecture fitness functions

Gradually add CI checks:
- clients cannot import backend internals;
- client cannot call provider adapters;
- every public route has access declaration;
- no plaintext credential response;
- no critical business calculations in React;
- Tauri commands stay within HostCapabilities;
- module dependency direction;
- version/config consistency;
- ExperienceProfile cannot grant capability;
- AI invocation rechecks authority.

## 8. Definition of Done

Where applicable:
- domain semantics;
- API/data contract;
- authorisation/entitlement;
- provenance/snapshot;
- error states;
- observability;
- tests;
- docs;
- migration;
- compatibility;
- accessibility;
- EN/zh-CN;
- audit/security;
- release/feature-lifecycle impact;
- UX consistency against Product Experience Architecture.

## 9. ADR discipline

Continue the existing ADR authority.

Recommended new ADRs:
- modular monolith remains default;
- unified Data Platform/Data Product model;
- Functional Assignment/Work Mode != authorisation;
- Control Plane separation;
- Analysis Snapshot;
- Decision Case;
- projection/query layer;
- Tauri as replaceable thin host;
- cloud-neutral deployment;
- optional object storage only by measured need;
- Product Experience Architecture as binding interaction authority.
