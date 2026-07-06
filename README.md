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

Runtime truth lives in PostgreSQL. Web, Windows, Linux, SDK, and CLI clients read
runtime data through the backend API or SDK. Public client integrations target
`/api`; hidden compatibility routes such as `/api/v1` are not the documented
customer surface.

Current line: `v0.5-preview`

License: proprietary, all rights reserved. See [`LICENSE`](LICENSE).

Eurogas Nexus is not an ETRM replacement, execution venue, order router,
nomination-submission system, auto-trading system, legal-advice tool, or
official trading recommendation system.

## Product Scope

Eurogas Nexus is built for commercial European gas desks that need one workspace
for:

- infrastructure context across hubs, interconnection points, pipelines, LNG
  terminals, storage facilities, and balancing zones;
- DB-backed source monitoring for public and licensed providers;
- live or near-live market observations when customer access rights allow;
- route feasibility and route-cost comparison using capacity, tariff, access,
  and contract constraints;
- resource-pool-native portfolio optimization for physical gas, virtual hub
  positions, LNG regas, upstream offtake, screen purchases, and imported trade
  observations;
- EFET-style contract capture so purchase contracts feed a portfolio pool before
  sales routes are optimized and PnL is attributed back to contracts;
- strategy backtesting, shadow-running, monitoring, and risk-control signals;
- bilingual glossary and operational context for European gas trading terms;
- LLM-assisted analysis through backend-controlled provider integrations.

Route cost and allocation are Europe-wide explicit-leg concepts. The model
supports UK NTS, BBL, IUK, and additional TSO tariff source slots in the runtime
data model. Unsupported tariff rows must be imported into PostgreSQL before the
client presents them as available.

Production gaps must be shown as source-health, entitlement, readiness, or data
quality issues. The application must not hide missing live data behind fabricated
client values. Preview rows, when needed, are inserted into PostgreSQL with
explicit source provenance.

## Product Visuals

Eurogas Nexus is a visual, map-first decision-support product. README screenshots
should be synthetic or sanitized and must not contain licensed vendor material,
customer material, or real strategy parameters.

Recommended README visual set:

| Surface | Purpose | Suggested file |
| --- | --- | --- |
| Network map cockpit | European map-first workspace, resource-pool overlay, route candidates, warnings, and indicative PnL. | `docs/assets/readme/network-map-cockpit.png` |
| Scenario and route economics | Resource, destination, route, tariff, LNG readiness, and missing-input validation. | `docs/assets/readme/scenario-route-economics.png` |
| Review and report | Candidate comparison, warning stack, source references, lineage, and LLM-assisted commentary with human-review badges. | `docs/assets/readme/review-report.png` |

Authoritative UI contracts:

- [`docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md`](docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md)
- [`docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md`](docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md)
- [`docs/clients/UI_UX_STYLE_GUIDE-EN.md`](docs/clients/UI_UX_STYLE_GUIDE-EN.md)
- [`docs/clients/UI_UX_STYLE_GUIDE-CN.md`](docs/clients/UI_UX_STYLE_GUIDE-CN.md)

## Architecture

```mermaid
flowchart LR
    Sources["Public and licensed data sources"] --> Ingestion["Ingestion and normalization"]
    Ingestion --> DB[("PostgreSQL runtime store")]
    DB --> API["FastAPI backend /api"]
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
- Provider access material is backend-owned and never printed.
- Backend import must not open runtime database connections or run migrations.
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

```bash
python -m pip install -e ".[dev]"
```

Start the API:

```bash
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Start the Web client:

```bash
npm --prefix clients/web ci
npm --prefix clients/web run dev
```

The Web client defaults to `/api` in browser mode and to
`http://127.0.0.1:8000/api` in the Tauri desktop shell.

## Database and Runtime

Database URL precedence:

1. `RUNTIME_STORE_DATABASE_URL`
2. `DATABASE_URL`
3. `EUROGAS_NEXUS_DB_DSN`, legacy compatibility only

Useful operator commands:

```bash
python scripts/ops/validate_runtime_db.py --json
python scripts/ops/seed_preview_runtime_data.py
python scripts/ops/ingest_simulated_market_prices.py --loop
python scripts/ops/materialize_reference_edges.py
alembic current
alembic upgrade head
```

Compatibility command:

```bash
python scripts/ops/validate_v1_runtime_db.py --json
```

Only run migrations against the intended runtime database.

## Data Sources

The Source Center is the UI surface for provider categories, access posture,
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

Public feeds may not require access keys. Licensed feeds require the customer's
own rights and contractual permission.

## Clients

The Web client is the primary map-focused workspace. It has separate surfaces
for Network, Capacity, Market, Scenario, Contracts, Strategy, Review, Market
Positioning, Data Sources, Glossary, Runtime, Settings, and Manual.

