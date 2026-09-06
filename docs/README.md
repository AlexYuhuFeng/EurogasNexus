# Documentation Index

Mandarin companion: [README-CN.md](README-CN.md)

This index is the authoritative entry point for repository documentation. It
separates current/normative material from runbooks, design references, and
historical public references. If two documents disagree, follow
the current/normative document listed here and report the conflict.

## Read first

1. [Changelog](../CHANGELOG.md)
2. [Release readiness](release/RELEASE_READINESS.md) — current release status,
   validated gates, and known production gaps.
3. [Project directory and ownership](../PROJECT_DIRECTORY.md)
4. [Architecture decisions](architecture/ARCHITECTURE_DECISION_RECORD.md)

## Product planning

- [Commercial readiness backlog](product/COMMERCIAL_READINESS_BACKLOG.md)
- [Scheduled agent state](product/SCHEDULED_AGENT_STATE.md)
- [Product information architecture](product/PRODUCT_INFORMATION_ARCHITECTURE.md)
- [Trader context spec](product/TRADER_CONTEXT_SPEC.md)
- [Industry benchmark principles](product/INDUSTRY_BENCHMARK.md)
- [UX reference](product/UX_REFERENCE.md)
- [Gas-day calendar compatibility](product/GAS_DAY_CALENDAR_COMPATIBILITY.md)
- [Data operations specification](product/DATA_OPERATIONS_SPEC.md)

## Normative and current

These documents define binding engineering boundaries. Contracts and policies
are normative. Language companions (`-EN` / `-CN`) must describe the same
behavior.

### Governance and process

| Document | Authority |
| --- | --- |
| [Architecture decisions and ADR process](architecture/ARCHITECTURE_DECISION_RECORD.md) | Normative for architecture decisions |
| [Coding standards](engineering/CODING_STANDARDS.md) | Normative for Python code review |
| [API contract evolution policy EN](architecture/API_CONTRACT_EVOLUTION_POLICY.md) / [CN](architecture/API_CONTRACT_EVOLUTION_POLICY-CN.md) | Normative for `/api` change control |
| [API path policy](api/API_PATH_POLICY.md) | Normative for route prefixes |
| [Terminology standard](architecture/TERMINOLOGY.md) | Normative for product language |

### Engineering governance

- [Engineering governance index](engineering/README.md)
- [RFC process](engineering/RFC_PROCESS.md)
- [RFC index](engineering/RFC_INDEX.md) / [template](engineering/RFC_TEMPLATE.md)
- [ExecPlan index](engineering/EXECPLAN_INDEX.md) /
  [template](engineering/EXECPLAN_TEMPLATE.md)

### Architecture and contracts

- [API contract](api/API_CONTRACT.md)
- [Data science function catalog](api/DATA_SCIENCE_FUNCTIONS.md)
- [Public API conventions](api/API_CONVENTIONS.md)
- [Database contract](architecture/DB_CONTRACT.md)
- [Runtime store contract](architecture/RUNTIME_STORE_CONTRACT.md)
- [SDK and CLI contract](clients/SDK_CLI_CONTRACT.md)
- [Resource-pool contract EN](architecture/RESOURCE_POOL_CONTRACT-EN.md) /
  [CN](architecture/RESOURCE_POOL_CONTRACT-CN.md)
- [Testing contract](architecture/TESTING_CONTRACT.md)
- [Target product architecture](architecture/TARGET_PRODUCT_ARCHITECTURE.md)
- [European network geometry policy](architecture/EUROPEAN_NETWORK_GEOMETRY_POLICY.md)
- [Actor identity model](architecture/ACTOR_IDENTITY_MODEL.md) /
  [CN](architecture/ACTOR_IDENTITY_MODEL-CN.md)
- [OWL gas role model EN](ontology/OWL_GAS_ROLE_MODEL.md) /
  [CN](ontology/OWL_GAS_ROLE_MODEL-CN.md)
- [Natural-gas subject architecture](ontology/europe-natural-gas.md)

### Research data foundation

