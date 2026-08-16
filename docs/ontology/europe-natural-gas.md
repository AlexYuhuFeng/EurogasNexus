# 欧洲天然气贸易领域主体架构

> European Natural Gas Trading — Subject Architecture

- **定位**：本文件是「本体方法论」在**欧洲天然气贸易域**的实例落地，也是
  Eurogas Nexus 后续 gap 分析与重构的领域参照基线。
- **性质**：这是一份**领域架构 / 本体骨架**文档，不包含任何代码或实现细节。
- **版本**：v0.2（对齐本项目 `MARKET_PRACTICE_AUDIT-EN.md` 后）。
- **纪律**：方法论（元模型、L1–L5 分层、种子 vs 绑定）是稳定的、跨项目共享的；
  本文件的品种实体、受控词表、制度规则、可计算约束，属于欧洲天然气域自建内容。

---

## 0. 价值链总览

欧洲天然气贸易的完整链条，从"资源取得"到"履约结算"再到"风险治理"，可划分为
**12 个环节**。这 12 个环节就是本架构的"主干"（backbone），每个环节内部再展开
概念、关系、动作与约束。

```text
① 上游资源与合同   →  ② 枢纽与虚拟交易点   →  ③ 管网与互联点
                                                    │
④ 容量(entry/exit)  ←──  ⑤ TSO 准入与费率    ←────┘
                                                    │
⑥ 交易场所与产品    →  ⑦ LNG 再气化           →  ⑧ 储气
                                                    │
⑨ 平衡与提名        →  ⑩ 结算与保证金
                                                    │
⑪ 合规与出口治理   →  ⑫ 风险与策略(backtest/shadow-run)
```

这 12 个环节不是线性流程，而是一张**相互约束的图**：容量、费率和准入（④⑤）决定
一条路线（route）是否可行；交易场所的价格（⑥）与资源成本（①）之差决定经济性；
平衡与提名（⑨）决定履约不确定性；合规（⑪）对所有动作施加 fail-closed 的边界。

### 0.1 跨切概念（贯穿全链条）

以下三类不是独立的"环节"，而是**横向切穿 12 个环节**的支撑概念，单独列出以免遗漏：

- **汇率 FX**：`FxObservation` 必须区分 `pair` / `base_currency` / `quote_currency` /
  `rate_type` / `source` / `value_date`。`ECB` 可作为公开参考源（需算子显式采集）。
  所有跨币种（如 EUR↔GBP）的价差、净回值、PnL 都依赖 FX 换算。
- **天气与需求**：`HDD` / `CDD`（采暖/制冷度日）是需求驱动的量，用于需求 nowcast、
  储气季节性和价差判断；属于信号输入，不是交易动作。
- **数据源治理 Source Governance**：所有观测必须带 `source_system`、`source_reference`、
  `freshness`、`quality`、`entitlement_scope`；商业源需授权（fail-closed），模拟源
  （`*_Sim`）必须显式标记，不得冒充真实行情。

---

## 1. 各环节详解

> 每节按四格展开：**概念**（有哪些实体）、**关系**（实体间如何关联）、**动作**
> （谁对谁做什么，且均为需人工复核的决策动作）、**约束**（必须满足的规则）。

### ① 上游资源与合同 (Upstream Resources & Contracts)

**概念**
- `UpstreamResourceContract`（上游资源合同）：物理气、虚拟枢纽头寸、LNG 上游
  offtake、屏幕采购等资源来源的合同化表示。
- `ResourcePool`（资源池）：将所有可用资源汇聚成的组合，是优化的输入。
- 资源属性：`available_quantity_mwh_per_day`、`all_in_cost_gbp_mwh`、
  `delivery_tolerance_pct`、`nomination_tolerance_pct`、`booked_entry_capacity`。
- 合同条款：`EFET` 框架、`delivery_point`、`gas_year`、`settlement_frequency`、
  `eligible_sale_modes`。

**关系**
- `resource_contract feeds resource_pool`
- `resource_contract has delivery_point / gas_year / settlement terms`
- `resource_pool allocates_to route_candidate`

**动作（一等公民）**
- `CAPTURE_RESOURCE_TERM`：录入资源条款（需人工复核）
- `REVIEW_RESOURCE_ASSUMPTION`：复核资源假设
- `IMPORT_SCREEN_OBSERVATION`：导入屏幕成交观测（只读，见 ⑫）

