# 意向用户视角工作流验收（三 persona 浏览器实测）

任务：`task-3` ｜ 验收人：`user-uat`（意向用户代表）｜ 日期：2026-10-07
被测修订：工作树 `C:\Users\qqshu\Desktop\Dev Work\EurogasNexus`（含未提交改动）
产出范围：仅本文件。所有探针脚本在 `.dnx-out/persona/`，原始证据在 `.dnx-out/persona-out/`（均不在仓库源码目录内）。

---

## 0. 一句话结论

**现在不能把这三类用户直接放进去用。** 盘面/研究/策略三个 workspace 都渲染得很完整、也几乎没有静默失败——恰恰相反，产品在"把话说清楚"上做了大量工作（分层新鲜度徽章、结构化校验问题码、manifest 哈希、覆盖率、泄漏问题）——但**在三个真实用户最依赖的那一个数字上，界面给出了会让人做错决定的结果**：

1. 交易员：同一屏上 `TTF–NBP day-ahead` 同时是 **−2.09 / +1.14 / +2.11** 三个数，其中 **−2.09 是错的符号**，而且它来自服务端返回行序（非确定性），另外 5 个枢纽用的是另一种算法。
2. 时序工程师：快照状态写 `COMPLETE`，但自带质量报告写 `build_blocked: true`、`missing_percentage: 100`、`coverage 0`；同一 spec 二次构建 **HTTP 500 `IntegrityError`**，界面却让用户去看一个空的结构化问题列表。整条 lineage 全是 `sim:*`，但快照层面**没有任何 Simulated 标记**。
3. 策略分析师：**全局没有样本外 / 留出 / 滚动前推**，策略工作台**没有泄漏词汇**，`Max drawdown 0 GBP` 出现在运行历史和 KPI 对比里但**没有任何地方说明它怎么算**；一次评估窗口 365 天里有 **306 天（84%）落在平台第一条行情之前**，仍然落库成 `COMPLETED_WITH_WARNINGS` + `+51,009 GBP`。

按严重度：**产品缺陷 8 条（Critical 1 / High 4 / Medium 3）**，**环境限制 3 条**。

---

## 1. 验收环境、启动方式与证据路径

### 1.1 栈

| 组件 | 事实 |
|---|---|
| 内嵌 PostgreSQL 16.2 | `127.0.0.1:51356`（`.dnx-out/pg-endpoint.txt`），库 `nexus_browser` |
| API | `uvicorn apps.api.main:app --host 127.0.0.1 --port 8000` |
| Web | Vite dev `http://127.0.0.1:3000` |
| Chromium | Playwright 1.55.0 headless shell（`scripts/ci/browser-acceptance/node_modules/playwright`） |
| 登录 | 真实登录表单 `#sign-in-username` / `#sign-in-password` / `.sign-in-dev-form button[type=submit]`，未注入 session |

### 1.2 启动命令（全部实际执行）

```bat
:: API（加载 .dnx-out/user-uat.env，其中 RUNTIME_STORE_DATABASE_URL 指向 51356）
cmd /c ".dnx-out\run_api_uat.cmd"

:: Web
Start-Process cmd.exe -ArgumentList "/c",".dnx-out\run_web_uat.cmd" -RedirectStandardOutput ".dnx-out\vite.log" ...

:: persona 探针
cmd /c ".dnx-out\persona\run.cmd A-trader.mjs"
cmd /c ".dnx-out\persona\run.cmd A-spreads.mjs"
cmd /c ".dnx-out\persona\run.cmd A-spread-order4.mjs"
cmd /c ".dnx-out\persona\run.cmd A-fx.mjs"
cmd /c ".dnx-out\persona\run.cmd B-engineer.mjs preseed"
cmd /c ".dnx-out\seed_research.cmd"          :: scripts/research/seed_research_catalog.py
cmd /c ".dnx-out\persona\run.cmd B-engineer.mjs postseed"
cmd /c ".dnx-out\persona\run.cmd B-dup.mjs"
cmd /c ".dnx-out\persona\run.cmd C-analyst.mjs"
cmd /c ".dnx-out\persona\run.cmd C-analyst3.mjs"
cmd /c ".dnx-out\persona\run.cmd C-analyst4.mjs"
```

健康检查：`GET /api/health → 200 {"status":"ok","profile":"development","authentication":"enforced"}`；`GET http://127.0.0.1:3000/ → 200`。

### 1.3 CORS 坑（已规避，记录备查）

`.dnx-out/browser-acceptance.env` 中已设 `EUROGAS_NEXUS_CORS_ORIGINS=http://127.0.0.1:3000`。**全程 0 条 `origin_not_allowed` / 403**。所有 persona 证据文件的 `httpErrors` 汇总（`verify_http.py`）：

```
A-trader.json             {'401':1,'404':2,'failed:ERR_FAILED':2,'failed:ERR_ABORTED':33}
A-trader-spreads.json     {'401':1,'404':2,'failed:ERR_FAILED':2,'failed:ERR_ABORTED':32}
B-engineer-preseed.json   {'401':1,'404':2,'failed:ERR_FAILED':2,'failed:ERR_ABORTED':4}
B-engineer-postseed.json  {'401':1,'404':4,'500':1,'failed:ERR_FAILED':4,'failed:ERR_ABORTED':16}
C-analyst.json            {'401':1,'404':3,'failed:ERR_FAILED':2,'failed:ERR_ABORTED':34}
recon.json                {'401':1,'404':4,'failed:ERR_FAILED':4,'failed:ERR_ABORTED':18}
```

- `401` 各文件 1 条：登录完成前的 `/api/me`，正常。
- `404`：`node_modules/.vite/deps/maplibre-gl-worker.mjs`（Vite dep optimizer，环境限制 E-4）。
- `ERR_ABORTED`：workspace 导航取消在途请求，正常。
- **`500` 1 条：就是 B-D1 的二次构建**，在 `B-engineer-postseed` 与 `B-dup` 两次独立运行中都出现。

