# V1 Full Project Release Scope

## Release Definition

Eurogas Nexus V1 is an internal European gas research and decision-support
release. It must provide a PostgreSQL-backed backend, stable `/api` routes,
Python SDK, CLI, web workspace, and Windows client shell for research workflows.

V1 may produce research trading ideas, candidate rankings, explanations, data
gaps, and risk warnings for human review. V1 must not create official trading
recommendations, order instructions, execution instructions, nomination
instructions, legal advice, official approvals, trade-capture records, or ETRM
records.

## Required Product Surfaces

V1 release includes:

1. Backend/API service.
2. PostgreSQL runtime store and Alembic migrations.
3. Python SDK.
4. CLI.
5. Web client.
6. Windows client package shell.
7. Release validation and packaging documentation.

## Required Backend Capabilities

Backend/API V1 must include:

- `/api/health`;
- runtime status/readiness;
- source registry and ingestion run metadata;
- live-source connector contracts and gated runtime status for ECB, ENTSOG,
  GIE, EEX, Trayport, ICE OCM, and weather providers;
- canonical reference network;
- geometry-topology-market mapping;
- PostgreSQL-backed market observation support from entitled or operator-owned
  inputs;
- PostgreSQL-backed flow, capacity, and outage support from public/operator
  source ingestion;
- PostgreSQL-backed LNG/regas support from GIE ALSI or entitled customer
  sources;
- PostgreSQL-backed storage support from GIE AGSI or entitled customer sources;
- weather/demand metric support only after a configured weather source or
  operator-owned input is ingested into PostgreSQL;
- capacity contract and route eligibility context;
- route cost research workflow;
- indicative netback research workflow;
- feasibility research workflow;
- allocation scenario research workflow;
- monitoring and alert research flags;
- weather-adjusted nowcast research workflow;
- strategy backtest research workflow;
- shadow run paper-evaluation workflow;
- LLM-assisted market movement and route explanation workflow with citations;
- backend-served glossary;
- research brief/report workflow;
- governance, entitlement, export, and audit foundations.

## Required Client Capabilities

All V1 clients access runtime data through SDK/API boundaries. No client opens a
PostgreSQL connection, imports backend DB/runtime-store modules, or reads
backend local data files directly.

### Python SDK

The SDK must:

- target `/api`;
- expose typed clients for released backend routes;
- preserve metadata, warnings, missing inputs, source references, lineage,
  `research_only`, and `human_review_required`;
- redact secrets in errors;
- avoid backend internal imports.

### CLI

The CLI must:

- call SDK/API only;
- provide health and runtime validation commands;
- provide source, scenario, research, and release-readiness inspection commands
  for released workflows;
- default to read-only/dry-run behavior;
- require `--execute` for any future write-like command;
- output human and JSON forms where useful.

### Web Client

The web client must:

- consume `/api`;
- show backend, DB, source, and warning posture;
- be map-first;
- provide Network, Capacity, Market, Scenario, Strategy, Review, Sources,
  Glossary, Runtime, and Settings workspaces;
- show live-source posture for ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM,
  weather, and LLM analysis;
- show route options, capacity/contract constraints, market/weather signals,
  and shadow-run outputs;
- display source references, lineage, assumptions, missing inputs, warnings,
  and human-review state;
- avoid direct DB, vendor API, and secret access.

### Windows Client

The Windows client must:

- package or launch the web workspace;
- configure backend base URL;
- store only non-sensitive UI preferences;
- show health/runtime/source posture;
- preserve the map-first workflow, capacity/contract views, strategy shadow-run
  review, glossary, and LLM-assisted analysis panels exposed by the web
  workspace;
- avoid direct DB, vendor API, and secret access;
- avoid copying historical Desktop source.

## Data Scope

V1 implementation must use:

- live local PostgreSQL for runtime validation and release-like operation;
- synthetic fixtures and manual sample templates where real source entitlement
  is not approved;
- explicit source references for all data;
- fail-closed behavior for unknown commercial/vendor data.

V1 must not commit:

- `.env`;
- credentials;
- API keys;
- tokens;
- raw vendor data;
- internal commercial data;
- contracts;
- real strategy parameters;
- generated commercial reports.

## Research Output Requirements

Every research workflow output must include:

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

Required disclaimer for reports:

```text
This report is a research decision-support output and not a trading
recommendation, order instruction, execution instruction, official approval, or
official risk decision.
```

## Release Non-goals

V1 does not include:

- trade execution;
- order entry;
- order routing;
- trade capture;
- nomination submission;
- official approval workflow;
- legal advice;
- official trading recommendations;
- auto-trading;
- ETRM replacement behavior;
- company SSO/OIDC unless separately approved;
- ungated live vendor connector execution;
- ungated live LLM provider execution.

Live vendor connector and LLM provider execution are allowed only when a scoped
milestone documents internet requirement, credentials, entitlement, export
policy, provider terms, secret handling, mocked tests, and operator validation.

## Completion Definition

V1 release is complete only when every required product surface passes its
acceptance gates in `docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md`, release
validation passes, and all remaining gaps are explicitly documented as accepted
limitations rather than hidden missing work.

Execution queue:

- `docs/release/V1_RELEASE_MILESTONE_BACKLOG.md`

Missing milestone ExecPlans must be created from:

- `docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md`
