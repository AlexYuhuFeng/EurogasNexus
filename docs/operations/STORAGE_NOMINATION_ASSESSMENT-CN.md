# 储气与提名评估运营手册

英文版：[STORAGE_NOMINATION_ASSESSMENT.md](STORAGE_NOMINATION_ASSESSMENT.md)

## 目的

R34 把已验证的储气调度和提名窗口引擎暴露为交易员复核的评估工作流。这些
端点绝不提交储气预订、提名或改提名。

```text
POST /api/optimization/storage-dispatch
POST /api/optimization/nomination-window
```

## 契约

两个端点只接受 `decision_context=SANDBOX_SCENARIO`。在 DB 所有的储气设施与
提名窗口 master 数据交付前，`RUNTIME_DECISION` 返回 422。

- 储气调度输入为显式设施参数与价格周期。
- 提名输入为显式窗口与按时间排序的指令。
- 结果始终 `human_review_required=True`，在配置运行库时写入
  `optimization_runs` 证据。

## 示例：储气调度

```json
{
  "facility": {
    "initial_inventory_mwh": 100,
    "minimum_inventory_mwh": 0,
    "maximum_inventory_mwh": 200,
    "maximum_injection_mwh": 50,
    "maximum_withdrawal_mwh": 50,
    "terminal_inventory_mwh": 100
  },
  "periods": [
    {"period_id": "p1", "market_price_gbp_mwh": 10},
    {"period_id": "p2", "market_price_gbp_mwh": 30}
  ],
  "inventory_step_mwh": 50
}
```

## 示例：提名评估

```json
{
  "initial_quantity_mwh": 100,
  "windows": [
    {
      "window_id": "within-day",
      "opens_at": "00:00",
      "closes_at": "06:00",
      "maximum_change_mwh": 10
    }
  ],
  "instructions": [
    {
      "submitted_at": "2026-01-01T01:00:00+00:00",
      "requested_quantity_mwh": 115
    }
  ]
}
```

响应包含接受/调整后的量与原因码（`ACCEPTED`、
`RENOMINATION_CHANGE_LIMIT_APPLIED`、`OUTSIDE_NOMINATION_WINDOW`）。仅为评估。

## Runtime decision（R34A）

两个端点现在在 PostgreSQL master 存在时接受 RUNTIME_DECISION：

- 储气：`facility_id` + `gas_day` 组装设施 master、最新库存观测、市场周期与
  as-of FX；
- 提名：`gas_day` 组装有效窗口 master；指令仍是显式评估输入。

RUNTIME_DECISION 会拒绝客户端提供的设施/窗口事实。表：
`storage_facility_masters`、`storage_inventory_observations`、
`nomination_window_masters`（迁移 `0023`）。

## 安全验收

`scripts/security/run_security_acceptance.py --json` 输出自动化证据。在渗透
测试、OIDC TLS 评审、备份恢复演练和负责人签批完成前，外部验收仍为
BLOCKED。本仓库永远不会加入提交动作。
