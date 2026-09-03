# LLM 分析与报告规范 - 中文

## V1 决策

DeepSeek 是 V1 首个支持的实时 LLM provider。OpenAI、Claude 以及其他 provider 保留为后续扩展槽位，只有在适配器、凭据、审计和测试完成后才启用。

LLM 调用不得在 import、测试、Web、Windows、SDK 或 CLI 中直接发生。唯一允许路径为：

```text
Client -> /api -> backend analysis route -> backend credential store -> DeepSeek
```

## 凭据规则

用户可通过 provider credential UI/API 输入 DeepSeek API key。后端负责写入 PostgreSQL 中的加密凭据。明文 key 是 write-only，不得返回给客户端、日志、报告或测试。

Provider ID：

- `DEEPSEEK`：V1 首选 LLM provider；
- `LLM`：legacy/generic fallback credential slot。

## 分析能力

V1 analysis 支持：

- 基于后端 snapshot 的 DB inquiry；
- business-logic ontology 解释；
- glossary Q&A；
- PnL tracking readiness 和 warnings；
- TSO operation status report；
- portfolio/resource/contract report；
- market movement synthesis；
- strategy run 和 shadow-run context summary。

LLM provider 不是事实来源。事实来源始终是 PostgreSQL。Provider 接收结构化 snapshot，不直接访问数据库。

## 报告生成

报告必须包含：

- 当前 portfolio 或 selected resources/contracts；
- 当前 strategy 和 strategy run state；
- 已持久化时的 historical PnL；
- 所选时间段相关的 market prices、quantities、FX、route costs、flows、storage、LNG 和 warnings；
- 带 citations 的候选市场 decision-support commentary。

报告必须包含 source references、missing inputs、warnings、`research_only` 和 `human_review_required`。

## Glossary 集成

Glossary term 可通过下列 endpoint 暴露操作上下文：

```text
GET /api/glossary/{term}/context
```

示例：

- Zeebrugge Entry Point、GATE LNG 或 TTF：描述、所选 snapshot/duration 的容量与容量使用率、相关 hub/screen/assessment 价格、route options 和 source status。
- ICIS Heren：assessment 描述、授权数据 warning、相关价格和 market-source context。

如果 runtime DB 数据不可用，endpoint 必须返回带明确 warnings 的 partial context，不得发明客户数据。

## 当前 endpoints

```text
GET  /api/analysis/ontology
POST /api/analysis/query
POST /api/reports/portfolio
GET  /api/glossary/{term}/context
```

## 互联网要求

只有在 `invoke_provider=true` 且已配置 DeepSeek 凭据时才需要互联网。离线开发和测试使用 deterministic snapshot output，且不得调用任何 LLM provider。
