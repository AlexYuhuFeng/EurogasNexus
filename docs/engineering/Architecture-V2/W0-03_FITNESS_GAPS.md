# W0-03 Fitness Gaps — architecture fitness functions and fitness-gap inventory

Task ID: W0-03 (part 1)
Status: COMPLETE for the two declared deliverables
Authority: `docs/engineering/Architecture-V2/10_DOCUMENTATION_NFR_TESTING.md` section 7
(“Architecture fitness functions”), `docs/engineering/Architecture-V2/14_VALIDATION_PACK.md`
section A, `docs/engineering/Architecture-V2/12_MIGRATION_ROADMAP.md` Wave 0
(“architecture fitness tests”), `docs/engineering/Architecture-V2/18_DEEPSEEK_WORKER_PROTOCOL.md`.

Deliverables of this task:

- `tests/contract/test_architecture_v2_fitness.py` — static fitness tests (pytest + standard
  library only; no `fastapi`, no `pydantic`, no `sqlalchemy`, no import of anything under `src/`).
- this document — the fitness-gap inventory.

No existing file was modified by this task. The only new files are the two above.

## 1. How to read the table

“Current coverage” names an existing test that already guards the invariant, or `none`.
“Decision” is one of:

- `IMPLEMENTED IN THIS TASK` — the invariant genuinely holds at the inspected revision and a
  static check now asserts it.
- `ALREADY COVERED` — an existing test already guards it; it is cited, not duplicated.
- `OPEN GAP` — the invariant does not hold (or cannot be asserted today); the gap is recorded
  here with evidence and remediation instead of being written as a failing test.

## 2. The ten fitness functions

