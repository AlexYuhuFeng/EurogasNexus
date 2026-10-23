# Linux role and strategy privacy acceptance — 2026-10-22

## Verdict and scope

The tested backend ownership/sharing slice is suitable for review. This is **not a
production delivery approval**. Evidence applies to the current uncommitted work
based on `c4ff4a9`, not to earlier environment snapshots or historical acceptance
counts. No changes were pushed or deployed to a customer installation.

Validation used Linux, Python 3.11, an isolated local PostgreSQL database migrated
to `0041_job_owner_identity`, Uvicorn, Vite and system Chromium. Named synthetic
identities represented trader/analyst, reviewer, viewer and ADMIN. Trader is a
business workflow; it uses an explicitly granted ANALYST role, not a new implicit
authority. Browser sessions were locally issued fixtures, not customer SSO.

## Delivered behavior

- New strategies bind ownership to the active authenticated principal and default
  to PRIVATE. Attribution text cannot assign ownership. The owner selects PRIVATE,
  PUBLIC within this deployment, or explicit eligible active groups.
- Shared readers can read authorized strategy/version/run information, but cannot
  modify, freeze, fork, execute or republish the owner's strategy. Source licence
  and role checks remain additional requirements. ADMIN alone does not grant
  commercial strategy access.
- Collection ACLs precede limits. Child resources, capability handlers and linked
  portfolio/review/analysis projections enforce the same privacy boundary. Jobs
  bind a dedicated `owner_principal_id` foreign key separately from attribution
  text and disclose only their server-recorded owner's work; foreign reads/cancels return
  404 and foreign owner filters return an empty list.
- Existing ownerless strategies remain private and quarantined. No free-text owner
  inference or mass ownership reassignment occurs. Migration downgrade is refused
  because older code would remove the privacy boundary.
- Existing name-only jobs remain quarantined. Migration 0041 is additive and does
  not guess ownership from a name that could collide with an identity ID. Agent
  review-pack access resolves the review-pack ID through its actual parent run,
  restoring owner review confirmation/replay without exposing another user's pack.
- API-key scopes intersect current owner grants. Empty key scopes grant the public
  baseline only. External LLM invocation and credential testing obey the existing
  outbound-provider switch before opening a connection.
- Web sharing controls and Python SDK expose the ownership contract. Admin grant
  controls validate drafts and retain recoverable failures; disabling an identity
  takes effect on subsequent authorization requests.
- Group audiences on the strategy collection are loaded in a batch restricted to
  the visible page, avoiding a separate query for each owned strategy.

## Evidence

| Check | Result and limits |
| --- | --- |
| Actual HTTP against PostgreSQL | 25/25 sharing assertions: private isolation, version protection, public read-only, owner-only writes, ADMIN denial, group access, membership withdrawal and persisted owner edits. |
| Linux Chromium, strategy workflow | 7/7: private navigator isolation, PUBLIC save/reload, read-only recipient, return to private, eligible group selection, no unhandled page errors. |
| Linux Chromium, ADMIN workflow | 8/8: role/scope save and reload, empty-role rejection, injected transport failure and retry, disable/enable immediately reflected by API authorization, no unhandled page errors. |
| Initial focused backend regression | 506 passed: full security suite plus registry, jobs, shadow, projection, federation and public API surface tests. Two dependency deprecation warnings. |
| Final security and contract regression | 952 passed, two dependency deprecation warnings. |
| Actual multi-role HTTP workflows | 77/77 after restart: named-role boundaries, Unicode private draft persistence, exact synthetic NPV 4.50, key-scope attenuation, revocation, identity disable/session rejection and role changes. |
| Actual trader contract HTTP workflow | 15/15: persisted create/read/edit, stale token conflict, preserved prior records and unauthorized role rejection. |
| Actual job isolation on PostgreSQL | 7/7: stable owner list/cancel, foreign/legacy attribution collision denial and unchanged refused job states. |
| Installed wheel | Build succeeded; separately started installed API passed 6 HTTP checks; installed SDK passed 6 real HTTP ownership/group-discovery/share/withdrawal checks. This is not native installer or image evidence. |
| Query-count regression | Owner sharing/API/DB foundation: 40 passed; one versus three GROUPS rows have constant SELECT count and a single page-bounded audience query. |
| Runtime readiness | Migration 0041 applied and repeated; 95 required tables present, no readiness warnings. Missing sharing-table regressions added. |
| Import/capability/SDK integration | 75 passed across DB foundation, capability runtime/API/MCP, SDK sharing and privacy suites; overlaps other suites and is not an additive unique-test count. |
| Web | 935 passed, 3 skipped; production build passed. |

