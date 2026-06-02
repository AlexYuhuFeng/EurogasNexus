# 运行上下文术语表规格

## 目的

术语表不是静态帮助文本，而是交易员驾驶舱的一部分。用户选择术语时，
系统必须同时说明该术语的含义，并展示运行库中让该术语具有商业意义的
上下文：容量、容量使用量、价格、实时标记、路线选项、合同、来源、预警
和数据质量。

## 权威 API

`GET /api/v1/glossary/{term}/context` 是运行上下文术语表的唯一权威接口。
Web、Windows、CLI 和 SDK 调用方必须通过 API 或 SDK 使用该能力。任何客户
端都不得直接连接 PostgreSQL，也不得直接读取后端本地数据文件。

支持的查询参数：

- `lang=en|zh|zh-CN`
- `duration_start_utc`
- `duration_end_utc`

## 必须返回的结构

响应必须保留既有字段，并包含 V1 分组上下文字段：

- `description`、`description_en`、`description_zh_cn`
- `requested_duration`
- `entity_summary`
- `matched_entities`
- `capacity`
- `capacity_usage`
- `metrics`
- `related_prices`
- `live_market_marks`
- `related_routes`
- `related_contracts`
- `context_sections`
- `related_sources`
- `data_quality`
- `warnings`
- `research_only=true`
- `human_review_required=true`

`capacity_usage` 必须支持用户选择的时间段。如果一个时间段内匹配到多条流量
记录，API 必须返回平均使用量、峰值使用量、使用率百分比、峰值使用率百分比、
来源引用和观测数量。如果流量单位为 `mcm/d`，容量单位为 `MWh/d`，V1 可以使用
明确记录的换算假设 `1 mcm = 10,550 MWh`，直到后续版本接入按热值换算的能力。

## 匹配规则

解析器必须是确定性的，并且以数据库为先。

1. 从用户请求的术语开始。
2. 加入匹配到的术语名称、别名、相关术语和来源引用。
3. 匹配以下运行库表中的记录：
   - `capacity_profiles`
   - `flow_observations`
   - `market_observations`
   - `live_market_marks`
   - `route_candidates`
   - `upstream_resource_contracts`
4. 根据术语和运行记录推断 `context_type`：
   - 入口点术语或入口点运行记录为 `entry_point`；
   - 出口点运行记录为 `exit_point`；
   - 枢纽术语为 `hub`；
   - 市场/交易场所术语为 `venue`；
   - 价格术语或匹配价格记录为 `price_assessment`；
   - 未匹配到更强类型但有容量/流量点记录时为 `capacity`；
   - 只有在没有更强术语或运行库信号时才使用 `generic`。
5. 只有在没有专用 profile 且没有任何运行库匹配时，才返回
   `TERM_CONTEXT_MAPPING_PARTIAL`。

`Easington Entry Point` 这样的硬编码示例可以继续作为提示，但功能不得局限于
Easington/Bacton。只要客户在 PostgreSQL 中加载了术语、容量、流量、价格、路线
和合同记录，`St Fergus Entry Point` 等其他点也必须能够生成上下文。

## 示例行为

对于 `Easington Entry Point`，上下文应展示：

- 英国 NTS/海滩交付说明；
- 用户选择的时间段；
- 容量档案；
- 以 MWh/d 或 mcm/d 表示的容量使用量及百分比；
- 相关 NBP、ICE OCM 和 ICIS Heren 价格；
- 实时 bid/ask/last 屏幕标记；
- 路线候选；
- 关联上游合同；
- 预警和数据质量元数据。

对于 `ICIS Heren`，上下文应展示：

- 授权价格评估说明；
- 客户授权或操作员录入的运行库价格记录；
- 通过相关术语连接的 ICE OCM/NBP 等屏幕标记；
- 在未明确存在授权与客户加载的授权数据前，必须包含
  `ICIS_HEREN_REQUIRES_CUSTOMER_LICENSED_DATA`。

## Web 和 Windows 体验规则

Web 工作台是唯一 UI 源，Windows 客户端包装构建后的 Web 客户端。术语表面板
必须展示：

- 高价值术语的快捷上下文按钮；
- 获取上下文前的时间段选择器；
- 匹配实体标签；
- 指标卡片；
- 容量、价格/实时标记、路线、合同和数据质量分组；
- 对用户可见的预警。

本功能仅用于决策支持。不得创建订单、提交提名、执行审批、提供法律意见，
也不得生成官方交易建议。