| # | Fitness function | V2 source | Current coverage | Decision | Evidence (path:line) | Remediation for gaps |
| --- | --- | --- | --- | --- | --- | --- |
| FF1 | Clients cannot import backend internals | `10_DOCUMENTATION_NFR_TESTING.md` §7 bullet 1 | `none` for this direction; adjacent: `tests/contract/test_import_boundaries.py:9` (domain ↛ fastapi), `tests/contract/test_client_release_surface.py:184` (Web client holds no DB URL) | IMPLEMENTED IN THIS TASK | `tests/contract/test_architecture_v2_fitness.py` (client scope = 146 authored files: `clients/web/src`, `clients/web/tests`, `clients/desktop/src-tauri/src`, `clients/desktop/src-tauri/capabilities`, both `package.json`, `clients/web/index.html`, `clients/web/vite.config.ts`, `clients/desktop/src-tauri/tauri.conf.json`, `clients/desktop/src-tauri/Cargo.toml`); zero case-sensitive occurrences of `eurogas_nexus`, `eurogas_nexus_sdk`, `eurogas-nexus-sdk`, `packages/python-sdk`, `src/eurogas_nexus`; client base URL `clients/web/src/api/client.ts:5`-`:6` (`/api` for the browser, `http://127.0.0.1:8000/api` for the desktop host) | none — see §6 limits |
| FF2 | Client cannot call provider/vendor APIs directly | `10_DOCUMENTATION_NFR_TESTING.md` §7 bullet 2 | `none` before this task | IMPLEMENTED IN THIS TASK + OPEN GAP FF2-G1 | vendor hosts are anchored in repository evidence: `scripts/ops/ingest_public_sources.py:76` (`www.ecb.europa.eu`), `:77`-`:80` (`transparency.entsog.eu`), `:82`-`:83` (`agsi.gie.eu`, `alsi.gie.eu`); `src/eurogas_nexus/llm/deepseek.py:10` (`api.deepseek.com`); `src/eurogas_nexus/domain/route_cost/european_public_tariffs.py:24` (`bblcompany.com`), `:26` (`fluxys.com`); `src/eurogas_nexus/domain/route_cost/uk_rules.py:4` (`gasgovernance.co.uk`); `docs/ontology/europe-natural-gas.md:525`-`:529` (`eex.com`, `theice.com`); `docs/product/INDUSTRY_BENCHMARK.md:9`-`:40` (`trayport.com`, `kpler.com`, `argusmedia.com`); zero occurrences of any such host in the asserted client scope (146 files) and in an exploratory scan of all 168 text files under `clients/` excluding generated trees and lock files | FF2-G1 (CSP `connect-src` breadth) |
| FF3 | Every public API route has an access/permission declaration | `10_DOCUMENTATION_NFR_TESTING.md` §7 bullet 3 | ALREADY COVERED: `tests/security/test_permissions_registry.py:13`; registry assertions also in `tests/api/test_agents_api.py:101`, `tests/api/test_dataops_api.py:34`, `tests/api/test_research_data_api.py:208`, `tests/security/test_operator_principal_gate.py:13` | IMPLEMENTED IN THIS TASK (static) + ALREADY COVERED + OPEN GAP FF3-G1, FF3-G2 | registry `src/eurogas_nexus/security/permissions.py:38` (118 patterns), `:172` (method-scoped override), `:176` (enforcement status), `:188` (role floors), `:198` (resolver); dependency `src/eurogas_nexus/api/dependencies/route_permission.py:28` and `:52` (`permission_not_declared`); wiring `src/eurogas_nexus/api/app.py:24`-`:32`; profiles `src/eurogas_nexus/api/route_profiles.py:28`-`:47`; static check resolves all 171 route decorators under `src/eurogas_nexus/api/routes/public` against the registry with 0 unmatched | FF3-G1, FF3-G2 |
| FF4 | No plaintext credential response | `10_DOCUMENTATION_NFR_TESTING.md` §7 bullet 4 | ALREADY COVERED: `tests/security/test_provider_credentials_api.py:30` (encrypted + redacted), `:98` (rotate/disable/local-validation write-only); one-time plaintext key issuance is intentional in `tests/security/test_identity_model.py:37` | IMPLEMENTED IN THIS TASK (static) + ALREADY COVERED | `src/eurogas_nexus/api/routes/public/credentials.py:460`-`:475` (`_provider_status`), `:478`-`:490` (`_credential_status`), `:332` (write path encrypts `{"api_key": ...}`), `:540` (envelope warning “credential values are write-only”); static check proves the response builders expose only metadata keys and never `encrypted_payload`/`credential_fingerprint` | FF4-G1 (repo-wide secret-in-response check absent) |
| FF5 | No critical business calculations in React | `10_DOCUMENTATION_NFR_TESTING.md` §7 bullet 5 | adjacent only: `tests/contract/test_client_release_surface.py::test_web_client_resource_pool_options_are_backend_owned` (`:1523`), `tests/contract/test_workspace_derived_data_contract.py:19` (display-only derived helpers) | IMPLEMENTED IN THIS TASK + OPEN GAP FF5-G1 | declared Web dependencies `clients/web/package.json:12`-`:20`; every external import specifier in `clients/web/src` resolves to a declared dependency (`@tauri-apps/api`, `i18next`, `maplibre-gl`, `react`, `react-dom`, `react-i18next`, `zustand`) and none is a solver/numeric package; compute is requested from the backend: `clients/web/src/api/client.ts:1940` (`/route-cost/recommend`), `:1943` (`/route-cost/resource-pool/optimize`), `:1946` (`/strategy-lab/evaluate`), `:2018` (`/backtest-experiments`), `:2125` (`/research/netback`); no client file stem matches an optimiser/solver/engine/backtest-engine pattern | FF5-G1 (client-side indicative arithmetic) |
| FF6 | Tauri commands stay within HostCapabilities | `10_DOCUMENTATION_NFR_TESTING.md` §7 bullet 6; `14_VALIDATION_PACK.md` §E; `12_MIGRATION_ROADMAP.md` Wave 1 | partial: `tests/contract/test_client_release_surface.py:103` (capability ACL is exactly `core:default`), `:76` (host window/splash behaviour) | IMPLEMENTED IN THIS TASK + OPEN GAP FF6-G1 (partially closed by Wave 1) | host declarations `clients/desktop/src-tauri/src/main.rs:50`, `:82`, `:101`, `:108`, `:125`; registration `:214`-`:220`; client-side allowlist `clients/web/src/app/host/hostCapabilities.ts` (`HOST_COMMANDS`, delivered and documented as [W1-04](W1-04_HOST_CAPABILITIES_CONTRACT.md)); capability file `clients/desktop/src-tauri/capabilities/default.json:6`; static check proves declared == registered == allowlist == the five commands the Web workspace can invoke | FF6-G1 (capability ACL still does not mirror the per-command class) |
| FF7 | Module dependency direction (api → application/domain → db/infrastructure, never the reverse) | `10_DOCUMENTATION_NFR_TESTING.md` §7 bullet 7 | partial: `tests/contract/test_import_boundaries.py:9` (domain ↛ fastapi), `:21` (SDK/CLI ↛ domain) | IMPLEMENTED IN THIS TASK (restricted) + OPEN GAP FF7-G1 … FF7-G4 | rules that hold: `domain` imports neither `eurogas_nexus.api` nor `eurogas_nexus.application`; `db` imports neither `api` nor `application`; `security` does not import `api`; `optimization` imports no other package at all; reverse `api` importers outside `src/eurogas_nexus/api` are frozen to two modules (see FF7-G1) | FF7-G1 … FF7-G4 |
| FF8 | Version/config consistency | `10_DOCUMENTATION_NFR_TESTING.md` §7 bullet 8 | ALREADY COVERED: `tests/contract/test_client_release_surface.py:27` (`test_release_versions_are_aligned`: `pyproject.toml`, `clients/desktop/src-tauri/Cargo.toml`, `clients/desktop/src-tauri/tauri.conf.json`, `clients/web/package.json`, `clients/desktop/package.json` all `0.5.0`); adjacent `tests/release/test_release_engineering.py:51`, `tests/contract/test_docs_alignment.py:143` | ALREADY COVERED — not duplicated | `tests/contract/test_client_release_surface.py:40`-`:46` | none |
| FF9 | ExperienceProfile cannot grant capability | `10_DOCUMENTATION_NFR_TESTING.md` §7 bullet 9; `06_IDENTITY_ACCESS_CONTROL_PLANE.md:118`; `12_MIGRATION_ROADMAP.md` Wave 2 | `none` | OPEN GAP | no `ExperienceProfile`, `FunctionalAssignment` or `WorkMode` token exists anywhere under `src/`; access is the fixed role model `src/eurogas_nexus/security/authorization.py:21` (`Permission`), `:55` (`ROLE_PERMISSIONS`), `:127` (`Role.ADMIN` = every permission), `:164` (`authorize`); the client navigation is the fixed five-primary model `clients/web/src/app/navigation/productNavigation.ts:18`-`:54` | FF9-G1 |
| FF10 | AI/agent invocation rechecks authority | `10_DOCUMENTATION_NFR_TESTING.md` §7 bullet 10; `14_VALIDATION_PACK.md` §C (“AI invocation re-authorises”) | ALREADY COVERED (behavioural): `tests/security/test_llm_provider_gate.py:64` (provider blocked by profile), `:87` (entitlement blocks unlicensed snapshot), `:139` (release API reports provider disabled); capability entitlement `tests/unit/test_agent_capability_runtime.py:127`, `:384`, `:416`; agent route permissions `tests/api/test_agents_api.py:101` | IMPLEMENTED IN THIS TASK (static fail-closed ordering) + ALREADY COVERED | `src/eurogas_nexus/api/routes/public/analysis.py:364` (caller opt-in), `:369` (profile gate), `:373` (snapshot entitlement re-check), `:391` (credential load), `:422` (provider call); per-request re-authorisation `src/eurogas_nexus/api/app.py:24`-`:32` | none required; residual limits in §6 |

