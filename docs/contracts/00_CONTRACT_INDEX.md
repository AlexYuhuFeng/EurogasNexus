# Contract Index

This directory defines the V1.0 bootstrap contracts for Eurogas Nexus. Contracts
are product boundaries, not business feature specifications.

## Contract Set

| Contract | Scope |
| --- | --- |
| `01_REPOSITORY_CONTRACT.md` | Repository topology and ownership |
| `02_IMPORT_BOUNDARY_CONTRACT.md` | Import direction and side-effect rules |
| `03_CORE_CONTRACT.md` | Shared primitives and configuration |
| `04_DB_CONTRACT.md` | Database and migration boundary |
| `05_RUNTIME_STORE_CONTRACT.md` | Ephemeral runtime state boundary |
| `06_API_CONTRACT.md` | API app, route profiles, and route rules |
| `07_DOMAIN_CONTRACT.md` | Domain package boundaries |
| `08_APPLICATION_WORKFLOW_CONTRACT.md` | Workflow orchestration boundary |
| `09_INFRASTRUCTURE_CONNECTOR_CONTRACT.md` | Infrastructure adapter boundary |
| `10_INGESTION_ETL_CONTRACT.md` | Ingestion and normalization boundary |
| `11_DATA_QUALITY_CONTRACT.md` | Validation and quality checks |
| `12_STREAMING_KAFKA_CONTRACT.md` | Future streaming and Kafka boundary |
| `13_AUTH_AUDIT_CONTRACT.md` | Runtime auth and audit boundary |
| `14_GOVERNANCE_ENTITLEMENT_CONTRACT.md` | Governance and entitlement boundary |
| `15_SDK_CLI_CONTRACT.md` | SDK and CLI boundary |
| `16_RELEASE_DEPLOYMENT_CONTRACT.md` | Release and deployment boundary |
| `17_TESTING_CONTRACT.md` | Test taxonomy and expectations |
| `18_NEW_FILE_TEMPLATE.md` | Required review checklist for new files |
| `19_FUNCTION_SIGNATURE_CATALOG.md` | Current shell signatures |
| `20_MODULE_OWNERSHIP_MATRIX.md` | Module ownership matrix |

## Bootstrap Rule

If a proposed change needs behavior outside these contracts, update the contract
first and add a matching boundary test before implementing the behavior.

## Related Docs

- `../architecture/PROJECT_NORTH_STAR.md`
- `../architecture/WHOLE_PROJECT_CAPABILITY_BLUEPRINT.md`
- `../architecture/REFERENCE_EVIDENCE_LOG.md`
- `../architecture/ARCHITECTURE_DECISION_RECORD.md`
- `../architecture/CLAUDE_CODE_DELIVERY_BRIEF.md`
- `../architecture/CLAUDE_CODE_GOAL_MODE.md`
- `../architecture/CLAUDE_CODE_START_PROMPTS.md`
- `../architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md`
- `../architecture/CURRENT_PAUSE_POINT.md`
- `../architecture/CLAUDE_CODE_EXECUTION_PLAYBOOK.md`
- `../architecture/NEXT_DEVELOPMENT_QUEUE.md`
- `../architecture/OFFLINE_CLAUDE_CODE_GUIDE.md`
- `../architecture/TARGET_PRODUCT_ARCHITECTURE.md`
- `../architecture/REFERENCE_PROJECT_LESSONS.md`
- `../architecture/FUTURE_CLIENT_UX_REFERENCE.md`
- `../architecture/V1_DOMAIN_DELIVERY_MAP.md`
- `../architecture/V1_STEPWISE_DELIVERY_ROADMAP.md`
- `../clients/README.md`
- `../clients/CLIENT_DELIVERY_MILESTONES.md`
- `../clients/CLIENT_API_CONTRACT.md`
- `../clients/CLIENT_DESIGN_SYSTEM.md`
- `../clients/SDK_CLIENT_DESIGN_SPEC.md`
- `../clients/CLI_CLIENT_DESIGN_SPEC.md`
- `../clients/WEB_CLIENT_DESIGN_SPEC.md`
- `../clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
- `../clients/WINDOWS_DEMO_UX_REFERENCE.md`
- `../architecture/V1_BACKEND_ARCHITECTURE.md`
- `../architecture/V1_GAP_REPORT.md`
- `../policies/PRODUCT_BOUNDARY_POLICY.md`
- `../policies/DEPENDENCY_POLICY.md`
- `../policies/DATA_POLICY.md`
- `../api/API_PROFILES.md`
- `../api/API_SURFACE_BLUEPRINT.md`
- `../data/CANONICAL_DATA_MODEL_BLUEPRINT.md`
- `../product/RESEARCH_WORKFLOW_BLUEPRINT.md`
- `../operations/VALIDATION.md`
- `../compliance/RESEARCH_ONLY_COMPLIANCE.md`
- `../release/V1_RELEASE_READINESS.md`
- `../release/V1_FULL_PROJECT_RELEASE_SCOPE.md`
- `../release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md`
- `../release/V1_RELEASE_MILESTONE_BACKLOG.md`
- `../release/V1_RELEASE_ACCEPTANCE_MATRIX.md`
- `../release/V1_RELEASE_EXECPLAN_TEMPLATE.md`