**约束**
- 资源成本与数量必须是**合同化事实**，客户端不得凭空捏造。
- 资源术语必须能在上游合同 → 资源池 → 销售路径 → PnL 之间**溯源**（lineage）。

---

### ② 枢纽与虚拟交易点 (Hubs & Virtual Trading Points)

**概念**
- 虚拟交易点 `VirtualHub`：一个市场区内的记账式交易点，代表该区内的平衡价格。
- 主要枢纽：`TTF`（荷兰，欧洲大陆基准）、`NBP`（英国）、`THE`（德国市场区，
  由 NCG/Gaspool 于 2021 合并）、`PEG`（法国）、`CEGH`（奥地利 Baumgarten）、
  `PSV`（意大利）、`ZTP`（比利时 Zeebrugge）。
- `MarketArea` / `BalancingZone`：与枢纽一一对应的平衡区，是 entry-exit 模型的
  地理与结算单元。

**关系**
- `hub is_price_anchor_of market_area`
- `market_area contains entry_points / exit_points`
- `hub links_to adjacent hub via interconnection_point`

**动作**
- `MARK_AT_HUB`：按枢纽价格盯市
- `TRANSFER_BETWEEN_ZONES`：跨市场区转移（需容量与准入，见 ③④⑤）

**约束**
- 枢纽价格是**虚拟**的：同区内任何 entry/exit 组合的净气量都归结到该枢纽价。
- 跨枢纽 = 跨市场区，必须通过互联点容量，不可无容量直连。

---

### ③ 管网与互联点 (Transmission Network & Interconnection Points)

**概念**
- `ReferenceNode`（参考节点）：枢纽、互联点、LNG 终端、储气库、平衡区的几何/拓扑锚点。
- `ReferenceEdge`（参考边）：节点间的物理/拓扑连接（corridor）。
- `InterconnectionPoint (IP)`：相邻市场区之间的连接点，是跨境容量的计量单位。
- `ReferenceFacility`：LNG 终端、储气库等设施。
- `FlowObservation`（流量观测）：须带 point/direction/TSO/country/period/source/
  freshness，且必须区分流量性质 **actual（实际）/ nomination（提名）/ allocation（分配）/
  forecast（预测）**。
- `OutageEvent`（检修/中断事件）：见 §④。
- `ENTSOG`：欧盟 TSO 网络与透明度平台（数据源）。

**关系**
- `node connects_via edge`
- `interconnection_point links market_area_a ↔ market_area_b`
- `facility located_at node`

**动作**
- `MATERIALIZE_TOPOLOGY`：物化参考网络（数据资产，非交易动作）
- `QUERY_ROUTE`：查询路线

**约束**
- 拓扑来自**权威数据源**（ENTSOG / 客户装载），客户端不提供权威几何。
- 未经校验的坐标/边必须标记为 `source_derived_corridor` 或 `display_approximation`。

---

### ④ 容量（Entry/Exit Capacity）

**概念**
- `CapacityProduct`：容量产品，按时段分为 **yearly / quarterly / monthly /
  day-ahead / within-day**。
- `EntryCapacity` / `ExitCapacity`：入口/出口容量。
- `FirmCapacity`（固定）/ `InterruptibleCapacity`（可中断）。
- `BundledCapacity`（捆绑，跨 IP 入口+出口）/ `UnbundledCapacity`。
- **容量口径必须区分**：`technical`（技术容量）/ `booked`（已订）/ `available`（可用）。
- `CapacityProfile`：某容量产品的有效区间与数量。
- `CapacityObservation`：容量观测，须带 point/direction/TSO/country/period/source/
  freshness/booking_platform（如 PRISMA）。
- `OutageEvent`：检修/中断事件，须带 point/facility/operator/direction/start/end/
  status/capacity_impact。
- `CAM NC`（欧盟 2017/459）：标准化容量分配机制（拍卖平台 PRISMA）。
- `CompanyTsoAccess`：公司对特定 TSO/点的准入权利。

**关系**
- `capacity_profile valid_for [valid_from, valid_to] at point`
- `route_candidate requires capacity_profile + company_tso_access`
- `capacity_auction allocates capacity_product`