## 3. Open gaps

### FF2-G1 — desktop CSP does not bound outbound origins

- Evidence: `clients/desktop/src-tauri/tauri.conf.json:40` sets
  `connect-src 'self' http://localhost:* http://127.0.0.1:* https:`.
- Effect: vendor-endpoint absence is guaranteed by literal absence in client source and by the
  absence of client-side credentials — not by an origin policy. Any `https:` host is reachable
  from the WebView.
- Remediation: replace the `https:` catch-all with the configured backend origin plus the map-tile
  hosts already listed in `img-src`, generated from deployment configuration rather than hardcoded.

### FF3-G1 — `/api/internal/*` is outside the permission registry

- Evidence: the registry `src/eurogas_nexus/security/permissions.py:38`-`:167` declares no
  `/api/internal/...` path; the internal router mounts nine operations under
  `src/eurogas_nexus/api/routes/internal/router.py:13`; three modules enforce the internal token
  in-handler (`src/eurogas_nexus/api/routes/internal/identity_admin.py:48`,
  `src/eurogas_nexus/api/routes/internal/portfolio_import.py:29`,
  `src/eurogas_nexus/api/routes/internal/source_certification.py:55`), while
  `src/eurogas_nexus/api/routes/internal/health.py:8` and
  `src/eurogas_nexus/api/routes/internal/shadow.py:10` declare no access requirement at all.
