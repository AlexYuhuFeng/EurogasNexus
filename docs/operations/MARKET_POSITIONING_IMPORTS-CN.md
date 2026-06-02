# 市场持仓观察导入

## 目的

Eurogas Nexus V1 可以在交易员驾驶舱中展示外部屏幕订单观察和指示性组合
PnL 快照。R19 增加了受治理的内部导入路径，用于把这些观察记录写入
PostgreSQL。R21 在该路径前增加内部操作员 token 和显式 principal 校验。

这不是下单、订单路由、交易捕获、结算、会计、提名或自动交易。导入记录只是
外部系统状态的只读决策支持观察。

## 路由

仅内部 profile 暴露：

```text
POST /api/internal/portfolio/import-observations
```

必需请求头：

```text
X-Eurogas-Internal-Token: <由操作员管理的 token>
X-Eurogas-Principal: <操作员或后端任务标识>
```

后端运行环境必须配置 `EUROGAS_NEXUS_INTERNAL_API_TOKEN`。如果环境变量未配置、
请求未带 token、token 不匹配，或 `X-Eurogas-Principal` 为空，路由会在访问
数据库前失败关闭。这是 V1 内部操作员 token 门禁，不是公司 SSO/OIDC。token
不得被日志打印、API 返回、提交到仓库，或保存在 Web、Windows、SDK、CLI 客户端。

正式客户端继续读取：

```text
GET /api/v1/portfolio/screen-orders
GET /api/v1/portfolio/pnl-snapshots
GET /api/v1/portfolio/live-summary
```

## 权限要求

导入路由默认失败关闭。导入前，PostgreSQL 必须存在已授权的
`entitlement_decisions` 记录，覆盖每一个来源和数据集组合：

| 观察类型 | 数据集 |
| --- | --- |
| 屏幕订单 | `screen-orders` |
| 组合 PnL 快照 | `portfolio-pnl` |

示例授权组合：

```text
ICE_OCM / screen-orders
INTERNAL_PNL / portfolio-pnl
```

如果授权缺失，整个批次会被拒绝，不写入任何观察记录。

## 审计和运行记录

每一个成功或拒绝的批次都会写入：

- 一条 `ingestion_runs`；
- 一条 `audit_events`。

拒绝批次记录 `status=failed` 和 `outcome=denied`。成功批次记录
`status=succeeded` 和 `outcome=succeeded`。

## Payload 规则

每个批次必须包含：

- `batch_id`
- `source_reference`
- `screen_orders`
- `pnl_snapshots`
- `research_only=true`
- `human_review_required=true`

屏幕订单观察必须包含来源、交易场所、买卖方向、产品、交付窗口、价格、数量、
已成交量、剩余量、状态、观察时间、来源引用和治理标记。

PnL 快照必须包含组合、估值时间、已实现/未实现/指示性 PnL、提前回收现金价值、
市场价值、数量、估值基础、来源引用、预警列表和治理标记。

## 客户部署规则

客户特定的 EEX、ICE OCM、Trayport、经纪商、Kpler、Platts 或内部 PnL 适配器
应先标准化为该 payload，再由受治理的后端任务调用内部路由或仓储函数。Web、
Windows、SDK 和 CLI 正式客户端不得直接写这些表。
