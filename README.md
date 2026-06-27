# Eurogas Nexus

Eurogas Nexus V1.0 is a DB-first, API-first, SDK-required European gas
decision-support platform for pipeline gas, LNG regas, beach delivery resources,
route economics, market marks, source posture, resource-pool optimization, and
human-reviewed strategy analysis. V1 includes the backend/API, PostgreSQL
runtime store, Python SDK, CLI, web workspace, and Windows client shell.

PostgreSQL is the runtime source of truth. Web, Windows, CLI, and SDK clients
must access runtime data through `/api` or SDK calls. Clients must not open
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
/api
```

Bootstrap compatibility remains for:

```text
/api/health
```

New SDK, CLI, Web, and Windows code must target `/api`.

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
  ingestion-run evidence before `/api/portfolio/*` exposes them read-only.
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

## 涓枃鎽樿

Eurogas Nexus V1.0 浠?PostgreSQL 浣滀负杩愯鏃朵簨瀹炴潵婧愶紝浠?API/SDK 浣滀负鎵€鏈夊鎴风
鐨勬暟鎹闂竟鐣屻€俉eb銆乄indows銆丆LI 鍜?SDK 涓嶅緱鐩存帴杩炴帴鏁版嵁搴擄紝涔熶笉寰椾粠鏈湴鏂囦欢璇诲彇
杩愯鏃跺競鍦烘暟鎹€?
鍏紑鎴栧凡鎺堟潈鐨勬暟鎹簮搴旀寜鈥滃畼鏂规潵婧愭垨宸叉巿鏉冩潵婧?-> PostgreSQL -> API/SDK -> 瀹㈡埛绔€?鐨勯摼璺繍琛屻€?ECB FX銆丒NTSOG 娴侀噺/杩炴帴鐐?TSO access銆丟IE AGSI/ALSI銆佸叕寮€ TSO tariff 绛夊熀纭€璁炬柦
鍜屽弬鑰冩暟鎹笉搴斾娇鐢ㄨ繍琛屾椂妯℃嫙 fallback銆備环鏍笺€佷氦鏄撳睆骞曘€佺粡绾晢銆並pler銆丳latts銆?ICIS銆丄rgus銆両CE銆丒EX銆乀rayport 绛夊晢涓氭暟鎹渶瑕佸鎴峰嚟璇併€佹巿鏉冨拰鎺ュ叆鍚堝悓鍚庢墠鑳借繘鍏?姝ｅ紡杩愯閾捐矾銆?
褰撳墠璺嚎鎴愭湰鑳藉姏闄愬畾鍦ㄨ嫳鍥?National Gas NTS锛屼絾涓嶉檺鍒朵簬 Easington 鎴?Bacton銆?鍙 PostgreSQL 涓瓨鍦ㄥ凡瀹℃牳鐨勮嫳鍥?NTS entry/exit tariff 琛岋紝绯荤粺鍗冲彲鎸夌浉搴旂偣浣?璁＄畻璺嚎鎴愭湰銆傛墍鏈夌瓥鐣ャ€丳nL銆佽矾绾裤€丩NG regas銆佽祫婧愭睜浼樺寲銆佸競鍦轰俊鍙峰拰鏈涓婁笅鏂?杈撳嚭鍧囦负闇€瑕佷汉宸ュ鏍哥殑鍐崇瓥鏀寔缁撴灉锛屼笉鏄鍗曟墽琛屻€佽嚜鍔ㄤ氦鏄撱€佹彁鍚嶆彁浜ゃ€佸畼鏂瑰鎵广€?娉曞緥鎰忚鎴栧畼鏂逛氦鏄撳缓璁€?