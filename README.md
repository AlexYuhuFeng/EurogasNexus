# Eurogas Nexus

[![CI](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/ci.yml/badge.svg)](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/ci.yml)
[![Build and Release](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/release.yml/badge.svg)](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/release.yml)
[![Release](https://img.shields.io/github/v/release/AlexYuhuFeng/EurogasNexus?include_prereleases&label=release)](https://github.com/AlexYuhuFeng/EurogasNexus/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/database-PostgreSQL-4169E1)](https://www.postgresql.org/)
[![React](https://img.shields.io/badge/web-React%20%2B%20MapLibre-61DAFB)](https://maplibre.org/)
[![Tauri](https://img.shields.io/badge/desktop-Tauri-FFC131)](https://tauri.app/)

Eurogas Nexus is a PostgreSQL-first European gas intelligence workspace for
portfolio monitoring, infrastructure visibility, route economics, data-source
operations, strategy evaluation, and trader-reviewed decision support.

Runtime truth lives in PostgreSQL. Web, Windows, Linux, SDK, and CLI clients
read it through the backend API or SDK.

Current line: `v0.5-preview`

Eurogas Nexus is not an ETRM replacement, execution venue, order router,
nomination-submission system, auto-trading system, legal-advice tool, or
official trading recommendation system.

## Contents

- [Product Scope](#product-scope)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Database](#database)
- [Data Sources](#data-sources)
- [Clients](#clients)
- [Testing](#testing)
- [Build and Release](#build-and-release)
- [Documentation](#documentation)
- [Security](#security)
- [中文说明](#中文说明)

## Product Scope

Eurogas Nexus is built for commercial European gas desks that need one workspace
for:

- infrastructure context across hubs, interconnection points, pipelines, LNG
  terminals, storage facilities, and balancing zones;
- DB-backed source monitoring for public and licensed providers;
- live or near-live market observations when customer credentials and
  entitlements allow access;
- route feasibility and route-cost comparison using capacity, tariff, access,
  and contract constraints;
- resource-pool-native portfolio optimization for physical gas, virtual hub
  positions, LNG regas, upstream offtake, screen purchases, and
  customer-imported trades;
- EFET-style contract capture so purchase contracts feed a portfolio pool before
  sales routes are optimized and PnL is attributed back to contracts;
- strategy backtesting, shadow-running, monitoring, and risk-control signals;
- bilingual glossary and operational context for European gas trading terms;
- LLM-assisted analysis through backend-controlled provider integrations.

Route cost and allocation are no longer UK-only concepts. The model is designed
for Europe-wide explicit-leg routing, with UK NTS, BBL, IUK, and additional TSO
tariff source slots represented in the runtime data model. Unsupported tariff
rows must be imported into PostgreSQL before the client presents them as
available.

Production gaps must be shown as source-health, entitlement, readiness, or data
quality issues. The application must not hide missing live data behind
fabricated client values. Demo records, when needed, are inserted into
PostgreSQL with demo provenance.

## Architecture

```mermaid
flowchart LR
    Sources["Public and licensed data sources"] --> Ingestion["Ingestion and normalization"]
    Ingestion --> DB[("PostgreSQL runtime store")]
    DB --> API["FastAPI backend"]
    API --> SDK["Python SDK"]
    API --> CLI["CLI"]
    API --> Web["Web client"]
    API --> Desktop["Windows / Linux desktop client"]
```

Core rules:

- PostgreSQL is the runtime source of truth.
- Public client paths use `/api`.
- Clients use backend API or SDK only.
- Clients do not connect directly to PostgreSQL.
- Provider credentials are backend-owned, write-only from client forms, and
  never printed.
- Backend import must not connect to PostgreSQL or run migrations.
- Migrations are explicit operator actions.
- Source failures must be visible and diagnosable.

## Repository Layout

```text
apps/                   Process entry points
  api/                  FastAPI runtime entry point
clients/
  web/                  React, Vite, MapLibre Web client
  desktop/              Tauri desktop shell
src/eurogas_nexus/
  api/                  API factory, profiles, and routes
  cli/                  Operator CLI
  db/                   SQLAlchemy, sessions, registry, health checks
  domain/               Business-domain models and services
  ingestion/            Source adapters and ingestion contracts
  runtime_store/        PostgreSQL-backed repositories
  sdk/                  Python SDK clients
alembic/                Migration environment
docs/                   Architecture, contracts, operations, release docs
scripts/                Operator and release scripts
tests/                  API, contract, integration, SDK, CLI, release tests
```

## Quick Start

Requirements:

- Python 3.11+
- Node.js 24+
- Rust stable for desktop builds
- PostgreSQL for runtime workflows

Install Python dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Start the API:

```powershell
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Start the Web client:

```powershell
npm --prefix clients/web ci
npm --prefix clients/web run dev
```

The Web client defaults to `/api` in browser mode and to
`http://127.0.0.1:8000/api` in the Tauri desktop shell.

## Database

Database URL precedence:

1. `RUNTIME_STORE_DATABASE_URL`
2. `DATABASE_URL`
3. `EUROGAS_NEXUS_DB_DSN`, legacy compatibility only

Validate a runtime database without writes:

```powershell
python scripts/ops/validate_v1_runtime_db.py --json
```

Seed local demo rows into the configured test database:

```powershell
python scripts/ops/seed_demo_runtime_data.py
```

The seed script writes public tariff references, public route templates,
DB-resident demo prices, a demo portfolio contract, glossary rows, and
route-candidate map edges. It does not call external APIs, run migrations, or
print secrets.

Run the live-shaped simulated EEX, ICE OCM, and ICIS price worker against the
same runtime market tables used by real connectors:

```powershell
$env:RUNTIME_STORE_DATABASE_URL = "postgresql+psycopg://eurogas:eurogas_dev@127.0.0.1:5432/eurogas_nexus"
python scripts/ops/ingest_simulated_market_prices.py --loop
```

These rows are marked `EEX_Sim`, `ICE_OCM_Sim`, and `ICIS_Sim` and include
tenor metadata for within-day, day-ahead, and month-ahead views. The default
simulation cadence is ICE OCM every 15 seconds, EEX every 60 seconds, and ICIS
daily. Use the same script without `--loop` for a one-batch smoke test, or
`--loop --max-iterations 3` for bounded validation. See
`docs/operations/SIMULATED_MARKET_PRICE_SOURCES.md`.

Rebuild route-candidate map edges after route candidates change:

```powershell
python scripts/ops/materialize_reference_edges.py
```

The materializer writes route-candidate corridors into `reference_edges` with
`route_geometry_state`, `geometry_quality`, and `geometry_warning` metadata.
Current generated edges are source-derived corridors or leg sequences, not
surveyed physical pipeline polylines.

Run migrations explicitly:

```powershell
alembic current
alembic upgrade head
```

Only run migrations against the intended runtime database.

## Data Sources

The Source Center is the UI surface for provider categories, credentials,
diagnostics, last-update status, record counts, and failure reasons.

| Category | Providers and scope |
| --- | --- |
| Prices | Platts, ICIS, Argus, EEX, ICE OCM, Trayport, Kpler |
| Price simulation | EEX_Sim, ICE_OCM_Sim, ICIS_Sim for source-shaped runtime testing |
| FX | ECB reference rates |
| Infrastructure | ENTSOG, GIE AGSI, GIE ALSI |
| Tariffs | BBL, IUK, National Gas NTS, GTS, NaTran, German TSOs, Fluxys Belgium, CNMC/Enagas |
| Weather | HDD/CDD modelling provider slot |
| LLM | DeepSeek first, with later provider expansion |

Public feeds may not require API keys. Licensed feeds require the customer's
own credentials, entitlements, and contractual permission.

## Clients

The Web client is the primary map-focused workspace. It has separate surfaces
for:

- Network: resource-pool map, active resource-path overlay, recommended sale
  paths, route/capacity warnings, indicative PnL, and decision support;
- Capacity: ENTSOG flow/capacity, TSO access, tariffs, GIE storage, and GIE LNG;
- Market: terminal-style European gas hub board, regional TTF spreads, ECB FX,
  and exchange/broker source posture;
- Scenario: route economics, LNG readiness, and pool optimization runs;
- Contracts: EFET-style resource, delivery, pricing, settlement, capacity
  terms, JSON draft import, and persisted resource-contract library;
- Strategy: backtest, shadow-run, monitoring, and risk controls;
- Review: warnings, route allocation evidence, and reports;
- Order Records: read-only screen-order observations and live PnL snapshots;
- Data Sources: provider categories, API-key posture, diagnostics, and refresh
  state;
- Glossary: bilingual operational definitions and linked context;
- Runtime: API, database, and ingestion readiness;
- Settings: language, theme, unit, currency, session defaults, service-access
  posture, and backend-boundary guardrails;
- Manual: customer-facing page map and operating boundary.

The desktop client packages the same Web workspace through Tauri and targets:

- Windows NSIS installer;
- Linux Debian package.

Desktop clients must use the backend API. They must not become a local database
or credential store.

## SDK and CLI

Install the package in editable mode:

```powershell
python -m pip install -e ".[dev]"
```

Use the CLI:

```powershell
eurogas-nexus --help
```

The SDK and CLI follow the released backend API contract and are intended for
operator checks, automation, internal tooling, notebooks, and integration tests.

## Testing

Recommended validation before pushing:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
npm --prefix clients/web run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Focused client and route-cost validation:

```powershell
pytest -q tests/contract/test_client_release_surface.py
pytest -q tests/integration/test_route_cost_db_api.py tests/api/test_route_cost_api.py
```

## Build and Release

GitHub Actions publishes preview releases from `main`:

- CI: Python linting and targeted backend/client contract tests;
- Web build: Vite production build and packaged Web artifact;
- Desktop build: Windows NSIS installer and Linux DEB package;
- Release: GitHub pre-release with generated artifacts.

Local release scripts mirror the workflow:

```powershell
./scripts/release/build_v1_release.ps1 -Bundle nsis
```

```bash
./scripts/release/build_v1_release.sh --bundle deb
```

Releases are published at
[github.com/AlexYuhuFeng/EurogasNexus/releases](https://github.com/AlexYuhuFeng/EurogasNexus/releases).

## Documentation

Start here:

- [Project directory](PROJECT_DIRECTORY.md)
- [API path policy](docs/api/API_PATH_POLICY.md)
- [API contract](docs/contracts/06_API_CONTRACT.md)
- [Database contract](docs/contracts/04_DB_CONTRACT.md)
- [Runtime store contract](docs/contracts/05_RUNTIME_STORE_CONTRACT.md)
- [Resource pool contract EN](docs/contracts/21_RESOURCE_POOL_CONTRACT-EN.md)
- [Resource pool contract CN](docs/contracts/21_RESOURCE_POOL_CONTRACT-CN.md)
- [Client API contract](docs/clients/CLIENT_API_CONTRACT.md)
- [Client tech stack](docs/clients/CLIENT_TECH_STACK.md)
- [Map-first trader cockpit spec EN](docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md)
- [Map-first trader cockpit spec CN](docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md)
- [UI/UX style guide EN](docs/clients/UI_UX_STYLE_GUIDE-EN.md)
- [UI/UX style guide CN](docs/clients/UI_UX_STYLE_GUIDE-CN.md)
- [Live PostgreSQL operations](docs/operations/LIVE_POSTGRESQL_V1.md)
- [Validation guide](docs/operations/VALIDATION.md)
- [Release readiness](docs/release/V1_RELEASE_READINESS.md)

## Security

This is a public repository. Do not commit:

- `.env` files;
- API keys, tokens, passwords, or provider credentials;
- real vendor data or raw licensed market data;
- internal commercial data;
- confidential contracts or counterparty terms;
- real strategy parameters;
- customer deployment details.

Report security issues through [SECURITY.md](SECURITY.md).

## 中文说明

Eurogas Nexus 是面向欧洲天然气交易与运营团队的 PostgreSQL 优先智能工作台，用于统一管理管网、枢纽、互联点、LNG 接收站、储气库、容量、费率、市场价格、汇率、合同、资源池、路线经济性、策略监控、数据源诊断和术语知识。

核心原则：

- 运行时事实数据必须进入 PostgreSQL。
- Web、Windows、Linux、SDK 和 CLI 都必须通过后端 API 或 SDK 访问数据。
- 客户端不得直接连接数据库。
- 客户端不得保存供应商 API Key 或客户凭据。
- 数据源故障、权限缺失、表缺失、刷新失败必须明确展示。
- 不得用伪造实时数据掩盖真实数据缺口。
- 如需演示数据，应写入 PostgreSQL，并标注 demo provenance。

当前 `v0.5-preview` 版本提供决策支持和市场分析能力，但不执行交易、不下单、不路由订单、不提交提名、不替代 ETRM、不提供法律意见，也不构成官方交易建议。

中文文档入口：

- [地图优先交易工作台规范](docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md)
- [UI/UX 风格指南](docs/clients/UI_UX_STYLE_GUIDE-CN.md)
- [LLM 分析与报告规范](docs/architecture/LLM_ANALYSIS_REPORTING_SPEC-CN.md)
- [市场实践审计](docs/architecture/MARKET_PRACTICE_AUDIT-CN.md)
- [市场定位数据导入说明](docs/operations/MARKET_POSITIONING_IMPORTS-CN.md)

## License

Proprietary. All rights reserved unless a separate written license grants
additional rights.
