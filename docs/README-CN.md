# 文档索引

英文主文档：[README.md](README.md)

本索引区分当前实现规范和历史规划。开发时先阅读“当前状态和队列”，不要把
所有 blueprint 或已完成 ExecPlan 当成需要重新实现的任务。

## 当前状态和队列

1. [当前暂停点](architecture/CURRENT_PAUSE_POINT-CN.md)
2. [下一步开发队列](architecture/NEXT_DEVELOPMENT_QUEUE-CN.md)
3. [产品北极星](architecture/PROJECT_NORTH_STAR.md)
4. [生产就绪待办](release/PRODUCTION_READINESS_BACKLOG.md)

## 架构和合同

- [目标产品架构](architecture/TARGET_PRODUCT_ARCHITECTURE.md)
- [API 合同](contracts/06_API_CONTRACT.md)
- [数据库合同](contracts/04_DB_CONTRACT.md)
- [运行存储合同](contracts/05_RUNTIME_STORE_CONTRACT.md)
- [SDK/CLI 合同](contracts/15_SDK_CLI_CONTRACT.md)
- [资源池合同中文](contracts/21_RESOURCE_POOL_CONTRACT-CN.md)
- [资源池合同英文](contracts/21_RESOURCE_POOL_CONTRACT-EN.md)

## 本体

- [OWL 天然气角色模型中文](ontology/OWL_GAS_ROLE_MODEL-CN.md)
- [OWL 天然气角色模型英文](ontology/OWL_GAS_ROLE_MODEL.md)
- [欧洲天然气主体架构](ontology/europe-natural-gas.md)
- [本体化 gap 报告](ontology/gap-report.md)

## 客户端

- [客户端文档索引](clients/README.md)
- [Web 应用架构中文](clients/WEB_APPLICATION_ARCHITECTURE-CN.md)
- [Web 应用架构英文](clients/WEB_APPLICATION_ARCHITECTURE-EN.md)
- [工作区导航](clients/WORKSPACE_NAVIGATION_SPEC.md)
- [UI/UX 中文规范](clients/UI_UX_STYLE_GUIDE-CN.md)
- [UI/UX 英文规范](clients/UI_UX_STYLE_GUIDE-EN.md)

## 运行和部署

- [本地开发](operations/LOCAL_DEVELOPMENT.md)
- [验证指南](operations/VALIDATION.md)
- [PostgreSQL 运行指南](operations/LIVE_POSTGRESQL.md)
- [身份、授权与审计治理中文](operations/IDENTITY_AUDIT_GOVERNANCE-CN.md)
- [身份、授权与审计治理英文](operations/IDENTITY_AUDIT_GOVERNANCE.md)
- [OIDC access token 中文](operations/OIDC_ACCESS_TOKEN-CN.md)
- [OIDC access token 英文](operations/OIDC_ACCESS_TOKEN.md)
- [生产数据源运营中文](operations/PRODUCTION_SOURCE_OPERATIONS-CN.md)
- [生产数据源运营英文](operations/PRODUCTION_SOURCE_OPERATIONS.md)
- [储气与提名评估中文](operations/STORAGE_NOMINATION_ASSESSMENT-CN.md)
- [储气与提名评估英文](operations/STORAGE_NOMINATION_ASSESSMENT.md)
- [部署角色中文](deployment/DEPLOYMENT_ROLES-CN.md)
- [部署角色英文](deployment/DEPLOYMENT_ROLES-EN.md)
- [安全验收证据中文](release/SECURITY_ACCEPTANCE_EVIDENCE-CN.md)
- [安全验收证据英文](release/SECURITY_ACCEPTANCE_EVIDENCE.md)
- [发布就绪](release/RELEASE_READINESS.md)

## 文档状态规则

- `contracts/`、当前架构政策和当前运行指南具有规范性。
- `*-EN.md` 与 `*-CN.md` 是语言配套文件，必须描述同一行为。
- `.agent/plans/` 记录范围明确的实现决策和完成证据；已完成计划属于历史记录。
- 名称含 `BLUEPRINT`、`REFERENCE` 或 `AUDIT` 的文件默认提供背景，只有当前队列明确启用时才是实施任务。
