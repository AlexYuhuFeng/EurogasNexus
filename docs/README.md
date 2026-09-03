# Documentation Index

Mandarin companion: [README-CN.md](README-CN.md)

This index is the authoritative entry point for repository documentation. It
separates current/normative material from runbooks, design references,
historical planning, and archived records. If two documents disagree, follow
the current/normative document listed here and report the conflict.

## Read first

1. [Changelog](../CHANGELOG.md)
2. [Current pause point](architecture/CURRENT_PAUSE_POINT.md) — verified runtime
   and product baseline.
3. [Production readiness backlog](release/PRODUCTION_READINESS_BACKLOG.md) — active
   production gaps and remaining work.
4. [Project directory and ownership](../PROJECT_DIRECTORY.md)
5. [Architecture decisions](architecture/ARCHITECTURE_DECISION_RECORD.md)
6. [RFC process](engineering/RFC_PROCESS.md) and
   [accepted RFCs](engineering/rfc/README.md)
7. [Archive policy](policies/ARCHIVE_POLICY.md)
## Normative and current

These documents define binding engineering boundaries. Contracts and policies
are normative. Language companions (`-EN` / `-CN`) must describe the same
behavior.

### Governance and process

| Document | Authority |
| --- | --- |
| [Architecture decisions and ADR process](architecture/ARCHITECTURE_DECISION_RECORD.md) | Normative for architecture decisions |
| [RFC process](engineering/RFC_PROCESS.md) | Normative for cross-cutting engineering changes |
| [RFC index](engineering/rfc/README.md) | Index of accepted RFCs |
| [Archive policy](policies/ARCHIVE_POLICY.md) | Normative for documentation lifecycle |
| [Coding standards](engineering/CODING_STANDARDS.md) | Normative for Python code review |
| [API contract evolution policy EN](architecture/API_CONTRACT_EVOLUTION_POLICY.md) / [CN](architecture/API_CONTRACT_EVOLUTION_POLICY-CN.md) | Normative for `/api` change control |
| [API path policy](api/API_PATH_POLICY.md) | Normative for route prefixes |
| [Terminology standard](architecture/TERMINOLOGY.md) | Normative for product language |

### Architecture and contracts

- [Contract index](contracts/00_CONTRACT_INDEX.md)
- [API contract](contracts/06_API_CONTRACT.md)
- [Public API conventions](contracts/API_CONVENTIONS.md)
- [Database contract](contracts/04_DB_CONTRACT.md)
- [Runtime store contract](contracts/05_RUNTIME_STORE_CONTRACT.md)
- [SDK and CLI contract](contracts/15_SDK_CLI_CONTRACT.md)
- [Resource-pool contract EN](contracts/21_RESOURCE_POOL_CONTRACT-EN.md) /
  [CN](contracts/21_RESOURCE_POOL_CONTRACT-CN.md)
- [Testing contract](contracts/17_TESTING_CONTRACT.md)
- [Target product architecture](architecture/TARGET_PRODUCT_ARCHITECTURE.md)
- [Backend implementation blueprint](architecture/BACKEND_IMPLEMENTATION_BLUEPRINT.md)
- [Optimization layer](architecture/PHASE_TWO_OPTIMIZATION.md) /
  [CN](architecture/PHASE_TWO_OPTIMIZATION-CN.md)
- [European network geometry policy](architecture/EUROPEAN_NETWORK_GEOMETRY_POLICY.md)
- [Actor identity model](architecture/ACTOR_IDENTITY_MODEL.md) /
  [CN](architecture/ACTOR_IDENTITY_MODEL-CN.md)
- [OWL gas role model EN](ontology/OWL_GAS_ROLE_MODEL.md) /
  [CN](ontology/OWL_GAS_ROLE_MODEL-CN.md)
- [Natural-gas subject architecture](ontology/europe-natural-gas.md)
- [Ontology gap report](ontology/gap-report.md)

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
- [Backup and restore](operations/BACKUP_RESTORE.md)
- [Service level objectives](operations/SLO.md)
- [Production source operations EN](operations/PRODUCTION_SOURCE_OPERATIONS.md) /
  [CN](operations/PRODUCTION_SOURCE_OPERATIONS-CN.md)
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