前一轮 101 条 403 确为环境变量缺失所致，本轮未复现。

### 1.4 我对运行时数据做的改动（必须声明）

以上"交付态"（preseed）先测，然后再跑**仓库里已有的** `scripts/research/seed_research_catalog.py` 补充 CR-14 研究目录，目的只是区分"部署没播种"与"产品做不到"。新增行（全部 additive）：

| 表 | 变化 |
|---|---|
| `canonical_entities` | +6（hub）、+interconnector 映射 |
| `feature_definitions` | +2（`NBP_TTF_DA_SPREAD`、`ROUTE_MARGIN`） |
| `target_definitions` | +3（`NBP_DA_PRICE_D1`、`TTF_DA_PRICE_D1`、`NBP_TTF_SPREAD_D1`） |
| `series_definitions` | +3 |
| `dataset_snapshots` | +1（`dataset-snapshot-121d5b494c8a-uat-persona-b-postseed`） |
| `strategies` / `strategy_versions` / `strategy_runs` | +1 / +1 / +2 |
| `backtest_series` / `backtest_decision_events` / `backtest_attribution` | +365 / +365 / +483 |

交付态本身（未被我改动时）：`market_observations 2382`、24 个源、`identity_principals 1`（ADMIN+ANALYST），而 `feature_definitions / target_definitions / dataset_snapshots / strategies / strategy_runs / upstream_contract_revisions` 全部为 **0 行**。

---

## 2. 判定口径

- **产品缺陷**：真实用户能走到的路径上，产品给出的东西是错的、自相矛盾的、或会让人得出错误结论；且不依赖本机特殊性。
- **环境限制**：只在"本机 / 本次验收环境"成立，换 CI 或标准安装即消失，或属于 Windows/工具链限制。
- 未跑通 ≠ 缺陷。**能跑通但数字会误导 = 缺陷**，本轮多数发现属于后者。

---

## 3. Persona A：欧洲天然气交易员

> 关注：TTF/NBP/PEG 等枢纽的日前与日内决策支持。
> 四个必答问题：期限？报价类型（bid/ask/mid/评估价）？气日时区？数据有多旧？

### 3.1 实测结果：**可完成 6 / 受阻断 0 / 但存在 3 条会误导决策的产品缺陷**

#### ✅ 可完成的工作流（附观测）

| # | 工作流 | 证据 |
|---|---|---|
| A-1 | 真实表单登录 → Market workspace | `{"signedIn": true}`，cookie 正常，全程 0 个 403 |
| A-2 | 四个任务页切换：Overview / Curves & Spreads / Network / Capacity & Events | `tabs: [{id:"#market-cockpit-task-overview",text:"Overview"},…]` |
| A-3 | 四个期限切换：Within-day / Day-ahead / Weekend / Month-ahead | `tenorTabs: ["Within-day","Day-ahead","Weekend","Month-ahead"]`，`defaultTenor: "day-ahead"` |
| A-4 | 6 枢纽 × 4 期限 = **24 个价格牌**渲染，且与页面自己的读一致 | `mismatches: []`，24/24 逐位匹配 `/api/market/quotes` 的 bid/ask，单位串全对 |
| A-5 | 报价类型标注 | 24/24 渲染 `Bid / Ask · EUR/MWh · Age 4h`；`quoteTypeLabelsRendered: ["Bid / Ask"]` |
| A-6 | 模拟数据在**取值处**披露 | 24/24 低价牌 `aria-label` 含 `· Simulated source`（`simulatedDisclosureMissing: []`），source matrix 有 `SIMULATED SOURCE` 徽章 |
| A-7 | 气日 / 时区 | `Time basis: As-of instant · 2026-10-06 · Gas-day calendar EU-CAM-UTC-2025`；`/api/market/observations` 的 day-ahead `delivery_start_utc=2026-10-07T04:00:00Z`（= 10 月 7 日 06:00 CEST，**夏令时下正确的 EU 气日边界**） |
| A-8 | 数据新鲜度分层 | `7 slice(s) stale, missing or unavailable`；Quotes STALE 32 rows / Normalised quotes STALE 500 / Observations STALE 500 / Intraday opportunities UNKNOWN 10 / Spreads UNKNOWN 10 / Monitoring MISSING 0 / Data sources STALE 5 |
| A-9 | FX 参考与逐行单位 | `ECB FX references` 面板 6 行 EURGBP `0.8600`，Observed 带 `UTC` |
| A-10 | 日内决策流展开 | 每行展开后显示 Buy ask / Sell bid / Gross spread / Route cost / Max quantity / Indicative net value + `TTF -> BBL -> NBP` + `Confidence` + `Simulated source` |

**结论：交易员"能不能看到 TTF/NBP/PEG 的日前与日内盘面"——能，而且 24 个组合逐位对得上，报价类型和单位都在取值处标注了。这一层做得比一般终端干净。**

#### ❌ 产品缺陷 A-D1（High）：同一屏 `TTF–NBP day-ahead` 出现三个互不相等的数，且 `Regional comparison` 里 NBP 的**符号是反的**

同一 workspace、同一次会话、同一瞬间渲染：

| 表面 | 标签 | 数值 |
|---|---|---|
| Overview 枢纽板 | `Spread to TTF` | **`n/a`**（6 行全部），tooltip `spread_basis=unavailable; spread_source=unavailable` |
| Curves & Spreads → Regional comparison | `NBP … SPREAD TO TTF` | **`-2.09 EUR/MWh`** |
| Curves & Spreads → Intraday decision feed（折叠态） | `TTF → NBP · day-ahead EXPIRED` | **`1.14 EUR/MWh`**（未标注这是 net margin） |
| `GET /api/market/spreads` | `TTF -> NBP day-ahead` | **`2.1078 ~ 2.1928`**（venues 不同） |

