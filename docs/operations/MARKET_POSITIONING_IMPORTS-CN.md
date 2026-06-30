# 市场定位导入运行手册 - 中文

## 目的

Eurogas Nexus V1 可以在交易员驾驶舱中展示导入后的屏幕订单观察和指示性组合 PnL
快照。导入的目标是把外部系统状态写入 PostgreSQL，供 `/api/portfolio/*` 只读
端点展示。

这不是订单录入、订单路由、交易捕获、结算、会计、提名或自动交易。导入记录只是
外部系统状态的只读决策支持观察。

## 内部路线

仅 internal profile 暴露：

```text
POST /api/internal/portfolio/import-observations
```

必需请求头：

```text
X-Eurogas-Internal-Token: <operator-managed-token>
X-Eurogas-Principal: <operator-or-job-id>
```

后端运行环境必须配置：

```text
EUROGAS_NEXUS_INTERNAL_API_TOKEN
```

如果环境变量缺失、请求 token 缺失、token 不匹配，或者
`X-Eurogas-Principal` 为空，路线会在访问数据库之前失败关闭。这是 V1 内部操作员
token 门禁，不是公司 SSO/OIDC。token 不得写入日志、API 返回、仓库文件、Web、
Windows、SDK 或 CLI 客户端。

正式客户端继续读取：

```text
GET /api/portfolio/screen-orders
GET /api/portfolio/pnl-snapshots
GET /api/portfolio/live-summary
```

## 授权要求

导入路线默认失败关闭。导入前，PostgreSQL 必须存在已授权的
`entitlement_decisions` 记录，覆盖每一个 source/dataset 组合。

| 观察类型 | Dataset |
| --- | --- |
| 屏幕订单 | `screen-orders` |
| 组合 PnL 快照 | `portfolio-pnl` |

示例授权组合：

```text
ICE_OCM / screen-orders
INTERNAL_PNL / portfolio-pnl
```

如果授权缺失，整个批次会被拒绝，不写入任何观察记录。

## 审计和运行证据

每一个成功或拒绝的批次都必须写入：

- 一条 `ingestion_runs` 记录；
- 一条 `audit_events` 记录。

拒绝批次记录 `status=failed` 和 `outcome=denied`。成功批次记录
`status=succeeded` 和 `outcome=succeeded`。

## Payload 规则

每个批次必须包含：

- `batch_id`;
- `source_reference`;
- `screen_orders`;
- `pnl_snapshots`;
- `research_only=true`;
- `human_review_required=true`。

屏幕订单观察必须包含来源、交易场所、买卖方向、产品、交付窗口、价格、数量、
已成交数量、剩余数量、状态、观察时间、来源引用和治理标记。

PnL 快照必须包含组合、估值时间、已实现 PnL、未实现 PnL、指示性 PnL、提前回款
价值、市场价值、数量、估值基础、来源引用、警告列表和治理标记。

## 客户部署规则

客户特定的 EEX、ICE OCM、Trayport、经纪商、Kpler、Platts 或内部 PnL 适配器应先
标准化为该 payload 形状，再由受治理的后端任务调用内部路线或仓储函数。

Web、Windows、SDK 和 CLI 正式客户端不得直接写这些表，也不得保存外部订单或 PnL
文件作为运行时事实来源。
