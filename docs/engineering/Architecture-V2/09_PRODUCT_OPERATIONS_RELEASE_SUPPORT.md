# Product Operations, Deployment, Release and Support

## 1. Deployment profiles

### Developer
Local tooling/Compose, PostgreSQL, worker, public/simulated data.

### Internal / Small Team
TLS gateway, application runtime, PostgreSQL, worker/scheduler, identity, backup and monitoring.

### Enterprise
Load-balanced application runtime, HA/managed PostgreSQL, approved secret manager,
optional broker/cache, optional object storage, enterprise IdP, central logs/metrics/traces,
backup/DR and organisation-required network controls.

Kubernetes may be a deployment adapter, not a product dependency.

## 2. Environments

Formal environment model:
DEV -> TEST -> UAT -> PROD.

Promotion should not depend on manual source edits.

## 3. Observability

Converge:
- structured logs;
- metrics;
- traces/correlation;
- health/readiness;
- job telemetry;
- pipeline/freshness telemetry;
- audit events;
- business service health.

Normal users see:
- Market Data Healthy/Delayed
- Portfolio Current/Stale
- Network Current/Degraded
- AI Available/Restricted

Operators see:
- PostgreSQL
- pools
- worker
- scheduler
- adapters
- queue
- migrations
- LLM provider

## 4. Reliability

Preserve current backup/restore, DR, incident-response, migration-preflight, performance-budget and
SLO assets.

Validate them against real deployment profiles.

Define RPO/RTO by data class.

Market data that can be re-ingested is different from:
- audit;
- Decision Records;
- portfolio state;
- manual commercial inputs.

## 5. Upgrade / rollback

Every release requires:
- pre-upgrade compatibility check;
- backup/restore point;
- migration plan;
- application deployment;
- post-deploy validation;
- rollback classification.

Every DB migration should state:
- backward-compatible?
- application rollback compatible?
- destructive?
- forward-fix only?

## 6. Versioning

Use SemVer:
`MAJOR.MINOR.PATCH`

Channels:
- dev
- preview
- rc
- stable

0.5.x remains legacy preview.
Architecture V2 does not imply product 2.0 or even 1.0.

## 7. Existing release engineering

Keep and integrate with current machinery:
- canonical version consistency;
- semantic tags;
- release manifest;
- SBOM;
- vulnerability evidence;
- checksums;
- provenance;
- immutable digest;
- compatibility metadata;
- fail-closed stable gate.

Do not rebuild this system from scratch.

## 8. Release manifest target

Should identify:
- product version;
- channel;
- commit;
- API contract version;
- DB schema revision;
- canonical data model version;
- capability registry version;
- configuration schema version;
- agent contract version;
- relevant model/solver schema versions;
- minimum compatible client/server;
- artefact integrity/signing information.

## 9. Feature lifecycle

EXPERIMENTAL -> PREVIEW -> LIMITED -> GA -> DEPRECATED -> RETIRED.

Availability =
`feature enabled × user authorised × scope valid × data entitled`

Feature flags are not permissions.

## 10. Diagnostics

Provide a safe Diagnostics Bundle containing:
- version/build;
- environment identity;
- API/DB compatibility;
- dependency health;
- job/error IDs;
- non-sensitive config summary;
- safe recent logs.

Exclude:
- secrets;
- private keys/tokens;
- raw licensed data;
- unauthorised commercial data.

## 11. Capacity planning

Before GA define expected:
- named/concurrent users;
- portfolios;
- API rate;
- time-series volume;
- ingestion volume;
- dataset/backtest size;
- retention;
- AI run volume.

Infrastructure sizing should follow evidence, not generic cloud templates.
