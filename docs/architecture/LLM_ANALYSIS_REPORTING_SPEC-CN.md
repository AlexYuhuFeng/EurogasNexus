# LLM 分析与报告规格 - CN

## V1 决策

DeepSeek 是 V1 第一个支持的实时 LLM Provider。OpenAI、Claude 和其他 provider
保留为凭证/适配器槽位，后续里程碑再添加并测试。

导入代码、测试、Web、Windows、SDK 和 CLI 都不得直接调用 LLM。唯一允许的实时
路径是：

```text
Client -> /api/v1 -> backend analysis route -> backend credential store -> DeepSeek
```

## 凭证规则

用户可以通过供应商凭证 UI/API 输入 DeepSeek API Key。后端将其加密存储在
PostgreSQL 中。明文 key 只写不读，不得返回给客户端、日志、报告或测试。

Provider ID：

- `DEEPSEEK`：V1 首选 LLM provider；
- `LLM`：旧版/通用 fallback 凭证槽。

## 分析能力

V1 分析支持：

- 基于后端快照的 DB inquiry；
- business logic ontology 解释；
- glossary Q&A；
- PnL tracking readiness 和预警；
- TSO operation status report；
- portfolio/resource/contract report；
- market movement synthesis；
- strategy run 和 shadow-run context summary。

LLM provider 不是事实来源。事实来源仍然是 PostgreSQL。Provider 只能接收结构化
快照，不得直接访问数据库。

## 报告生成

报告必须包含：

- 当前 portfolio 或选定 resources/contracts；
- 正在运行的 strategy 和 strategy run 状态；
- 若已持久化 PnL series，则展示自 strategy/portfolio 生效以来的历史 PnL；
- 选定时间段内相关市场价格、数量、FX、路线成本、flow、storage、LNG 和 warning；
- 带引用的候选市场决策支持 commentary。

报告必须包含 source references、missing inputs、warnings、`research_only` 和
`human_review_required`。

## 术语表集成

术语表 term 可通过以下端点暴露运营上下文：

```text
GET /api/v1/glossary/{term}/context
```

示例：

- Easington Entry Point：描述、容量、选定快照/时间段的容量使用率、相关
  NBP/ICE OCM/ICIS 价格、路线选项和来源状态。
- ICIS Heren：价格评估描述、license warning、相关价格和市场来源上下文。

如果运行时 DB 数据不可用，端点必须返回带明确 warning 的 partial context，不得
编造客户数据。

## 当前端点

```text
GET  /api/v1/analysis/ontology
POST /api/v1/analysis/query
POST /api/v1/reports/portfolio
GET  /api/v1/glossary/{term}/context
```

## 互联网要求

只有在 `invoke_provider=true` 且已配置 DeepSeek credential 时才需要互联网。
离线开发和测试使用确定性的 snapshot output，不得调用任何 LLM provider。
