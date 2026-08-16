# Eurogas Nexus 本体化 Gap 报告

> 对照 `docs/ontology/europe-natural-gas.md`（主体架构 v0.2），盘点 Eurogas Nexus
> 现有 glossary / ontology / guardrails 的「已有 / 缺 / 重复 / 冲突」。
> 本报告**只陈述事实与建议**，不修改任何代码。

- **版本**：v0.1
- **范围**：仅后端/领域层（`src/eurogas_nexus/`）+ DB 模型 + 与本体相关的 API。
- **方法**：按五构件（概念/关系/动作/受控词表/约束）+ L1–L5 分层逐项核对代码。

---

## 0. 核心结论（先说重点）

Eurogas Nexus 的领域知识层**已经存在，但处于"隐式 + 分散 + 部分重复"状态**，与
主体架构的差距不是"没有"，而是"没有单一真相源"和"没有声明式约束"。最值得优先
处理的三件事：

1. **重复**：存在 **4 套重叠的本体面**，且其中一套（`business_ontology_terms` 表）
   是**无写入者的孤儿表**。
2. **分散**：`research_only` / `human_review_required` 两个治理布尔被硬编码在
   **约 50 个文件**里，没有单一出处。
3. **缺**：没有 `MarketArea` / `InterconnectionPoint` 一等实体，没有集中式 L5
   约束模块（唯一例外是 `governance/entitlement.py`，这恰是应推广的正面样板）。

---

## 1. 现状盘点（有据）

### 1.1 四套重叠的"本体"面（重复）

| # | 位置 | 内容 | 状态 |
|---|---|---|---|
| A | `src/eurogas_nexus/domain/analysis.py:117` `business_logic_ontology()` | 硬编码 dict：16 实体 / 8 关系 / 5 guardrails | 代码常量，经 `/api/analysis/ontology` 暴露 |
| B | `src/eurogas_nexus/domain/glossary.py:35` `baseline_glossary_terms()` | 硬编码 list：29 条双语术语 | 代码常量，经 `/api/glossary` 暴露，作为 DB 回退 |
| C | `src/eurogas_nexus/db/models/glossary.py:11` `GlossaryTermRecord` → `glossary_terms` | 数据库表 | 由 `scripts/ops/seed_preview_runtime_data.py:333` 写入，是运行时真相 |
| D | `src/eurogas_nexus/db/models/analysis.py:58` `BusinessOntologyRecord` → `business_ontology_terms` | 数据库表（migration 0008） | **孤儿：全仓库无任何写入者** |

**冲突/风险**：A/B 是代码常量、C 是 DB、D 是空表——四者语义重叠却**没有单一真相源**，
与"PostgreSQL 是运行时唯一真相"的铁律相悖。A 的 `entities`（16 个）与 B 的
`category`（institution/venue/hub/capacity/price/financial/contract/weather/
infrastructure/route）**命名不一致**，是真实的概念漂移点。

### 1.2 治理布尔散落（分散）

`research_only` / `human_review_required` 被硬编码在约 **50 个文件**，横跨：

- `workflows/`（legacy 工作流壳：route_cost / netback / feasibility / allocation /
  monitoring / nowcast / backtest / shadow_run / models）
