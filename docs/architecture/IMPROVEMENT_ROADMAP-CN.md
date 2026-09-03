# Eurogas Nexus 架构改进路线图（已定稿 v1.0）

> 语言规范说明：本文件为中文文档，按仓库惯例使用 `-CN` 后缀（2026 年整理时
> 从 `IMPROVEMENT_ROADMAP.md` 更名）；暂无对应英文版，属历史定稿文档。
> 执行状态以 `docs/release/PRODUCTION_READINESS_BACKLOG.md` 与 `docs/architecture/CURRENT_PAUSE_POINT.md` 为准。

> 状态：**已定稿，按建议执行**。决策点 D1–D9 已拍板（见 §4 批注）。
> 执行方式：每个阶段独立 ExecPlan（12 节）、独立验收、独立回滚。
> 目标：让架构真正支撑「trader-reviewed 决策支持 + 近实时分析」，
> 同时守住既有边界（PostgreSQL 唯一真相、无执行、human-review、零新依赖除非评审）。

---

## 0. 目标与约束

- **目标**：近实时（秒级）数据分析处理 + 可信的复核/审计链 + 可运营性。
- **硬约束**：不引入 Kafka/Redis（触发阈值写入本文档，不实施）；不改产品边界
  （无执行/订单/提名/自动交易）；不动假数据 pipeline；不增加依赖除非 ExecPlan 评审。
- **方法**：每个阶段独立 ExecPlan、独立验收、独立回滚。

---

## 1. 现状问题清单（已核实，按优先级）

### 1.1 结构性（影响目标达成）

| # | 问题 | 证据 | 影响 |
|---|---|---|---|
| **F** | 消费模型是 10 秒轮询 + 定时全扫，无推送 | `useWorkspaceRuntime.ts:5` `MARKET_REFRESH_INTERVAL_MS=10_000`；worker 每 10 秒全扫 | 近实时天花板就是 10 秒 |
| **A** | 可观测性为零：无结构化日志、无延迟/新鲜度/错误指标 | 全仓无 `logging`/prometheus/otel；唯一 "metrics" 是 LLM 业务指标 | 近实时=盲飞，无法证明 SLA |
| **C** | 审计覆盖面极窄：`audit_events` 唯一写入者是 `market_positioning_import` | grep 证实 | 复核/决策无审计，信任链断环 |
| **P2** | 前端重实现领域逻辑 | `marketPriceNormalization.ts` 做 FX/tenor 规范化；`strategyScenario.ts` 组装策略场景 | 双实现漂移风险，交易员看到的数字可能与后端不一致 | S3.3 已修复 ✅（前端已删除重实现并消费后端规范化视图） |
| **P3** | 复核不是后端工作流 | review 是 UI 状态，无 `candidate→reviewed→accepted/rejected→audited` 持久化 | "决策支持"的定义性能力缺失 |

### 1.2 治理/运营（越晚越贵）

| # | 问题 | 证据 |
|---|---|---|
| **B** | 数据生命周期缺失：无保留/归档/分区/清理 | grep 零命中 |
| **P1** | 运行时真相分裂：存在无写入者表（`strategy_alerts` 定义了但无写入路径） | 模型存在、monitoring 只读、无 add |
| **D** | 契约演化无策略：stable unversioned `/api` + 5 surface 手维护 DTO | sdk/ 下 19 个 DTO 文件与后端靠自觉同步 |
| **E** | 幂等性部分确立：`upsert_market_quotes` 有（仿真源）；`public_sources` 摄入路径未审计 | grep | S3.2 已修复 ✅ |
| **P4** | 模拟数据掩盖未验证的 provider 集成 | 所有真实 connector 是 `research_only` 壳，活跃的是 `_Sim` |
| **P5** | 表面蔓延 + 遗留壳层：5 surface + `workflows/` 并行遗留层 | `workflows/*` 端点全部 `_blocked` |
| **P7** | 测试姿态契约强、运行时弱：真实 PG 端到端不在 CI | 474 测试中 25 个 DB-backed api 测试在无 DB 环境直接 error |
| **P6** | 规则散落：entitlement/audit/constraints/AGENTS.md 四处 | 已部分收编，有残留 |

---

## 2. 目标架构（一页）

