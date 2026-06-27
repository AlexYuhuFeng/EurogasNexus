# Eurogas Nexus

[![CI](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/ci.yml/badge.svg)](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/ci.yml)
[![Build and Release](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/release.yml/badge.svg)](https://github.com/AlexYuhuFeng/EurogasNexus/actions/workflows/release.yml)

Eurogas Nexus is a DB-first European gas decision-support workspace for route
economics, source diagnostics, portfolio context, strategy shadow-run, glossary
context, and operator-reviewed market analysis.

PostgreSQL is the runtime source of truth. Every client surface uses the backend
API or SDK. Web, Windows, CLI, and SDK clients must not connect directly to
PostgreSQL, read runtime data files, or store vendor credentials.

## What It Does

- Map-first European gas cockpit for hubs, interconnection points, LNG
  terminals, flows, capacity, tariffs, and route options.
- Source Center for price, FX, infrastructure, tariff, weather, and LLM provider
  status, credentials, runtime record counts, and ingestion diagnostics.
- UK National Gas NTS route-cost support for audited tariff rows in PostgreSQL.
  The current tariff model is UK-only, but it is not restricted to Easington or
  Bacton.
- Contract/resource economics for beach delivery, LNG regas, route capacity,
  early cash value, and portfolio/resource-pool optimization.
- Strategy lab contracts for backtest, shadow-run, and live-monitor evaluation
  using sourced prices, screen marks, time windows, scoring components, and risk
  controls.
- Operational glossary available through API, SDK, Web, and Windows clients in
  English and Mandarin Chinese.
- DeepSeek is the first V1 LLM provider slot. LLM analysis is backend-mediated,
  credential-gated, citation-oriented, and human-review only.

All strategy, PnL, route, LNG, resource-pool, market, and LLM outputs are
decision-support candidates requiring human review. They are not executable
orders, auto-trading actions, nomination submissions, official approvals, legal
advice, or official trading recommendations.

## Quick Start

```powershell
python -m pip install -e ".[dev]"
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Run the API:

```powershell
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Run the Web client:

```powershell
npm --prefix clients/web ci
npm --prefix clients/web run dev
```

Build the Windows desktop client:

```powershell
npm --prefix clients/desktop ci
npm --prefix clients/desktop run build -- --bundles nsis
```

## Runtime Database

Database URL precedence:

1. `RUNTIME_STORE_DATABASE_URL`
2. `DATABASE_URL`
3. `EUROGAS_NEXUS_DB_DSN` legacy fallback

The app import path does not connect to the database and does not run
migrations. Runtime DB validation is explicit:

```powershell
python scripts/ops/validate_v1_runtime_db.py --json
```

Source data should flow as:

```text
official/licensed source -> ingestion/normalization -> PostgreSQL -> API/SDK -> clients
```

Test/demo data belongs in the test PostgreSQL instance or test fixtures. The
production runtime must not use synthetic fallback data for source availability,
flows, capacity, tariffs, storage, LNG, FX, or provider status.

## Data Sources

The Source Center is backed by `/api/sources` and `/api/credentials/providers`.
It groups sources by operational category:

- Prices: Platts, ICIS, Argus, EEX, ICE OCM, Trayport, Kpler
- FX: ECB
- Infrastructure: ENTSOG, GIE AGSI/ALSI
- Tariffs: National Gas NTS
- Weather: HDD/CDD-capable weather provider slot
- LLM: DeepSeek

Credentials are write-only and backend-owned. Public feeds such as ECB and
ENTSOG do not require API keys for the supported public use cases. Licensed
sources require the customer to configure credentials and entitlement outside
the client runtime.

## API And SDK Boundary

Stable client routes use:

```text
/api
```

New clients, SDK calls, and CLI commands must target `/api`. Clients should use
the SDK or typed HTTP client surface, never direct database access.

Core entry points:

- API app: `apps/api/main.py`
- backend package: `src/eurogas_nexus`
- DB models and runtime foundation: `src/eurogas_nexus/db`
- Alembic migrations: `alembic/versions`
- Python SDK: `src/eurogas_nexus/sdk`
- Web client: `clients/web`
- Windows/Linux desktop shell: `clients/desktop`

## Build And Release

Every push to `main` runs:

- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`

Release workflow outputs:

- Web artifact: `clients/web/dist`
- Windows artifact: Tauri NSIS `.exe`
- Linux artifact: Tauri Debian `.deb`
- GitHub Release with collected artifacts

Local release builds use the same contract:

```powershell
./scripts/release/build_v1_release.ps1 -Bundle nsis
```

```bash
./scripts/release/build_v1_release.sh --bundle deb
```

The release scripts do not start Docker, call live market providers, run live
connectors, or print secrets.

## Security And Data Policy

This is a public repository. Do not commit secrets, `.env` files, API keys,
tokens, real vendor data, raw market data, internal commercial data, contracts,
or real business strategy parameters.

Provider credentials must stay in the backend credential store. API responses
may return redacted previews, local validation state, and diagnostics, but never
credential values.

## Documentation Map

ExecPlans: `.agent/plans/`

- Current status: `docs/architecture/CURRENT_PAUSE_POINT.md`
- Product boundary: `docs/policies/PRODUCT_BOUNDARY_POLICY.md`
- DB contract: `docs/contracts/04_DB_CONTRACT.md`
- Runtime store contract: `docs/contracts/05_RUNTIME_STORE_CONTRACT.md`
- API contract: `docs/contracts/06_API_CONTRACT.md`
- Client API contract: `docs/clients/CLIENT_API_CONTRACT.md`
- Web design: `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- Windows design: `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
- UI style guide: `docs/clients/UI_UX_STYLE_GUIDE-EN.md` and
  `docs/clients/UI_UX_STYLE_GUIDE-CN.md`
- Live PostgreSQL policy: `docs/operations/LIVE_POSTGRESQL_V1.md`
- Release scope: `docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md`
- Release readiness: `docs/release/V1_RELEASE_READINESS.md`

## 中文摘要

Eurogas Nexus 是以 PostgreSQL 为运行时事实来源、以 API/SDK 为客户端边界的欧洲天然气
决策支持工作台。Web、Windows、CLI 和 SDK 都不得直接连接数据库，也不得在客户端保存
供应商密钥。数据源应按照“官方或授权来源 -> 入库与标准化 -> PostgreSQL -> API/SDK ->
客户端”的链路运行。

当前版本提供数据源中心、地图工作台、英国 National Gas NTS 路线成本、资源组合经济性、
策略影子运行、运行时数据库诊断、术语库和 DeepSeek LLM 分析入口。所有输出均为需要人工
复核的决策支持结果，不是自动交易、订单执行、提名提交、官方审批、法律意见或官方交易建议。
