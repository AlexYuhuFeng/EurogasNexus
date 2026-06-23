# Eurogas Nexus

Eurogas Nexus V1.0 is a DB-first, API-first, SDK-required European gas
decision-support platform for pipeline gas, LNG regas, beach delivery resources,
route economics, market marks, source posture, resource-pool optimization, and
human-reviewed strategy analysis. V1 includes the backend/API, PostgreSQL
runtime store, Python SDK, CLI, web workspace, and Windows client shell.

PostgreSQL is the runtime source of truth. Web, Windows, CLI, and SDK clients
must access runtime data through `/api/v1` or SDK calls. Clients must not open
PostgreSQL connections, read backend local data files, or store vendor
credentials.

## Start Here

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

GitHub Actions runs Python validation plus parallel client build jobs:

- Web artifact: `clients/web/dist`
- Windows client artifact: Tauri NSIS `.exe`
- Linux client artifact: Tauri Debian `.deb`

Core entry points:

- API app: `apps/api/main.py`
- backend package: `src/eurogas_nexus`
- DB models and runtime foundation: `src/eurogas_nexus/db`
- Alembic migrations: `alembic/versions`
- Python SDK: `src/eurogas_nexus/sdk`
- Web client: `clients/web`
- Windows shell: `clients/desktop`
- current handoff: `docs/architecture/CURRENT_PAUSE_POINT.md`
- project map: `PROJECT_DIRECTORY.md`
- ExecPlans: `.agent/plans/`

## API Prefix

Stable client routes use:

```text
/api/v1
```

Bootstrap compatibility remains for:

```text
/v1/health
```

New SDK, CLI, Web, and Windows code must target `/api/v1`.

## Build And Release

Every push to `main` runs `.github/workflows/release.yml`. The workflow validates
the backend, builds the Web client, builds the Windows NSIS installer, builds the
Linux DEB package, and publishes a GitHub Release with all release artifacts.

Local release builds use the same contract:

```powershell
./scripts/release/build_v1_release.ps1 -Bundle nsis
```

```bash
./scripts/release/build_v1_release.sh --bundle deb
```

Use `-InstallDependencies` or `--install-dependencies` only when `node_modules`
is missing or stale. The scripts do not start Docker, run live connectors, call
market providers, or print secrets.

## Current V1 Capabilities

- UK National Gas NTS route-cost support is UK-only in this release, but it is
  not hard-coded to Easington or Bacton. Any UK NTS entry/exit point can be
  priced when audited tariff rows exist in PostgreSQL.
- Route economics include entry capacity, exit capacity where applicable,
  National Gas commodity charges, contract tolerance allowance, live bid-based
  PnL marking, early recovered cash value, and TSO-access constraints.
- LNG regas readiness covers terminal access, slot/cargo window matching,
  send-out capacity, cross-month allocation, delivery mode, physical entry
  delivery requirements, pricing basis, and downstream TSO access.
- Portfolio/resource-pool optimization supports multiple upstream resources,
  contract-specific costs and tolerances, compatible sale options, route costs,
  early cash value, and access constraints.
- Imported external screen-order observations and portfolio PnL snapshots are
  DB-first, API/SDK-readable, and surfaced in the map-first cockpit as
  read-only decision-support context.
- Internal/operator imports for screen-order observations and indicative PnL
  snapshots are governed by fail-closed entitlement checks and write audit plus
  ingestion-run evidence before `/api/v1/portfolio/*` exposes them read-only.
  The internal import route is additionally protected by
  `EUROGAS_NEXUS_INTERNAL_API_TOKEN`, `X-Eurogas-Internal-Token`, and explicit
  `X-Eurogas-Principal` headers.
- Strategy lab supports backtest, shadow-run, and live-monitor evaluation
  contracts for SAP/ICIS day-ahead versus ICE OCM style intraday strategies,
  5-minute bar windows, scoring components, allocation targets, stop-loss
  controls, and warning output.
- DeepSeek is the first V1 live LLM provider slot. LLM analysis and report
  endpoints use backend snapshots, encrypted backend credentials, citations, and
  human-review guardrails. Offline/test mode returns deterministic snapshot
  output without provider calls.
