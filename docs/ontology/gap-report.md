# Eurogas Nexus 本体化 Gap 报告

> 对照 `docs/ontology/europe-natural-gas.md`（主体架构 v0.2），盘点 Eurogas Nexus
> 现有 glossary / ontology / guardrails 的「已有 / 缺 / 重复 / 冲突」。
> 本报告**只陈述事实与建议**，不修改任何代码。

- **版本**：v0.2（2026 整改后修订；v0.1 见 git 历史）
- **范围**：仅后端/领域层（`src/eurogas_nexus/`）+ DB 模型 + 与本体相关的 API。
- **方法**：按五构件（概念/关系/动作/受控词表/约束）+ L1–L5 分层逐项核对代码。

---

## 0. 状态更新（Gate 0 整改后）

v0.1 的若干结论已被后续实现推翻，先修正以免误导：

1. **typed ontology 已存在**：`src/eurogas_nexus/domain/ontology/` 已实现
   `concepts.py`（约 27 个 typed concepts）、`relations.py`、`actions.py`、
   `constraints.py`、`vocabulary.py`（受控词表）与 `bindings.py`（约 20 个
   DB binding）。migration 0016 已删除旧 `business_ontology_terms` 表，
   v0.1 中"孤儿表"问题已不存在。本节第 1.1 条的 A/D 两套面已收口。
2. **集中式 L5 约束已起步**：`domain/constraints/`（access / risk /
   route_economics）已存在；Gate 0 整改中把 TSO 准入改为显式三态
   （`AccessStatus`：CONFIRMED / DENIED / UNKNOWN）并加入本体词表
   `vocabulary.py`；容量可用性改为三态（`CapacityStatus`：KNOWN /
   NOT_REQUIRED / UNKNOWN），UNKNOWN 对跨区路线 fail-closed。route-cost
   枚举已改为从本体词表再导出（`domain/route_cost/enums.py` 是薄兼容层）。
3. **本报告其余"缺/重复/冲突"仍然成立**，尤其是：DB binding 与概念的字段级
   不一致（审计约 13/20 处）、`Measure`/`Money`/`GasDayRef` 等 Semantic
   Kernel v1 值对象未建立、glossary 无稳定 `concept_id`、Hub/MarketArea 仍是
   代码闭集而非 DB reference master。这些列入 Gate 2（Ontology v0.3 ExecPlan）。

## 0a. 状态更新（Gate 1–3 整改后）

- **Semantic Kernel v1 已建立**：`domain/ontology/semantic_kernel.py` 提供
  `CanonicalId`/`ExternalIdentifier`/`Measure`/`Money`/`PriceBasis`/
  `FxConversionRef`/`TimeInterval`/`GasDayRef`/`GasYearRef`/`EffectivePeriod`/
  `JurisdictionRef`/`RegulatoryInstrumentRef`/`SourceRef`/`LineageRef`/
  `OntologyVersion`/`MappingVersion`，含版本化法规注册表（2024/1789 重铸
  715/2009、2024/1106 修订 REMIT、CAM 2017/459、互操作 2015/703）。
- **binding 字段级对齐已机器化**：`bindings.py` 新增 `CONCEPT_SLOT_COLUMN_MAPS`
  （20 个 binding × 全部 slot），`tests/unit/test_ontology_binding_integrity.py`
  强制"每个 slot 都能解析到真实列"，漂移即测试失败；migration 0019 补齐
  `flow_observations.kind`、`capacity_profiles.capacity_product/scope`。
- **容量产品语义拆分**：`CapacityProductDuration`（yearly/quarterly/monthly/
  daily/within-day）与 `AuctionTiming` 分离，WEEKLY 标记为
  `CAPACITY_PRODUCT_EXTENSIONS`；`StatusKind`（SUCCESS/PARTIAL/BLOCKED/UNKNOWN）
  统一优化器状态；`ActionKindCategory`（SYSTEM/ANALYTICAL/DECISION_CANDIDATE/
  EXTERNAL_ACTION）分类动作。
- **Gate 1–3 续批**：`/api/optimization/resource-pool` 的 RUNTIME_DECISION 模式
  （只消费 DB 快照、拒绝客户端价格、持久化 snapshot_id，输入无法组装时
  fail-closed 422）；migration 0020 为 glossary 增加稳定 `concept_id` 列、
  为 `reference_market_hubs` 增加有效期/替代/市场区列（DB reference master
  落地，`MARKET_HUB_SUPERSESSIONS` 记录 NCG/GASPOOL→THE）；行情/分析行序列化
  带行级 `entitlement_scope` 标注；`security/permissions.py` 声明式路由权限
  注册表（91 条路径全部可解析，凭据写操作为 OPERATOR，后续里程碑强制
  principal）。