**动作**
- `BOOK_CAPACITY`（本架构仅**表示**，不提交）：预留容量
- `ALLOCATE_CAPACITY`：在优化中分配容量（纸面）

**约束**
- 容量是**方向性**的（entry 与 exit 分开），且按 gas day/product 有效。
- 共享容量在组合层面**全局约束**：多个销售路径不得重复占用同一容量。
- 客户端不得把未装载到 PostgreSQL 的费率/容量当作可用。

---

### ⑤ TSO 准入与费率 (TSO Access & Tariffs)

**概念**
- `TSO`（输气系统运营商）：National Grid NTS、GTS、NaTran、德国 TSO、Fluxys 等。
- `TsoTariff`：费率，分**容量费（capacity charge）**与**商品费（commodity charge）**。
- `TAR NC`（欧盟 2017/460）：统一输气费率结构（参考价方法论）。
- 参考走廊：`BBL`、`IUK`、`NTS` 等。
- `CompanyTsoAccess`：公司的 TSO 准入（见 ④）。

**关系**
- `route_candidate requires tso_tariff + company_tso_access`
- `tso_tariff charged_at point, direction`

**动作**
- `VALIDATE_ACCESS`：校验 TSO 准入
- `ESTIMATE_ROUTE_COST`：估算路线成本

**约束**
- 未在运行时库中的费率行**不可用**，必须显式装载。
- 准入校验 **fail-closed**：未知商业数据源默认拒绝。

---

### ⑥ 交易场所与产品 (Venues & Products)

**概念**
- 交易场所 `Venue`：`EEX`、`ICE`（含 `ICE OCM` 英国日内）、`Trayport`（经纪网络）、
  场外经纪（broker）。
- 产品 `Product`：按**时间粒度**分 `day-ahead`、`within-day/intraday`、`weekend`、
  `month`、`quarter`、`season`、`year`；按**类型**分 `spot`、`forward`、`futures`、
  `options`。
- 价格类型：`bid` / `ask` / `last` / `mid` / `settlement`。
- 价格评估源：`ICIS Heren`、`Platts`、`Argus`（需授权）。
- **两类价格数据，语义必须区分**（这是正确性的关键）：
  - `MarketObservation`（市场观测）= 评估、指数、结算价、衍生价（assessment / index /
    settlement / derived）；
  - `LiveMarketMark`（实时盯市 mark）= 来自 `ICE OCM`、`EEX`、`Trayport`、broker 的
    **可成交屏幕 mark**（在代码里对应 `live_market_marks` 表，AUDIT 文档称 `MarketPriceMark`）。
  - `MarketQuote`（L1 报价）= 规范化的盘口（bid/ask/量），驱动日内机会扫描。

**关系**
- `observation has source_system, venue, hub, product, tenor`
- `live_market_mark marks position at bid/ask/last`
- `quote triggers opportunity scan`

**动作**
- `OBSERVE_PRICE`：采集/规范化价格（数据动作）
- `MARK_TO_MARKET`：盯市
- `EVALUATE_SPREAD`：评估价差

**约束**
- **卖方向用可成交/指示 bid 估值，买方向用 ask**——不得用 mid 冒充可成交价。
- 每个 mark 必须带 `venue, hub, product, delivery_window, unit, currency, source,
  freshness, quality, entitlement_scope`。
- 价格必须带 `source_system` 与 `source_reference`（溯源）。
- 模拟源（`*_Sim`）必须显式标记，不得冒充真实行情。
- 商业数据源需客户授权/许可，无授权 fail-closed。

---

### ⑦ LNG 再气化 (LNG Regasification)

**概念**
- `LNGTerminal`：LNG 接收站。
- `Regasification` / `Send-out`：再气化与管网注入。
- `Slot`：接收站窗口（船期窗口）。
- `ALSI`（GIE 的 LNG 透明度平台）。
- 显式输入：`terminal_access`（接收站准入）、`cargo_arrival_window`（船期窗口）、
  `regas_slot`（再气化窗口）、`cargo_size`（船货规模）、`send_out_capacity`（外输能力）、
  `storage/holding_constraints`（储存/滞留约束）、`pricing_basis`、`delivery_mode`。

**关系**
- `lng_regas_scenario requires terminal_access + slot_window`
- `send_out feeds market_area`