- Effect: “every public route has an access declaration” holds for the public surface (171 route
  decorators verified), but not for the internal surface, and the existing registry test
  `tests/security/test_permissions_registry.py:13` cannot see it because the default application
  does not mount the internal router.
- Remediation: register internal paths in the permission registry (or give the internal router its
  own declared access table), make it a dependency rather than per-handler code, and extend the
  registry coverage test to the internal profile.

### FF3-G2 — the registry is only enforced in the release profile

- Evidence: `src/eurogas_nexus/api/app.py:24`-`:32` attaches `require_public_api_auth`,
  `require_identity` and `require_route_permission` only when `route_profile.require_auth` is true;
  only the RELEASE profile sets `require_auth=True`
  (`src/eurogas_nexus/api/route_profiles.py:41`-`:47`). The INTERNAL profile has
  `include_internal=True` with `require_auth` defaulting to `False`
  (`src/eurogas_nexus/api/route_profiles.py:35`-`:40`), so no profile both mounts the internal
  routes and enforces the registry.
- Effect: in development and internal profiles the registry is documentation, not enforcement;
  `permission_not_declared` (`src/eurogas_nexus/api/dependencies/route_permission.py:52`) can only
  fire in the release profile.
- Remediation: attach the route-permission dependency to the routers instead of the application
  (or attach it in every profile with PUBLIC as the explicit default), so an undeclared path fails
  closed regardless of profile.

### FF4-G1 — no repo-wide secret-in-response check

- Evidence: the static check added here covers only
  `src/eurogas_nexus/api/routes/public/credentials.py`; the runtime guard is
  `tests/security/test_provider_credentials_api.py:30`. No test asserts that other route modules
  (runtime, diagnostics, release metadata, admin) never return a stored secret value.
- Remediation: add one shared assertion over the route package — no response builder may read a
  field whose name matches a secret pattern (`api_key`, `token`, `password`, `secret`,
  `encrypted_payload`, `fingerprint`) — and keep the credential module as the only module allowed
  to name the plaintext field inside the encryptor call.

### FF5-G1 — the React client performs indicative arithmetic for display

- Evidence: `clients/web/src/app/model/usePortfolioDecisionModel.ts:130`-`:136` derives
  `rawDecisionPnl` from `netback * allocated_mwh_per_day` when the backend pool result is absent;
  `clients/web/src/app/resourcePoolMapPaths.ts:189`-`:195` derives
  `indicativeNetMarginGbpMwh = sale_price − (contract_cost + variable_cost + tolerance_risk +
  route_cost)` for map labels. Both prefer the backend-supplied value
  (`total_net_pnl_gbp_per_day` at `:131`, `net_margin_gbp_mwh` at
  `clients/web/src/app/resourcePoolMapPaths.ts:208`) and neither implements an optimiser, PnL
  engine or backtest engine.
- Effect: no critical engine lives in React, but two margin/PnL numbers can be produced client-side,
  which is exactly the class of drift the fitness function is meant to prevent.
- Remediation: once the backend always returns the field for these views, delete the local
  formulas (fail closed to “unavailable” instead), or label them as client-derived estimates and
  pin them with a client test comparing the derived value against the backend value.