- **Gate 1–4 续批（第二轮）**：release profile 下 OPERATOR 路由强制
  `X-Eurogas-Principal`（401 缺失 / 403 无效，`api/dependencies/route_permission.py`）；
  Hub 读取端已带有效期/替代字段（`MarketHubDTO` 扩展 + 集成测试）；
  依赖治理落地：`scripts/ci/audit_dependencies.py` 离线许可审计（GPL 族/
  SSPL/BUSL/Elastic/RSAL/Commons-Clause/PolyForm fail-closed）、
  `scripts/ci/freeze_lock.py` 生成 `requirements.lock`（36 个精确版本），
  CI 新增 `dependency-audit` job（许可审计 + pip-audit CVE 扫描）。
- **Gate 1–4 续批（第三轮）**：客户端认证联动——SDK/CLI 通过
  `EUROGAS_NEXUS_API_TOKEN` / `EUROGAS_NEXUS_PRINCIPAL` 环境变量自动携带
  Bearer 与 principal 头（`sdk/_http.py` 统一包装，16 个模块切换）；Web
  Settings 新增 API token 与操作员身份设置（localStorage），全部请求自动
  带头；SSE 因 `EventSource` 无法设头，token 走 `?api_key=` 查询通道
  （后端 `require_public_api_auth` 已接受，文档注明日志注意事项）；顺带修复
  潜伏的 `ontology/__init__` ↔ `constraints/access` 循环导入（constraints
  改为 PEP 562 惰性暴露）；备份能力落地：`scripts/ops/backup_runtime.py`
  （pg_dump 包装、拒绝非 PG DSN）+ `docs/operations/BACKUP_RESTORE.md`
  （含验证清单）。
- **Gate 1–4 续批（第四轮）**：审计项 3 落地——`domain/monitoring/freshness.py`
  共享 freshness 评估（live/stale/unknown，期望内 live、超期 stale、无期望
  unknown），Source Center 读取端按 `freshness_expectation_minutes` 对照最新
  观测时间：有记录但超期 → `stale`（不再伪装 active），diagnostics 增加
  `data_stale`，active 计数自动排除陈旧源；审计项 7 落地——Review 工作区新增
  **证据包面板**（状态/算法/最优性/已分配量/缺失输入/来源引用），DTO 补
  `algorithm`/`optimality` 字段。
- **Gate 1–4 续批（第五轮）**：审计项 4 落地——`ingest_public_sources.py`
  增加 fail-closed 门禁（entitlement 全源检查 + ENTSOG/GIE 认证 gate，被拦
  源记录 failed 运行而非静默跳过）、`_get_with_retry` 支持 429/5xx 重试并
  尊重 `Retry-After`、空响应记录 failed 运行（`empty_response`）、except
  捕获 RuntimeError 保证失败必落运行记录；migration 0021 新增
  `raw_payload_archives`（raw→canonical 谱系归档，含 sha256、2MB 上限），
  ingest 脚本对 ECB/ENTSOG/GIE 原始载荷全部归档；真实 PostgreSQL 测试路径
  ——`tests/integration/test_postgres_backed_smoke.py` 直接打配置的运行时库
  （必需表契约/DB-backed API 读/审计写读/raw 归档写读），CI 的
  `run_postgres_ci.sh` 在 PG16 service 上执行（本地用临时库验证迁移链
  0001→0021 与 4 项 smoke 全过）。
- **Gate 1–4 续批（第六轮）**：审计项 2 后半落地——research 端点全部显式
  sandbox 语义（`api/dependencies/sandbox.py` 依赖：拒绝
  `decision_context=RUNTIME_DECISION` 声称，响应 meta 带
  `decision_context: SANDBOX_SCENARIO`，7 条 research 路径契约测试）；
  审计项 10 的负载测试路径——`scripts/ops/load_smoke.py`（进程内 ASGI
  传输、无服务器无网络、asyncio 并发、p50/p95/p99 百分位 + 错误率阈值，
  本地实测 150 请求 0 错误），已入 CI validate job；`Measure` 值对象最小
  落地——`money_triple_valid`（金额/币种/单位三元组契约）接入
  `route_cost_service`，定价组件缺币种/单位时 fail-closed
  （`MONEY_TRIPLE_INVALID`），不再按裸数字累加。
- **Gate 1–4 续批（第七轮）**：审计项 7 补齐——资源池结果新增
  `assumptions`（线性模型/精确最优、同币种同单位比较、跨区准入与容量
  fail-closed、仅决策支持），SDK DTO 与 Web DTO 同步，Review 证据包面板
  展示假设清单（中英词条）；release workflow 依赖锁定——release validate
  改为 `pip install -r requirements.lock` + `--no-deps` 可编辑安装，发布
  构建跑在审计过的精确版本上；`docs/operations/SLO.md` 建立预览级 SLO
  目标与自动化证据映射（可用性/延迟/错误率/DB 可达/数据新鲜度诚实性/
  审计完整性/摄入运行记账）。
