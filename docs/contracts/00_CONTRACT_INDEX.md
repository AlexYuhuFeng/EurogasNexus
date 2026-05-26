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

- `../architecture/V1_BACKEND_ARCHITECTURE.md`
- `../architecture/V1_GAP_REPORT.md`
- `../policies/PRODUCT_BOUNDARY_POLICY.md`
- `../policies/DEPENDENCY_POLICY.md`
- `../policies/DATA_POLICY.md`
- `../api/API_PROFILES.md`
- `../operations/VALIDATION.md`
- `../compliance/RESEARCH_ONLY_COMPLIANCE.md`
- `../release/V1_RELEASE_READINESS.md`