由 `/api/market/quotes` 直接算：`NBP mid 33.6823 − TTF mid 31.5245 = +2.1578`。NBP 是**贵**的那一边。
但 `Regional comparison` 显示 **`-2.09`** → 交易员会读到"NBP 比 TTF 便宜 2.09 EUR/MWh"，**方向相反**。

原因（`clients/web/src/components/MarketTerminal.tsx:317-345`）：`/api/market/spreads` 全部 10 行都是 `TTF->NBP`，客户端把它们折成 `Map`，同一 hub-pair 后写覆盖先写；`spreadToTtfFor("NBP", tenor)` 走 `reverse.get("NBP:TTF:day-ahead")` 后 `return -reverse`。其余 5 个枢纽在该 Map 里查不到 → 回落到**另一种定义** `liveSpread = mid − TTF mid`。于是**同一个标题为 "Spread to TTF" 的 6 行里，5 行是 mid−mid（hub−TTF），1 行是"某条任意 venue 对的价差取负"**。

#### ❌ 产品缺陷 A-D2（High，非确定性）：上面那个 `-2.09` 不取决于市场，取决于**服务端返回行的顺序**

决定性实验（`A-spread-order4.mjs`，拦截 `/api/projections/market-context`，除 `slices.spreads.rows` 的顺序外不改动任何值）：

```
servedSpreadRows        末条 TTF→NBP day-ahead = Trayport/Trayport = 2.0878
                        → 面板 NBP = -2.09
payload 顺序反转后       末条 TTF→NBP day-ahead = EEX/EEX       = 2.1078
                        → 面板 NBP = -2.11
changed = { "NBP": { "before": "-2.09 EUR/MWh …", "after": "-2.11 EUR/MWh …" } }
其余 5 个枢纽不变（它们不走这条路径）
```

同一份数据、同一份代码，只改数组顺序，NBP 的"相对 TTF 价差"就变了。**这不是市场状态，是实现副作用。**

> 证据：`.dnx-out/persona-out/A-spread-order4.json`、`A-spread-order.png`

#### ❌ 产品缺陷 A-D3（Medium）：日内决策流底部时间戳是**本地时间、无日期、无时区**，与全页 UTC 不一致；叠加 "refreshes every 10 seconds" 会被读成"刚刚更新"

同一屏上：

```
.intraday-feed-footer : "PostgreSQL decision feed · refreshes every 10 seconds  06:00:05"
market context strip  : "As of 2026-10-07 02:24:29 UTC"
全部切片时间戳        : "2026-10-06 22:00:05 UTC"
```

浏览器时区 `Asia/Shanghai`（`offsetMinutes: -480`）：`22:00:05Z + 8h = 次日 06:00:05`。
实现：`clients/web/src/components/IntradayDecisionFeed.tsx:112-119` 用 `toLocaleTimeString([], {hour,minute,second})`，**未传 `timeZone`、未渲染日期**。

同时该展开行写 `Quote age: 0.0s`，而同一报价在价格牌上写 `Age 4h`（`/api/market/opportunities` 的 `quote_age_seconds` 对全部 10 行都是 `0`，而 `detected_at_utc = 2026-10-06T22:00:05Z`）。两处"新鲜度"相差 4 小时。

> 证据：`.dnx-out/persona-out/A-trader-spreads.json`（`A4b browser timezone` / `A4c every timestamp the page shows` / `A5c` / `A5d`）

#### ❌ 产品缺陷 A-D4（Medium）：`Spread to TTF` 列在两个页面用两套模型，一处全 `n/a` 一处有值

Overview 的值来自"必须与当前报价匹配的**未过期** intraday opportunity"（`marketOverviewModel.ts:179-212`，`spread = opportunity?.gross_spread ?? null`）；全部 10 条 opportunity 都是 `EXPIRED` → 6 行全 `n/a`。而一页之外的 Curves 用完全不同的来源给出数值。同一个列名，两种含义，且在"同一份数据、同一时刻"给出矛盾结果。

#### ⚠️ 观察 A-D5（Low，文案风险）：真实厂商名做标题、模拟数据做内容

- 面板正文：`Exchange and broker feeds are shown when sourced from EEX, ICE OCM, Trayport, Platts, ICIS, Argus, or Kpler; the terminal does not fabricate missing prices.`
- 而 6 个枢纽的 source 分别是 `EEX_SIM` / `EEX_Sim` / `ICE_OCM_Sim` / `Trayport_Sim`，source matrix 全部 `SIMULATED SOURCE`。
- FX 面板标题 `ECB FX references`，每一行 Source 却是 `ECB_UAT_Sim`。
- 取值处有披露（牌面 `EEX_SIM` + aria `· Simulated source` + source matrix 徽章），**所以不算静默**；但标题层用真名、内容层是模拟，快速浏览时容易把"EEX_Sim"读成 EEX 的产品代码。另外同一屏同时出现 `EEX_SIM`（牌面）与 `EEX_Sim`（矩阵）两种写法。

#### ⚠️ 观察 A-D6（Low）：图表取值与牌面取值不同源但同标签

曲线泳道 `market-curve-lanes` 用 `quoteMid(quote) ?? row?.latest?.price`——有 L1 报价时显示 mid，否则直接显示 normalized observation 单价（可能是 `ICIS_Sim` 的 `daily_assessment`），**同一个 `Day-ahead 31.52` 位置不说明它是 mid 还是评估价**。

### 3.2 交易员小结