- ECB FX, ENTSOG flows, and GIE storage/LNG are represented as PostgreSQL-backed
  runtime observations when ingested by an operator.
- Glossary terms are backend-served and available through API, SDK, Web, and
  Windows surfaces in English and Mandarin Chinese.
- Glossary context is operational and DB-derived: selecting `Easington Entry
  Point`, `ICIS Heren`, `NBP`, `ICE OCM`, or a customer-loaded point such as
  `St Fergus Entry Point` can show matched entities, capacity, selected-duration
  capacity usage, utilization percentage, related prices, live marks, route
  candidates, linked contracts, warnings, and data-quality metadata from the
  runtime API.

All strategy, PnL, route, LNG, resource-pool, and market outputs are
decision-support candidates requiring human review. They are not executable
orders, auto-trading actions, nomination submissions, official approvals, legal
advice, or official trading recommendations.

## Product Boundary

Do not add trade execution, order entry, order routing, trade capture,
nomination submission, official approval, legal advice, official trading
recommendations, auto-trading, ETRM replacement behavior, or company SSO/OIDC in
V1 unless a future approved milestone explicitly changes this boundary.

Do not commit secrets, real vendor data, internal commercial data, raw market
data, contracts, or real business strategy parameters. This is a public
repository.

## Documentation Map

ExecPlans: `.agent/plans/`

- current pause point: `docs/architecture/CURRENT_PAUSE_POINT.md`
- market-practice audit EN/CN:
  `docs/architecture/MARKET_PRACTICE_AUDIT-EN.md` and
  `docs/architecture/MARKET_PRACTICE_AUDIT-CN.md`
- map-first cockpit spec EN/CN:
  `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md` and
  `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md`
- market positioning cockpit spec EN/CN:
  `docs/clients/MARKET_POSITIONING_COCKPIT_SPEC-EN.md` and
  `docs/clients/MARKET_POSITIONING_COCKPIT_SPEC-CN.md`
- operational glossary context spec EN/CN:
  `docs/clients/OPERATIONAL_GLOSSARY_CONTEXT_SPEC-EN.md` and
  `docs/clients/OPERATIONAL_GLOSSARY_CONTEXT_SPEC-CN.md`
- market-positioning import operations EN/CN:
  `docs/operations/MARKET_POSITIONING_IMPORTS-EN.md` and
  `docs/operations/MARKET_POSITIONING_IMPORTS-CN.md`
- LLM analysis and reporting spec EN/CN:
  `docs/architecture/LLM_ANALYSIS_REPORTING_SPEC-EN.md` and
  `docs/architecture/LLM_ANALYSIS_REPORTING_SPEC-CN.md`
- client API contract: `docs/clients/CLIENT_API_CONTRACT.md`
- SDK design: `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`
- Web design: `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- Windows design: `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
- live PostgreSQL policy: `docs/operations/LIVE_POSTGRESQL_V1.md`
- release scope and acceptance:
  `docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md`,
  `docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md`, and
  `docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md`

## 中文摘要

Eurogas Nexus V1.0 以 PostgreSQL 作为运行时事实来源，以 API/SDK 作为访问边界。
当前路线成本能力限定在英国 National Gas NTS，但不再限定为 Easington/Bacton
示例；只要 PostgreSQL 中存在已审核的英国 NTS 费率行，系统即可计算相应
entry/exit 点的路线成本。

Web 和 Windows 客户端必须通过 API/SDK 访问数据，不得直接连接数据库。供应商
API Key 只能通过后端凭证接口保存。策略、PnL、路线、LNG regas、资源池优化、
市场信号和术语表输出均为需要人工复核的决策支持结果，不是订单执行、自动交易、
提名提交、官方审批、法律意见或官方交易建议。

术语表上下文也是数据库优先能力。选择 `Easington Entry Point`、`ICIS Heren`
或客户加载的其他点位时，系统会通过 API 展示匹配实体、容量、所选时间段的容量
使用量、价格、实时标记、路线、合同、预警和数据质量信息。
