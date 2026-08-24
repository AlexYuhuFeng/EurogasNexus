# 组合网络优化运营手册

英文版：[PORTFOLIO_NETWORK_OPTIMIZATION.md](PORTFOLIO_NETWORK_OPTIMIZATION.md)

## 目的

`POST /api/optimization/portfolio-network` 是 R31 的 PostgreSQL 组合级日度
优化端点，把已验证的共享管容网络流引擎接入 PostgreSQL 拥有的商业与基础
设施事实。它只做决策支持：所有结果必须经交易员复核，绝不提交订单、提名、
管容预订或合同修改。

## 请求契约

```json
{
  "portfolio_id": "portfolio-id",
  "gas_day": "2026-01-01",
  "capacity_product": "ANNUAL",
  "firmness": "FIRM",
  "max_market_price_age_hours": 72,
  "decision_context": "RUNTIME_DECISION"
}
```

- `capacity_product`：`ANNUAL`、`QUARTERLY`、`MONTHLY`、`WEEKLY`、`DAILY`
  或 `WITHIN_DAY`。
- `firmness`：`FIRM`、`INTERRUPTIBLE`、`BACKHAUL` 或 `OFF_PEAK`。
- 不允许提交任何网络边、费率、管容、市场价格、合同量或 TSO 权限；
  Pydantic 会在任何数据库查询前拒绝额外字段。

## 从 PostgreSQL 组装的事实

| 领域输入 | 来源表 |
|---|---|
| 上游资源 | `upstream_resource_contracts` |
| 销售目的地 | `market_observations` 关联有效 `route_candidates` |
| 路径拓扑与路径管容 | `route_candidates` |
| 规范节点 ID | `reference_nodes` |
| 费率选择 | `tso_tariffs`（点/TSO/方向/气体年/产品/可靠性的精确匹配） |
| 公司 TSO 权限 | `company_tso_access`（`ACTIVE`/`CONFIRMED` 放行；`DENIED`/`INACTIVE`/`SUSPENDED` 阻断） |
| FX as-of 换算 | `fx_observations`（value date 不晚于 `gas_day`） |

市场价格只选择覆盖 `gas_day` 的观测，优先 day-ahead/within-day，同一基差下
优先非仿真数据。价格年龄按 `min(now, gas-day end)` 计算，历史 gas day 的
决策不会因为事后才评估而被误判为过期。

## 求解与归因

组装结果变成共享有向气体网络上的供应弧、可选销售弧和路由边。残量最小
成本流模型可以在更优组合出现时取消并重路由早先分配。最终流量被分解为
“来源→销售”路径，并聚合为合同级 PnL 归因：

- `quantity_mwh`
- `revenue_gbp`
- `supply_cost_gbp`
- `network_cost_gbp`
- `pnl_gbp`

合同级归因 PnL 之和等于组合目标值。

## 失败模式

| HTTP | 代码 | 含义 | 运营动作 |
|---|---|---|---|
| 422 | `sandbox_scenario_not_supported` | 向纯 DB 端点发送了沙箱场景 | 使用 `/api/optimization/route` 或 `/resource-pool` 做 what-if |
| 422 | `runtime_decision_input_blocked` | PostgreSQL 快照不完整或过期 | 检查 `blockers`，补录/刷新对应表后重试 |
| 503 | `runtime_db_not_configured` | 未配置运行数据库 URL | 配置 `RUNTIME_STORE_DATABASE_URL` |
| 503 | `runtime_db_unavailable` | 已配置但数据库不可用 | 检查 PostgreSQL 健康状态 |

常见阻断项包括 `UPSTREAM_CONTRACTS_MISSING`、`ROUTE_CANDIDATES_MISSING`、
`REFERENCE_NODES_MISSING`、`SUPPLY_NODE_MISSING:<contract>`、
`ROUTE_NODE_MISSING:<route>`、`MARKET_PRICE_MISSING:<point>`、
`MARKET_PRICE_STALE:<point>`、`MARKET_PRICE_CONVERSION_BLOCKED:<point>`、
`TSO_ACCESS_MISSING:<route>`、`TSO_ACCESS_DENIED:<route>`、
`ROUTE_CAPACITY_UNKNOWN:<route>` 和 `ROUTE_COST_MISSING:*`。被阻断的组合
绝不会进入求解器。

## 证据

每次成功运行都会追加一条不可变 `optimization_runs` 记录：

- `optimization_type = "portfolio_network"`
- `decision_context = "RUNTIME_DECISION"`
- `input_snapshot` 保存组装后的资源、销售选项、边、来源追踪、假设、市场和
  FX 观测 ID
- `output_snapshot` 保存完整结果，含路径级与合同级归因

通过 `GET /api/optimization/runs/{run_id}` 查询证据。

## 边界提醒

- 客户端不得直连 PostgreSQL，也不得直接调用数据提供商。
- 该端点是交易员复核的决策支持，不是执行通道。
- 响应信封保持 `research_only=True` 与 `human_review_required=True`。