The desktop client packages the same Web workspace through Tauri and targets
Windows NSIS and Linux Debian packages. Desktop clients must use the backend API;
they must not become a local database or access-material store.

## SDK and CLI

```bash
python -m pip install -e ".[dev]"
eurogas-nexus --help
```

The SDK and CLI follow the released backend API contract and are intended for
operator checks, automation, internal tooling, notebooks, and integration tests.

## Testing

Recommended validation before pushing:

```bash
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
npm --prefix clients/web run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Focused client and route-cost validation:

```bash
pytest -q tests/contract/test_client_release_surface.py
pytest -q tests/integration/test_route_cost_db_api.py tests/api/test_route_cost_api.py
```

Future hardening should add type-checking, safety scanning, dependency audit,
and doc-hygiene checks to CI. Track that work in
[`docs/release/PRODUCTION_READINESS_BACKLOG.md`](docs/release/PRODUCTION_READINESS_BACKLOG.md).

## Build and Release

GitHub Actions publishes preview releases from the manual `Build and Release`
workflow.

- CI: Python linting and targeted backend/client contract tests;
- Web build: Vite production build and packaged Web artifact;
- Desktop release build: Windows NSIS installer and Linux DEB package;
- Release: GitHub pre-release with generated artifacts.

Local release scripts mirror the workflow:

```powershell
./scripts/release/build_release.ps1 -Bundle nsis
```

```bash
bash scripts/release/build_release.sh --bundle deb
```

Compatibility scripts are retained temporarily:

```powershell
./scripts/release/build_v1_release.ps1 -Bundle nsis
```

```bash
bash scripts/release/build_v1_release.sh --bundle deb
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
- [Live PostgreSQL operations](docs/operations/LIVE_POSTGRESQL.md)
- [Validation guide](docs/operations/VALIDATION.md)
- [Release readiness](docs/release/RELEASE_READINESS.md)
- [Production readiness backlog](docs/release/PRODUCTION_READINESS_BACKLOG.md)
- [Documentation audit](docs/architecture/DOCUMENTATION_AUDIT.md)

## Governance and Production Readiness

- Repository boundary and contribution rules: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- License and ownership: [`LICENSE`](LICENSE)
- Current release-candidate evidence: [`docs/release/RELEASE_READINESS.md`](docs/release/RELEASE_READINESS.md)
- Actionable production backlog: [`docs/release/PRODUCTION_READINESS_BACKLOG.md`](docs/release/PRODUCTION_READINESS_BACKLOG.md)

Release-candidate status means the tested local scope is coherent. It does not
mean production multi-user deployment is complete.

## Security

This is a public repository. Do not commit restricted provider access material,
licensed vendor payloads, internal commercial material, confidential contracts or
counterparty terms, customer deployment details, real strategy parameters, or
non-public runtime configuration.

Report security issues through [`SECURITY.md`](SECURITY.md).

## 中文说明

Eurogas Nexus 是面向欧洲天然气交易与运营团队的 PostgreSQL 优先智能工作台，用于统一管理管网、枢纽、互联点、LNG 接收站、储气库、容量、费率、市场价格、汇率、合同、资源池、路线经济性、策略监控、数据源诊断和术语知识。

核心原则：

- 运行时事实数据必须进入 PostgreSQL。
- Web、Windows、Linux、SDK 和 CLI 都必须通过后端 API 或 SDK 访问数据。
- 稳定公开客户端路径为 `/api`。
- 客户端不得直接连接数据库。
- 客户端不得保存供应商访问材料。
- 数据源故障、权限缺失、表缺失、刷新失败必须明确展示。
- 不得用伪造实时数据掩盖真实数据缺口。
- 如需预览或测试数据，应写入 PostgreSQL，并标注明确的数据源 provenance。

当前 `v0.5-preview` 版本提供决策支持和市场分析能力，但不执行交易、不下单、不路由订单、不提交提名、不替代 ETRM、不提供法律意见，也不构成官方交易建议。

中文文档入口：

- [地图优先交易工作台规范](docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md)
- [UI/UX 风格指南](docs/clients/UI_UX_STYLE_GUIDE-CN.md)
- [LLM 分析与报告规范](docs/architecture/LLM_ANALYSIS_REPORTING_SPEC-CN.md)
- [市场实践审计](docs/architecture/MARKET_PRACTICE_AUDIT-CN.md)
- [市场定位数据导入说明](docs/operations/MARKET_POSITIONING_IMPORTS-CN.md)

## License

Proprietary. All rights reserved unless a separate written agreement grants
additional rights. See [`LICENSE`](LICENSE).
