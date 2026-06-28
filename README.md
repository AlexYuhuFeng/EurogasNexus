# Eurogas Nexus

[![CI](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/ci.yml/badge.svg)](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/ci.yml)
[![Build and Release](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/release.yml/badge.svg)](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/release.yml)
[![Releases](https://img.shields.io/github/v/release/AlexYuhuFeng/EurogasNexus?include_prereleases&label=release)](https://github.com/AlexYuhuFeng/EurogasNexus/releases)

Eurogas Nexus is a PostgreSQL-first European gas intelligence workspace for
portfolio visibility, infrastructure monitoring, route economics, source
diagnostics, glossary context, and trader-reviewed decision support.

The platform is designed around one rule: operational data belongs in the
backend database. Web, desktop, CLI, and SDK clients access runtime data through
the API or SDK only; clients do not connect directly to PostgreSQL and do not
store market-provider credentials.

> Current release line: `v0.5-preview`.
> The project is active preview software, not an ETRM replacement and not an
> automated trading or nomination system.

## Product Scope

Eurogas Nexus supports gas-market teams that need a single workspace for:

- map-focused European gas network context;
- hubs, interconnection points, LNG terminals, storage and infrastructure status;
- source health and credential diagnostics for public and licensed providers;
- UK National Gas NTS route-cost calculation from audited tariff records;
- contract and resource-pool economics for physical, virtual and LNG supply;
- strategy backtesting, shadow-run and live monitoring workflows;
- operational glossary access in English and Simplified Chinese;
- LLM-assisted analysis through backend-governed provider integrations.

Decision outputs are advisory and require human review. Eurogas Nexus does not
execute trades, route orders, submit nominations, provide legal advice, issue
official approvals, or generate official trading recommendations.

## Architecture

```text
public/licensed data source
        |
        v
ingestion + normalization
        |
        v
PostgreSQL runtime store
        |
        v
FastAPI backend  <---->  Python SDK / CLI
        |
        v
Web client + Windows/Linux desktop client
```

Core principles:

- PostgreSQL is the runtime source of truth.
- API imports must not connect to the database or run migrations.
- Credentials are backend-owned and write-only from client perspective.
- Source data quality must be explicit; approximated coordinates or missing
  topology are shown as such instead of silently falling back to fake data.
- Synthetic data is acceptable only for tests or explicitly loaded demo
  databases, not as production runtime fallback.

## Repository Layout

```text
apps/
  api/                 FastAPI entry point
  scheduler/           scheduled runtime jobs
  worker/              background worker surface
clients/
  web/                 React + Vite web workspace
  desktop/             Tauri desktop shell for Windows/Linux builds
src/eurogas_nexus/
  api/                 API factory and route modules
  db/                  SQLAlchemy models, sessions and DB health checks
  ingestion/           public/licensed source ingestion contracts
  runtime_store/       runtime persistence contracts
  sdk/                 Python SDK surface
alembic/               database migration environment
docs/                  architecture, contracts, operations and client specs
infra/                 deployment references
scripts/               operational and release scripts
tests/                 API, contract, integration, SDK, CLI, release and security tests
```

## Quick Start

Requirements:

- Python 3.11+
- Node.js 20+
- Rust stable, required for desktop builds
- PostgreSQL, required for runtime validation and live data workflows

Install Python dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run backend checks:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Run the API locally:

```powershell
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Run the web client:

```powershell
npm --prefix clients/web ci
npm --prefix clients/web run dev
```

Build the Windows desktop client:

```powershell
npm --prefix clients/web ci
npm --prefix clients/desktop ci
npm --prefix clients/desktop run build -- --bundles nsis
```

Build the Linux desktop package:

```bash
npm --prefix clients/web ci
npm --prefix clients/desktop ci
npm --prefix clients/desktop run build -- --bundles deb
```

## Runtime Database

Database URL precedence:

1. `RUNTIME_STORE_DATABASE_URL`
2. `DATABASE_URL`
3. `EUROGAS_NEXUS_DB_DSN`, legacy fallback

Validate a configured runtime database:

```powershell
python scripts/ops/validate_v1_runtime_db.py --json
```

Validation is read-only. It checks connectivity, required table presence and
Alembic revision status. It does not write records and does not run migrations.

## Data Sources

The Source Center groups provider status, credentials, update timing and record
counts by operational category.

| Category | Providers |
| --- | --- |
| Prices | Platts, ICIS, Argus, EEX, ICE OCM, Trayport, Kpler |
| FX | ECB |
| Infrastructure | ENTSOG, GIE AGSI, GIE ALSI |
| Tariffs | National Gas NTS, future European TSO tariff sources |
| Weather | provider slot for HDD/CDD modelling |
| LLM | DeepSeek first, with room for additional providers |

Public feeds such as ECB and supported ENTSOG endpoints do not require API keys.
Licensed feeds require customer-owned credentials and entitlements. Client
screens may show redacted credential previews and diagnostics, but never raw
secret values.

## API, SDK And Clients

Stable client routes use the `/api` prefix.

Clients should use:

- backend HTTP API for runtime workflows;
- Python SDK for scripted access and automation;
- CLI for operator checks and release/runtime diagnostics.

Clients must not:

- connect directly to PostgreSQL;
- read runtime CSV/JSON files as source-of-truth;
- store provider credentials locally;
- call market-provider APIs directly when the backend source layer owns that
  integration.

## Current Capability Notes

- UK National Gas NTS route-cost support is implemented for audited NTS tariff
  rows and is not limited to Easington or Bacton.
- European reference network nodes are displayed with explicit data-quality
  metadata. Some coordinates are currently marked as display approximations.
- Pipeline geometry is shown only when verified topology exists in PostgreSQL;
  the UI reports missing geometry instead of drawing fake routes.
- Price feeds that require licensed APIs should be represented through provider
  slots until credentials and entitlements are configured by the customer.

## Build And Release

GitHub Actions runs two workflows on `main`:

- `CI`: Python checks, targeted tests, web build and desktop build matrix.
- `Build and Release`: validates the release candidate, builds web/desktop
  artifacts, and publishes a GitHub pre-release with collected assets.

Local release scripts mirror the workflow contract:

```powershell
./scripts/release/build_v1_release.ps1 -Bundle nsis
```

```bash
./scripts/release/build_v1_release.sh --bundle deb
```

Release artifacts include:

- web build archive;
- Windows NSIS installer;
- Linux Debian package.

## Documentation

Start here:

- [Current Pause Point](docs/architecture/CURRENT_PAUSE_POINT.md)
- [Product Boundary Policy](docs/policies/PRODUCT_BOUNDARY_POLICY.md)
- [Architecture Decision Record](docs/architecture/ARCHITECTURE_DECISION_RECORD.md)
- [API Contract](docs/contracts/06_API_CONTRACT.md)
- [Client API Contract](docs/clients/CLIENT_API_CONTRACT.md)
- [Web Client Design Spec](docs/clients/WEB_CLIENT_DESIGN_SPEC.md)
- [Windows Client Design Spec](docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md)
- [UI/UX Style Guide EN](docs/clients/UI_UX_STYLE_GUIDE-EN.md)
- [UI/UX Style Guide CN](docs/clients/UI_UX_STYLE_GUIDE-CN.md)
- [Live PostgreSQL Policy](docs/operations/LIVE_POSTGRESQL_V1.md)
- [Release Readiness](docs/release/V1_RELEASE_READINESS.md)

## Security And Data Policy

This is a public repository. Do not commit:

- `.env` files;
- API keys, tokens, passwords or provider credentials;
- real vendor data or raw licensed market data;
- internal commercial data;
- contracts or confidential counterparty terms;
- real trading strategy parameters.

Report security issues through the process in [SECURITY.md](SECURITY.md).

## 中文简介

Eurogas Nexus 是面向欧洲天然气市场团队的 PostgreSQL 优先型决策支持工作台，
覆盖管网与 LNG 基础设施监控、数据源诊断、路线经济性、资源组合、策略影子运行、
术语库以及人工复核的市场分析。

项目的运行时事实来源是 PostgreSQL。Web、桌面端、CLI 和 SDK 都必须通过后端
API 或 SDK 访问数据，不允许客户端直接连接数据库，也不允许客户端保存供应商密钥。

当前版本属于 `v0.5-preview`。它用于辅助交易与运营人员理解市场、组合和路线选择，
但不执行交易、不提交提名、不替代 ETRM、不提供法律意见，也不构成官方交易建议。