### FF6-G1 — the native command surface is bounded, but the Tauri ACL does not mirror it

- Evidence: the host registers five commands
  (`clients/desktop/src-tauri/src/main.rs:214`-`:220`); the Web workspace declares the same five
  in `clients/web/src/app/host/hostCapabilities.ts` (`HOST_COMMANDS`) and, since Wave 1, classifies
  each one with a capability class in the same module (`HOST_COMMAND_CAPABILITIES`:
  `read_deployment_config` → `deploymentConfig`, `notify_client_ready` → `notifications`,
  `clear_client_session_data` → `secureStorage`, `start_loopback_auth` and
  `open_browser_login_and_wait` → `oidcLoopbackAuth`); capability membership on the host side is
  still expressed only by `clients/desktop/src-tauri/capabilities/default.json:6` (`core:default`).
- Effect: FF6 is asserted as a bounded allowlist plus a client-declared capability class. The Tauri
  capability ACL does not yet mirror the per-command class, and the Python fitness check asserts the
  allowlist rather than the mapping; the mapping is asserted by
  `clients/web/tests/experienceArchitecture.test.ts`.
- Remediation (remaining): generate the Tauri capability ACL from the declared classes so a new
  `#[tauri::command]` cannot be added without a host-side capability grant, and assert the mapping
  from the Python fitness check as well.

### FF7-G1 — `application` imports `api` (reverse edge)

- Evidence: `src/eurogas_nexus/application/agents/research_handlers.py:184` imports
  `eurogas_nexus.api.routes.public.research_data`;
  `src/eurogas_nexus/application/dataops_observability.py:108` imports
  `eurogas_nexus.api.middleware.observability`.
- Effect: an application module depends on a transport module; the target direction is
  api → application, never the reverse.
- Remediation: move `http_metric_lines` into an application/observability owner and pass the series
  into the route; have the research handler depend on an application-level service instead of the
  route module’s helper. Both modules are frozen as the only permitted exceptions in
  `tests/contract/test_architecture_v2_fitness.py`, so a new reverse edge fails immediately.

### FF7-G2 — `domain` imports `db`

- Evidence: `src/eurogas_nexus/domain/strategy_lab/run_orchestration.py:20` imports
  `eurogas_nexus.db.models` and `:326` imports `eurogas_nexus.db.repositories`.
- Effect: a domain module reaches into persistence; the rest of `domain` respects the direction.
- Remediation: move run orchestration into `application` or pass a repository port (protocol) into
  the domain function, then assert `domain ↛ db` in the fitness test.

### FF7-G3 — `db` imports `domain` and `security`

- Evidence: 35 import statements in 16 repository modules import `eurogas_nexus.domain.*`
  (for example `src/eurogas_nexus/db/repositories/agents.py:28`,
  `src/eurogas_nexus/db/repositories/market_intelligence.py:20`,
  `src/eurogas_nexus/db/repositories/identity.py:13`); `src/eurogas_nexus/security/provider_keys.py:14`
  and `:15` import `eurogas_nexus.db.models` / `eurogas_nexus.db.session`, forming a
  `db ↔ security` cycle.
- Effect: the persistence layer is not a one-way adapter today; the declared direction
  “domain → db/infrastructure” is inverted in the repository layer.
- Remediation: accept and document `db/repositories` as an adapter layer allowed to depend on
  domain contracts (an explicit constitution exception, not an accident), and break the
  `db ↔ security` cycle by moving provider-key cryptography and key storage access into a port the
  repository implements.

### FF7-G4 — no enforced direction rule for the remaining packages

- Evidence: `ingestion` imports `db` and `domain` (`src/eurogas_nexus/ingestion/simulated_market_prices.py`),
  `release` imports `domain` (`src/eurogas_nexus/release/constants.py`), `mcp` imports
  `application` and `domain` (`src/eurogas_nexus/mcp/server.py`), `security` imports `governance`
  (`src/eurogas_nexus/security/research_entitlement.py`), and `api` imports eight packages
  (`application`, `core`, `db`, `domain`, `governance`, `llm`, `optimization`, `release`,
  `security`).