**交付模式（delivery mode，不得强制单一模式）**
- `terminal_title_transfer`（接收站所有权转移）、`virtual_hub_sale`（虚拟枢纽销售）、
  `physical_entry_delivery`（物理入口交付）、`downstream_physical_delivery`（下游物理交付）。

**动作**
- `ASSESS_REGAS_READINESS`：评估再气化可行性

**约束**
- LNG 经济性 = 船货成本 + 再气化费 + 管网注入，须与管道气在同一边界比较。
- **跨月再气化窗口必须拆分到月**，分别做 PnL 与结算复核。
- 接收站容量来源与数据时效必须显式展示。

---

### ⑧ 储气 (Storage)

**概念**
- `StorageFacility`：地下储气库（UGS）。
- `Injection` / `Withdrawal`：注采。
- `AGSI`（GIE 的储气透明度平台）。
- `StorageObservation`：库存/注采观测。

**关系**
- `storage_facility located_at node`
- `withdrawal feeds market_area`

**动作**
- `ASSESS_STORAGE_DISPATCH`：评估储气调度（纸面）

**约束**
- 储气是**灵活性**与**季节性**工具，受注采速率与容量约束。

---

### ⑨ 平衡与提名 (Balancing & Nomination)

**概念**
- `Nomination`：向 TSO 提交的流量计划（**本架构只评估，不提交**）。
- `Re-nomination`：重提名。
- `Imbalance`：实际流量与提名的偏差。
- `Tolerance`：允许偏差。
- `Cash-out`：不平衡结算价格（within-day / day-ahead）。
- `BAL NC`（欧盟 312/2014）：管网平衡网络代码。
- `BalancingNeutralGas`：平衡中性气。

**关系**
- `nomination has tolerance`
- `imbalance settled_at cash_out_price`

**动作**
- `ASSESS_NOMINATION_WINDOW`：评估提名窗口（纸面）
- `MONITOR_IMBALANCE`：监控不平衡

**约束**
- **不提交提名**（产品边界：非提名提交系统）。
- 提名与不平衡是**履约不确定性**的来源，须反映在风险缓冲中。

---

### ⑩ 结算与保证金 (Settlement & Margin)

**概念**
- `EFET`：欧洲能源交易商联合会标准合同框架。
- `Settlement` / `Clearing`：结算与清算（ICE Clear、EEX）。
- `Variation Margin` / `Initial Margin`：变动/初始保证金。
- `SettlementPrice`：结算价。
- `Invoice`：发票。

**关系**
- `contract settled_at settlement_price`
- `position margined_via clearing_house`

**动作**
- `RECONCILE_PNL`：对账 PnL
- `COMPUTE_CASH_FLOW`：计算现金流（含早收现金价值）

**约束**
- **不替代结算系统/ETRM**：只做决策支持层面的现金流/PnL 估算。
- 盯市用可成交 bid/ask，而非虚拟 mid。

---

### ⑪ 合规与出口治理 (Compliance & Export Governance)

**概念**
- `REMIT`（欧盟 1227/2011）：批发能源市场完整性与透明性（内幕信息、操纵、交易报告）。
- `MiFID II`：金融工具市场指令（交易场所、持仓限额、报告）。
- `EMIR`：清算与衍生品报告。
- `EntitlementDecision`：数据/服务授权决策。
- `ExportPolicy`：出口治理。

**关系**
- `commercial_data requires entitlement`
- `output governed_by export_policy`

**动作**
- `ENFORCE_ENTITLEMENT`：授权校验
- `AUDIT_ACTION`：审计

**约束**
- 未知商业数据 **fail-closed**。
- 所有敏感操作需审计（actor、时间、范围、记录）。
- 输出是决策支持，**不构成**法律意见/官方交易建议。

---

### ⑫ 风险与策略 (Risk & Strategy)

**概念**
- `StrategyDefinition` / `StrategyRun`：策略定义与运行（backtest / shadow-run / live-monitor）。
- **策略家族（示例）**：`SAP/ICIS Heren 日前 vs ICE OCM`（价差）、`mean_reversion`
  （均值回归）、`scoring`（打分）、`best_buckets`（最优分桶）、`weighted_combination`
  （加权组合）。