| 维度 | 结论 |
|---|---|
| 期限 | ✅ 四个期限齐备，切换后与自有读完全一致 |
| 报价类型 | ⚠️ L1 报价处正确标 `Bid / Ask`；但 Overview 的 `Price` 列其实是 mid（列名只写 `Price`），曲线泳道可能回落成评估价而无标注 |
| 气日时区 | ✅ `EU-CAM-UTC-2025` 明示，且日前的 delivery 边界算对了 |
| 数据新鲜度 | ❌ 决策流底部本地时间无日期无时区；同一报价在牌面 `Age 4h`、在决策流 `Quote age: 0.0s`；`LIVE POLLING` + 源矩阵 `10s` 紧挨着 `Age 4h` |
| 静默混合 | ❌ **确认存在**：`Spread to TTF` 一个标签下混了 mid−mid 与"venue 价差取负"两种算法；折叠态决策流把 net margin 当无标签数字展示；Spread 数值随 payload 顺序变化 |

---

## 4. Persona B：时序模型构建工程师

> 关注：能否冻结可复现的训练/评估数据集。
> 四个必答问题：快照有哈希吗？能复现吗？有 lineage 吗？模拟数据会不会混进真实标定？

### 4.1 实测结果：**交付态可完成 0 / 受阻断 1；播种后 可完成 5 / 受阻断 2；产品缺陷 4 条**

#### 阶段一：交付态（runtime 未播种研究目录）

| 工作流 | 结果 |
|---|---|
| 打开 Research Data → Datasets / Features / Targets | 页面可达，但 `features: 0`、`targets: 0`、`datasets: 0`，UI 显示 `No feature definitions registered.` / `No target definitions registered.` / `No dataset snapshots built yet.` |
| 填 12 个字段的 Governed dataset spec → `Validate spec` | ❌ **被拒绝**：`Result: Spec rejected`，3 条结构化问题 |
| 点 `Build snapshot` | ❌ 按钮存在但 **disabled**，说明文字 `Build stays locked while validation reports issues.` |

结构化问题（逐条命名了犯错的 id）：

```
Spec hash           3a279cbef7dd7887fbc4498d59ef522617c7ed69aa2c50350f774d0cc13c89f4
Registry resolution RESOLVED
Reported issues     3
  feature_ids          unknown_feature_id          unknown feature_id: NBP_TTF_DA_SPREAD
  target_ids           unknown_target_id           unknown target_id: TTF_DA_PRICE_D1
  resampling_policy_id unknown_resampling_policy_id unknown resampling_policy_id: resampling/v1
```

**判定：这是"部署未播种"，不是产品缺陷——而且产品处理得很好（fail closed + 具名报错 + 明确锁住 Build）。** 但必须记入验收事实：**按浏览器验收的播种方式（`seed_preview_runtime_data.py` + `seed_uat_fixture.py` + `seed_browser_identity.py`），Persona B 的核心工作流一步都走不了。** 交付包没有把 `scripts/research/seed_research_catalog.py` 列入浏览器/UAT 播种序列。

#### 阶段二：执行仓库自带的 `scripts/research/seed_research_catalog.py` 之后

| # | 工作流 | 结果 |
|---|---|---|
| B-1 | Validate spec | ✅ `Result: Spec accepted`，`Spec hash fe52b1fee57db7e93d5427350fe110b2bf8da0e0614a0102f704b61f607e1f0b`，`Reported issues 0` |
| B-2 | Build snapshot | ✅ 创建 `dataset-snapshot-121d5b494c8a-uat-persona-b-postseed`，`Rows 70 / Columns 14`，`Artifact reference …/dataset.parquet` |
| B-3 | 快照事实与哈希 | ✅ `Snapshot ID` / `Spec hash fe52b1fe` / **`Content hash 121d5b494c8a36c5d3233b0de5b81ef45151efed83fad2a0a310256354a1518a`** / `Ontology energy-ontology/v1` / `Source cutoff 2026/10/6 00:00:00 UTC` |
| B-4 | Lineage | ✅ 252 条 `source_reference`（例 `sim:EEX_Sim:TTF:day-ahead:20260825T040000`） |
| B-5 | Leakage 报告 | ✅ `Leakage issues` 区块存在，35 条，全部 `severity: BLOCKER`，`code: TEMPORAL_INSUFFICIENT_IN_STRICT_DATASET`，逐行给出 `forecast_origin` / `availability_class: DERIVED_AS_OF` / `temporal_integrity: TEMPORAL_INSUFFICIENT` / `source_refs: []` |
| B-6 | 导出 | ❌ 设计上被封：`Export rights: EXPORT_RESTRICTED`，`Export is unavailable because the dataset policy is restricted.`（并说明 reference 留在服务端、不提供下载——**这是治理状态，不是故障，文案已讲清楚**） |

**所以：哈希有（spec + content，SHA-256）、lineage 有、leakage 有、source cutoff 有。这一层是产品真正的强项。**

#### ❌ 产品缺陷 B-D1（Critical）：同一 spec 二次构建 → HTTP 500 `IntegrityError`，且界面引导用户去看一个空的错误列表

```
POST http://127.0.0.1:3000/api/research/datasets  ->  500
{"detail":"Internal Server Error","error":"internal","family":"SYSTEM","severity":"critical",
 "recoverability":"unknown","message_key":"errors.internal.message","action_key":"errors.internal.action",
 "correlation_id":"61a2076b9bcd4dd6","operator_detail":"IntegrityError"}
```

同一时刻界面渲染的是：

```
Build result
The backend rejected this build. The structured issues are the authoritative reason,
adjust the spec and validate again.
```

而该面板内 **结构化问题数 = 0**（`issueBlocks: 0`, `issueCodes: []`，DOM 仅一个 `<p role="alert">`）。