```text
真实/仿真 provider
   │ 幂等摄入（upsert + 信号）
   ▼
PostgreSQL（唯一真相，保留策略）
   │ 增量触发（内存信号，非定时全扫）
   ▼
分析引擎（机会/策略/告警，粒度参数化 1min/滚动窗口）
   │ 结果 + 证据链（provenance + review_status）
   ▼
API / SSE 推送（EventSource，1–2s）
   ▼
客户端（Network/Market/Strategy）
   │
复核（actor + 审计事件，落库）──▶ 报告/导出（治理）
```

不变项：PostgreSQL 唯一真相、无执行、human-review、无 Kafka/Redis。

---

## 3. 分阶段计划

### 阶段 1：近实时决策管线（核心，含可观测性基线）

| 步骤 | 内容 | 改动面 |
|---|---|---|
| S1.1 | **SSE 推送交付**：`GET /api/stream/quotes`、`/opportunities`、`/alerts` 用 `StreamingResponse`；客户端 `EventSource` 替代 10 秒轮询（保留轮询作 fallback） | ✅ 已交付；前端 F3 另加顶栏数据模式徽章（`stream.live` / `stream.polling_fallback`，`streamingActive` 驱动） |
| S1.2 | **增量触发分析**：摄入落库后置内存"新鲜信号"，worker 只处理增量（上次以来新增/变化），节奏 10s→2–3s | ✅ 已交付（worker + 分析域） |
| S1.3 | **粒度参数化**：`target_bar_minutes` 支持 1 分钟/滚动窗口（默认保持 5 分钟兼容） | ✅ 已交付（strategy 域 + 前端 bar 选择器 1/5/15） |
| S1.4 | **可观测性基线**：`ingestion_runs`/`market_quotes` 已有 fresh 素材，新增「管线健康」聚合端点（每级新鲜度、延迟、错误率），供 Runtime 工作区展示 | ✅ 已交付（`/api/runtime/pipeline-health`；前端 F3：Runtime 面板展示每源状态/连续失败/报价新鲜度/开放告警/最新机会） |

**交付物**：SSE 端点、增量 worker、粒度参数、管线健康端点、测试、双语文档。
**验收**：端到端 quote→分析→推送 < 3 秒（仿真源）；轮询 fallback 可用；无新依赖。

### 阶段 2：信任链（复核 + 审计）

| 步骤 | 内容 |
|---|---|
| S2.1 | **复核生命周期后端化**：新增 `review_status` 持久化（candidate→reviewed→accepted/rejected），评审对象 = 机会/策略输出/报告 | ✅ 已交付（后端 `review_decisions` 表 + `/api/review/decisions` + 审计，迁移 `0017`；前端 Review 工作区决策历史流 + 记录器 `.agent/plans/F2_REVIEW_WORKFLOW_UI_EXECPLAN.md`，actor 仅页面内存、无浏览器持久化） |
| S2.2 | **审计覆盖**：所有敏感动作（复核、导出、凭据变更、摄入重跑）写 `audit_events`（actor/action/scope/evidence），与 S2.1 绑定 | ✅ 已交付：`record_audit_event` 共享助手；复核决策、凭据 upsert/删除、认证写入、公共源摄入（成功/失败）均写审计 |
| S2.3 | **契约一致性测试**：SDK DTO ↔ 后端 schema 的自动一致性检查（防 5 surface 漂移） | ✅ 已交付：`tests/contract/test_sdk_backend_parity.py`（SDK DTO ⊆ 后端载荷契约） |


### 阶段 3：数据治理

| 步骤 | 内容 |
|---|---|
| S3.1 | **保留策略**：市场观测/报价/机会按保留期归档/清理（默认值待定 D6），PG 分区或按时间清理 | ✅ 已交付：报价 30 天 / 观测 90 天 / 机会 7 天；`application/retention.py` + `scripts/ops/prune_runtime_data.py --dry-run` |
| S3.2 | **幂等性审计**：`public_sources` 摄入路径补 upsert/去重，保证重跑安全 | ✅ 已交付：`.agent/plans/S3_2_PUBLIC_INGESTION_IDEMPOTENCY_EXECPLAN.md`（自然键 PG upsert + first-seen `observed_at_utc` + 参考网络 source 作用域非空守卫替换 + 摄入审计） |
| S3.3 | **前端逻辑下沉**：新增「规范化市场视图」API（FX/tenor/spread 后端出），删前端 `marketPriceNormalization` 重实现 | ✅ 已交付（前后端全部）：`.agent/plans/S3_3_NORMALIZED_MARKET_VIEW_EXECPLAN.md`（后端 `/api/market/normalized`）+ `.agent/plans/F1_NORMALIZED_MARKET_VIEW_WEB_EXECPLAN.md`（前端删 `marketPriceNormalization.ts`，Strategy/Market 消费后端 `hub`/`tenor`/`price_gbp_mwh` 与 `/api/market/spreads`，契约测试禁客户端汇率/价差数学） |

