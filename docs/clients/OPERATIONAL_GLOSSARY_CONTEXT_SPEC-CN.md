# 运行上下文术语表规格

## 目的

术语表不是静态帮助文本，而是交易员驾驶舱的一部分。用户选择术语时，系统必须同时说明
术语含义，并展示该术语在当前运行数据中的业务上下文。

## V1 必须行为

`GET /api/v1/glossary/{term}/context` 是术语运行上下文的唯一权威接口。
客户端必须通过 SDK/API 调用，不得直接连接 PostgreSQL。

接口参数：

- `lang=en|zh|zh-CN`；
- `duration_start_utc`；
- `duration_end_utc`。

对于 `Easington Entry Point`，如运行库存在相关数据，响应必须包含：

- 定义和中英文描述；
- 用户选择的时间段；
- 容量档案；
- 容量使用量，包含绝对值和百分比；
- 相关 NBP、ICE OCM、ICIS Heren 价格；
- 实时屏幕价格标记；
- 路线方案；
- 关联上游资源合同；
- 预警和数据质量元数据。

对于 `ICIS Heren`，响应必须展示价格评估上下文，并在未确认客户授权运行数据前包含
`ICIS_HEREN_REQUIRES_CUSTOMER_LICENSED_DATA`。

## 数据来源

后端从现有运行表生成上下文：

- `capacity_profiles`；
- `flow_observations`；
- `market_observations`；
- `live_market_marks`；
- `route_candidates`；
- `upstream_resource_contracts`。

如果 PostgreSQL 未配置，API 可以返回合成示例上下文，但必须通过 warnings 和
source references 明确标记。

## Web 客户端规则

Web 和 Windows 客户端必须展示：

- 常用术语快捷按钮，例如 `Easington Entry Point`、`ICIS Heren`、`NBP`、`ICE OCM`；
- 获取上下文前的时间段选择；
- 容量、容量使用率、价格、实时标记和关联合同指标卡；
- 易扫描的相关路线和合同；
- 面向用户可见的预警。

本功能仅用于决策支持，不得创建订单、提名、审批或官方交易建议。