- Effect: only the four rules in the fitness test are machine-checked; the wider graph is not.
- Remediation: after FF7-G1 … FF7-G3 are resolved, extend `FORBIDDEN_LAYER_IMPORTS` in
  `tests/contract/test_architecture_v2_fitness.py` to the remaining packages and record each new
  exception deliberately.

### FF9-G1 — no ExperienceProfile contract exists

- Evidence: no `ExperienceProfile`, `experience_profile`, `FunctionalAssignment`,
  `functional_assignment`, `WorkMode` or `work_mode` token exists anywhere under `src/`
  (repository-wide search); access control is the fixed role model in
  `src/eurogas_nexus/security/authorization.py:21`, `:55`, `:127`, `:164`; client navigation is
  the fixed five-primary model in `clients/web/src/app/navigation/productNavigation.ts:18`-`:54`.
  The contract exists only as target text: `docs/engineering/Architecture-V2/06_IDENTITY_ACCESS_CONTROL_PLANE.md:118`-`:133`
  and `docs/engineering/Architecture-V2/12_MIGRATION_ROADMAP.md:41`-`:48` (Wave 2).
- Effect: FF9 cannot be asserted today; “a work mode or profile never grants capability” has no
  contract to test.
- Remediation: Wave 2 — define the backend ExperienceProfile response contract, derive
  `effective_capabilities` strictly from the role/permission model, and add a negative test that a
  profile (or work mode) can only narrow, never widen, the role-derived permission set. It is
  asserted in `AGENTS.md` rule 7 (“Work mode/persona never grants backend authority”).

## 4. Checks implemented in this task

All static; each asserts a fact verified at the inspected revision.

| Test | Fitness function |
| --- | --- |
| `test_clients_do_not_import_backend_internals` | FF1 |
| `test_vendor_endpoint_list_is_anchored_in_repository_evidence` (13 parametrised hosts) | FF2 support |
| `test_clients_do_not_reference_vendor_endpoints` | FF2 |
| `test_client_dependencies_carry_no_vendor_integration` | FF2 |
| `test_every_public_route_has_a_declared_permission` | FF3 |
| `test_release_profile_wires_route_permission_enforcement` | FF3 |
| `test_credential_responses_never_expose_plaintext_secret_fields` | FF4 |
| `test_react_client_declares_no_compute_engine_dependency` | FF5 |
| `test_react_client_imports_only_declared_dependencies` | FF5 |
| `test_business_compute_stays_behind_backend_endpoints` | FF5 |
| `test_tauri_commands_match_the_bounded_host_allowlist` | FF6 |
| `test_web_client_invokes_only_allowlisted_host_commands` | FF6 |
| `test_backend_packages_respect_forbidden_import_directions` | FF7 |
| `test_api_layer_imports_are_limited_to_documented_exceptions` | FF7 |
| `test_ai_provider_invocation_rechecks_authority_before_calling_provider` | FF10 |
| `test_fitness_gap_inventory_covers_every_fitness_function` | this document |

No test asserts FF8 (already covered elsewhere) or FF9 (no contract exists yet).

## 5. Tests run

Every result below is the observed output, not an expectation.

