# 市场实践对齐审计 - 中文

## 目的

本文是 Eurogas Nexus V1 继续贴近欧洲天然气市场真实业务的执行参考。它面向本地开发代理和维护人员，即使没有互联网，也应能按照本文判断当前模型是否符合产品方向。

## 产品边界

Eurogas Nexus 支持交易员进行决策、复核和策略评估。系统不得下单、路由订单、提交提名、捕获正式成交、发出官方审批、替代 ETRM 或提供法律意见。UI 和 API 应使用“决策支持”“待复核”“候选方案”“信号”“选项”等词，不得使用“执行”“下单”“提名”“官方推荐”等容易造成误解的表达。

## DB First 规则

PostgreSQL 是运行时事实来源。Web、Windows、Linux、CLI 和 SDK 只能通过 `/api` 或 Python SDK 访问运行时数据。CSV/JSON 只能作为模板、公开数据归档、报告、测试或明确的开发工件存在；trial/release 模式不得静默回退到本地文件。

## 当前市场实践状态

### 路由成本

- 当前释放线采用欧洲 explicit-leg route economics，不再以单一国家、单一点位或 demo route 为核心。
- 只要 PostgreSQL 中存在经审计的 tariff rows、route legs、容量和 TSO access 数据，任意欧洲路线都可以被定价。
- 已纳入 BBL、IUK 公开 corridor tariff 参考；UK NTS 可继续作为公开 TSO tariff 数据源存在。
- 成本栈应包括 entry capacity、exit capacity、跨境/TSO tariff leg、适用的 commodity/usage charge、合同 tolerance allowance、early recovered cash value。
- 路由评估必须考虑公司 TSO access。如果公司没有某条路线所需的 TSO access，该路线必须被阻断或标记为 partial，并给出清晰 warning。
- 当最便宜路线容量不足时，只能分配可用容量；剩余资源必须比较绕路销售、本地销售或其他市场销售的 netback，不能默认全部运往目标市场。
- Live PnL 对 sellable option 应使用可执行或可参考 bid；输出必须是 human-review decision support，不得成为执行指令。

### LNG Regas

- Terminal access、cargo arrival window、regas slot、cargo size、send-out capacity、storage/holding constraints、pricing basis、delivery mode、下游物理/虚拟交付要求必须是显式输入。
- LNG regas 合同可为 terminal title transfer、virtual hub sale、physical entry delivery 或 downstream physical delivery，不得强制套用同一模型。
- 跨月 regas window 必须拆分到月份，用于 PnL 和结算复核。
- Terminal capacity source 和 freshness 必须在有数据时展示。

### Portfolio / Resource Pool

- 客户可能拥有多个 upstream contract，具备不同交付条款、结算 lag、tolerance、成本、容量所有权、TSO access 和销售模式。
- 优化必须在 portfolio 层进行，按兼容销售选项分配资源，并考虑 route cost、early recovered cash value、access constraints 和容量限制。
- 系统可以给出候选 allocation target 和排序信号，但不得执行交易或提交提名。

### Market Price

- `MarketObservation` 用于 assessment、index、settlement 和 derived price。
- `MarketPriceMark` 或 live mark 用于 ICE OCM、EEX、Trayport、broker 或其他授权来源的 screen mark。
- 卖出估值使用 bid，买入估值使用 ask。
- 每条 mark 必须带 venue、hub、product、delivery window、unit、currency、source、freshness、quality 和 entitlement scope。

### FX

- `FxObservation` 必须区分 pair、base currency、quote currency、rate type、source 和 value date。
- ECB 可以作为公开 FX 参考源，但必须由 operator 显式 ingestion。

### Physical / Capacity

- Flow observation 必须包含 point、direction、TSO、country、period、source、freshness，以及 actual/nomination/allocation/forecast 类型。
- Capacity observation 必须区分 technical、booked、available、firm、interruptible、product tenor、direction 和 booking platform。
- Outage event 必须包含 affected point/facility、operator、direction、start/end、status 和 capacity impact。

### Contract / Capacity

- Capacity contract 应尽量以 `MWh/day` 等能源单位表示，不应只依赖 `boe/d`。
- Route eligibility 必须包含 business model、required capacity product、required market mark、required physical signal、constraints 和 confidence。
- 结算 lag、tolerance、allowed exit points、overrun handling、owned capacity 等合同特定输入必须由用户或 operator 配置。

### Strategy

- V1 必须支持 backtest、shadow-run 和 live-monitor evaluation contract。
- 策略可以包括 SAP vs ICIS Heren day-ahead vs ICE OCM、mean reversion、scoring、best buckets、weighted combinations 等。
- 策略必须支持时间窗口、bar size、selected resources/resource pools、risk controls、max single-market volume、stop-loss、stale-data blocking、TSO-access blocking 和 human-review warnings。
- 输出是 paper allocation target 或 decision-support signal，不是官方推荐、订单、提名、booking、trade capture 或 execution instruction。

### Glossary

- Glossary 是后端服务化产品界面，不是前端静态说明。
- 它必须覆盖机构、venue、概念、价格、hub、terminal、clearing、financial terms、contractual terms、capacity、storage、LNG、weather、route economics 和 source governance。
- `/api/glossary` 与 `/api/glossary/{term}` 必须支持 `lang=en`、`lang=zh`、`lang=zh-CN`。
- Python SDK、CLI、Web、Windows 都必须可以访问 glossary。
- Glossary term 必须包含 category、英文定义、中文定义、aliases、related terms 和 source references。

### Market Positioning

- `screen_order_observations` 存储外部 ICE OCM、EEX、Trayport、broker 或其他 screen-order 状态，仅用于展示和分析。
- `portfolio_pnl_snapshots` 存储 indicative PnL、cash value、market value、quantity、valuation basis、warnings 和 source context。
- `/api/portfolio/screen-orders`、`/api/portfolio/pnl-snapshots`、`/api/portfolio/live-summary` 面向 SDK/Web/Windows。
- 该层不是 trade capture，不得下单、路由、撤单、提名、审批或官方推荐任何交易。

## 是否需要互联网

实现当前 contracts 和 tests 不需要互联网。

只有当 operator 或开发代理需要验证最新 provider 文档、vendor API 条款、市场数据授权、包版本或官方 TSO tariff PDF 时，才需要互联网。

## 下一步优先级

1. 扩展欧洲 TSO tariff coverage、route topology 和 route optimization，所有数据进入 PostgreSQL。
2. 生产化 live ingestion scheduling、retry、monitoring 和 source health。
3. 完善 market marks、FX、capacity、outage、glossary 的 DB-backed API。
4. 先扩展 SDK DTO，再让 Web/Windows 消费新 endpoint。
5. 强化 strategy persistence、backtest、shadow run、live monitor、allocation targets 和 alerts。