这直接命中 Persona B 的核心问句"**能复现吗**"：spec hash 是稳定的（两次都是 `fe52b1fe…`），快照 id 也是从 content hash 派生的（`dataset-snapshot-121d5b494c8a-…`），所以第二次构建撞了唯一键——但产品既没有返回既有快照，也没有给干净的 409，而是 500 + `severity: critical`，并且把用户指向不存在的证据。

> 证据：`.dnx-out/persona-out/B-duplicate-build.json`（`posts` / `buildPanel.rawHtml`）

#### ❌ 产品缺陷 B-D2（High）：快照状态写 `COMPLETE`，自带质量报告写 `build_blocked: true` + `missing_percentage: 100`

目录行（浏览器实测）：

```
uat-persona-b-postseed   70 rows   14 cols   COVERAGE 0.0%   TEMPORAL_APPROXIMATE   2026/10/7 02:28:58 UTC   STATUS COMPLETE
```

`GET /api/research/datasets/{id}/quality`：

```json
{"rows":70,"origins":35,"observed_values":0,"missing_values":70,"missing_percentage":100,
 "temporal_integrity":"TEMPORAL_APPROXIMATE","minimum_coverage":0,"coverage":0,
 "build_blocked":true,"source_count":252}
```

即：**70 行全部为 null 的快照，状态是 `COMPLETE`**。质量事实都在界面上（`Coverage 0.0%`、`build_blocked true`、35 条 BLOCKER 泄漏问题），但**状态词与之矛盾**。一个要"冻结可复现训练集"的工程师如果只看状态列，会冻结一份全空数据集。

#### ❌ 产品缺陷 B-D3（High）：整条 lineage 全是模拟源，但快照层面**没有任何 Simulated 标记**

252 条 `source_reference` 全部形如 `sim:EEX_Sim:…` / `sim:ICIS_Sim:…` / `sim:Trayport_Sim:…`。快照详情栏逐字段检查结果：

```
Spec hash ✅  Content hash ✅  Lineage ✅  Source cutoff ✅  Leakage issues ✅
Temporal integrity ✅  Ontology ✅  Export rights ✅
"Simulated"        ❌ 未出现
"Artifact SHA-256" ❌ 未出现（i18n 里 research.artifact_sha256 已定义）
```

**这就是被点名的"静默混合"风险**：判断一份数据集是否含模拟标定，唯一线索是能否从 252 条 lineage 字符串里认出 `sim:` 前缀和 `_Sim` 后缀。产品在行情牌面做到了逐值披露（`aria-label: … · Simulated source`），在数据集层面**没有等价的字段**。

> 证据：`.dnx-out/persona-out/B-engineer-postseed.json`（`B2/B4/B5 detail rail as rendered`、`B-field-Simulated`、`B-field-Artifact SHA-256`）

#### ❌ 产品缺陷 B-D4（Medium）：`Registry resolution: RESOLVED` 出现在**被拒绝**的 spec 上

交付态下 spec 被拒（3 个未知 id），同一个 MetricStrip 却显示：

```
Result               Spec rejected
Spec hash            3a279cbe…
Registry resolution  RESOLVED     ← 与左侧"被拒"并列
Reported issues      3
```

`research_data.py:263-275` 里该字段的语义是"注册表**被查询过**"（`RESOLVED` vs `UNAVAILABLE`），但标签写的是"Registry resolution"，一行之隔就是 `Spec rejected`。用户会读成"id 都解析成功"。

### 4.2 时序工程师小结

| 必答问题 | 实测答案 |
|---|---|
| 快照有哈希吗？ | ✅ 有，spec hash + content hash 都是 SHA-256，逐位可读 |
| 能复现吗？ | ⚠️ spec hash 稳定（两次相同），但**二次构建 500 崩溃**；没有"同 spec → 返回既有快照"的语义 |
| 有 lineage 吗？ | ✅ 有，252 条 source reference，逐条可读 |
| 模拟数据会混进真实标定吗？ | ❌ **无法在快照层区分**——没有 Simulated 字段，lineage 全是 `sim:*` 却只靠字符串前缀辨认；同时 `COMPLETE` 与 `build_blocked:true` / 100% missing 并存 |
| 能拿到数据字节吗？ | ❌ 设计上封死（`EXPORT_RESTRICTED`），只给治理引用；文案已充分解释，非缺陷 |

---

## 5. Persona C：策略分析师

> 关注：策略版本对比与可复现基线。
> 三个必答问题：回撤怎么算的？有样本外结果吗？有没有泄漏控制？

### 5.1 实测结果：**可完成 6 / 受阻断 1；产品缺陷 2 条**

#### ✅ 可完成的工作流

| # | 工作流 | 观测 |
|---|---|---|
| C-1 | Design → 填表 → `Save draft` | 返回 `strategy-eca8e76d3c0044d4` + `strategy-version-3286f52092c845719c77`，界面 `v1 · DRAFT`，`0 BLOCKERS 1 WARNINGS` |
| C-2 | `Freeze version` | 版本转为 `FROZEN`（只读） |
| C-3 | Backtest → `Run backtest` | `strategy-run-ef4d166d3ebe40ba8fca1c78`，`COMPLETED_WITH_WARNINGS`，`engine backtest-engine/1` |
| C-4 | 运行历史 | 表头 `RUN / VERSION / PERIOD / STATUS / NET PNL / MAX DRAWDOWN / DATA QUALITY / ENGINE` |
| C-5 | 再跑一次 → Compare 选 2 条 | `Compatibility: COMPARABLE`，出 `KPI comparison` + `Data-quality comparison` + `Parameter and assumption differences` |
| C-6 | 运行 provenance | manifest 携带 `strategy_version_content_hash: sha256:79fd42f1576592f3441432334b0aeb6b0ca501f6e4278f9bd24724343b7ede3d`、`data_cutoff_utc`、`dataset_snapshot_id`、`evaluation_start/end`、完整 `strategy_definition` 与 `economic_assumptions` |

