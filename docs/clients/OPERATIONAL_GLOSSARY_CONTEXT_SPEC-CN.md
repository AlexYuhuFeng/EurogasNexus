# 操作型术语上下文规范

## 目的

Glossary 是交易员 cockpit 的产品表面，不是静态帮助文本。选择一个术语时，系统必须展示该术语含义，以及当前运行时数据如何让它具备商业意义：capacity、capacity in use、prices、live marks、route options、contracts、sources、warnings 和 data quality。

## Canonical API

`GET /api/glossary/{term}/context` 是操作型术语上下文的唯一来源。Web、Windows、CLI 和 SDK 必须通过 API 或 SDK 调用。任何客户端都不得直接连接 PostgreSQL 或读取后端本地数据文件。

支持参数：

- `lang=en|zh|zh-CN`
- `duration_start_utc`
- `duration_end_utc`

## 必需响应字段

响应必须保留旧标量字段，并包含 V1 分组字段：

- `description`, `description_en`, `description_zh_cn`
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

`capacity_usage` 必须支持选定时间段分析。多条 flow records 命中时，API 必须返回 average used capacity、peak used capacity、utilization percentage、peak utilization percentage、source references 和 observation count。若 flow 为 `mcm/d` 且 capacity 为 `MWh/d`，V1 可以使用明确标注的假设 `1 mcm = 10,550 MWh`，直到接入按 CV 的换算。

## 匹配规则

Resolver 必须 deterministic 且 DB-first：

1. 从请求 term 开始。
2. 加入匹配的 glossary term names、aliases、related terms 和 source refs。
3. 匹配运行库记录：
   - `capacity_profiles`
   - `flow_observations`
   - `market_observations`
   - `live_market_marks`
   - `route_candidates`
   - `upstream_resource_contracts`
4. 从 term 和 runtime records 推断 `context_type`：
   - `entry_point`：命中 entry point records；
   - `exit_point`：命中 exit point records；
   - `hub`：命中 hub glossary records；
   - `venue`：命中 venue glossary records；
   - `price_assessment`：命中 price glossary records 或 matched price rows；
   - `capacity`：未匹配到更强类型但命中 capacity/flow point；
   - `generic`：只有在没有更强 runtime 或 glossary signal 时使用。
5. 只有在无 dedicated profile 且无 runtime match 时，才返回 `TERM_CONTEXT_MAPPING_PARTIAL`。

功能不得绑定任何硬编码点位。只要 PostgreSQL 中存在 glossary、capacity、flow、price、route 和 contract records，`Zeebrugge Entry Point`、`GATE LNG`、`TTF` 或任意客户加载的 TSO asset 都必须可展示。

## 示例行为

对于 `Zeebrugge Entry Point`，上下文应展示：

- interconnector 或 TSO point 描述；
- selected duration；
- capacity profile；
- MWh/d 或 mcm/d 口径的 capacity in use 和百分比；
- 相关 hub、screen、assessment prices；
- live bid/ask/last screen marks；
- route candidates；
- linked upstream contracts；
- warnings 和 data-quality metadata。

对于 `ICIS Heren`，上下文应展示：

- licensed price-assessment 描述；
- customer-licensed 或 operator-entered runtime price records；
- 相关 screen marks；
- 除非 entitlement 和客户加载的授权数据明确存在，否则必须返回 `ICIS_HEREN_REQUIRES_CUSTOMER_LICENSED_DATA`。

## Web 和 Windows UX 规则

Web workspace 是唯一 UI 源；Windows 包装构建后的 Web client。Glossary panel 必须渲染：

- high-value terms 快捷上下文按钮；
- fetch context 前的 duration selectors；
- matched entity chips；
- metric cards；
- capacity、prices/live marks、routes、contracts、data quality 分组；
- visible warnings。

该功能仅为 decision support，不得创建订单、提名、审批、法律意见或官方交易推荐。