- `RiskControl`：风控——`stop_loss`（按累计纸面盈亏）、`max_single_market_volume`
  （单市场上限）、`require_tso_access`（TSO 准入阻断）、`stale_data_blocking`
  （过期数据阻断）、`min_expected_margin`（最小毛利）。
- 策略参数：`time_window`（如 15:00–17:00）、`bar_minutes`（如 5 分钟）、
  `positive/negative_spread_threshold`（正负价差阈值）。
- `PaperPnl` / `CumulativePnl` / `Drawdown` / `HitRate`：纸面绩效指标。
- `RouteCost` / `Netback`：路线成本 / 净回值。
- `ScreenOrderObservation` / `PortfolioPnlSnapshot`：只读导入的屏幕成交与组合 PnL 快照。

**关系**
- `strategy_run evaluates resource_pool + market_observation + risk_control`
- `route_cost derives_from tariff + capacity + access + fx`

**动作**
- `BACKTEST` / `SHADOW_RUN` / `LIVE_MONITOR`：三种纸面评估模式
- `REVIEW_STRATEGY_OUTPUT`：复核策略输出（`human_review_required=True`）

**约束**
- 策略输出**永远需人工复核**、**不可执行**（不自动下单）。
- 止损按**累计**纸面盈亏判定。
- 路线净回值 = 目标市场价值 − 路线/关税/换算/融资/处理成本。

---

## 2. 元模型五构件汇总

方法论规定元模型由五构件构成。本域的实例化如下：

### 2.1 概念（Concepts）—— 42 个核心实体
> 与 Eurogas Nexus 现有 `business_logic_ontology().entities`（16 个）对齐并扩充。

```text
UpstreamResourceContract, ResourcePool, VirtualHub, MarketArea, ReferenceNode,
ReferenceEdge, InterconnectionPoint, ReferenceFacility, FlowObservation,
OutageEvent, CapacityProfile, CapacityProduct, CapacityObservation,
CompanyTsoAccess, TSO, TsoTariff, Venue, Product, PriceType, MarketObservation,
LiveMarketMark, MarketQuote, FxObservation, WeatherObservation, LNGTerminal,
RegasScenario, StorageFacility, StorageObservation, Nomination, Imbalance,
SettlementPrice, EFETContract, EntitlementDecision, ExportPolicy,
StrategyDefinition, StrategyRun, RiskControl, PaperPnl, RouteCost, Netback,
ScreenOrderObservation, PortfolioPnlSnapshot
```

### 2.2 关系（Relations）—— 核心关系

```text
resource_contract feeds resource_pool
resource_pool allocates_to route_candidate
route_candidate requires tso_tariff + capacity_profile + company_tso_access
route_candidate consumes market_observation + live_market_mark
route_cost/netback converts via fx_observation
hub is_price_anchor_of market_area
market_area contains entry_points / exit_points
interconnection_point links market_area_a ↔ market_area_b
flow_observation measures flow at point (actual/nomination/allocation/forecast)
outage_event reduces capacity_availability at point/facility
lng_regas_scenario requires terminal_access + slot_window
storage_facility withdraws/injects into market_area
demand_nowcast driven_by weather_observation (hdd/cdd)
nomination has tolerance → imbalance → cash_out
strategy_run evaluates resource_pool + market_observation + risk_control
generated_report cites source_snapshots + strategy_runs
```

### 2.3 动作（Actions，一等公民）—— 全部为"需人工复核"的决策/纸面动作

```text
CAPTURE_RESOURCE_TERM, REVIEW_RESOURCE_ASSUMPTION, IMPORT_SCREEN_OBSERVATION,
MARK_AT_HUB, TRANSFER_BETWEEN_ZONES, MATERIALIZE_TOPOLOGY, QUERY_ROUTE,
BOOK_CAPACITY(纸面), ALLOCATE_CAPACITY(纸面), VALIDATE_ACCESS, ESTIMATE_ROUTE_COST,
OBSERVE_PRICE, MARK_TO_MARKET, EVALUATE_SPREAD, ASSESS_REGAS_READINESS,
ASSESS_STORAGE_DISPATCH, ASSESS_NOMINATION_WINDOW, MONITOR_IMBALANCE,
RECONCILE_PNL, COMPUTE_CASH_FLOW, ENFORCE_ENTITLEMENT, AUDIT_ACTION,
BACKTEST, SHADOW_RUN, LIVE_MONITOR, REVIEW_STRATEGY_OUTPUT
```