**可复现性正面结果**：同一冻结版本跑两次，KPI **逐分一致**——

```
KPI                       AF7CFB72             8FCA1C78
Net indicative PnL        +51,008.73 GBP       +51,008.73 GBP
Gross indicative PnL      +51,008.73 GBP       +51,008.73 GBP
Modeled costs             0 GBP                0 GBP
Max drawdown              0 GBP                0 GBP
Coverage                  16.2%                16.2%
Hit ratio                 100.0%               100.0%
Temporal integrity        APPROXIMATE          APPROXIMATE
warnings                  5                    5
```

引擎是确定性的、provenance 是完整的（**但在 Shadow 页**；见 C-D2）。

#### ❌ 产品缺陷 C-D1（High）：评估窗口 365 天里 306 天（84%）落在平台第一条行情之前，仍然落库为 `COMPLETED_WITH_WARNINGS` + `+51,009 GBP` + `Hit ratio 100%` + `Max drawdown 0`

数据库实测：

```
market_observations 窗口 : 2026-08-08T04:00:00Z → 2026-10-06T22:00:05Z   (2382 行)
strategy_runs            : evaluation 2025-10-06T00:00Z → 2026-10-06T00:00Z
                           data_cutoff 2026-10-06T00:00Z   (== evaluation_end，无留出)
backtest_series          : 365 行，2025-10-06T05:00Z → 2026-10-05T05:00Z
   非零 net_indicative_pnl : 59 行      (= 16.2% 覆盖率，与界面 Coverage 16.2% 一致)
   非零 modeled_costs      : 0 行
   决策时点 < 2026-08-08T04:00Z 的行数        : 306
   其中 net_indicative_pnl <> 0 的行数        : 0
backtest_decision_events : 365 行（每个空数据日都产出一条决策事件）
```

即：**84% 的评估窗口平台没有任何价格，引擎照常逐日产生决策事件、记录 0.0 PnL，并把这些天计入 `Hit ratio 100%` / `Max drawdown 0`。**

产品的披露是**有**的，但位置很弱：`Coverage 16.2%` 与 `Temporal integrity APPROXIMATE` 只出现在 Compare 的 KPI 表里；运行历史的表头旁边只有 `DATA QUALITY: APPROXIMATE` 一个词，而同一行最显眼的数字是 `+51,009 GBP`。没有任何地方把这 16.2% 标成"结论不可用"。

> 证据：`.dnx-out/persona/db_backtest.py`、`C-analyst-4.json → compareKpis / runHistory`

#### ❌ 产品缺陷 C-D2（High）：**不存在样本外**，策略工作台**没有泄漏词汇**，`Max drawdown` 无定义

四个任务页逐页扫描页面全文（策略与版本已选中，工作台已填充）：

| 词/概念 | Design | Backtest | Compare | Shadow |
|---|---|---|---|---|
| out-of-sample / holdout / walk-forward | ❌ | ❌ | ❌ | ❌ |
| leakage / look-ahead | ❌ | ❌ | ❌ | ❌ |
| in-sample 划分 | ❌ | ❌ | ❌ | ❌ |
| drawdown | ❌ | ✅（仅列头 `MAX DRAWDOWN`） | ✅（选 2 条后出现） | ✅ |
| drawdown 的定义（peak/trough/算法/口径） | ❌ | ❌ | ❌ | ❌ |
| data cutoff / dataset snapshot / manifest hash / reproducible | ❌ | ❌ | ❌ | ✅ |
| Coverage | ❌ | ❌ | ✅（选 2 条后） | ❌ |

Backtest 任务的**全部**可配置项（浏览器实测）：

```
Version · Period start · Period end · Gas-day context · Missing-data policy
· Transaction cost treatment · Transaction cost GBP/MWh
（+ Experiment name / period / hypothesis）
```

**没有**训练/测试切分、**没有**留出期、**没有**滚动前推、**没有**随机种子、**没有**样本量控制。

对照产品自己的目录：`research.leakage_issues = Leakage issues` 只存在于 Research Data workspace；Strategy Lab 一处都没有。

> 直接回答："**回撤怎么算的**"——产品里没有答案。"**有样本外结果吗**"——没有，一处也没有。"**有没有泄漏控制**"——策略侧没有。

#### ⚠️ 观察 C-D3（Medium）：成本不可用却计入净额

Design 页有明确告警 `WARNING: Transaction cost is UNAVAILABLE and will not be subtracted.`，manifest 也记录 `transaction_cost_policy: EXPLICIT_ZERO_UNMODELED` / `slippage_policy: UNMODELED` —— **披露到位**。但 Compare 的 KPI 表只写 `Modeled costs 0 GBP`，不再重复这条告警；`Net indicative PnL = Gross indicative PnL` 看起来像"零成本策略"，而不是"成本未建模"。

### 5.2 策略分析师小结

| 必答问题 | 实测答案 |
|---|---|
| 回撤怎么算的？ | ❌ 无任何定义/口径说明；数值（0 GBP）与序列算术自洽，但用户无法判断它是否排除了 306 个空数据日 |
| 有样本外结果吗？ | ❌ 完全没有，四个任务页都不存在该概念；`data_cutoff == evaluation_end`，全量在样本内 |
| 有没有泄漏控制？ | ❌ 策略侧无；泄漏能力只在 Research Data（且 35 条 BLOCKER 仍不阻止快照落库，见 B-D2） |
| 版本对比可用吗？ | ✅ 可用，需要 ≥2 条已持久化 run；同版本两次 run KPI 逐分一致 |
| 可复现基线有吗？ | ⚠️ provenance 完整（manifest hash / data cutoff / dataset snapshot / version content hash / engine / git commit）**但只在 Shadow 页呈现**，Backtest 与 Compare 页看不到 |