Local evidence is in ignored `.local-runtime/strategy-sharing/` (`http-results.json`,
`browser-results.json`, reader/owner screenshots) and
`.local-runtime/admin-ui-acceptance/` (`results.json`, retry/final screenshots).
Credentials and sessions remain private and must not be attached to a release.
Lifecycle tests issue a fresh synthetic session for each run because disabling a
principal correctly revokes the previous session; an initial repeat with a revoked
fixture returned 401 and was corrected without changing production behavior.
The initial browser harness incorrectly waited for network idle on a polling app;
its navigation was corrected to wait for DOM and visible application controls.
The development origin was explicitly configured in the API CORS allowlist so
cookie-authenticated mutations passed the existing origin check.

Repeatable source tests include `tests/security/test_strategy_owner_sharing.py`,
`test_strategy_aggregate_privacy.py`, `test_identity_key_attenuation.py`,
`test_llm_adapter_egress.py`, `tests/api/test_jobs_api.py`,
`tests/sdk/test_strategy_registry_sharing_client.py` and `tests/domain/federation/`.

## Functional regression repairs

The broader API/SDK run initially failed 37 checks. Most fixtures relied on a
shared deployment token, ownerless strategies or fake database sessions. They now
use actual named database identities and owned resources while preserving numeric,
serializer and authorization assertions. Actual defects found were inconsistent
job ownership and the review-pack/run-ID mismatch described above. The API surface
census is now 187 paths / 201 operations, with group administration explicitly
recorded as a direct control-plane API. Source-contract drift after the existing
bounded ENTSOG extraction and historical delivery-document path listings were
corrected. Full-repository Ruff passes; readiness hygiene tests passed 16 with 17
platform/tool-dependent skips, not claimed as executed native acceptance.

## Regional architecture

[Assessment](../../architecture/GLOBAL_DATA_DEPLOYMENT_ASSESSMENT.md) recommends
independent regional application/database/storage/IAM installations. The
[exchange contract](../../architecture/REGIONAL_EXCHANGE_PROTOCOL_V1.md) establishes
EU/CN/CA/SG namespaces, a versioned envelope, ownership/provenance/approval
references, idempotency, expiry and exact-byte integrity checks. It is an offline
contract foundation, not an enabled transfer service. No cross-region replication,
peer authentication, receiving endpoint or regional deployment is claimed.

## Remaining delivery gates

- Native Linux installation/package validation has not been refreshed for this
  tree; browser validation is not Tauri installer evidence. Windows/macOS and
  external signing/notarization are also outside this evidence.
- Current-tree image/CVE and local restore evidence are recorded in
  [backend runtime acceptance](17_BACKEND_RUNTIME_ACCEPTANCE.md). Production restore,
  customer IdP acceptance and licensed-provider certification remain outstanding.
- The ADMIN browser still displays failed commercial reads in the global status
  banner although access is correctly denied. Role-aware page loading/status UX
  and the broader text-overflow/design work remain open, per backend-first scope.
- No production-scale latency/load claim follows from small synthetic fixtures.
  The batch-query regression bounds the new list overhead, not total system capacity.
- Existing ownerless resources require a separately verified ownership recovery
  procedure before operators can restore their access. No automatic assignment is safe.