> **禁止的动作**（硬边界，来自 Eurogas Nexus 产品定位）：`PLACE_ORDER`、
> `ROUTE_ORDER`、`AMEND/CANCEL_ORDER`、`TRADE_CAPTURE`、`SUBMIT_NOMINATION`、
> `OFFICIAL_APPROVAL`、`AUTO_TRADE`、`LEGAL_ADVICE`、`ETRM_REPLACEMENT`。

> **语言纪律**：产品/API/UI 只允许用 `decision support`、`review`、`candidate`、
> `signal`、`option`；不得出现 `execute`、`book`、`nominate`、`official
> recommendation` 这类"执行/下单/提名/官方建议"措辞。

### 2.4 受控词表（Controlled Vocabulary）

| 维度 | 受控取值 |
|---|---|
| 枢纽/交易点 | TTF、NBP、THE、NCG、Gaspool、PEG、CEGH、PSV、ZTP |
| 产品/tenor | day-ahead、within-day、intraday、weekend、month、quarter、season、year、spot、forward、futures、options |
| 价格类型 | bid、ask、last、mid、settlement、assessment、index |
| 价格数据性质 | MarketObservation（assessment/index/settlement/derived）vs LiveMarketMark（可成交屏幕 mark） |
| 容量口径 | entry、exit、firm、interruptible、bundled、unbundled、technical、booked、available |
| 流量性质 | actual、nomination、allocation、forecast |
| LNG 交付模式 | terminal_title_transfer、virtual_hub_sale、physical_entry_delivery、downstream_physical_delivery |
| 汇率 | pair、base/quote currency、rate_type、value_date（ECB 参考源） |
| 天气 | HDD、CDD |
| 平台/机构 | PRISMA、ENTSOG、ACER、GIE（AGSI、ALSI）、EEX、ICE OCM、Trayport、ICIS Heren、Platts、Argus |
| 制度/监管 | REMIT、MiFID II、EMIR、CAM NC、TAR NC、BAL NC、EFET |
| 术语基线 | 现有 `glossary.py` 的 29 条（TTF、NBP、Entry/Exit Capacity、Bid/Ask、Mark-to-Market、EFET、Nomination、Tolerance、Netback、Route Cost、LNG、Send-out、Storage、HDD/CDD…）即为种子 |

### 2.5 约束（Constraints）—— 可计算 + 制度

| 类型 | 约束 | 落点 |
|---|---|---|
| 制度 | PostgreSQL 是运行时唯一真相 | L4 |
| 制度 | 客户端只经 API/SDK，不直连 DB | L4 |
| 制度 | LLM 不是事实源，只解释持久化证据 | L4 |
| 制度 | 输出需人工复核、不可执行 | L4 |
| 可计算 | 容量方向性 + 跨组合全局约束 | L5 |
| 可计算 | 止损按累计纸面盈亏判定 | L5 |
| 可计算 | 净回值 = 目标价 − 全成本 | L5 |
| 可计算 | 准入/授权 fail-closed | L5 |

---

## 3. 知识层 L1–L5 落点

| 层 | 内容 | 本域实例 |
|---|---|---|
| L1 声明式本体 | 概念、关系、受控词表 | §2.1/2.2/2.4 |
| L2 流程 | 端到端工作流 | §0 的 12 环节；Network→Scenario→Review 工作流 |
| L3 经验 | 交易员启发式 | 价差阈值、窗口（15:00–17:00）、分桶逻辑 |
| L4 制度 | 规则/边界 | REMIT/EFET/准入/审计、§2.5 制度约束 |
| L5 可计算约束 | 可校验规则 | §2.5 可计算约束（容量守恒、止损、净回值、fail-closed） |

**正确性分工**：L1/L4/L5 的"正确性"由确定性引擎/校验器负责；L3 的"生成"可交 LLM，
但 LLM 输出必须被 L5 校验器约束、并被 L4 的 human-review 边界兜底。

---

## 4. 与 Eurogas Nexus 现有模型的初步对照（gap 种子）

> 这是后续 gap 报告的起点，此处只列**已识别**的对齐/缺口，不展开。

