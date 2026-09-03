# Documentation Index

Mandarin companion: [README-CN.md](README-CN.md)

This index is the authoritative entry point for repository documentation. It
separates current/normative material from runbooks, design references,
historical planning, and archived records. If two documents disagree, follow
the current/normative document listed here and report the conflict.

## Read first

1. [Changelog](../CHANGELOG.md)
2. [Release readiness](release/RELEASE_READINESS.md) — current release status,
   validated gates, and known production gaps.
3. [Project directory and ownership](../PROJECT_DIRECTORY.md)
4. [Architecture decisions](architecture/ARCHITECTURE_DECISION_RECORD.md)
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
- [Incident response](operations/INCIDENT_RESPONSE.md)
- [Release signing](operations/RELEASE_SIGNING.md)
- [Provider live validation](operations/PROVIDER_VALIDATION.md)
- [Cost observation sources](operations/COST_OBSERVATION_SOURCES.md)
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
