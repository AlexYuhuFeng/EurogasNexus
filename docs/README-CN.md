# 文档索引

英文主文档：[README.md](README.md)

本索引是仓库文档的权威入口，用于区分当前/规范文档、运维手册、设计参考与
历史公开参考。如两份文档冲突，以当前/规范文档为准并报告冲突。

## 先读

1. [更新日志](../CHANGELOG.md)
2. [发布就绪](release/RELEASE_READINESS.md) — 当前发布状态、已验证门槛与已知生产差距。
3. [项目目录与归属](../PROJECT_DIRECTORY.md)
4. [架构决策记录](architecture/ARCHITECTURE_DECISION_RECORD.md)
## 规范与当前文档

### 治理与流程

- [架构决策与 ADR 流程](architecture/ARCHITECTURE_DECISION_RECORD.md)
- [代码规范](engineering/CODING_STANDARDS.md)
- [API 合同演进政策 EN](architecture/API_CONTRACT_EVOLUTION_POLICY.md) /
  [CN](architecture/API_CONTRACT_EVOLUTION_POLICY-CN.md)
- [API 路径政策](api/API_PATH_POLICY.md)
- [术语标准](architecture/TERMINOLOGY.md)

### 工程治理

- [工程治理索引](engineering/README.md)
- [RFC 流程](engineering/RFC_PROCESS.md)
- [RFC 索引](engineering/RFC_INDEX.md) / [模板](engineering/RFC_TEMPLATE.md)
- [ExecPlan 索引](engineering/EXECPLAN_INDEX.md) /
  [模板](engineering/EXECPLAN_TEMPLATE.md)

### 架构与合同

- [API 合同](api/API_CONTRACT.md)
- [数据科学函数目录](api/DATA_SCIENCE_FUNCTIONS.md)
- [公共 API 约定](api/API_CONVENTIONS.md)
- [数据库合同](architecture/DB_CONTRACT.md)
- [运行存储合同](architecture/RUNTIME_STORE_CONTRACT.md)
- [SDK/CLI 合同](clients/SDK_CLI_CONTRACT.md)
- [资源池合同 EN](architecture/RESOURCE_POOL_CONTRACT-EN.md) /
  [CN](architecture/RESOURCE_POOL_CONTRACT-CN.md)
- [目标产品架构](architecture/TARGET_PRODUCT_ARCHITECTURE.md)
- [测试合同](architecture/TESTING_CONTRACT.md)
- [欧洲网络几何政策](architecture/EUROPEAN_NETWORK_GEOMETRY_POLICY.md)
- [主体身份模型](architecture/ACTOR_IDENTITY_MODEL-CN.md)
- [OWL 天然气角色模型 EN](ontology/OWL_GAS_ROLE_MODEL.md) /
  [CN](ontology/OWL_GAS_ROLE_MODEL-CN.md)
- [天然气主体架构](ontology/europe-natural-gas.md)

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

- [事故响应](operations/INCIDENT_RESPONSE.md)
- [发布签名](operations/RELEASE_SIGNING.md)
- [供应商实时验证](operations/PROVIDER_VALIDATION.md)
- [成本观测来源](operations/COST_OBSERVATION_SOURCES.md)

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
- [安全验收证据 EN](release/SECURITY_ACCEPTANCE_EVIDENCE.md) /
  [CN](release/SECURITY_ACCEPTANCE_EVIDENCE-CN.md)
- [部署角色 EN](deployment/DEPLOYMENT_ROLES-EN.md) /
  [CN](deployment/DEPLOYMENT_ROLES-CN.md)

## 文档状态规则

- 当前架构政策、API 合同、客户端标准和当前运维手册具有规范性。
- `*-EN.md` 与 `*-CN.md` 是语言配套文件，必须描述同一行为。

## 文档维护

- 内部 Markdown 链接由
  [`scripts/ci/check_markdown_links.py`](../scripts/ci/check_markdown_links.py)
  检查。
- 过时文档在更新引用后移除，不在公开交付仓库中保留内部里程碑证据。
