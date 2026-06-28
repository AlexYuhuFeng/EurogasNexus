# Eurogas Nexus

[![CI](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/ci.yml/badge.svg)](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/ci.yml)
[![Build and Release](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/release.yml/badge.svg)](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/release.yml)
[![Release](https://img.shields.io/github/v/release/AlexYuhuFeng/EurogasNexus?include_prereleases&label=release)](https://github.com/AlexYuhuFeng/EurogasNexus/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/runtime-PostgreSQL-4169E1)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-Proprietary-lightgrey)](#license)

Eurogas Nexus is a PostgreSQL-first intelligence workspace for European gas
portfolio, infrastructure, route economics, source diagnostics, strategy
monitoring, and trader-reviewed decision support.

It is built for commercial gas teams that need a single operating surface for
European gas network context, source health, contract economics, resource-pool
views, route-cost comparison, glossary context, and research-grade market
analysis across Web, Windows, Linux, SDK, and CLI clients.

> Current release line: `v0.5-preview`.
> The preview line is not an ETRM replacement, trade execution system, order
> router, nomination platform, legal-advice tool, or automated trading system.

## Contents

- [What It Does](#what-it-does)
- [Current Status](#current-status)
- [Architecture](#architecture)
- [Repository Layout](#repository-layout)
- [Quick Start](#quick-start)
- [Runtime Database](#runtime-database)
- [Data Sources](#data-sources)
- [Clients](#clients)
- [SDK And CLI](#sdk-and-cli)
- [Development](#development)
- [Build And Release](#build-and-release)
- [Documentation](#documentation)
- [Security And Data Policy](#security-and-data-policy)
- [Chinese Summary](#chinese-summary)
- [License](#license)

## What It Does

Eurogas Nexus provides a DB-backed workspace for:

- European gas network map context across hubs, interconnection points, LNG
  terminals, storage facilities, and pipeline relationships;
- source monitoring for public and licensed providers, including credential
  status, ingestion health, update timing, and data-quality flags;
- UK National Gas NTS route-cost calculation from tariff records, not limited
  to a small set of example entry or exit points;
- contract and resource-pool modelling for physical, virtual, LNG, hub, and
  portfolio supply structures;
- indicative PnL, cash timing, early cash-value, balancing exposure, route
  feasibility, TSO access, and capacity-position checks;
- strategy backtest, shadow-run, and real-time monitoring surfaces;
- bilingual glossary and operational context for institutions, hubs, terminals,
  contracts, clearing, prices, trading concepts, and infrastructure terms;
- LLM-assisted analysis through backend-controlled provider integrations.

Decision support is advisory. Human review remains mandatory for trading,
operations, nominations, portfolio allocation, and risk decisions.

## Current Status

| Area | Status |
| --- | --- |
| Backend API | FastAPI application with stable `/api` route policy |
| Runtime store | PostgreSQL-first SQLAlchemy and Alembic foundation |
| SDK | Python SDK surface for released backend workflows |
| CLI | Operator checks and release/runtime diagnostics |
| Web client | React + Vite map-focused workspace |
| Desktop client | Tauri shell for Windows and Linux packages |
| Source control plane | Provider registry, credential posture, and ingestion status |
| Route cost | UK National Gas NTS route-cost support |
| Releases | GitHub Actions builds Web, Windows, and Linux preview assets |

Known preview limitations are tracked in the release and architecture docs.
Gaps must be explicit; production-like modes must not hide missing data behind
silent file or generated-data fallbacks.

## Architecture

```text
public and licensed data sources
        |
        v
ingestion adapters and normalization
        |
        v
PostgreSQL runtime store
        |
        v
FastAPI backend  <---->  Python SDK / CLI
        |
        v
Web client and Tauri desktop clients
```

Core rules:

- PostgreSQL is the runtime source of truth.
- Clients access runtime data through the backend API or SDK.
- Clients do not connect directly to PostgreSQL.
- Clients do not store provider credentials.
- Backend imports must not connect to the database or run migrations.
- Migrations are explicit operator actions.
- Public client routes use `/api`; versioned compatibility paths are hidden.
- Runtime gaps are reported as data-quality or readiness issues.
- Demo data, when needed, is loaded into PostgreSQL as demo records and is not
  treated as production truth.

## Repository Layout

```text
apps/
  api/                 FastAPI entry point
  scheduler/           scheduled runtime job surface
  worker/              background worker surface
clients/
  web/                 React + Vite Web workspace
  desktop/             Tauri desktop shell for Windows and Linux
src/eurogas_nexus/
  api/                 API app factory and route modules
  cli/                 command-line operator surface
  db/                  SQLAlchemy models, sessions, registry, health checks
  ingestion/           data-source adapters and ingestion contracts
  runtime_store/       PostgreSQL-backed repository contracts
  sdk/                 Python SDK clients
alembic/               database migration environment
docs/                  architecture, contracts, operations, client, release docs
infra/                 deployment references
scripts/               operations and release scripts
tests/                 API, contract, integration, SDK, CLI, release, security tests
```

## Quick Start

Requirements:

- Python 3.11+
- Node.js 20+
- Rust stable, required for desktop builds
- PostgreSQL, required for runtime validation and live-data workflows

Install the Python package:

```powershell
python -m pip install -e ".[dev]"
```

Run the backend validation set:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
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

Build the Web client:

```powershell
npm --prefix clients/web run build
```

Build the Windows desktop installer:

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
3. `EUROGAS_NEXUS_DB_DSN`, legacy fallback only

Validate a runtime database:

```powershell
python scripts/ops/validate_v1_runtime_db.py --json
```

The validation script is read-only. It checks connectivity, required table
presence, and Alembic revision status. It does not write records and does not
run migrations.

Database URLs are redacted before display. Do not print or commit full database
DSNs.

## Data Sources

The Source Center is the operational home for provider configuration,
credential posture, diagnostics, update status, and record counts.

| Category | Providers and scope |
| --- | --- |
| Prices | Platts, ICIS, Argus, EEX, ICE OCM, Trayport, Kpler |
| FX | ECB reference rates |
| Infrastructure | ENTSOG, GIE AGSI, GIE ALSI |
| Tariffs | National Gas NTS and future European TSO tariff sources |
| Weather | HDD/CDD modelling provider slot |
| LLM | DeepSeek first; other providers can be added through backend integration |

Public feeds such as supported ECB and ENTSOG endpoints may not require API
keys. Licensed feeds require customer-owned credentials and entitlements.

Credential rules:

- Credentials are entered through governed client surfaces.
- Raw secrets are stored and maintained by the backend.
- Client screens may show status and redacted previews only.
- Missing provider access must be visible as source-health or entitlement
  issues, not hidden behind fabricated live data.

## Clients

### Web

The Web client is the primary browser workspace. It is map-focused and includes
specialized workspaces for:

- Network overview and topology quality;
- Market and price monitoring;
- Scenario and route economics;
- Strategy lab and shadow-run state;
- Source diagnostics and provider credentials;
- Glossary;
- Runtime readiness;
- Settings, language, units, and light/dark theme.

### Desktop

The desktop client packages the Web workspace through Tauri. The release
workflow builds:

- Windows NSIS installer;
- Linux Debian package.

Desktop clients must use the backend API. They must not connect directly to
PostgreSQL and must not become a local data store for provider secrets.

## SDK And CLI

The Python SDK provides typed access to released backend workflows for
automation, notebooks, and internal tooling.

The CLI supports operator-facing checks such as:

- API health;
- database readiness;
- source posture;
- scenario and runtime inspection;
- release validation.

Both SDK and CLI target the backend API contract. They do not bypass the API to
read client files as runtime truth.

## Development

Recommended local checks before pushing:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
npm --prefix clients/web run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Additional focused test areas:

```powershell
pytest -q tests/workflows tests/unit tests/ingestion tests/streaming
pytest -q tests/contract/test_client_release_surface.py
pytest -q tests/contract/test_docs_alignment.py
```

Development policy:

- Keep data models DB-first.
- Keep source gaps explicit.
- Keep API imports database-safe.
- Keep client behavior aligned with `/api`.
- Do not add trade execution, order routing, nomination submission, or company
  SSO/OIDC until those are explicitly scoped and governed.

## Build And Release

GitHub Actions runs on `main`:

- `CI`: Python checks, targeted tests, Web build, and desktop build matrix.
- `Build and Release`: release validation, Web artifact packaging, Windows
  installer build, Linux package build, and GitHub pre-release publication.

Local release scripts mirror the workflow contract:

```powershell
./scripts/release/build_v1_release.ps1 -Bundle nsis
```

```bash
./scripts/release/build_v1_release.sh --bundle deb
```

Published preview releases are available at:

[github.com/AlexYuhuFeng/EurogasNexus/releases](https://github.com/AlexYuhuFeng/EurogasNexus/releases)

## Documentation

Start with these documents:

ExecPlans: `.agent/plans/`

- [Project Directory](PROJECT_DIRECTORY.md)
- [Current Pause Point](docs/architecture/CURRENT_PAUSE_POINT.md)
- [Product Boundary Policy](docs/policies/PRODUCT_BOUNDARY_POLICY.md)
- [Architecture Decision Record](docs/architecture/ARCHITECTURE_DECISION_RECORD.md)
- [API Path Policy](docs/api/API_PATH_POLICY.md)
- [API Contract](docs/contracts/06_API_CONTRACT.md)
- [Client API Contract](docs/clients/CLIENT_API_CONTRACT.md)
- [Web Client Design Spec](docs/clients/WEB_CLIENT_DESIGN_SPEC.md)
- [Windows Client Design Spec](docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md)
- [UI/UX Style Guide EN](docs/clients/UI_UX_STYLE_GUIDE-EN.md)
- [UI/UX Style Guide CN](docs/clients/UI_UX_STYLE_GUIDE-CN.md)
- [Live PostgreSQL Policy](docs/operations/LIVE_POSTGRESQL_V1.md)
- [Validation Guide](docs/operations/VALIDATION.md)
- [Release Readiness](docs/release/V1_RELEASE_READINESS.md)

## Security And Data Policy

This is a public repository. Do not commit:

- `.env` files;
- API keys, tokens, passwords, or provider credentials;
- real vendor data or raw licensed market data;
- internal commercial data;
- contracts or confidential counterparty terms;
- real trading strategy parameters;
- customer deployment details.

Report security issues through [SECURITY.md](SECURITY.md).

## Chinese Summary

Eurogas Nexus 是面向欧洲天然气交易与运营团队的 PostgreSQL 优先型智能工作台，
用于统一展示管网、LNG、库容、枢纽、互联点、价格、汇率、合同、资源池、
路线经济性、策略影子运行、数据源诊断和术语知识。

项目的运行时事实来源是 PostgreSQL。Web、Windows、Linux、SDK 和 CLI 客户端
必须通过后端 API 或 SDK 访问数据，不能直接连接数据库，也不能在客户端保存
供应商 API Key 或其他敏感凭据。

当前版本是 `v0.5-preview`。它提供交易决策支持和市场分析，但不执行交易，
不下单，不路由订单，不提交提名，不替代 ETRM，不提供法律意见，也不构成官方
交易建议。生产交付时，客户应连接自己的 PostgreSQL 和数据源凭据，通过后端
数据源层把真实数据写入数据库。

## License

Proprietary. All rights reserved unless a separate written license grants
additional rights.
