# 文档索引

英文主文档：[README.md](README.md)

本索引是仓库文档的权威入口，用于区分当前/规范文档、运维手册、设计参考、
历史规划与归档记录。如两份文档冲突，以当前/规范文档为准并报告冲突。

## 先读

1. [更新日志](../CHANGELOG.md)
2. [当前暂停点](architecture/CURRENT_PAUSE_POINT-CN.md)
3. [下一步开发队列](architecture/NEXT_DEVELOPMENT_QUEUE-CN.md)
4. [项目目录与归属](../PROJECT_DIRECTORY.md)
5. [架构决策记录](architecture/ARCHITECTURE_DECISION_RECORD.md)
6. [RFC 流程](engineering/RFC_PROCESS.md) 与
   [已接受 RFC](engineering/rfc/README.md)
7. [归档政策](policies/ARCHIVE_POLICY.md)
## 规范与当前文档

### 治理与流程

- [架构决策与 ADR 流程](architecture/ARCHITECTURE_DECISION_RECORD.md)
- [RFC 流程](engineering/RFC_PROCESS.md)
- [RFC 索引](engineering/rfc/README.md)
- [归档政策](policies/ARCHIVE_POLICY.md)
- [代码规范](engineering/CODING_STANDARDS.md)
- [API 合同演进政策 EN](architecture/API_CONTRACT_EVOLUTION_POLICY.md) /
  [CN](architecture/API_CONTRACT_EVOLUTION_POLICY-CN.md)
- [API 路径政策](api/API_PATH_POLICY.md)
- [术语标准](architecture/TERMINOLOGY.md)

### 架构与合同

- [合同索引](contracts/00_CONTRACT_INDEX.md)
- [API 合同](contracts/06_API_CONTRACT.md)
- [公共 API 约定](contracts/API_CONVENTIONS.md)
- [数据库合同](contracts/04_DB_CONTRACT.md)
- [运行存储合同](contracts/05_RUNTIME_STORE_CONTRACT.md)
- [SDK/CLI 合同](contracts/15_SDK_CLI_CONTRACT.md)
- [资源池合同 EN](contracts/21_RESOURCE_POOL_CONTRACT-EN.md) /
  [CN](contracts/21_RESOURCE_POOL_CONTRACT-CN.md)
- [目标产品架构](architecture/TARGET_PRODUCT_ARCHITECTURE.md)
- [后端实施蓝图](architecture/BACKEND_IMPLEMENTATION_BLUEPRINT.md)
- [优化层](architecture/PHASE_TWO_OPTIMIZATION-CN.md)
- [欧洲网络几何政策](architecture/EUROPEAN_NETWORK_GEOMETRY_POLICY.md)
- [主体身份模型](architecture/ACTOR_IDENTITY_MODEL-CN.md)
- [OWL 天然气角色模型 EN](ontology/OWL_GAS_ROLE_MODEL.md) /
  [CN](ontology/OWL_GAS_ROLE_MODEL-CN.md)
- [天然气主体架构](ontology/europe-natural-gas.md)
- [本体化 gap 报告](ontology/gap-report.md)

### 客户端规范

- [客户端文档索引](clients/README.md)
- [UI 与内容标准](clients/UI_CONTENT_STANDARDS.md) — 唯一的 UI/内容权威标准。
- [UI/UX 风格指南 EN](clients/UI_UX_STYLE_GUIDE-EN.md) /
  [CN](clients/UI_UX_STYLE_GUIDE-CN.md) — `UI_CONTENT_STANDARDS.md`
  的双语配套文档。
- [客户端技术栈](clients/CLIENT_TECH_STACK.md)
- [客户端 i18n 与主题](clients/CLIENT_I18N_THEME_SPEC.md)
- [客户端 API 合同](clients/CLIENT_API_CONTRACT.md)
- [工作区导航](clients/WORKSPACE_NAVIGATION_SPEC.md)
- [Web 应用架构 EN](clients/WEB_APPLICATION_ARCHITECTURE-EN.md) /
  [CN](clients/WEB_APPLICATION_ARCHITECTURE-CN.md)
- [地图优先决策驾驶舱 EN](clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md) /
  [CN](clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md)
- [市场定位驾驶舱 EN](clients/MARKET_POSITIONING_COCKPIT_SPEC-EN.md) /
  [CN](clients/MARKET_POSITIONING_COCKPIT_SPEC-CN.md)
- [运营术语上下文 EN](clients/OPERATIONAL_GLOSSARY_CONTEXT_SPEC-EN.md) /
  [CN](clients/OPERATIONAL_GLOSSARY_CONTEXT_SPEC-CN.md)

### 政策

- [产品边界政策](policies/PRODUCT_BOUNDARY_POLICY.md)
- [数据政策](policies/DATA_POLICY.md)
- [依赖政策](policies/DEPENDENCY_POLICY.md)

## 当前运维手册

- [本地开发](operations/LOCAL_DEVELOPMENT.md)
- [本地 Docker 运行时](operations/LOCAL_DOCKER_RUNTIME.md)
- [验证指南](operations/VALIDATION.md)
- [PostgreSQL 运行指南](operations/LIVE_POSTGRESQL.md)
  （[兼容说明](operations/LIVE_POSTGRESQL_V1.md)）