## Release, security, and deployment

- [Release readiness](release/RELEASE_READINESS.md)
- [Production readiness backlog](release/PRODUCTION_READINESS_BACKLOG.md)
- [Security acceptance evidence EN](release/SECURITY_ACCEPTANCE_EVIDENCE.md) /
  [CN](release/SECURITY_ACCEPTANCE_EVIDENCE-CN.md)
- [Deployment roles EN](deployment/DEPLOYMENT_ROLES-EN.md) /
  [CN](deployment/DEPLOYMENT_ROLES-CN.md)
- [Windows AllInOne installer EN](deployment/ALL_IN_ONE_INSTALLER-EN.md) /
  [CN](deployment/ALL_IN_ONE_INSTALLER-CN.md)

## Design references

Context and visual direction, not implementation queues. Re-read only when the
current queue explicitly activates a related UI milestone.

- [UX layout blueprints](design/UX_LAYOUT_BLUEPRINTS.md)
- [UI audit 2026-08-31](design/UI_AUDIT_2026-08-31.md)
- [UI audit 2026-09-01](design/UI_AUDIT_2026-09-01.md)
- [Intraday decision feed EN](product/INTRADAY_DECISION_FEED-EN.md) /
  [CN](product/INTRADAY_DECISION_FEED-CN.md)
- [Market practice audit EN](architecture/MARKET_PRACTICE_AUDIT-EN.md) /
  [CN](architecture/MARKET_PRACTICE_AUDIT-CN.md)

## Historical and planning

Background, delivery history, and finalized planning material. Do not treat
these as implementation instructions unless a current queue item activates
them.

- [Project north star](architecture/PROJECT_NORTH_STAR.md)
- [Product delivery master plan](architecture/PRODUCT_DELIVERY_MASTER_PLAN.md)
- [Whole-project capability blueprint](architecture/WHOLE_PROJECT_CAPABILITY_BLUEPRINT.md)
- [Real-time market intelligence blueprint](product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md)
- [Research workflow blueprint](product/RESEARCH_WORKFLOW_BLUEPRINT.md)
- [Reference evidence log](architecture/REFERENCE_EVIDENCE_LOG.md)
- [Reference project lessons](architecture/REFERENCE_PROJECT_LESSONS.md)
- [Documentation consistency audit](architecture/DOCUMENTATION_AUDIT.md)
- [Architecture improvement roadmap CN](architecture/IMPROVEMENT_ROADMAP-CN.md)
- [Completed V1 delivery history](archive/architecture/V1_STEPWISE_DELIVERY_ROADMAP.md)

## Archived

Superseded or completed documents live under the
[archive index](archive/README.md) and are retained for provenance only. They
are not current authority. See the
[archive policy](policies/ARCHIVE_POLICY.md) for criteria and process.

## Document status rules

- `contracts/`, current architecture policies, current client standards, and
  current runbooks are normative.
- `*-EN.md` and `*-CN.md` are language companions and must describe the same
  behavior.
- Files named `BLUEPRINT`, `REFERENCE`, or `AUDIT` provide context unless a
  current queue item explicitly activates them.
- `.agent/plans/` records scoped implementation decisions and completion
  evidence; completed plans are historical.
- Anything under `docs/archive/` is historical, regardless of wording inside
  the file.

## Documentation maintenance

- Internal Markdown links are checked by
  [`scripts/ci/check_markdown_links.py`](../scripts/ci/check_markdown_links.py).
- Move obsolete documents through the
  [archive policy](policies/ARCHIVE_POLICY.md); do not delete or mass-move
  uncertain material.
- Cross-cutting changes start with the [RFC process](engineering/RFC_PROCESS.md);
  architecture changes also update
  [ADR-0001 onward](architecture/ARCHITECTURE_DECISION_RECORD.md).