- `domain/`（analysis / market_positioning / strategy_lab / route_cost/* / monitoring）
- `db/models/`（observation / strategy / market_positioning / monitoring /
  market_intelligence / analysis）
- `api/routes/public/`（多个 `_env` 封装里重复 `"research_only": True`）
- `sdk/`、`ingestion/`

**唯一正面样板**：`src/eurogas_nexus/governance/entitlement.py` 已把 fail-closed
集中成一个模块（"Entitlement and export decision shells — fail-closed by default"），
`governance/audit.py` 也已独立。这说明"集中式治理"这条路项目里已有先例，只是没推广。

### 1.3 领域模块形态（缺/占位）

`src/eurogas_nexus/domain/` 下已实现：

- `route_cost/`（13 个文件：tariff_selection、european_public_tariffs、
  uk_public_tariffs、uk_rules、capacity_requirement、resource_pool、lng_regas、
  live_markets、route_optimizer、route_cost_service、schemas、enums、tariff_models）
- `strategy_lab/evaluation.py`、`market_positioning.py`、`market_positioning_import.py`、
  `analysis.py`、`glossary.py`、`market_intelligence/opportunity_engine.py`、`monitoring/`

以下为**仅有 `__init__.py` 的占位包**（无实现）：`allocation / assets / economics /
feasibility / market / netback / nowcast / operations / relationships / reporting /
resources / topology / weather`。这些包名与主体架构的环节**部分对应、部分脱节**，
是"目录在、能力不在"的实例。

### 1.4 已有且应保留的资产（good）

- `governance/entitlement.py`（fail-closed 集中化）+ `governance/audit.py`
- 双语术语基线 `glossary.py`（29 条，带 aliases/related_terms/source_refs）
- `strategy_lab`（本轮已补 DB 持久化 + 累计绩效，见上轮交付）
- 标准化 `data/meta` 信封（`research_only`/`human_review_required` 语义一致，虽散落）

---

## 2. 五构件 × 四状态 矩阵

| 构件 | 已有 | 缺 | 重复 | 冲突 |
|---|---|---|---|---|
| 概念（concepts） | `reference_market_hubs`（枢纽已是表）、`reference_nodes.node_type`（含 `interconnection`）、`reference_tso_access_points`（含相邻国/相邻运营商/CAM-CMP）、`topology_market_mappings`（node↔hub 绑定） | **market area / balancing zone 聚合层**（hub=点、zone=区域/国家，当前未显式建模）；`business_ontology_terms` 表无内容 | A/B/C/D 四套实体面 | A 的 entities 与 B 的 category 命名不一致 |
| 关系（relations） | `business_logic_ontology()` 8 条字符串关系 | 无类型化关系（全是扁平字符串）；无 zone↔hub 绑定 | — | — |
| 动作（actions） | `PaperAction`、`candidate_action_for_review`、`StrategyRunMode` | 无统一动作词表/白名单（no-execution 靠散落的语言约定） | legacy `workflows/` 与 domain 重复 | 无 |
| 受控词表（vocab） | `glossary.py` 29 条 + `glossary_terms` 表 | 无"唯一权威词表"；产品/tenor 规范化散在前端 | A/B/C 三处词表 | 前端 `marketPriceNormalization` 与后端术语可能漂移 |
| 约束（constraints） | `governance/entitlement.py`（fail-closed）、`strategy_lab` 止损、`route_cost` 容量/净回值 | 无集中式 L5 约束模块；容量守恒/净回值/止损散在 domain | — | `research_only` 在 data 与 meta 双处（AGENTS.md 明确"仅 meta 兼容"，但多处 model 仍当 data 字段） |

---

## 3. L1–L5 分层核对

| 层 | 现状 | 判定 |
|---|---|---|
| L1 声明式本体 | 有 `business_logic_ontology()`（扁平 dict）+ `glossary_terms` 表，但无类型化、无单一源 | **部分，需显式化 + 单一化** |
| L2 流程 | 工作流散在 Web（Network→Scenario→Review）与 operator 命令，无后端流程模型 | **缺** |
| L3 经验 | 价差阈值/时间窗/分桶散在 `strategy_lab` 与前端 `strategyScenario.ts` | **部分，未声明式** |
| L4 制度 | `governance/entitlement.py` + `audit.py` + AGENTS.md 明文 | **部分，已集中但未覆盖全量** |
| L5 可计算约束 | 容量/净回值/止损散在 `route_cost`、`strategy_lab` | **部分，散落，需抽取** |

---

## 4. 建议的 ExecPlan 切片（按优先级，每个都小步、可验收）

> 遵循 AGENTS.md：每个切片一个 ExecPlan + 测试 + 双语文档；DB-first；import-safe。

1. **S1 — 单一本体源（收口 4 套重复）**
   决定保留谁：建议 `glossary_terms` 表为词表真相，`business_logic_ontology()`
   改为**由 DB 驱动的类型化 L1**（或反之，但必须单一）；`business_ontology_terms`
   表要么接入写入、要么迁移下线。这是最高优先级的"止血"。

2. **S2 — 市场区/平衡区聚合层（窄化后）**
   参考网络**已具备** hub（`reference_market_hubs` + `hub_code`）、interconnection
   （`node_type` + `reference_tso_access_points`）、node↔hub 绑定
   （`topology_market_mappings`）。真正的缺口仅是 **market area / balancing zone
   聚合层**（hub=点、zone=区域/国家）。只需新增轻量 `market_areas` 引用表并把
   hub/zone 绑定，**无需重建 hub/IP**。直接喂给 glossary-context 与 R31 跨境分配。

3. **S3 — 集中式 L5 约束模块**
   新 `domain/constraints/`（import-safe、声明式、单测），先抽已有且已测的两个：
   净回值/路线成本公式、容量守恒 + 止损；再抽 entitlement fail-closed（并入现有
   `governance/entitlement.py` 的推广）；no-execution 做成动作白名单枚举。

4. **S4 — 治理布尔收口**
   `research_only`/`human_review_required` 收敛为信封层统一注入（保持 data 不冗余），
   消除 ~50 文件的硬编码。此切片范围较大，建议最后做，且单独评估影响面。

---

## 5. 未决问题（留给讨论）

1. 四套本体面里，**保留哪一套做单一真相源**？（建议 C=glossary_terms 表，D 下线或并入）
2. 占位包（`allocation/economics/feasibility/market/netback/...`）是**保留作未来目录**，
   还是清理掉以减噪？
3. `research_only` 在 data 字段的存量用法，是**一次性迁移到 meta**，还是冻结不动？
4. S1–S4 的执行顺序是否需要调整（例如先做 S2 锚点、再收口 S1）？

---

## 参考文件（本报告依据）

- `src/eurogas_nexus/domain/analysis.py`（`business_logic_ontology()`）
- `src/eurogas_nexus/domain/glossary.py`（`baseline_glossary_terms()`）
- `src/eurogas_nexus/db/models/glossary.py`、`src/eurogas_nexus/db/models/analysis.py`
- `src/eurogas_nexus/governance/entitlement.py`、`src/eurogas_nexus/governance/audit.py`
- `scripts/ops/seed_preview_runtime_data.py`
- `docs/architecture/MARKET_PRACTICE_AUDIT-EN.md`
