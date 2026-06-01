# 市场持仓驾驶舱规范 - CN

## 目的

本规范定义 V1 的只读订单/PnL 驾驶舱扩展。它用于帮助天然气交易人员在地图优先
工作台中查看外部屏幕活动、组合估值、路线经济性和策略输出，但不会把 Eurogas
Nexus 变成订单执行、订单路由、提名提交或 ETRM 系统。

## 绝对数据边界

运行时事实来源是后端 API 背后的 PostgreSQL。客户端只能使用：

```text
Web/Windows/SDK -> /api/v1/portfolio/* -> 后端仓储 -> PostgreSQL
```

客户端不得直接连接 PostgreSQL，不得保存订单/PnL 文件，不得直接调用交易所，
也不得读取后端原始数据文件。外部订单记录只是导入的观察数据，不是交易捕获记录，
V1 不允许从客户端修改或撤销这些订单。

## 已启用 API

- `GET /api/v1/portfolio/screen-orders`
- `GET /api/v1/portfolio/pnl-snapshots`
- `GET /api/v1/portfolio/live-summary`

所有端点都返回 `research_only=true` 和 `human_review_required=true`。

## 已启用数据库表

- `screen_order_observations`
- `portfolio_pnl_snapshots`

这些表由 Alembic 版本 `0009_market_positioning_foundation` 引入。

## Web/Windows UX 规则

- 首页必须保持地图优先。
- 如果节点上下文足够，地图必须用动画高亮展示当前订单/PnL 相关路线。
- 当实时盯市结果尚未产生时，地图上方指标条必须使用运行时观察数据展示指示性
  PnL。
- 侧栏必须展示订单状态、已成交数量、剩余数量、合约代码、指示性 PnL、提前回款
  价值和未完成屏幕订单数量。
- 界面文案不得使用 “下单”、“路由订单”、“批准”、“提名” 或 “立即交易” 等执行类
  表述。

## 验收测试

- `tests/api/test_portfolio_api.py`
- `tests/contract/test_market_positioning_models.py`
- `tests/sdk/test_portfolio_client.py`
- `tests/contract/test_client_release_surface.py`

## 下一步扩展

Milestone 2 应增加由导入器控制的客户订单/PnL upsert 路径、带授权过滤的查询、
以及可审计 lineage。除非产品边界正式变更，客户端表面仍必须保持只读。
## R19 内部导入路径

R19 已实现首个内部导入路径：

```text
POST /api/internal/portfolio/import-observations
```

该路由仅供内部/操作员使用。除非 `entitlement_decisions` 对每一个来源和数据集组合授权，
否则批次默认失败关闭。成功和拒绝的批次都会写入 `ingestion_runs` 与 `audit_events`。
Web、Windows、SDK 和 CLI 正式客户端必须继续使用只读 `/api/v1/portfolio/*` 路由。
