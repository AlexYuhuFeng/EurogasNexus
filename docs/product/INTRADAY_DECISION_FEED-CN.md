# 日内决策信息流

英文主文档：[INTRADAY_DECISION_FEED-EN.md](INTRADAY_DECISION_FEED-EN.md)

## 目标

日内决策信息流持续比较相互兼容的买卖报价，并扣除实际可用路径的物理和商业成本，在 Network 和 Market 工作区向交易员显示有时效限制的候选机会。它不下单、不预订管容、不提交提名、不做交易捕获，也不承诺无风险利润。

已经实现的数据链路只有一条：

```text
持牌或模拟适配器
  -> 标准化 L1 报价
  -> PostgreSQL market_quotes
  -> 后端路径和机会扫描
  -> PostgreSQL intraday_opportunities
  -> GET /api/market/opportunities
  -> SDK、Web、Windows 和 Linux 客户端
```

客户端不计算价差，也不直接连接 PostgreSQL 或市场数据供应商。

## 运行时数据合同

Alembic 版本 `0014_intraday_decision_feed` 新增：

| 数据表 | 权威内容 |
| --- | --- |
| `market_quotes` | 标准化 L1 买价、卖价、最新价、可见深度、交付窗口、事件和接收时间、币种/单位、来源身份、质量和模拟标记。 |
| `company_tso_access` | 按有效期记录公司对各 TSO/运营商的准入状态。 |
| `intraday_opportunities` | 后端扫描快照，包括报价 ID、路径、经济性、数量上限、来源、假设、阻断项、警告和有效期。 |

迁移必须由运营人员显式执行。导入 API 或运行单元测试不会连接数据库或自动执行迁移。

## 计算规则

后端针对每条有效候选路径，按来源、交易场所和产品选择最新报价。只有方向、产品、交付起止时间、单位和币种转换兼容时，才进行比较。

计算只使用可执行报价侧，不使用最新价或中间价：

```text
毛价差 = 卖出 bid - 换算后的买入 ask
净边际 = 毛价差 - 路径成本 - 交易成本 - 风险缓冲
最大数量 = min(买入 ask 深度, 卖出 bid 深度, 路径可用管容)
指示性净价值 = 净边际 * 最大数量
```

只有同时满足以下条件，状态才是 `ACTIONABLE_REVIEW`：

- 买入 ask 和卖出 bid 都是当前报价；
- 产品和交付窗口完全一致；
- 路径费率成本及单位/币种已确认；
- TSO 准入已确认；
- 路径管容和可见报价深度均为正；
- 报价未超过最大时效；
- 净边际超过配置阈值。

否则结果为 `WATCH` 或 `BLOCKED`，并提供机器可读原因。超过 `valid_until_utc` 后，API 返回 `EXPIRED` 并加入 `OPPORTUNITY_EXPIRED`；后台 worker 停止后，历史机会不会继续显示为当前可审阅机会。

该结果只是“可执行价差候选”，不是无风险利润。L1 可见深度不能保证同步成交、管容最终可用、平衡结果、清算结算结果，也不能排除延迟和基差风险。

## 模拟源和正式源

商业订阅尚未配置时，`EEX_Sim`、`ICE_OCM_Sim` 和 `Trayport_Sim` 每 10 秒生成标准化 L1 报价。模拟源与正式适配器使用完全相同的 `market_quotes` 合同和后端扫描器，所有模拟报价及衍生机会都明确显示模拟标记。

替换模拟源时，只需实现写入相同字段的持牌数据适配器。正式适配器必须保留供应商产品标识、bid/ask、可见深度、交付期、事件时间、接收时间、去重键、币种/单位、权限、质量和来源引用。领域逻辑、API、SDK 和客户端不得因此修改。

运行模拟源不需要互联网。实现和验证 EEX、ICE OCM、Trayport、ICIS 等商业正式源需要互联网、客户合法凭证、许可和数据权限。

## 运行方式

配置 PostgreSQL 运行时 URL，显式执行迁移，然后启动 worker：

```powershell
alembic upgrade head
python scripts/ops/ingest_simulated_market_prices.py --loop
```

worker 对每个到期数据源 tick 写入一个事务，记录 ingestion run，写入标准化报价，扫描当前路径并持久化结果。Network、Market 或 Strategy 工作区打开时，Web 和桌面客户端每 10 秒读取一次 API。

状态解释：

- 无数据：worker、路径、费率、TSO access 或数据源配置不完整；
- `BLOCKED`：发现候选，但强制证据缺失或准入被拒绝；
- `WATCH`：当前经济性未达到复核阈值；
- `ACTIONABLE_REVIEW`：应立即检查，并独立确认成交和物理约束；
- `EXPIRED`：当前没有有效的后端快照。

## API 和 SDK

稳定公共接口：

```text
GET /api/market/quotes
GET /api/market/opportunities
GET /api/market/spreads
```

`spreads` 是从已持久化机会派生的兼容摘要。新客户端应使用 quotes 和 opportunities 接口。Python SDK 提供 `fetch_market_quotes_result()` 和 `fetch_intraday_opportunities_result()`，并保留响应元数据和警告。

## 发布边界

R30B 验证路径级跨市场决策信息流以及完整的 DB/API/SDK/客户端链路。R31 仍负责共享管容下的组合级分配、替代路径、本地销售选项和合同级 PnL 归因。多用户认证、商业数据权限强制执行、生产级持久调度和正式数据源认证仍属于后续发布门禁。