### 阶段 4：生产化收口

| 步骤 | 内容 |
|---|---|
| S4.1 | **契约演化策略**：版本化/弃用政策文档 + 兼容测试门 | ✅ 已交付：`.agent/plans/S4_1_CONTRACT_EVOLUTION_POLICY_EXECPLAN.md`（`API_CONTRACT_EVOLUTION_POLICY.md` 双语 + `tests/contract/test_api_surface_stability.py` 钉死 90 条路径集合） |
| S4.2 | **Provider 认证门**：真实适配器过「模拟→真实」测试门，未过门不许标 live | ✅ 已交付：`.agent/plans/S4_2_PROVIDER_CERTIFICATION_GATE_EXECPLAN.md`（`provider_certifications` 表 + 域门 + internal 写入端点 + `/api/sources` fail-closed：未认证 licensed 源标 `active_uncertified` 且永不为 workflow_ready；前端 F4：Sources 认证徽章 + `certify` 下一动作） |
| S4.3 | **表面收敛**：`workflows/` 遗留壳层显式标记 deprecated 或移除 | ✅ 已完成：Web/SDK/CLI 迁移后物理移除 10 条 `/api/workflows/*`（旧路径返回 404）；`src/eurogas_nexus/api/routes/public/workflows.py` 与 `sdk/workflows.py` 已删除 |
| S4.4 | **身份/授权（对接 R32）**：为 S2 的 actor 提供身份模型，Server 角色可多用户 | ✅ 最小形态交付：`.agent/plans/S4_4_ACTOR_IDENTITY_MODEL_EXECPLAN.md`（`ACTOR_IDENTITY_MODEL.md` 双语 + `domain/identity/principal.py` 唯一校验器，复核/internal/认证写入统一走 `normalize_principal`）；多用户认证与 SSO 仍属 R32 待办 |

---

## 4. 关键决策点（已拍板 ✅）

- **D1 延迟目标** ✅：可见性 1–2 秒、分析产出 2–3 秒。
- **D2 阶段 1 含可观测性基线** ✅：含。
- **D3 复核生命周期最小形态** ✅：`review_status` 字段 + 审计事件。
- **D4 SSE vs WebSocket** ✅：SSE（EventSource 原生、Tauri 兼容、单向推送）。
- **D5 分析粒度** ✅：1 分钟 bar / 滚动窗口；默认保持 5 分钟兼容。
- **D6 保留策略默认值** ✅：报价 30 天 / 观测 90 天 / 机会 7 天（阶段 3 实施）。
- **D7 阶段顺序** ✅：1→2→3→4 按序。
- **D8 假数据 pipeline 定位** ✅：独立不动，仅作为近实时/可观测性的只读验证数据源。
- **D9 前端下沉** ✅：提到阶段 2 一起做。

---

## 5. 非目标（明确不做）

- Kafka/Redis/流式（触发阈值：真实高频源接入或多 worker 信号丢失时才评审引入）
- 亚秒/高频策略
- 执行/订单/提名/自动交易
- 假数据 pipeline 重构
- 新依赖（除非 ExecPlan 评审通过）

---

## 6. 验收与风险

- 每阶段独立 ExecPlan（12 节）、独立测试、独立回滚。
- 主要风险：SSE 与现有轮询并存期的行为漂移；增量分析的正确性（漏更新）；
  复核/审计的数据模型与既有表耦合。
- 缓解：每阶段先契约测试后实现；增量分析带"全量兜底"开关；审计用追加式只写。

---

## 7. 文档

- 本文件（EN 讨论稿）；拍板后出 CN 版 + 每阶段 ExecPlan。