| Command | Result |
| --- | --- |
| `python -m pytest tests/contract/test_markdown_links.py tests/contract/test_import_boundaries.py tests/contract/test_web_client_structure.py -q -p no:cacheprovider` — run **before** this task’s files existed | `8 passed` in 0.30 s |
| `python -m pytest tests/contract/test_architecture_v2_fitness.py -q -p no:cacheprovider` | `28 passed` in 1.70 s |
| `python -m pytest tests/contract/test_markdown_links.py tests/contract/test_import_boundaries.py tests/contract/test_web_client_structure.py -q -p no:cacheprovider` — intermediate run, while another worker’s new document had broken links | `1 failed, 7 passed` in 0.38 s |
| `python -m pytest tests/contract/test_markdown_links.py tests/contract/test_import_boundaries.py tests/contract/test_web_client_structure.py -q -p no:cacheprovider` — final run, after that worker repaired the links | `8 passed` in 0.32 s |
| `python -m pytest tests/security/test_permissions_registry.py tests/security/test_provider_credentials_api.py tests/security/test_llm_provider_gate.py -q -p no:cacheprovider` (citation confirmation for FF3, FF4, FF10) | `28 passed`, 2 third-party deprecation warnings, in 5.77 s |
| `python -m pytest tests/contract/test_client_release_surface.py -q -p no:cacheprovider` (citation confirmation for FF6 and FF8) | mid-task: `1 failed, 30 passed` in 1.26 s; final re-run after the other worker repaired that test: `31 passed` in 1.05 s |
| `python -m pytest tests/contract/test_client_release_surface.py::test_release_versions_are_aligned tests/contract/test_client_release_surface.py::test_windows_client_has_minimal_safe_permissions tests/contract/test_client_release_surface.py::test_web_client_uses_api_only_and_supports_mandarin_theme tests/contract/test_workspace_derived_data_contract.py -q -p no:cacheprovider` | `1 failed, 4 passed` in 0.18 s (same mid-task failure) |
| `python -m pytest tests/contract/test_client_release_surface.py::test_release_versions_are_aligned tests/contract/test_client_release_surface.py::test_windows_client_has_minimal_safe_permissions -q -p no:cacheprovider` — final, for the FF6 and FF8 citations | `2 passed` in 0.04 s |
| `git status --short` | before: pre-existing automation prompt/script edits, `docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md`, untracked `W0-01_CLIENT_INVENTORY.md`; after: the same entries plus concurrent Wave 1 client work and the two files created by this task (see §5.2) |

The FF8 citation (`test_release_versions_are_aligned`) and the FF6 citation
(`test_windows_client_has_minimal_safe_permissions`) both pass. The FF5 citation
(`tests/contract/test_workspace_derived_data_contract.py`) passes.

### 5.1 Transient failures during the task, all from concurrent work

Two failures were observed while this task ran. Both came from files another worker created or
changed in the same working tree; both were repaired by that worker before this task ended, and
both final runs are green. This task modifies no existing file and caused neither.

1. `tests/contract/test_client_release_surface.py::test_web_client_uses_api_only_and_supports_mandarin_theme`
   failed at line 211 (`assert "__TAURI_INTERNALS__" in api_client`) because the concurrent Wave 1
   host-capability refactor moved host detection out of `clients/web/src/api/client.ts` (which held
   `"__TAURI_INTERNALS__"` at `:11` and `tauri.localhost` at `:13` at the inspected revision) into
   the new `clients/web/src/app/host/hostCapabilities.ts`. The refactor matches Constitution rule 50
   and `docs/engineering/Architecture-V2/05_CLIENT_HOST_CROSS_PLATFORM.md` section 5; the contract
   test was updated by the same worker and the file now reports `31 passed`.
2. `docs/engineering/Architecture-V2/W0-03_ARCHITECTURE_RECONCILIATION.md` (another worker’s new
   document) contained two broken links — `../architecture/ARCHITECTURE_DECISION_RECORD.md` and the
   same target with a `#decision-15-...` anchor; the correct relative path from that directory is
   `../../architecture/ARCHITECTURE_DECISION_RECORD.md` — which made
   `tests/contract/test_markdown_links.py::test_all_local_markdown_links_resolve` fail. Running the
   checker `scripts/ci/check_markdown_links.py` directly at that moment returned exactly those two
   links and attributed both to that file; this document contains no Markdown links and contributed
   none. That worker repaired the links and the command is now `8 passed`.

### 5.2 Working-tree state quoted in this document

The counts in this inventory (146 authored client files, 171 public route decorators, 118 registry
patterns, five host commands) are the state inspected at revision
`dd1abe143cec7b6bd9a1c90090b210b59b5fe0ba` plus the uncommitted work present at that moment - the
Wave 1 client contracts, which are committed with this slice
([W0-03 reconciliation](W0-03_ARCHITECTURE_RECONCILIATION.md) section 1). The
assertions in `tests/contract/test_architecture_v2_fitness.py` are re-evaluated on every run and
are the authoritative statement; a concurrent writer can only make a real change fail, never make
a stale claim pass.