- [Energy ontology](research/ENERGY_ONTOLOGY.md)
- [Temporal data model](research/TEMPORAL_DATA_MODEL.md)
- [Feature registry](research/FEATURE_REGISTRY.md)
- [Target registry](research/TARGET_REGISTRY.md)
- [Dataset architecture](research/DATASET_ARCHITECTURE.md)
- [Point-in-time datasets](research/POINT_IN_TIME_DATASETS.md)
- [ML readiness](research/ML_READINESS.md)
- [Agent capability contract](agents/CAPABILITY_CONTRACT.md)
- [Agent-native architecture](agents/AGENT_NATIVE_ARCHITECTURE.md)
- [Capability registry](agents/CAPABILITY_REGISTRY.md)
- [MCP server](agents/MCP_SERVER.md)
- [Research plan](agents/RESEARCH_PLAN.md)
- [Strategy IR](agents/STRATEGY_IR.md)
- [Research orchestration](agents/RESEARCH_ORCHESTRATION.md)
- [Risk challenger](agents/RISK_CHALLENGER.md)
- [Agent replay](agents/AGENT_REPLAY.md)
- [Agent evaluation](agents/AGENT_EVALUATION.md)
- [Agent security and entitlement](agents/SECURITY_AND_ENTITLEMENT.md)

### Client standards

- [Client documentation index](clients/README.md)
- [UI and content standards](clients/UI_CONTENT_STANDARDS.md) — single
  authoritative UI/content standard.
- [UI/UX style guide EN](clients/UI_UX_STYLE_GUIDE-EN.md) /
  [CN](clients/UI_UX_STYLE_GUIDE-CN.md) — bilingual companions to
  `UI_CONTENT_STANDARDS.md`.
- [Client tech stack](clients/CLIENT_TECH_STACK.md)
- [Client i18n and theme](clients/CLIENT_I18N_THEME_SPEC.md)
- [Client API contract](clients/CLIENT_API_CONTRACT.md)
- [Workspace navigation](clients/WORKSPACE_NAVIGATION_SPEC.md)
- [Web application architecture EN](clients/WEB_APPLICATION_ARCHITECTURE-EN.md) /
  [CN](clients/WEB_APPLICATION_ARCHITECTURE-CN.md)
- [Map-first decision cockpit spec EN](clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md) /
  [CN](clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md)
- [Market-positioning cockpit spec EN](clients/MARKET_POSITIONING_COCKPIT_SPEC-EN.md) /
  [CN](clients/MARKET_POSITIONING_COCKPIT_SPEC-CN.md)
- [Operational glossary context spec EN](clients/OPERATIONAL_GLOSSARY_CONTEXT_SPEC-EN.md) /
  [CN](clients/OPERATIONAL_GLOSSARY_CONTEXT_SPEC-CN.md)

### Policies

- [Product boundary policy](policies/PRODUCT_BOUNDARY_POLICY.md)
- [Data policy](policies/DATA_POLICY.md)
- [Dependency policy](policies/DEPENDENCY_POLICY.md)

## Current runbooks

Operational procedures and operator-facing guides:

- [Local development](operations/LOCAL_DEVELOPMENT.md)
- [Local Docker runtime](operations/LOCAL_DOCKER_RUNTIME.md)
- [Validation](operations/VALIDATION.md)
- [Live PostgreSQL](operations/LIVE_POSTGRESQL.md)

- [DB migrations](operations/DB_MIGRATIONS.md)
- [DB runtime hardening](operations/DB_RUNTIME_HARDENING.md)
- [Production reliability](operations/PRODUCTION_RELIABILITY_SPEC.md)
- [Performance baseline](operations/PERFORMANCE_BASELINE.md)
- [Performance budget](operations/PERFORMANCE_BUDGET.md)
- [Backup and restore](operations/BACKUP_RESTORE.md)
- [Disaster recovery](operations/DISASTER_RECOVERY.md)
- [Release rollback](operations/RELEASE_ROLLBACK.md)
- [Incident response](operations/INCIDENT_RESPONSE.md)
- [Release signing](operations/RELEASE_SIGNING.md)
- [Provider live validation](operations/PROVIDER_VALIDATION.md)
- [Cost observation sources](operations/COST_OBSERVATION_SOURCES.md)
- [Service level objectives](operations/SLO.md)
- [Production source operations EN](operations/PRODUCTION_SOURCE_OPERATIONS.md) /
  [CN](operations/PRODUCTION_SOURCE_OPERATIONS-CN.md)