---

## 6. 重点核查汇总裁决

### 6.1 界面上可能被误解的项

| 项 | 会不会误解 | 结论 |
|---|---|---|
| 数据新鲜度（牌面） | 基本不会 | `Age 4h` + 切片 `STALE` + `7 slice(s) stale, missing or unavailable` 三处一致且醒目 |
| 数据新鲜度（决策流底部） | **会** | 本地时间 `06:00:05`、无日期无时区，紧邻 "refreshes every 10 seconds"，全页其它地方是 `2026-10-06 22:00:05 UTC` |
| 数据新鲜度（决策流详情） | **会** | 同一报价牌面 `Age 4h`、详情 `Quote age: 0.0s` |
| 单位 | 取值处都有（`EUR/MWh`，33 处）；不会误解 | ✅ |
| 币种 | 盘面 33 处 `EUR/MWh`、0 处 `GBP/MWh`，不混币 | ✅（但 NBP 用 EUR 报价无任何惯例说明，属观察项） |
| 报价类型 | **部分会** | 牌面 `Bid / Ask` 正确；Overview `Price` 列实为 mid；曲线泳道可能回落评估价 |
| 期限 | 不会 | 四个期限分页 + 曲线泳道逐期限列出 |
| 气日/时区 | 不会 | `EU-CAM-UTC-2025` 明示，delivery 边界正确 |
| 快照状态 | **会** | `COMPLETE` vs `build_blocked: true` + 100% missing |

### 6.2 静默混合清单（本任务的专项）

| # | 混合内容 | 位置 | 判定 |
|---|---|---|---|
| M-1 | `Spread to TTF` 一列混 **mid−mid** 与 **"某 venue 价差取负"** 两种算法 | Curves → Regional comparison | ❌ 确认，且 NBP 符号反了 |
| M-2 | `Spread to TTF` 一个列名在两个页面代表两种模型（executable opportunity 价差 vs M-1） | Overview vs Curves | ❌ 确认，同数据同刻互相矛盾 |
| M-3 | 折叠态决策流把 **net margin（已扣 route cost）** 当无标签数字展示；`Gross spread` 只在展开后可见，而 0 ACTIVE 时全部默认折叠 | Curves → Intraday decision feed | ❌ 确认 |
| M-4 | 同一"新鲜度"概念在一屏内混 **UTC+日期** 与 **本地时间无日期** | Curves | ❌ 确认 |
| M-5 | 图表泳道在 mid 与评估价之间**无标注切换** | Curves → curve lanes | ⚠️ 观察 |
| M-6 | **模拟价格进入数据集**：252 条 lineage 全 `sim:*`，快照层无 Simulated 标记 | Research → 快照详情 | ❌ 确认 |
| M-7 | 全空快照（100% missing）与 `COMPLETE` 状态并存 | Research → 目录行 | ❌ 确认 |
| M-8 | 真实厂商名做面板标题（EEX / ECB）而内容为 `*_Sim` | Market | ⚠️ 取值处已披露，命名层风险 |

---

## 7. 总体结论：现在能不能给这三类用户用？

### 7.1 分人群

| 人群 | 能用吗 | 理由 |
|---|---|---|
| **A 欧洲天然气交易员** | **不能**（做决策用途） | 唯一一个他想看的跨枢纽数字（`Spread to TTF`）在同一屏出现三个值、其中 NBP **符号反向**且随返回顺序漂移；新鲜度表述自相矛盾。**能看盘，不能据此决策。** 若只当"模拟盘面浏览"用，可用。 |
| **B 时序模型构建工程师** | **不能** | 交付态研究目录为空，核心工作流一步都走不了；补种之后哈希/lineage/leakage 都很好，但同一 spec 二次构建 500 崩溃、`COMPLETE` 与 100% missing 并存、快照层无法区分模拟标定。**"冻结一份可信数据集"这个动作目前做不干净。** |
| **C 策略分析师** | **不能**（做基线/对比用途） | 版本对比与确定性引擎是真实的，但**没有样本外、没有泄漏控制、回撤无定义**，且 84% 评估窗口无数据仍产出 `+51,009 GBP` / `Hit ratio 100%` 的头条数字。**能跑对比流程，拿不到可对外引用的基线。** |

### 7.2 上线前必须补齐（按优先级）

1. **修 `Spread to TTF` 的定义与符号**（A-D1/A-D2/A-D4）。一个列名只能有一种定义，且定义要在界面上写明（mid−mid 还是可成交价差、正向是哪边）。顺手消掉 Map 后写覆盖导致的顺序依赖。
2. **统一时间戳渲染**（A-D3）。全产品一个格式化入口：带日期、带时区标识；决策流的"Quote age"要么按 now 重算，要么明确标注"检测时"。
3. **让状态词与质量结论一致**（B-D2）。`build_blocked: true` / `coverage 0` 的快照不能叫 `COMPLETE`；把 coverage 提到目录行与运行历史的头条数字旁边。
4. **修二次构建的 500**（B-D1）。同 spec 应返回既有快照或干净的 409；绝不能把用户指向空的结构化问题列表。当前 UI 文案与后端行为不一致，等于把 critical 错误伪装成"你的 spec 有问题"。
5. **给数据集加模拟标记**（B-D3）。快照层需要一个显式字段（如 `simulated_share` / `calibration_eligible`），不能靠 lineage 字符串前缀辨认。
6. **补样本外与泄漏控制**（C-D2）。至少要有训练/留出切分或滚动前推；回撤要给出口径说明；策略侧的运行摘要也应像 Research 那样把 leakage/coverage 摆出来。
7. **把 provenance 从 Shadow 页提到 Backtest/Compare**（C-D2）。manifest hash / data cutoff / dataset snapshot 现在只在 Shadow 出现，而分析师对比的正是 Backtest。
8. **文案层**：面板标题不要用真实厂商名覆盖模拟内容（`ECB FX references` → 明确标注模拟；`EEX_SIM`/`EEX_Sim` 统一写法）。
9. **交付/部署**：把 `scripts/research/seed_research_catalog.py` 纳入浏览器/UAT 播种序列，或在文档里明确"研究数据工作台需要额外播种"。

