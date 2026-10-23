# Global deployment and data movement assessment

This assessment covers the current repository, not a claim of regional residency,
regulatory compliance or a deployed federation. The low-cost recommendation is
**independent regional installations with separate databases and credentials**.
A shared multi-region database or federated query layer needs a separate design.

## Current implementation and actual boundaries

| Data path | Repository evidence | Global deployment implication |
| --- | --- | --- |
| API and workers → PostgreSQL | `src/eurogas_nexus/db/session.py` resolves one runtime URL; `deploy/runtime/compose.yaml` shares one PostgreSQL service and named volume | There is no regional router or replication policy. The operator determines physical storage location, network path and database transport protection. A local Compose volume does not establish a country or cloud region. |
| Identity and authorization | `src/eurogas_nexus/db/models/identity.py`, `src/eurogas_nexus/security/capabilities.py` | Roles and source-family entitlements are implemented; organization, portfolio, market and region scopes are explicitly unsupported. Do not treat roles, work modes or dataset labels as tenant or regional isolation. |
| Research files and exports | `src/eurogas_nexus/core/config.py`, `src/eurogas_nexus/domain/research/export.py` | The research artifact root is configurable local storage. Export/download also moves data to the requesting workstation; backend storage location cannot constrain subsequent copies. |
| Backup and restore | `scripts/ops/backup_runtime.py`, `scripts/ops/backup_restore_drill.py` | Backup files and restore targets are independent copies. Their locations, retention, encryption, key custody and recovery permissions must be controlled alongside the live database. Local restore success is not proof of a compliant regional recovery target. |
| Authentication | `src/eurogas_nexus/security/oidc.py` | OIDC discovery, token exchange and identity claims cross the configured identity-provider boundary. SSO federation is implemented; that does not imply federated application data or cross-installation authorization. |
| Provider ingestion | Provider adapters and `src/eurogas_nexus/api/routes/public/credentials.py` | External provider endpoints and credentials remain separate from data entitlements. Provider licenses may restrict region, raw/derived redistribution, export and model use; a successful connection does not grant those rights. |
| LLM requests | `src/eurogas_nexus/llm/deepseek.py` | Completion messages and authorization headers leave the installation for the fixed DeepSeek HTTPS endpoint. Credential tests also transmit credentials. HTTPS protects transport, not residency or recipient processing location. |
| Audit/logs | `src/eurogas_nexus/governance/audit.py`, `src/eurogas_nexus/db/repositories/audit.py` | Centralized log collection, support bundles and observability exports can create additional copies. Redaction does not make business identifiers or operational metadata unrestricted. |

## Low-cost change implemented

The existing `llm_external_provider_enabled` policy is now checked at **both**
DeepSeek adapter entrypoints before any HTTP operation: completion and credential
connection testing. Previously the analysis route checked this policy but other
callers could reach the adapter without that check. Monitoring and credential-test
callers now receive `provider_disabled` / `LLM_PROVIDER_DISABLED_IN_PROFILE`.

The setting retains its existing semantics: `EUROGAS_NEXUS_ENV=trial` or `release`
forces external LLM calls off, including an explicit enable override. In development,
set `EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED=false` to disable them. Settings are
cached per process: restart the API and workers after changing deployment policy.
The API profile and runtime environment are separate settings; do not assume that
an API profile alone selects the runtime environment's policy.

This closes a concrete application egress bypass. It does **not** block provider
feeds, OIDC, database connections, downloads or arbitrary host network activity.
Use infrastructure egress rules as an independent control, and allow only the
endpoints approved for the installation. No new service, schema, synchronization
protocol or regional label was introduced.

## Recommended regional operating model

1. Deploy one complete application/worker/database stack per approved region or
   isolation domain, with region-specific credentials and storage. Avoid mounting
   another region's database or artifact root into that stack.
2. Keep backups, artifact storage, log sinks and their encryption keys in the
   approved domain. Validate database TLS and ingress HTTPS for the chosen topology;
   the default local Compose deployment is not proof for remote connections.
3. Register each installation with the intended identity provider, audience and
   callbacks. Grant access independently. Never copy bearer tokens or session
   stores across installations to simulate federation.
4. Disable external LLM calls where outbound processing is not approved. Review
   provider ingestion and OIDC separately; neither is covered by the LLM switch.
5. For a required cross-region exchange, explicitly select the allowed dataset,
   entitlement, recipient, purpose, provenance, retention and transport path.
   Prefer an auditable one-way export of approved derived data initially. Do not
   replicate the full commercial database or assume anonymization from aggregation.
6. Test unauthorized regional access, export denial, backup restore placement and
   loss of regional connectivity. Independent deployments currently provide no
   automatic global search, failover, conflict resolution or shared live state.

Infrastructure and customer policy evidence are prerequisites to a residency claim.
Jurisdiction-specific legal and licensing conclusions require the relevant owners;
this technical assessment does not determine them.

## Cost and architecture decision

Estimates are engineering planning ranges for an existing deployment team, not
measured delivery promises. They exclude procurement, external approvals and data
license negotiations.

| Option | Indicative work | Decision |
| --- | --- | --- |
| Close existing LLM egress-policy bypass | Less than one engineering day plus focused regression checks | Implemented in this change. |
| Operate independent regional installations | Roughly 2–5 engineering days per first region, assuming existing infrastructure/IAM automation; more for recovery/security acceptance | Reuse current architecture; deployment work remains unperformed. |
| Governed one-way dataset exchange | Roughly 1–3 weeks after scope, format, entitlement and transport are agreed | Design a bounded contract first; not implemented here. |
| Federated queries with tenant/region authorization | Several weeks to months | Requires regional/tenant identity namespaces, query authorization, disclosure controls, provenance and failure semantics. Not a low-cost configuration change. |
| Bidirectional active-active data synchronization | Multi-month programme | Requires ownership/conflict rules, deletion/retention propagation, key management, partitions and disaster recovery design. Not justified by current evidence. |

The current source-family entitlement model cannot safely substitute for tenant or
regional boundaries inside one shared deployment. Keep the first step operationally
isolated and defer a federation layer until concrete cross-region use cases and
measured demand justify the additional architecture.