| 环节 | 现有资产 | 缺口/重复/冲突（初判） |
|---|---|---|
| ① 资源 | `UpstreamResourceContract`、`ResourcePool`、Contracts 工作区 | 合同条款模型已较全；缺统一"资源假设溯源"声明 |
| ② 枢纽 | `reference_market_hubs`（`hub_code`）、`glossary.py` | 枢纽已是一等表，`topology_market_mappings` 已做 node↔hub 绑定；缺 **market area/zone 聚合层** |
| ③ 管网 | `reference_nodes/edges`、`reference_tso_access_points`、`GasNetworkMap` | `node_type` 已含 `interconnection`，`tso_access_points` 已含相邻国/相邻运营商/CAM-CMP；基本完整，缺 zone 归属显式化 |
| ④⑤ 容量/费率 | `capacity_profiles`、`tso_tariffs`、`company_tso_access` | 有表；费率/准入的 fail-closed 校验散在代码 |
| ⑥ 场所/产品 | `market_observations`、`live_market_marks`、`market_quotes`、`/api/market/normalized` | 产品/tenor/FX 规范化已由后端 `/api/market/normalized` 统一（原前端 `marketPriceNormalization` 已删除）；前端仅消费 `hub`/`tenor`/`price_gbp_mwh` |
| ⑦⑧ LNG/储气 | `lng_observations`、`storage_observations`、`LngRegasScenario` | 有观测；LNG 再气化经济性模型是原型 |
| ⑨ 平衡/提名 | `nomination` 原型、`tolerance` 术语 | 提名只评估不提交（符合边界）；模型为内部原型 |
| ⑩ 结算 | `EFET` 术语、`portfolio_pnl_snapshots` | 现金流/PnL 是导入观测；无结算系统（符合边界） |
| ⑪ 合规 | `entitlement_decisions`、`audit_events` | 有表；fail-closed 与审计深度待生产化 |
| ⑫ 策略 | `strategy_definitions/runs`、shadow-run 持久化 | 已较完整；绩效/风控可再收紧 |

---

## 5. 开放问题与讨论点

1. **互联点语义已基本存在，是否还需独立实体**：`node_type="interconnection"` +
   `reference_tso_access_points`（相邻国/相邻运营商/CAM-CMP）已承载"跨境容量"语义。
   是否值得再抽独立 `InterconnectionPoint`，还是维持现状？（当前建议：维持，等 R31
   跨境分配有真实需求再升格。）
2. **市场区/平衡区聚合层**：hub 已是一等表，缺的是 `market_area` / `balancing_zone`
   聚合层（hub=点、zone=区域/国家）。是否新增轻量 `market_areas` 引用表并把 hub/zone 绑定？
3. **约束抽取优先级**：L5 可计算约束（容量守恒、止损、净回值、fail-closed）里，
   哪个先抽成"声明式约束 + 单一校验器"？
4. **共享层边界**：本文件哪些内容可并入跨项目的 `methodology.md`（元模型/L1-L5/纪律），
   哪些必须留在本域实例（实体/词表/制度/约束）？

---

## 参考来源

- 本项目 `docs/architecture/MARKET_PRACTICE_AUDIT-EN.md`（市场实践对齐审计，本文件 v0.2 已对齐）
- 本项目 `src/eurogas_nexus/domain/glossary.py`（29 条双语术语基线）
- [ENTSOG Network Codes and Guidelines](https://www.entsog.eu/network-codes-and-guidelines)（CAM NC / TAR NC / BAL NC）
- [EEX Natural Gas Markets](https://www.eex.com/en/markets/natural-gas)
- [Introduction to the TTF Gas Hub — Clever Markets](https://clevermarkets.com/blog/introduction-to-the-ttf-gas-hub/)
- [GIE — Gas Infrastructure Europe（AGSI / ALSI）](https://www.gie.eu/)
- [ICE Endex OCM（英国日内市场迁移到 ICE）](https://ir.theice.com/press/news-details/2015/ICE-Endex-Transitions-the-UKs-On-the-Day-Commodity-Market-to-the-ICE-Trading-Platform/default.aspx)
- [欧洲管网平衡机制（BAL NC）经验分析 — 北极星电力网](https://news.bjx.com.cn/html/20240730/1391977.shtml)