## 6. Coverage limits

These limits are deliberate; they are not claims of repository-wide verification.

1. Scope of the client checks is the authored client source listed in
   `tests/contract/test_architecture_v2_fitness.py` (`clients/web/src`, `clients/web/tests`, the
   Web build/config files, `clients/desktop/src-tauri/src`,
   `clients/desktop/src-tauri/capabilities`, both client manifests). Excluded on purpose:
   `clients/desktop/src-tauri/gen/**` (generated Tauri ACL schemas), `node_modules`,
   `package-lock.json`, `Cargo.lock`, icons, and client prose such as `clients/README.md:10`-`:11`
   which documents where the Python SDK and CLI live.
2. FF1 and FF2 are literal-token checks. They cannot detect backend or vendor access performed
   through a generated bundle, an obfuscated string, a runtime URL built from configuration, or a
   transitive dependency. They are a guard against the ordinary failure mode (a developer importing
   the backend package or hardcoding a provider endpoint), not a proof of isolation.
3. FF3's static check covers `src/eurogas_nexus/api/routes/public/**` only — the surface the
   registry and the existing registry test are about. `/api/internal/**` and `/api/dev/**` are
   covered by FF3-G1 and FF3-G2 above, not by an assertion. The check re-implements the registry's
   matching modes (prefix family, templated, longest pattern) for coverage purposes; it does not
   re-implement or replace the ranking logic in `src/eurogas_nexus/security/permissions.py:198`.
4. FF4's static check covers the credential route module only (FF4-G1). It does not prove that no
   other endpoint can return a stored secret, and it does not replace the runtime assertion in
   `tests/security/test_provider_credentials_api.py:30`.
5. FF5 asserts the dependency and import surface plus backend ownership of optimisation, route-cost,
   netback, strategy evaluation and backtest endpoints. It does not audit arithmetic inside the
   components; the two known client-side derived values are recorded as FF5-G1 rather than denied.
6. FF6 asserts a frozen allowlist of five commands, the consistency of `main.rs` with the Web
   workspace's declared command names, and (with Wave 1) a client-declared capability class per
   command. It does not assert that the Tauri capability ACL mirrors those classes (FF6-G1). The
   `HOST_COMMANDS` module it cross-checks is delivered as the Wave 1 HostCapabilities contract
   ([W1-04](W1-04_HOST_CAPABILITIES_CONTRACT.md)); the check discovers native command names from
   either that constant or direct `invoke("<cmd>")` literals and fails loudly if neither shape is
   present, so it cannot pass silently after a revert.
7. FF7 asserts four forbidden directions plus a frozen two-module exception list. It does not
   assert the full package graph (FF7-G4) and it does not assert `domain ↛ db`, `db ↛ domain` or the
   `db ↔ security` cycle, because those edges exist today and are documented as FF7-G2 and FF7-G3.
8. FF10's static check covers the `_maybe_invoke_provider` entrypoint in
   `src/eurogas_nexus/api/routes/public/analysis.py` only. It does not prove that every agent
   capability handler consults entitlement; that behaviour is covered by the runtime tests cited in
   the table.
9. No check in this task verifies the deployment configuration actually in force at runtime
   (profiles are asserted statically), and no check touches live PostgreSQL, providers or the
   network.
10. The working tree was being modified by concurrent Wave 1 client work while this task ran. The
    counts quoted here (146 client files, 168 client files, 171 route decorators, 118 registry
    patterns, five host commands) are the state actually inspected; the assertions in
    `tests/contract/test_architecture_v2_fitness.py` are re-evaluated on every run and are the
    authoritative statement.

## 7. Non-goals

- No change to any existing file, test, route, permission, credential path or client source.
- No commit, push, merge or stash.
- No duplication of the version/config consistency test (FF8) or of the runtime security suites.
- No new gap is “fixed” by weakening an existing test; every gap is recorded with its evidence and
  a remediation, to be scheduled as its own bounded task.