- [Source failure](operations/SOURCE_FAILURE.md)
- [Backfill](operations/BACKFILL.md)
- [Source certification](operations/SOURCE_CERTIFICATION.md)
- [Data freshness](operations/DATA_FRESHNESS.md)
- [SSO/OIDC](operations/SSO_OIDC.md)
- [User access](operations/USER_ACCESS.md)
- [API keys](operations/API_KEYS.md)
- [Security audit](operations/SECURITY_AUDIT.md)
- [Access revocation](operations/ACCESS_REVOCATION.md)
- [Simulated market price sources](operations/SIMULATED_MARKET_PRICE_SOURCES.md)
- [Portfolio network optimization EN](operations/PORTFOLIO_NETWORK_OPTIMIZATION.md) /
  [CN](operations/PORTFOLIO_NETWORK_OPTIMIZATION-CN.md)
- [Storage and nomination assessment EN](operations/STORAGE_NOMINATION_ASSESSMENT.md) /
  [CN](operations/STORAGE_NOMINATION_ASSESSMENT-CN.md)
- [Identity, authorization, and audit governance EN](operations/IDENTITY_AUDIT_GOVERNANCE.md) /
  [CN](operations/IDENTITY_AUDIT_GOVERNANCE-CN.md)
- [OIDC access token EN](operations/OIDC_ACCESS_TOKEN.md) /
  [CN](operations/OIDC_ACCESS_TOKEN-CN.md)
- [DeepSeek live monitoring EN](operations/LLM_MONITORING-EN.md) /
  [CN](operations/LLM_MONITORING-CN.md)
- [Market positioning imports EN](operations/MARKET_POSITIONING_IMPORTS-EN.md) /
  [CN](operations/MARKET_POSITIONING_IMPORTS-CN.md)

## User and UAT documentation

- [Quick start](user/QUICK_START.md)
- [Market workflow](user/MARKET_WORKFLOW.md)
- [Portfolio workflow](user/PORTFOLIO_WORKFLOW.md)
- [Strategy Lab](user/STRATEGY_LAB.md)
- [Shadow monitoring](user/SHADOW_MONITORING.md)
- [Decision review](user/DECISION_REVIEW.md)
- [Data status and provenance](user/DATA_STATUS_AND_PROVENANCE.md)
- [Commercial UAT plan](uat/COMMERCIAL_UAT_PLAN.md)
- [Trader UAT script](uat/TRADER_UAT_SCRIPT.md)
- [UAT feedback template](uat/UAT_FEEDBACK_TEMPLATE.md)
- [RC defect register](uat/RC_DEFECT_REGISTER.md)
- [AI evaluation report](uat/AI_EVALUATION_REPORT.md)
- [Accessibility report](uat/ACCESSIBILITY_REPORT.md)
- [I18N report](uat/I18N_REPORT.md)
- [RC acceptance report](uat/RC_ACCEPTANCE_REPORT.md)

## Release, security, and deployment

- [Release readiness](release/RELEASE_READINESS.md)
- [Release engineering specification](release/RELEASE_ENGINEERING_SPEC.md)
- [Release channels](release/RELEASE_CHANNELS.md)
- [GA release gates](release/GA_RELEASE_GATES.md)
- [Software supply chain](release/SUPPLY_CHAIN.md)
- [Update policy](release/UPDATE_POLICY.md)
- [Install Windows](release/INSTALL_WINDOWS.md)
- [Install Linux](release/INSTALL_LINUX.md)
- [Third-party notices](../THIRD_PARTY_NOTICES.md)
- [Security acceptance evidence EN](release/SECURITY_ACCEPTANCE_EVIDENCE.md) /
  [CN](release/SECURITY_ACCEPTANCE_EVIDENCE-CN.md)
- [Deployment roles EN](deployment/DEPLOYMENT_ROLES-EN.md) /
  [CN](deployment/DEPLOYMENT_ROLES-CN.md)

## Document status rules

- Current architecture policies, API contracts, client standards, and
  current runbooks are normative.
- `*-EN.md` and `*-CN.md` are language companions and must describe the same
  behavior.

## Documentation maintenance

- Internal Markdown links are checked by
  [`scripts/ci/check_markdown_links.py`](../scripts/ci/check_markdown_links.py).
- Remove obsolete documents after current references are updated; do not keep
  internal milestone evidence in the public release repository.
