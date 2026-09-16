# W0-02 — Backend Access, Entitlement, Provider and Control-Plane Inventory

Status: INVENTORY (documentation only; no code changed). Task: W0-02, Architecture V2.
Target authority: `docs/engineering/Architecture-V2/06_IDENTITY_ACCESS_CONTROL_PLANE.md`,
`07_DATA_PLATFORM.md`, `11_CURRENT_TO_TARGET_GAP_MATRIX.md`. Current-behaviour authority: the
repository. Every claim below names a repository path and line. No secret value was read or printed.

## 1. How API routes declare identity and permission requirements today

### 1.1 Mechanism name

The mechanism is the **declarative public-route permission registry** in
`src/eurogas_nexus/security/permissions.py` (docstring lines 1-9: "Every public path must resolve to a
declared permission — the registry test fails CI on any path without a declaration"). It is a
path-pattern table, not a per-handler decorator: routes carry no `@require_permission(...)`; the
requirement is derived from the request path (plus the HTTP method for one override).

### 1.2 Registration and wiring

- Route profiles: `src/eurogas_nexus/api/route_profiles.py:28-47` define `development`, `internal`
  and `release`. Only `release` sets `require_auth=True` (`route_profiles.py:45`); `development`
  additionally sets `include_dev=True` (`route_profiles.py:33`) and `internal` sets
  `include_internal=True` (`route_profiles.py:39`).
- App factory: `src/eurogas_nexus/api/app.py:22` resolves the profile, and `app.py:24-32` installs
  three application-level dependencies **only when `route_profile.require_auth` is true**:
  `require_public_api_auth`, then `require_identity`, then `require_route_permission`. The resulting
  list is passed to `FastAPI(dependencies=...)` at `app.py:33-40`.
- Consequence: in the `development` and `internal` profiles **no authentication dependency is
  installed app-wide**, so `request.state.identity` is never populated. Handlers needing a principal
  fall back to the compatibility principal (`api/dependencies/row_entitlement.py:25`,
  `api/dependencies/entitlement.py:51`, `api/dependencies/route_permission.py:60`) or to `None`
  (`api/routes/public/agents.py:74-81`). The code default profile is `development`
  (`src/eurogas_nexus/core/config.py:112`, `:144`).
- Route mounting: `src/eurogas_nexus/api/route_registration.py:47-83` mounts 28 public routers, the
  internal router only when `include_internal` (`:78-79`) and the dev router only when
  `include_dev` (`:81-82`).

### 1.3 The registry vocabulary and matching

- `Permission` (route category) is declared at `src/eurogas_nexus/security/permissions.py:17-26`
  with the values `public`, `read`, `write`, `governed`, `review`, `operator`, `admin`.
  `Permission.WRITE` is declared but appears in no `ROUTE_PERMISSIONS` entry
  (`permissions.py:38-167`), so it is currently unreachable.
- `ROUTE_PERMISSIONS` (`permissions.py:38-167`) is a `tuple[tuple[str, Permission], ...]`;
  `METHOD_ROUTE_PERMISSIONS` (`permissions.py:172-174`) carries the single method-aware override
  `("POST", "/api/research/datasets", Permission.GOVERNED)`.
- Resolution: `permission_for_path()` (`permissions.py:198-231`) ranks literal routes (0) over
  templated routes (1) over prefix families (2), longest pattern wins, and **raises `KeyError`
  (lines 229-230) when no declaration matches** — deliberately, so an undeclared path cannot be
  served silently.
- Enforcement: `require_route_permission()` (`src/eurogas_nexus/api/dependencies/route_permission.py:28-103`)
  turns that `KeyError` into HTTP 500 `permission_not_declared` (`route_permission.py:48-58`),
  then compares the resolved identity's role against the declared role floor
  (`route_permission.py:60-73`, HTTP 403 `identity_role_forbidden`). Only for `OPERATOR` and `ADMIN`
  categories does it require more (`route_permission.py:75-102`): an identity-key caller is trusted as
  the actor (`route_permission.py:78-82`), otherwise the spoofable-in-principle
  `X-Eurogas-Principal` header must validate as an operator principal
  (`route_permission.py:25`, `route_permission.py:84-102`; 401 when missing, 403 when invalid).

Concrete examples of declared requirements:

| Path | Declared permission | Registry line |
|---|---|---|
| `/api/health` | `public` | `security/permissions.py:40` |
| `/api/me` | `read` | `security/permissions.py:53` |
| `/api/access/users`, `/api/audit` | `admin` | `security/permissions.py:54`, `:60` |
| `/api/credentials/providers` | `read` | `security/permissions.py:63` |
| `/api/credentials/{provider_id}/rotate` | `operator` | `security/permissions.py:67` |
| `/api/sources/{source_id}/run` | `operator` | `security/permissions.py:95` |
| `/api/source-certifications/{source_id}/certify` | `operator` | `security/permissions.py:100` |
| `/api/analysis/query` | `governed` | `security/permissions.py:70` |
| `/api/research/datasets/{dataset_snapshot_id}/export` | `governed` | `security/permissions.py:161` |
| `/api/capabilities/{capability_id}/invoke` | `governed` | `security/permissions.py:143` |

Pinned by `tests/security/test_permissions_registry.py:13-18` (every OpenAPI path must resolve),
`:21-28` (credential writes stay `operator`), `:31-40` (policy-gated paths stay `governed`),
`:43-49` (longest-pattern-wins), `:52-56` (method-aware research dataset),
`:67-72` (role floors), `:74-80` (declared enforcement status).

### 1.4 The second, independent mechanism: handler-level fine-grained authorization

`src/eurogas_nexus/security/authorization.py` is a separate RBAC expansion layer with its own
`Permission` StrEnum (`authorization.py:21-52`, 29 values) and `ROLE_PERMISSIONS`
(`authorization.py:55-128`). It is invoked **inside handlers**, not by the app-wide dependency:
`src/eurogas_nexus/api/routes/public/access.py:40-56` (`_require_admin`) calls
`authorize(principal, permission)` and returns 403 `permission_denied`. `authorize()`
(`authorization.py:164-224`) fails closed on unknown permission (`:178-185`), on non-ACTIVE
principal (`:186-193`), and denies identity/audit administration for the legacy token principal
(`:194-209`).

### 1.5 Public API token, identity resolution, and profile exposure

- `require_public_api_auth` (`src/eurogas_nexus/api/dependencies/public_auth.py:18-65`) accepts
  `Authorization: Bearer`, `X-Eurogas-Api-Key`, or `?api_key=` (query channel for SSE), exempts the
  `/api/auth/` prefix (`public_auth.py:15`, `:41-42`) and cookie sessions (`:43-45`), and fails
  closed with 503 when no token is configured.
- `require_identity` (`src/eurogas_nexus/api/dependencies/identity.py:39-73`) resolves, in order:
  `X-Eurogas-Identity` DB key (`:57-60` → `:91-124`), `X-Eurogas-Oidc-Access-Token` (`:62-65` →
  `:183-217`), backend session cookie `eurogas_session` (`:67-70` → `:127-180`). With no credential
  at all it attaches `legacy_public_token_principal()` **and records
  `request.state.identity_authenticated = False`** (`identity.py:52-55`) — attaching a compatibility
  principal is explicitly documented as not the same as authenticating a caller (`identity.py:4-10`).
  That flag is what `GET /api/me` reads (`src/eurogas_nexus/api/routes/public/auth.py:285-292`,
  `auth.py:327-334`).
- Documentation/OpenAPI exposure is profile-gated: `app.py:36-38` hides `/docs`, `/redoc` and
  `/openapi.json` for `internal` and `release`; `app.py:60-61` adds the bearer scheme declaration only
  when OpenAPI is exposed.
- The internal administration surface (`/api/internal/*`) authenticates with a static internal token
  plus an explicit operator principal: `src/eurogas_nexus/security/internal_api.py:35-79`
  (`validate_internal_operator_headers`), consumed by
  `src/eurogas_nexus/api/routes/internal/identity_admin.py:43-56`. These paths are **not** in the
  public permission registry; they only exist in the `internal` profile.

## 2. Current role / permission / capability vocabulary as implemented

All values below are read from code.

**Roles** — `src/eurogas_nexus/security/identity.py:36-47`: `VIEWER`, `ANALYST`, `REVIEWER`,
`OPERATOR`, `ADMIN`. Rank order is not the enum order: `ROLE_RANK`
(`identity.py:50-56`) is `VIEWER 0, REVIEWER 1, ANALYST 2, OPERATOR 3, ADMIN 4`, and
`role_allows()` (`identity.py:116-124`) is a rank comparison, i.e. a role floor is inclusive of
higher ranks. Note the documented "least-privilege ordered" ordering (`identity.py:38-41`) does not
match the rank table, and `ANALYST` outranks `REVIEWER`.

**Route permission categories** — `security/permissions.py:17-26` (listed in §1.3).

**Declared enforcement status** — `security/permissions.py:176-183`: `public/read/governed/review`
are `api_token`, `operator/admin` are `principal_required`. The enum itself documents
`principal_required` as "declared; enforcement in next milestone" (`permissions.py:33`), while
`route_permission.py:75-102` now does enforce an operator/administrator identity. The registry
comment and the enforcement code therefore disagree; `tests/security/test_permissions_registry.py:74-80`
pins the registry's self-description, not the enforcement code.

**Role floors per category** — `security/permissions.py:188-195`: `public`→`VIEWER`,
`read`→`VIEWER`, `governed`→`ANALYST`, `review`→`REVIEWER`, `operator`→`OPERATOR`, `admin`→`ADMIN`.

**Fine-grained permissions** — `security/authorization.py:21-52`, 29 values:
`me.read`, `market.read`, `portfolio.read`, `portfolio.write`, `strategy.read`, `strategy.create`,
`strategy.edit`, `strategy.freeze`, `strategy.retire`, `strategy.shadow.manage`, `scenario.create`,
`optimization.run`, `review.read`, `review.record`, `source.read`, `source.run`, `source.backfill`,
`source.credentials.write`, `source.certification.manage`, `runtime.read`, `identity.read`,
`identity.manage`, `api_keys.manage`, `audit.read`, `analysis.query`, `capability.read`,
`capability.invoke`, `agent.read`, `agent.research`.

**Role→permission expansion** — `security/authorization.py:55-128`. `ADMIN` is
`frozenset(set(Permission))` (`authorization.py:127`), i.e. every fine-grained permission including
all commercial-data read/write permissions. `VIEWER` gets 9 read-ish permissions
(`authorization.py:56-68`); `REVIEWER` adds only `review.record` (`authorization.py:76`);
`ANALYST` adds portfolio write, strategy lifecycle, scenario, optimization, analysis and agent
research (`authorization.py:83-106`); `OPERATOR` adds source run/backfill/credentials/certification
(`authorization.py:107-126`). Unknown roles/permissions fail closed via `authorize()`
(`authorization.py:174-185`), and `permission_role_floor()` (`authorization.py:235-242`) returns
`ADMIN` for an unassigned permission.

**Agent capability vocabulary** — separate again. Capabilities are registered in
`src/eurogas_nexus/application/agents/registry.py` and typed by `CapabilityDefinition`
(`src/eurogas_nexus/domain/agents/contracts.py:104-126`), which carries
`required_permissions` (default `["capability.invoke"]`, `contracts.py:115`), an
`entitlement_policy` string of comma-separated source families (default `"none"`,
`contracts.py:116`) and an `ActionPolicy` (`contracts.py:49`, `:126`). Both fields are evaluated
before the handler runs (`src/eurogas_nexus/application/agents/runtime.py:136-167`).

**Inconsistency found** — `Role` includes `REVIEWER`
(`security/identity.py:43-47`) but the internal identity-creation payload restricts role to
`^(VIEWER|ANALYST|OPERATOR|ADMIN)$` (`src/eurogas_nexus/api/routes/internal/identity_admin.py:25`),
so a `REVIEWER` principal cannot be created through that route even though the enum and
`ROLE_PERMISSIONS` support it. The admin route
(`src/eurogas_nexus/api/routes/public/access.py:26-31`, `:98-113`) does not pattern-restrict roles —
it normalizes through `role_value()` and `assign_access()`
(`src/eurogas_nexus/application/enterprise_auth.py:498-508`).

## 3. Organisational and commercial scope as represented today

**Commercial scope exists.** It is a flat, case-folded string list of **source families** held on the
principal as `AuthenticatedPrincipal.data_scopes` (`security/identity.py:80`), persisted on
`IdentityPrincipalRecord.data_scopes` (`src/eurogas_nexus/db/models/identity.py:38`). The check is
`principal_allows_source_family()` (`security/identity.py:227-245`):

- the family is derived by stripping a `_Sim` suffix (`identity.py:220-224`);
- the baseline families `operator-input`, `ENTSOG`, `GIE`, `ECB`, `Weather` are always allowed
  (`identity.py:21-29`, `:242-243`);
- otherwise the principal needs `*` or the case-folded family in `data_scopes` (`identity.py:244-245`);
- an empty family returns `False` (`identity.py:240-241`) — fail-closed.

The commercial family universe is declared twice with different casings:
`PUBLIC_BASELINE_SOURCE_FAMILIES = {"operator-input","ENTSOG","GIE","ECB","Weather"}`
(`identity.py:21-29`, mixed case, matched case-sensitively at `identity.py:242`) and
`COMMERCIAL_SOURCE_FAMILIES = {"EEX","ICE_OCM","Trayport","ICIS","Argus","Kpler","Platts"}`
(`src/eurogas_nexus/domain/dataops/entitlement.py:23-33`). The admin read surface advertises the
commercial list upper-cased — `TRAYPORT`, `PLATTS`, `ARGUS`, `KPLER`
(`api/routes/public/access.py:144-153`) — while the enforcement comparison for non-baseline families
is case-folded (`identity.py:244`), so both spellings work there. Baseline membership
(`identity.py:242`) is not case-folded, so a lowercase `weather` grant would miss the `Weather`
baseline entry and fall through to the scope grant. Recorded as an observation for §10, not a defect
claim.

Grants are administered only by an ADMIN through `PATCH /api/access/users/{principal_id}`
(`api/routes/public/access.py:79-128`), writing `roles` and `data_scopes` via `assign_access`
(`application/enterprise_auth.py:489-511`, upper-casing scopes at `:506-508`). Principal creation
defaults to an **empty** scope list (`db/repositories/identity.py:78-82`). OIDC provisioning maps
identity groups to scopes through `EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP`
(`security/oidc.py:30-31`, `:646-659`; `application/enterprise_auth.py:411-421`), with a configurable
scope claim (`oidc.py:24`, `:702-703`).

**Organisational scope is absent.** A repository-wide search for `organisation`, `organization`,
`org_id`, `tenant` and `scope_refs` across `src/eurogas_nexus` returns no matches. There is no
organisation, portfolio, market/hub, contract/resource or region scope in the authorization model.
Portfolio identifiers exist as business entities in payloads (for example
`clients/web/src/api/client.ts:943`) but are not authorization inputs. V2 doc 06 §4 lists all six
dimensions; today only a source-family dimension is enforced.

## 4. Data entitlement enforcement: enforced vs declared-only

### 4.1 Enforced

- **Row filtering on governed reads.** `api/dependencies/row_entitlement.py:28-36` (`filter_rows`)
  delegates to `domain/dataops/entitlement.py:63-88` (`filter_rows_for_principal`), which drops rows
  whose `source_system` the principal may not see. Live call sites:
  `api/routes/public/lng.py:52-54`, `lng.py:92-94`, `physical.py:26-28`, `physical.py:56-58`,
  `storage.py:51-53`, `storage.py:90-92`; `market.py:160` and `:238` apply the same predicate directly.
- **Derived-result gating.** `row_entitlement.py:39-63` (`require_derived_access`) delegates to
  `derived_result_access` (`domain/dataops/entitlement.py:91-117`), denying when *any* contributing
  source family is disallowed. Called by `api/routes/public/analysis.py:68-74` (analysis query with
  `invoke_provider=true`) and `analysis.py:123-129` (portfolio report). Pinned by
  `tests/security/test_dataops_entitlement_api.py:97-151`.
- **Export.** `governance/entitlement.py:128-155` (`export_check`) denies unknown scope (`:145-149`)
  and restricts internal-research scope with `no-redistribution` (`:151-154`). Dataset export is gated
  by `api/routes/public/research_data.py:454-458` (envelope `export_policy`), `:646`
  (`row_export_policy` per row) and `security/research_entitlement.py:63-92`
  (`effective_entitlement_envelope`, `policy_source: "dataops"`). Portfolio-report export is
  separately blocked at `analysis.py:130-154` with HTTP 403 `export_denied`. Pinned by
  `tests/security/test_llm_provider_gate.py:212-254`.
- **Snapshot read authorization.** `security/research_entitlement.py:115-149`
  (`trusted_source_definitions`, `principal_can_read_snapshot`) re-derives authorization from
  persisted provenance rather than request metadata; called at `research_data.py:315`, `:387`, `:418`,
  `:454`.
- **External-LLM usage.** Two independent controls: (a) a profile switch disabling external providers
  in `trial`/`release` (`core/config.py:127-135`, `:116`), pinned by
  `tests/security/test_llm_provider_gate.py:18-59`; (b) a payload gate — `analysis.py:67-74` requires
  derived access before provider invocation and `analysis.py:92-94` emits
  `LLM_PAYLOAD_FILTERED:contract_prices` when contract prices are not authorized. Contract prices are
  filtered from LLM payloads by default (`test_llm_provider_gate.py:161-209`).
- **Capability entitlement.** `application/agents/runtime.py:146-167` (`_denied_entitlement`) checks
  every family in the capability's `entitlement_policy` against `principal_allows_source_family`
  before the handler runs.
- **Legacy principal bypass (important).** `filter_rows_for_principal` returns **all rows** when
  `principal.auth_method == "legacy_public_token"` (`domain/dataops/entitlement.py:77-78`), and
  `derived_result_access` returns `ALLOWED` for the same condition (`:102-103`). That principal
  carries `data_scopes=("*",)` and the `OPERATOR` role (`security/identity.py:127-145`) and is what
  gets attached in the `development`/`internal` profiles and in `release` for SDK/CLI callers
  presenting only the static API token (`api/dependencies/identity.py:52-55`). So the strongest
  entitlement check is currently a **no-op** on exactly the deployments and clients that do not
  present an identity key. Pinned as intended by
  `tests/security/test_identity_row_entitlement.py:93`
  (`test_legacy_public_token_retains_unfiltered_market_view`).

### 4.2 Declared-only / not wired

- **`require_entitlement` is dead code.** `api/dependencies/entitlement.py:18-98` implements a
  fail-closed source-system dependency (whitelist `:47-50`, denial audit `:101-118`). A repository-wide
  search finds only its own definition in `src/` plus one prose mention in
  `docs/engineering/UX01_EXECPLAN.md:541`. **No route declares it**, so it enforces nothing today.
- **`EntitlementScope.LICENSED` is declared but never produced.** `governance/entitlement.py:10-16`
  declares four scopes; `entitlement_scope_for_source` (`:60-74`) only returns `internal-research` or
  `unknown`.
- **`Permission.WRITE`** is declared (`security/permissions.py:24`) but used in no registry entry.
- **Redistribution and effective dates/expiry** (V2 doc 06 §5, doc 07 §2) have no implementation:
  `export_check` emits `no-redistribution` as a static label (`governance/entitlement.py:153`) and no
  expiry field is evaluated in `governance/` or `security/`. Certification records carry an optional
  `expires_at_utc` (`api/routes/public/source_operations.py:308`), which is source certification, not
  data entitlement.
- **Raw-vs-derived distinction** is not a first-class service; it is derived per call from
  `KNOWN_ENTITLED_SYSTEMS_V1` (`governance/entitlement.py:46-57`) and the registry's
  `licensed_data.export_allowed` flag (`security/research_entitlement.py:81-84`).
- **Calculation entitlement** is not gated per capability beyond the route category and the
  capability `entitlement_policy`; there is no `calculate` verb in the entitlement vocabulary
  (V2 doc 06 §5 lists `view / calculate / export / redistribute / external-LLM`).

### 4.3 Contract fixtures

`tests/contract/test_governance_foundation.py` pins the decision defaults: `:7-12` denied by default,
`:29-34` unknown source fails closed, `:65-71` unknown scope export denied, `:73-92` restriction and
public-clearance cases, `:145-151` `EntitlementScope` values.

## 5. Provider / source administration and credential handling

### 5.1 Backend ownership map

| Concern | Owning surface | Evidence |
|---|---|---|
| Provider connection registry (provider ids, whether a credential is required, public baseline providers) | `api/routes/public/credentials.py` | `credentials.py:13-27` (`ProviderId`), `:29-49` (`PUBLIC_PROVIDERS`, `PROVIDERS`) |
| Credentials (store, rotate, status, local validation, connection test, delete) | `api/routes/public/credentials.py` | `:95-112` upsert, `:115-132` rotate, `:135-182` status, `:185-252` local validation, `:255-310` connection test, `:398-441` delete |
| Source registry, source health/runs listing, ingestion runs | `api/routes/public/sources.py` | `:69-92` list/detail, `:92-104` `GET /api/ingestion-runs` |
| Ingestion / scheduler operations (run, backfill, retry, enable-disable) | `api/routes/public/source_operations.py` | `:117-138`, `:141-177`, `:180-212`, `:215-243`; service `src/eurogas_nexus/application/dataops_runtime.py:68` (`scan_scheduler`), `:245` (`request_operator_run`), `:278` (`set_source_enabled`), `:316` (`runtime_source_operations`) |
| Certification | `api/routes/public/source_operations.py` (public, operator) and `api/routes/internal/source_certification.py` (internal) | `source_operations.py:246-259` list, `:262-314` certify; `internal/source_certification.py:38-116` upsert |
| Runtime posture (DB, release metadata, dependency matrix, pipeline health, source-operations, metrics) | `api/routes/public/runtime.py` and `source_operations.py` | `runtime.py:10-11`, `:68-69`, `:116-117`, `:220-221`; `source_operations.py:317-330` (`/api/runtime/source-operations`), `:333+` (`/api/runtime/metrics`) |
| Audit | `api/routes/public/access.py` (public ADMIN) and `api/routes/internal/identity_admin.py` (internal) | `access.py:244-281` (`GET /api/audit`); `identity_admin.py:308-350` export, `:351-386` prune |
| Identity / API-key administration | `api/routes/public/access.py` (ADMIN) and `api/routes/internal/identity_admin.py` (internal operator) | `access.py:59-241`; `identity_admin.py:59-306` |
| Ingestion connectors / provider adapters | `src/eurogas_nexus/ingestion/` | `ingestion/connectors/base.py:12-24` (`ConnectorMetadata.credential_fields`), `:45-67` (`MockConnector` used when credentials are absent) |

### 5.2 Credentials are references/ciphertext, not values, in every read path

- Storage model: `ProviderCredentialRecord` stores `encrypted_payload`, `redacted_preview` and
  `credential_fingerprint` only (`src/eurogas_nexus/db/models/observation.py:250-274`); the docstring
  at `:251-255` states the plaintext is never persisted.
- Encryption: Fernet over sorted-key JSON (`security/credentials.py:43-67`), key derived from
  `EUROGAS_NEXUS_SECRET_KEY` (`:15`, `:132-143`); a missing key raises (`:134-135`) and the API maps
  that to 503 `credential_store_not_configured` (`api/routes/public/credentials.py:324-325`, `:501-508`).
- Redaction: `redact_secret_value` returns `first2***last2`, all-asterisks for ≤4 characters, or empty
  (`security/credentials.py:91-106`).
- Decryption happens only in backend paths that call the provider or validate the ciphertext:
  `security/provider_keys.py:6-26` (`load_provider_api_key`), consumed by
  `api/routes/public/monitoring.py:133`, `analysis.py:391`, `credentials.py:283` and
  `application/monitoring_service.py:67`, `:89`.

### 5.3 Can any API response return a plaintext provider credential? Evidence: no

- The status serialiser exposes no payload field, only `label`, `configured`, `status`,
  `redacted_preview`, `last_tested_*` (`credentials.py:478-490`); `list_credential_providers` uses the
  same serialiser (`credentials.py:86-92`, `:460-475`).
- The source-registry surface exposes only credential metadata (`api/routes/public/sources.py:748-769`)
  and a coarse state (`sources.py:410-417`).
- The envelope warns: "Credential values are write-only and never returned by the API"
  (`credentials.py:540`), and the connection test returns only status plus an error code (`:300-306`).
- Test evidence: `tests/security/test_provider_credentials_api.py:30-60` asserts `secret-value` is
  absent from the write response, the stored ciphertext, `redacted_preview` and the provider list.
- **Distinct exception, identity material only:** identity API-key creation returns a plaintext bearer
  exactly once (`api/routes/public/access.py:207-213`, internal equivalent
  `api/routes/internal/identity_admin.py:167`, `:219`). That is `nexus_<key_id>_<secret>`
  (`security/identity.py:148-159`); only its hash is stored (`identity.py:162-180`,
  `db/models/identity.py:69`). Not a provider credential, and never re-readable.

## 6. Client control-plane surfaces and the endpoints they call

All four surfaces are mounted as pages of the single "system" primary workspace alongside business pages:
`clients/web/src/app/navigation/productNavigation.ts:47-53` lists
`sources, runtime, research, agents, settings, manual, glossary, access`.

| Client surface | Backend endpoints called | Current classification per V2 doc 06 §8 |
|---|---|---|
| `clients/web/src/components/AccessCenter.tsx` | `GET /api/access/users`, `GET /api/access/api-keys`, `GET /api/audit`, `GET /api/access/sso`, `PATCH /api/access/users/{id}`, `POST /api/access/api-keys/{key_id}/revoke` (`AccessCenter.tsx:41-46`, `:49-70`; API wrappers `clients/web/src/api/client.ts:2137-2149`) | **Control plane.** It is a business-user page that renders users, roles, data scopes, API keys, audit rows and the SSO profile, and it is reachable from the normal workspace navigation. Client-side gating is `currentUser?.permissions.includes("identity.manage")` (`AccessCenter.tsx:33-39`, `:72-81`) — a UX guard only; the server enforces ADMIN (`security/permissions.py:54-61`, `access.py:40-56`). |
| `clients/web/src/components/SourceCenter.tsx` | `GET /api/sources`, `GET /api/credentials/providers`, `PUT /api/credentials/{provider_id}`, `POST /api/credentials/{provider_id}/connection-test`, plus the workspace `GET /api/sources` posture metadata (`client.ts:1846`, `:1895`, `:1897`, `:1904`; wired via `clients/web/src/app/hooks/useSourceCenterController.ts:42-79` and `useAppController.ts:54-59`) | **Mixed — REFACTOR target.** Provider credential entry and connection testing are control-plane (V2 doc 06 §8 "Provider Connections", "Credentials"); source posture, freshness, credential state and certification state are operator/business posture. It has no client call to run/backfill/retry/enable or certify. |
| `clients/web/src/components/RuntimeWorkspace.tsx` | `GET /api/runtime/db`, `GET /api/runtime/release`, `GET /api/runtime/dependencies`, `GET /api/runtime/pipeline-health`, plus workspace `GET /api/sources` (`client.ts:2065-2067`, `:1872`, `:1846`; props wired at `clients/web/src/app/workspaces/WorkspaceRenderer.tsx:199-211`) | **Control plane.** V2 doc 06 §8 gives the Control Plane "Pipelines", "Runtime" and "System Config". The workspace exposes release readiness, dependency health, scheduler state and source/certification blockers to any user who can open the page. |
| `clients/web/src/components/SettingsCenter.tsx` (the `settings` tab) | Consumes already-fetched `GET /api/credentials/providers`, `GET /api/runtime/db`, `GET /api/runtime/release` plus local release metadata (`SettingsCenter.tsx:69-73`, `:118-122`, `:174-183`, `:236-243`; props at `WorkspaceRenderer.tsx:214-226`) | **Mixed — REFACTOR target.** Release/version/about information is business-appropriate; the API-service and credential-status panels are control-plane provider administration presented as a settings page. |

Backend-only operator surfaces with **no client call today**: `POST /api/sources/{id}/run`,
`/backfill`, `/retry`, `PATCH /api/sources/{id}/enabled`,
`POST /api/source-certifications/{id}/certify`, `GET /api/source-certifications`,
`GET /api/ingestion-runs`, `GET /api/runtime/source-operations`, `GET /api/runtime/metrics`. A search
across `clients/web/src` returns no matches for these; they are exercised by
`tests/api/test_dataops_api.py:34-35`, `:46-161` and pinned at
`tests/contract/test_api_surface_stability.py:163-172`.

## 7. Does platform administration automatically imply commercial data access today?

Two different answers, and the distinction is currently unstable.
- **Capability-wise: yes.** `ROLE_PERMISSIONS[Role.ADMIN] = frozenset(set(Permission))`
  (`security/authorization.py:127`) grants ADMIN every fine-grained permission, including
  `market.read`, `portfolio.read`, `portfolio.write`, `strategy.*`, `optimization.run`,
  `analysis.query`, `agent.research` and `source.*`. `authorize()` returns `allowed=True` for any of
  them (`authorization.py:210-217`), and `role_allows()` for the route floor also admits ADMIN
  everywhere (`security/identity.py:116-124`). The admin console returns the effective permission list
  for any principal, including ADMIN (`application/enterprise_auth.py:453-486`; surfaced at
  `GET /api/me`, `api/routes/public/auth.py:300-314`).
- **Data-entitlement-wise: no, but only while `data_scopes` stays empty.** Commercial row access is
  decided by `principal_allows_source_family`, which reads `data_scopes` and never the role
  (`security/identity.py:227-245`). Principal creation defaults `data_scopes` to an empty list
  (`db/repositories/identity.py:78-82`), and OIDC JIT provisioning derives scopes from the group→scope
  map, not the role (`application/enterprise_auth.py:411-421`). A principal with `ADMIN` and no scopes
  therefore cannot read commercial families through the row filter.
- **Why the answer is unstable:** the same ADMIN surface can write `data_scopes` for any principal,
  including itself (`PATCH /api/access/users/{principal_id}`, `api/routes/public/access.py:79-128`) and
  can mint a new key for any principal (`POST /api/access/api-keys`, `access.py:181-218`); the
  `data_scopes` vocabulary shown there is a flat list including the wildcard (`access.py:144-153`).
  There is no separate approval, no separation of duties between "manage identity" and "grant
  commercial data", and no audit distinction beyond the generic `governance.access` event
  (`access.py:292-319`). V2 doc 06 §7 requires exactly that separation ("Commercial access is
  separately granted") — today it is separately *stored* but not separately *controlled*.

## 8. Does AI/agent invocation re-authorise against user authority?

**Partly: yes for the capability API and MCP; no for the direct backend LLM endpoints.**

- Re-authorisation exists and is shared. `CapabilityRuntime.invoke`
  (`application/agents/runtime.py:32-123`) rebuilds an `AuthenticatedPrincipal` from the invocation
  context and calls the same `authorize()` used by human handlers (`runtime.py:126-143`), then the
  same family entitlement check (`runtime.py:146-167`), before any handler executes. Non-ACTIVE,
  unknown-permission and unentitled cases return a blocked `CapabilityResult` (`runtime.py:71-86`);
  `HUMAN_ONLY` capabilities are never agent-invokable and `HUMAN_CONFIRMATION` capabilities require an
  explicit confirmation flag (`runtime.py:53-69`). The docstring names it the "Shared enforcement
  boundary for API, SDK, and MCP" (`runtime.py:26-27`).
- The API passes the real authenticated principal: `api/routes/public/agents.py:73-88` builds the
  `AgentInvocationContext` from `request.state.identity`. Research plans are validated against
  entitled families at `agents.py:295-300` and
  `application/agents/research_orchestrator.py:281-287`.
- MCP passes an **environment-configured pseudo-principal, not a user**: `_agent_context()`
  (`src/eurogas_nexus/mcp/server.py:549-564`) reads `EUROGAS_NEXUS_AGENT_ROLE` (default `ANALYST`),
  `EUROGAS_NEXUS_AGENT_PRINCIPAL` (default `service:mcp`) and `EUROGAS_NEXUS_AGENT_DATA_SCOPES`
  (default `*`). Registry capability tools invoke through `CapabilityRuntime`
  (`mcp/server.py:567-590`), so permission and entitlement are re-checked — against that service
  identity, not the calling user. The legacy read/sandbox MCP tools bypass the runtime and call the
  SDK directly (`mcp/server.py:60-271`), inheriting only the API token and principal the SDK sends.
- With no identity attached (development/internal profiles), the agent API substitutes a synthetic
  `ANALYST` with `data_scopes=["*"]` (`api/routes/public/agents.py:74-81`) — a broad default rather
  than a denial.
- **Direct LLM endpoints do not re-authorise against user authority at all.** `POST
  /api/monitoring/alerts/{alert_id}/analysis` (`api/routes/public/monitoring.py:118-155`) loads the
  backend provider key (`monitoring.py:133`) and invokes the provider with no principal, no scope and
  no entitlement check; its route permission is the read family (`security/permissions.py:83`,
  `/api/monitoring/` → `READ`). Likewise `analysis.py:391` loads the provider key inside
  `_maybe_invoke_provider`; there the derived-access gate applies only when the caller sets
  `invoke_provider=true` (`analysis.py:67-74`) and the profile switch is the second control
  (`core/config.py:127-135`). So for AI use, entitlement is enforced on *payload composition*, not on
  a per-user AI capability grant.
- The documented intent matches the implemented capability path and overstates MCP:
  `docs/agents/SECURITY_AND_ENTITLEMENT.md:1-11` states the agent inherits the normal authenticated
  principal and that `CapabilityRuntime` checks permission before every handler "including MCP" —
  true for registry-backed MCP tools, false for the legacy read/sandbox tools and for the two direct
  LLM routes above.

## 9. Current-to-target mapping

| Target area | Current implementation | Decision | Target note |
|---|---|---|---|
| Capability model | Two parallel vocabularies: 7 route categories (`security/permissions.py:17-26`) and 29 dotted fine-grained permissions (`security/authorization.py:21-52`); roles are rank bundles (`security/identity.py:50-56`) | **EVOLVE** | V2 doc 06 §3 capabilities (`market.read`, `portfolio.read`, `scenario.run`, `provider.credential.manage`, `access.manage`, …) already share the dotted naming style of `authorization.py`; extend that vocabulary rather than invent a third one. `backtest.run`, `dataset.build`, `dataset.export`, `provider.connection.view` are currently only route categories. |
| Scope | Flat `data_scopes` source-family strings on the principal (`security/identity.py:80`, `db/models/identity.py:38`); baseline set is implicit (`identity.py:21-29`) | **EVOLVE** | Add organisation/portfolio/market/region dimensions per V2 doc 06 §4; today they are absent, and the baseline/commercial family sets are declared in two places with two casings (`identity.py:21-29` vs `domain/dataops/entitlement.py:23-33`). |
| Entitlement service | Fail-closed decision shells (`governance/entitlement.py`), a dead dependency (`api/dependencies/entitlement.py:18-98`), row filtering and derived gating that no-op for the legacy principal (`domain/dataops/entitlement.py:77-78`, `:102-103`) | **REFACTOR** | V2 doc 07 §2 requires a first-class entitlement service covering view/calculate/export/redistribute/external-LLM. Consolidate the four current decision points (`governance`, `domain/dataops`, `security/research_entitlement`, `api/dependencies/entitlement`) behind one service and remove the legacy bypass. |
| Provider connection | Backend-owned provider registry, credential store and connection tests (`api/routes/public/credentials.py`) | **KEEP** | V2 doc 07 §2 "Provider Connection" (endpoint, credential reference, quota, health, scheduler, ingestion, certification): endpoint/credential/health/ingestion/certification exist; **quota is not modelled** anywhere in `credentials.py` or `sources.py`. |
| Control plane | Administration exists as pages inside the business workspace (`productNavigation.ts:47-53`) with an ADMIN role and a UX-only client guard (`AccessCenter.tsx:33-39`) | **REFACTOR** | V2 doc 06 §8 requires a distinct product surface and "normal business users should not navigate through these controls" (`06_IDENTITY_ACCESS_CONTROL_PLANE.md:116`). |
| Audit | `AuditEventRecord` plus targeted writers: credential upsert/delete (`credentials.py:354-366`, `:426-437`), access administration (`access.py:292-319`), entitlement/identity denials (`api/dependencies/entitlement.py:101-118`, `api/dependencies/identity.py:220-237`), operator source actions (`source_operations.py:429+`) | **EVOLVE** | Audit writes are best-effort and swallow exceptions (`access.py:318-319`, `identity.py:236-237`, `entitlement.py:117-118`), and several of them are unreachable because the entitlement dependency is unused. V2 target needs audit for capability grants, scope changes, entitlement decisions and AI invocations. |
| Secret handling | Fernet-encrypted provider payloads with redaction and fingerprint (`security/credentials.py:43-119`), write-only API surface (`credentials.py:478-490`, `:540`), identity keys hashed (`db/models/identity.py:69`) | **KEEP** | No plaintext provider credential is returnable by any endpoint (§5.3). Identity-key one-time reveal (`access.py:207-213`) is deliberate; keep it but treat it as control-plane-only output. |
| AI re-authorisation | `CapabilityRuntime` re-authorises permission and entitlement for API and registry-backed MCP (`application/agents/runtime.py:32-167`); MCP uses an env pseudo-principal (`mcp/server.py:549-564`); direct LLM routes do not re-authorise (`monitoring.py:118-155`) | **EVOLVE / ADD** | V2 doc 06 §9 requires every API call to be re-authorised server-side. Extend re-authorisation to the direct LLM routes and bind MCP to a real user identity. |

Items explicitly deferred: object storage and the Data Product semantic layer (V2 doc 07 §§1, 5) — **DEFER**, no inspected backend surface implements either; and a separate Control Plane deployment topology — **DEFER** until the surface split above lands.

## 10. Coverage limits, unresolved questions and follow-up tasks

### 10.1 What was inspected

Read in full: `api/app.py`, `api/route_profiles.py`, `api/route_registration.py`,
`api/function_catalog.py`, `api/dependencies/{identity,public_auth,route_permission,entitlement,row_entitlement}.py`,
`api/routes/public/{credentials,access,agents}.py`,
`security/{permissions,identity,authorization,credentials,provider_keys,research_entitlement,internal_api}.py`,
`governance/entitlement.py`, `domain/dataops/entitlement.py`, `domain/agents/contracts.py`,
`application/agents/runtime.py`, `mcp/server.py`, `db/models/observation.py:248-274`, and the four
named client components. Read partially: `api/routes/public/analysis.py:40-179` (of 863),
`monitoring.py:118-167`, `source_operations.py:100-339` (of 435), `sources.py:405-432`, `:744-803`
(of 855), `internal/identity_admin.py:1-60`, `auth.py:280-359`,
`application/enterprise_auth.py:400-511`, `db/repositories/identity.py:40-149`,
`core/config.py:100-169`, `security/oidc.py` (symbol index only).

Client line references reflect the working tree at inventory time. `clients/web/src/api/client.ts` and
`clients/web/src/app/workspaces/WorkspaceRenderer.tsx` were edited by another workstream during this
task, so their line numbers may drift; the four named components were unmodified.

### 10.2 Not inspected

- Route handlers not read: `api/routes/public/optimization.py` (52 KB), `route_cost.py` (36 KB),
  `strategy_registry.py` (31 KB), `research_data.py` (26 KB), `research.py`, `review.py`, `shadow.py`,
  `streaming.py`, `strategy_lab.py`, `contracts.py`, `cost_observations.py`, `glossary.py`,
  `health.py`, `lng.py`, `market.py`, `physical.py`, `portfolio.py`, `reference_network.py`,
  `runtime.py`, `storage.py`, `weather.py`, `api/routes/dev/*`,
  `api/routes/internal/{health,portfolio_import,shadow}.py`. Claims about these are limited to their
  registry declarations, OpenAPI presence and the `filter_rows` call sites found by search.
- Packages not inspected: `optimization/`, `release/`, `runtime_store/`, `streaming/`, `data_quality/`,
  `cli/`, `application/` beyond the files listed, `domain/` beyond the surfaces touched here, `db/`
  beyond two files, `ingestion/` beyond `connectors/base.py`.
- Consumers not inspected: `packages/python-sdk/`, `apps/`, `clients/desktop/` (Tauri shell),
  `alembic/`, `deploy/`, `infra/`, `scripts/`, `.github/workflows/`.
- Tests: only the task-named files plus `tests/security/{test_permissions_registry,test_provider_credentials_api,test_llm_provider_gate,test_dataops_entitlement_api,test_identity_row_entitlement,test_row_entitlement_scope}.py`
  and `tests/contract/test_api_surface_stability.py:130-209`. `tests/{uat,evals,integration,workflow}/`
  were not inspected.

### 10.3 Unresolved questions

1. Is the legacy-principal entitlement bypass (`domain/dataops/entitlement.py:77-78`, `:102-103`)
   acceptable in `release` where SDK/CLI callers present only the static API token, or must those
   callers migrate to identity keys first? It is pinned as intended (`tests/security/test_identity_row_entitlement.py:93`),
   so changing it is a contract decision.
2. Should the unwired `require_entitlement` be deleted (documentation-only) or wired into governed
   routes? `docs/engineering/UX01_EXECPLAN.md:541` describes it as existing behaviour, which is
   inaccurate today.
3. Should `PERMISSION_ENFORCEMENT` (`security/permissions.py:176-183`) reflect the enforcement now in
   `api/dependencies/route_permission.py:75-102`, given
   `tests/security/test_permissions_registry.py:74-80` pins the stale values?
4. Is the case-sensitivity asymmetry between baseline (`security/identity.py:242`, exact) and
   commercial (`identity.py:244`, case-folded) families intended?
5. Should `REVIEWER` be creatable via `POST /api/internal/identities` (`api/routes/internal/identity_admin.py:25` excludes it), and should `ROLE_RANK` (ANALYST above REVIEWER, `security/identity.py:50-56`) be reconciled with the "least-privilege ordered" docstring?
6. Does V2 intend MCP to carry a real user identity, or is the environment service principal (`mcp/server.py:549-564`) accepted? `docs/agents/SECURITY_AND_ENTITLEMENT.md:3` claims the former.
7. Where does the boundary sit between "platform administration" and "commercial data grant" once a control plane exists? One ADMIN permission pair covers both today (`security/authorization.py:44-45`, `api/routes/public/access.py:63`, `:84`).

### 10.4 Follow-up tasks (proposed, not performed)

- Decide the fate of `require_entitlement` and reconcile `PERMISSION_ENFORCEMENT` (questions 2, 3).
- Define the single entitlement service boundary and its deprecated wrappers before any capability-model change lands.
- Specify the control-plane surface split from the §6 classification before REFACTOR work on `SourceCenter`/`SettingsCenter`.
- Specify how AI routes obtain user authority (`monitoring.py:118-155`, `analysis.py:391`) and whether MCP gains a user identity.
- Inventory the consumers relying on the legacy-principal unfiltered view (SDK, CLI, Tauri) before the bypass is removed.
