# 市场定位驾驶舱规范 - 中文

## 目的

本规范定义 V1 的只读订单与 PnL 驾驶舱扩展。它帮助天然气交易员在地图优先的
Eurogas Nexus 工作台中查看外部屏幕活动、组合估值、路线经济性和策略输出，但
不会把 Eurogas Nexus 变成执行系统、订单路由系统、提名系统或 ETRM。所有输出
都属于决策支持，必须由交易员人工复核。

## 绝对数据边界

运行时事实来源是后端 API 背后的 PostgreSQL。正式客户端只能使用：

```text
Web / Windows / SDK -> /api/portfolio/* -> backend repositories -> PostgreSQL
```

客户端不得直接连接 PostgreSQL，不得保存订单或 PnL 文件，不得调用交易所或经纪商
接口，不得读取后端原始数据文件。外部订单记录只是导入后的观察数据，不是交易捕获
记录，也不能在 V1 中从客户端修改、撤销或确认。

## 已启用 API

```text
GET /api/portfolio/screen-orders
GET /api/portfolio/pnl-snapshots
GET /api/portfolio/live-summary
```

这些端点必须保持只读，并且返回的业务含义必须是 `research_only=true` 与
`human_review_required=true`。

## 已启用数据库表

- `screen_order_observations`
- `portfolio_pnl_snapshots`

这些表由 Alembic 版本 `0009_market_positioning` 引入，并通过后续导入、授权和
审计工作流继续使用。

## Web 和 Windows 体验规则

- 首页必须保持地图优先。
- 当节点和路线上下文足够时，地图可以用动画高亮当前订单或 PnL 相关走廊。
- 动画只用于信息展示，不代表提名、调度、订单路由或执行路径。
- 侧栏应展示订单状态、已成交数量、剩余数量、合约代码、指示性 PnL、提前回款价值
  和未完成屏幕订单数量。
- 文案必须避免使用“下单”“路由订单”“批准”“提名”“立即交易”等执行类表达。
- 缺少导入记录时，界面应显示明确的空状态或不可用状态，不得在浏览器侧生成样例订单
  或样例 PnL。

## 内部导入路线

R19/R21 已经实现内部操作员导入路线：

```text
POST /api/internal/portfolio/import-observations
```

该路线只在 internal profile 下暴露，并且需要：

```text
EUROGAS_NEXUS_INTERNAL_API_TOKEN
X-Eurogas-Internal-Token
X-Eurogas-Principal
```

如果后端没有配置 token、请求没有提供 token、token 不匹配，或者 principal 为空，
路线会在访问数据库之前失败关闭。这是 V1 内部操作员 token 门禁，不是公司
SSO/OIDC。

正式 Web、Windows、SDK 和 CLI 客户端必须继续使用只读 `/api/portfolio/*` 路线，
不得调用内部导入路线。

## 授权和审计

内部导入必须在写入观察表之前检查 `entitlement_decisions`。如果任意
source/dataset 组合没有授权，整个批次应被拒绝，并记录失败的 `ingestion_runs`
和 `audit_events`。成功批次也必须写入运行记录和审计记录。

## 接受测试

- `tests/api/test_portfolio_api.py`
- `tests/contract/test_market_positioning_models.py`
- `tests/sdk/test_portfolio_client.py`
- `tests/contract/test_client_release_surface.py`

## 下一步扩展

后续工作应加强导入器控制的客户订单/PnL upsert、授权过滤、审计 lineage、Review 页
中的警告和来源证据展示。除非产品边界被正式修改，客户端表面仍然必须保持只读。