### 7.3 环境限制（非产品缺陷，但会影响后续验收）

| # | 现象 | 判定 |
|---|---|---|
| E-1 | **Vite dev server 崩溃**：队友在 `clients/web/` 里创建探针文件 `.dnx-scan-probe.mjs`，Windows 文件监听器 `EBUSY` 直接杀死进程 —— `Error: EBUSY: resource busy or locked, watch '…\clients\web\.dnx-scan-probe.mjs'` | 环境限制（Windows + Vite 监听）。**触发条件：在被监听目录内创建/删除文件。** 会让浏览器验收假失败，运维接手者必须知道；探针一律放 `.dnx-out/` |
| E-2 | `.dnx-out/browser-acceptance.env` 里 `RUNTIME_STORE_DATABASE_URL` 端口过期（写 53241，实际 51356，`pgserver` 每次启动换端口） | 验收环境自身问题。改进建议：该文件应由脚本从 `.dnx-out/pg-endpoint.txt` 生成（Lead 已加 `refresh_browser_env.py`，本轮我用 `.dnx-out/user-uat.env` 的修正副本启动 API） |
| E-3 | `EUROGAS_UAT_PYTHON` shim 使 sweep 的 agent fixture refresh 失败（`spawnSync …python.cmd EINVAL`） | 环境限制，本机无系统 Python。**本轮三个 persona 探测均未依赖该步骤** |
| E-4 | `maplibre-gl-worker.mjs` 404（Vite dep optimizer） | 环境限制，不影响本轮任何断言 |

### 7.4 我做过的探针侧修正（避免误判）

为了不把探针 bug 报成产品缺陷，记录两处：

- 我的第一版"价差 vs 机会"对照脚本按 `(from_hub,to_hub,period)` 朴素匹配，把不同 venue 的行配到了一起，得到"`/api/market/spreads` 与 opportunities 不一致"的假象。实际两者由同一个 `opportunity_id` 关联，数值**完全一致**（`33.7423 − 31.5495 = 2.1928`）。该假信号已废弃。
- 第一次尝试用 `page.route("**/api/market/spreads**")` 反转顺序未生效，因为市场车道由 `/api/projections/market-context` 拥有（`stores/api.ts:1467 marketLaneIsCurrent = !projectionLanes.marketContext.requested`）。改拦 projection 后实验成立（A-D2 的证据即来自此）。

---

## 8. 附录

### 8.1 原始证据文件（`.dnx-out/persona-out/`）

| 文件 | 内容 |
|---|---|
| `recon.json` | 三个 workspace 的首次侦察（文本 + API 读） |
| `A-trader.json` / `A-trader.log` | 24 牌逐位对照、切片新鲜度、气日、Overview 板 |
| `A-trader-spreads.json` / `A-spreads.log` | 三个价差来源、决策流展开、时间戳清点、时区 |
| `A-spread-order4.json` | **A-D2 决定性实验**：仅反转 projection 的 spreads 行序 |
| `A-spread-order.png` / `A-curves-expanded.png` / `A-curves-fx.png` / `A-market-overview.png` | 截图 |
| `A-fx.json` | `ECB FX references` 面板实渲染 |
| `B-engineer-preseed.json` | 交付态：注册表空、校验拒绝、Build 锁死 |
| `B-engineer-postseed.json` | 播种后：哈希、lineage、leakage、质量、详情栏全文 |
| `B-duplicate-build.json` | **B-D1 证据**：500 `IntegrityError` + 空问题列表 |
| `C-analyst.json` | Design→Freeze→Backtest 端到端、manifest、run 记录 |
| `C-analyst-3.json` | 第二次 run + Compare 解锁 |
| `C-analyst-4.json` | Backtest 可配置项清单、四页词汇扫描、KPI 对比表 |
| `C-compare-final.png` / `C-compare2.png` | 截图 |

探针脚本：`.dnx-out/persona/{lib.mjs, A-trader.mjs, A-spreads.mjs, A-spread-order4.mjs, A-fx.mjs, B-engineer.mjs, B-dup.mjs, C-analyst.mjs, C-analyst3.mjs, C-analyst4.mjs}`；DB 探针 `.dnx-out/persona/{market_facts.py, db_range.py, db_backtest.py, db_counts.py, db_empty.py}`；启动器 `.dnx-out/{run_api_uat.cmd, run_web_uat.cmd, seed_research.cmd}`。

### 8.2 复现要点

- 探针通过 `.dnx-out/persona/run.cmd <script> [phase]` 运行；该脚本从 `.dnx-out/user-uat.env` 载入环境，并设置 `EUROGAS_UAT_PLAYWRIGHT_PATH` / `EUROGAS_UAT_OUTPUT_DIR` / `EUROGAS_UAT_BASE_URL`。
- A-D2 的实验脚本自带拦截与对照，不依赖任何种子副作用。
- B 的两个阶段必须分开跑：`preseed` 在未播种研究目录的库上，`postseed` 在跑过 `scripts/research/seed_research_catalog.py` 之后。
- C 需要先跑 `C-analyst.mjs`（创建策略/冻结/首跑），再跑 `C-analyst3.mjs`（第二次 run + Compare），否则 Compare 只有 0–1 条 run。
