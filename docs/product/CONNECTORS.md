# Connectors: one model for data feeds, imports and model services

Status: C1 and C2 implemented 2026-11-06 (`src/eurogas_nexus/domain/connectors/`); C3 delivered as
the Connectors view of Admin → Data Sources (#26, #33). Plan written 2026-11-05. Owner direction: data-source management should feel like
Claude connectors or ChatGPT plugins, a catalogue you connect and manage, not a
governance console. Related: #26, #33, #38, #40.

## Why

Today one provider is described in three places:

| Where | What it holds |
|---|---|
| `domain/ingestion/source_registry.py` | Catalogue row: category, datasets, description, licence scope |
| `domain/dataops/registry.py` | Operations: access mode, schedule, retry, freshness, certification |
| `security/provider_credentials.py` | Credential: environment variables, key file, store |

The Data Sources page then shows all three at once (posture cards, a priority queue,
credentials, certification, runtime) and the user has to assemble them. Adding a
provider means editing three files and the UI. A connector model puts each provider in
one declaration and gives the page one shape: a catalogue of connectors, each with one
detail view.

## The model

A **connector** is one declaration (a manifest) plus an adapter:

- **Identity:** id, name, publisher, version, documentation link.
- **Kind:** `data_feed` (fetches on a schedule), `file_import` (an operator imports the
  desk's own export), `model_service` (an LLM endpoint) or `export` (reports out to
  ERP/ETRM).
- **Datasets it provides:** for each dataset, a subject (gas prices, FX, rates, flows,
  storage, LNG, weather, power, outages), units, time basis and licence family. One
  connector can provide several datasets, and one subject can come from several
  connectors.
- **Authentication:** credential fields and the environment variables that may carry
  them, as in the credential contract (#38).
- **Operations:** default schedule, freshness expectation, retry and rate limits, and
  whether certification is required.
- **Entitlement:** public or licensed. A licensed dataset is served only through the
  licence register and data scopes, as today; connecting never grants a licence.

The three current registries become views derived from the manifests, so nothing reads
a provider from two places.

## What users see

**Connectors** (Admin) replaces the Data Sources tabs:

- A catalogue in three groups: **Connected**, **Needs attention**, **Available**. Each
  card shows the name, what it provides ("FX reference rates, €STR"), one status word and
  one action (Connect, Fix, Open).
- **Connect** is a short flow: enter or confirm credentials (or note that the
  environment provides them), test the connection, choose whether it runs on a
  schedule, and record certification where the source requires it. Each step says what
  it does and does not unlock.
- **One detail page per connector**, with tabs: Datasets, Health (freshness, last runs,
  failures), Credentials, Permissions (who may read its data) and History.
- **Needs attention** is the only cross-connector list: a failure, a missing key or a
  stale dataset, each with its fix.

Traders never see this. Their top bar shows one data-status chip; the detail is a hover
away, and it links here only for people who administer connectors.

## Plugins

Built-in connectors ship in the product. Others are Python packages that declare
themselves through a standard entry point (`eurogas_nexus.connectors`), so the
maintenance team or the client's IT can add, for example, a Kpler or ICIS connector
without changing the product. An installed plugin appears in the catalogue as
**Available**, and an administrator must enable it. No code is uploaded through the
browser: a plugin is installed with the deployment, reviewed like any dependency
(licence check, rule 18) and versioned with the release. Model services follow the same
path: OpenAI-compatible endpoints are built in, and other APIs come as plugins.

## What does not change

- Governance stays in the backend: data scopes, the licence register, certification for
  export-restricted sources, the four-eyes rules and audit. A connector cannot widen any
  of them.
- No new infrastructure (AGENTS rule 5): manifests are Python, state stays in PostgreSQL,
  and the scheduler and job runner are the existing ones.
- Stable source ids, lineage and stored history are kept; a connector maps onto the
  existing `src-*` ids.

## Slices

| # | Slice | Done when |
|---|---|---|
| C1 | Connector manifest; the three registries derived from built-in manifests | Registries and APIs unchanged byte-for-byte; one file per provider |
| C2 | Entry-point loading with an administrator allow-list | A test plugin appears as Available and runs only after it is enabled |
| C3 | Connectors page: catalogue, Connect flow, one detail page, Needs attention | Data Sources tabs retired; every current action reachable in at most two clicks |
| C4 | Model services as connectors | Configured provider and model shown, not "DeepSeek"; a second provider can be added without code |
| C5 | Plugin developer guide and template package | A sample connector built from the template passes the contract tests |

## Implementation (C1, C2)

- **Manifests:** `domain/connectors/manifest.py` defines `ConnectorManifest`. There is one module
  per built-in provider in `domain/connectors/builtin/`, listed in catalogue order in
  `domain/connectors/registry.py`. Families share a policy through
  `domain/connectors/operations.py` (tariffs, exchanges, licensed feeds, daily benchmark rates).
- **Derived registries:** the source registry (`registered_sources`), the data-operations
  registry (`source_definitions`) and the provider credential contract
  (`PROVIDER_CREDENTIAL_SPECS`) are derived from the manifests.
  `tests/unit/test_connector_manifests.py` compares all three with a snapshot taken before the
  move (`tests/fixtures/connectors/registry_snapshot.json`). Source rows and operations
  definitions are unchanged byte for byte. The credential list holds the same providers; the
  not-yet-implemented ones are now listed in catalogue order.
- **Plugins:** `domain/connectors/plugins.py` loads `eurogas_nexus.connectors` entry points. An
  installed plugin appears in the catalogue (`plugin: {name, enabled}` on its row) with its
  operations forced off until its entry-point name is listed in
  `EUROGAS_NEXUS_CONNECTOR_PLUGINS`. A plugin cannot replace a built-in `source_id`. A plugin
  that fails to load is skipped and logged.