- [数据库迁移](operations/DB_MIGRATIONS.md)
- [数据库运行加固](operations/DB_RUNTIME_HARDENING.md)
- [备份与恢复](operations/BACKUP_RESTORE.md)
- [SLO](operations/SLO.md)
- [生产数据源运营 EN](operations/PRODUCTION_SOURCE_OPERATIONS.md) /
  [CN](operations/PRODUCTION_SOURCE_OPERATIONS-CN.md)
- [模拟行情来源](operations/SIMULATED_MARKET_PRICE_SOURCES.md)
- [组合网络优化 EN](operations/PORTFOLIO_NETWORK_OPTIMIZATION.md) /
  [CN](operations/PORTFOLIO_NETWORK_OPTIMIZATION-CN.md)
- [储气与提名评估 EN](operations/STORAGE_NOMINATION_ASSESSMENT.md) /
  [CN](operations/STORAGE_NOMINATION_ASSESSMENT-CN.md)
- [身份、授权与审计 EN](operations/IDENTITY_AUDIT_GOVERNANCE.md) /
  [CN](operations/IDENTITY_AUDIT_GOVERNANCE-CN.md)
- [OIDC access token EN](operations/OIDC_ACCESS_TOKEN.md) /
  [CN](operations/OIDC_ACCESS_TOKEN-CN.md)
- [DeepSeek 实时监控 EN](operations/LLM_MONITORING-EN.md) /
  [CN](operations/LLM_MONITORING-CN.md)
- [市场定位导入 EN](operations/MARKET_POSITIONING_IMPORTS-EN.md) /
  [CN](operations/MARKET_POSITIONING_IMPORTS-CN.md)

## 发布、安全与部署

- [发布就绪](release/RELEASE_READINESS.md)
- [生产就绪待办](release/PRODUCTION_READINESS_BACKLOG.md)
- [安全验收证据 EN](release/SECURITY_ACCEPTANCE_EVIDENCE.md) /
  [CN](release/SECURITY_ACCEPTANCE_EVIDENCE-CN.md)
- [部署角色 EN](deployment/DEPLOYMENT_ROLES-EN.md) /
  [CN](deployment/DEPLOYMENT_ROLES-CN.md)
- [Windows AllInOne 安装 EN](deployment/ALL_IN_ONE_INSTALLER-EN.md) /
  [CN](deployment/ALL_IN_ONE_INSTALLER-CN.md)

## 设计参考

这些文档提供背景和视觉方向，不是实施队列；只有当前队列明确启用相关 UI
里程碑时才需要重读。

- [UX 布局蓝图](design/UX_LAYOUT_BLUEPRINTS.md)
- [UI 审计 2026-08-31](design/UI_AUDIT_2026-08-31.md)
- [UI 审计 2026-09-01](design/UI_AUDIT_2026-09-01.md)
- [日内决策信息流 EN](product/INTRADAY_DECISION_FEED-EN.md) /
  [CN](product/INTRADAY_DECISION_FEED-CN.md)
- [市场实践审计 EN](architecture/MARKET_PRACTICE_AUDIT-EN.md) /
  [CN](architecture/MARKET_PRACTICE_AUDIT-CN.md)

## 历史与规划

背景、交付历史和已定稿规划。除非当前队列明确启用，不要把其中内容当作新
实施指令。

- [产品北极星](architecture/PROJECT_NORTH_STAR.md)
- [产品交付总计划](architecture/PRODUCT_DELIVERY_MASTER_PLAN.md)
- [全项目能力蓝图](architecture/WHOLE_PROJECT_CAPABILITY_BLUEPRINT.md)
- [实时市场情报蓝图](product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md)
- [研究工作流蓝图](product/RESEARCH_WORKFLOW_BLUEPRINT.md)
- [参考证据日志](architecture/REFERENCE_EVIDENCE_LOG.md)
- [参考项目经验](architecture/REFERENCE_PROJECT_LESSONS.md)
- [文档一致性审计](architecture/DOCUMENTATION_AUDIT.md)
- [架构改进路线图](architecture/IMPROVEMENT_ROADMAP-CN.md)
- [V1 交付历史](archive/architecture/V1_STEPWISE_DELIVERY_ROADMAP.md)

## 归档

已取代或已完成的文档位于[归档索引](archive/README.md)，仅作溯源保留，不
再是当前权威。归档标准与流程见[归档政策](policies/ARCHIVE_POLICY.md)。

## 文档状态规则

- `contracts/`、当前架构政策、当前客户端标准和当前运维手册具有规范性。
- `*-EN.md` 与 `*-CN.md` 是语言配套文件，必须描述同一行为。
- 名称含 `BLUEPRINT`、`REFERENCE` 或 `AUDIT` 的文件默认提供背景，只有当前
  队列明确启用时才是实施任务。
- `.agent/plans/` 记录范围明确的实施决策和完成证据；已完成计划属于历史。
- `docs/archive/` 下的一切内容均为历史，不受文件内措辞影响。

## 文档维护

- 内部 Markdown 链接由
  [`scripts/ci/check_markdown_links.py`](../scripts/ci/check_markdown_links.py)
  检查。
- 过时文档按[归档政策](policies/ARCHIVE_POLICY.md)归档，不删除，也不批量
  移动不确定材料。
- 跨切面变更从 [RFC 流程](engineering/RFC_PROCESS.md) 开始；架构变更同步
  更新[架构决策记录](architecture/ARCHITECTURE_DECISION_RECORD.md)。