- **Gate 1–4 续批（第八轮，文档收尾）**：`docs/release/RELEASE_READINESS.md`
  同步当前真实状态——证据块更新为 alembic 0023 / 45 表 / 84 路径 / 890
  测试，Validated Gates 补入 release token+principal 认证、trial/release
  LLM 关闭与载荷过滤、FX as-of、TSO/容量 fail-closed、CAM GasDay、精确
  求解与 RUNTIME_DECISION、依赖锁定与许可/CVE 审计、PG16 smoke 与负载
  冒烟；多用户/角色与行级 entitlement 全量强制如实标注为未完成项。
- **沙箱内可执行整改已全部完成**：剩余验收项（CI pip-audit 首跑、PG16
  smoke 实跑、备份恢复演练、真实负载/渗透、真实供应商/LLM 联调、用户目录
  角色模型）均需网络/真实部署环境，属环境依赖而非代码整改。
- **API/SDK/MCP 完备化（第九轮起）**：P1 补齐 SDK 客户端——
  `sdk/optimization.py`（route/resource-pool/capacity/contracts 求解 +
  `runs/{run_id}` 证据，含 RUNTIME_DECISION 透传与 meta run_id）、
  `sdk/review.py`（读取+记录评审决策）、`sdk/credentials.py`（凭据姿态
  只读）；parity 测试把 SDK DTO 字段钉死到后端载荷。P2——CLI 新增
  optimize（JSON 请求文件）/optimization-run/analyze/sources/market/fx/
  flows/credential-providers/review-decisions 子命令（infeasible→退出码 1），
  `sdk/streaming.py` SSE 流式客户端（Last-Event-ID 恢复 + 纯解析器）。
  P3——`mcp/server.py` 只读 MCP server（stdlib JSON-RPC 2.0 over stdio，
  零新依赖）：initialize/tools/list/tools/call，8 个只读工具（来源/行情/
  FX/术语/本体/评审/路线成本/沙箱路线优化），复用 SDK 认证门禁、拒绝
  RUNTIME_DECISION、无写路径；CI 增加 MCP 握手 smoke。P3b——API 收敛：
  6 个列表端点补齐 limit（1..N 校验），`docs/contracts/API_CONVENTIONS.md`
  固化信封/分页/错误 detail/状态语义约定。
- **仍待办**：完整用户目录/角色（当前为 token+principal 服务身份）、
  `Measure` 值对象进一步全链路落地、备份恢复演练与真实环境负载/渗透测试、
  CI `pip-audit` 与 PG16 smoke 首次实跑（需网络/真库）。

---

## 0b. 核心结论（v0.1 原文，保留供对照）

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

## 0c. 结构整改决定（2026-09）

- `src/eurogas_nexus/workflows/`（旧 research-only 工作流壳）已整体并入
  `src/eurogas_nexus/domain/research/`，消除与 `domain/` 的重复；API 路由改为
  从 `eurogas_nexus.domain.research` 导入。
- 仅有 `__init__.py` 且无实现的占位包已从 `src/eurogas_nexus/domain/` 移除：
  `allocation / assets / economics / feasibility / netback / nowcast /
  operations / relationships / reporting / resources / topology / weather`。
  未来能力按 `docs/release/RELEASE_READINESS.md` 或 ExecPlan 落地时再
  创建实现包，不在源码树中保留空占位目录。


## 1. 现状盘点（有据）

### 1.1 四套重叠的"本体"面（重复）

| # | 位置 | 内容 | 状态 |
|---|---|---|---|
| A | `src/eurogas_nexus/domain/analysis/builders.py` `business_logic_ontology()` | 硬编码 dict：16 实体 / 8 关系 / 5 guardrails | 代码常量，经 `/api/analysis/ontology` 暴露 |
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
  `analysis/`（包：contracts / builders / glossary_*）、`glossary.py`、
  `market_intelligence/opportunity_engine.py`、`monitoring/`

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

- `src/eurogas_nexus/domain/analysis/builders.py`（`business_logic_ontology()`）
- `src/eurogas_nexus/domain/glossary.py`（`baseline_glossary_terms()`）
- `src/eurogas_nexus/db/models/glossary.py`、`src/eurogas_nexus/db/models/analysis.py`
- `src/eurogas_nexus/governance/entitlement.py`、`src/eurogas_nexus/governance/audit.py`
- `scripts/ops/seed_preview_runtime_data.py`
