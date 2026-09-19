# W0-03 — Architecture Reconciliation, Conflict Register and Wave 0 Gate

Status: **delivered (Wave 0 closure)**. Authority:
[12_MIGRATION_ROADMAP.md](12_MIGRATION_ROADMAP.md) Wave 0,
[14_VALIDATION_PACK.md](14_VALIDATION_PACK.md),
[10_DOCUMENTATION_NFR_TESTING.md](10_DOCUMENTATION_NFR_TESTING.md) sections 7-9, and
[AUTONOMOUS_EXECUTION_POLICY.md](AUTONOMOUS_EXECUTION_POLICY.md) sections 2-5.

Evidence base: [W0-01_CLIENT_INVENTORY.md](W0-01_CLIENT_INVENTORY.md) (client, routes, panels,
navigation, API dependencies), [W0-02_BACKEND_ACCESS_INVENTORY.md](W0-02_BACKEND_ACCESS_INVENTORY.md)
(identity, capability, entitlement, provider, control plane),
[W0-03_FITNESS_GAPS.md](W0-03_FITNESS_GAPS.md) (fitness-function coverage), the Wave 1 contracts
[W1-01](W1-01_SHELL_AND_ACTIVE_CONTEXT_CONTRACT.md) to [W1-05](W1-05_CANONICAL_EXPERIENCE_SPECS.md),
and [ADR-0016](../../architecture/ARCHITECTURE_DECISION_RECORD.md#decision-15-architecture-v2-programme-authority-and-product-experience-interaction-authority).

## 1. Wave 0 task status

| Task | Deliverable | Status |
|---|---|---|
| W0-01 | Client inventory (routes, workspaces, panels, navigation, client API dependencies) | **ACCEPTED** after repair (W0-01-R1, see section 2) |
| W0-02 | Backend access / entitlement / provider / control-plane inventory | **DELIVERED** (documentation-only; findings below) |
| W0-03 | Conflict register, current-to-target map, fitness gaps, Wave 0 gate | **DELIVERED** (this document) |
| ADR | Superseding decision for the UI authority conflict | **ACCEPTED** — ADR-0016 (Decision 15) |
| Fitness | Architecture fitness tests where the invariant genuinely holds | **DELIVERED** — `tests/contract/test_architecture_v2_fitness.py` |

## 2. W0-01-R1 independent review record (acceptance)

The original W0-01 was reviewed and returned REWORK_REQUIRED with five findings. The repair
(W0-01-R1) was then re-reviewed at HEAD `dd1abe1` against the sources, not against the worker's
summary. Checks performed for this acceptance:

| Review finding | Repair claim | Independent check | Result |
|---|---|---|---|
| 1. `orders`/Exposure conflation | `?workspace=orders` renders Overview; only `?task=exposure` mounts Market Positioning | Read `clients/web/src/app/model/commercialWorkflowModel.ts:14-17` (task-only resolver) and `clients/web/src/components/PortfolioWorkspace.tsx:150-165` (`openWorkspace("contracts", next)`) | Confirmed |
| 2. Shadow-surface reachability | `StrategyShadowRunTerminal` is unmounted; `StrategyShadowRunSections` is referenced only from it; `StrategyShadowShell` is the mounted path | Read `StrategyShadowRunTerminal.tsx:11-24` (five value + five type imports), confirmed 845 lines, and `StrategyLabWorkspace.tsx:8,95` mounts the shell | Confirmed |
| 3. KEEP conflation | Durable route identity kept as compatibility; navigation composition marked REFACTOR per gap matrix line 26 | Read inventory section 7 and the gap matrix rows 24-27 | Confirmed |
| 4. Historical whitespace evidence | Pre-existing `git diff --check` failure preserved as reported, fresh checks separated | Read inventory section 8.1 item 7 and 8.2 item 8 | Confirmed |
| 5. Citation meaning | Paths corrected; reachability distinguished from static reference; backend-wide claims qualified | `git diff --name-only d42e71b dd1abe1` shows only `.automation/*` drift, so client line references are valid; no `openWorkspace("orders")` producer exists in `clients/web/src` | Confirmed |

Outcome: **W0-01 and W0-01-R1 are accepted as documentation evidence.** The client inventory is the
current-behaviour baseline for the experience work; its coverage limits (client-only, path presence
rather than payload or authorization proof, no runtime or visual evidence) are accepted as recorded.

## 3. Conflict register

Each conflict is classified by resolution type. Nothing in this slice changes runtime behaviour to
resolve a conflict: the resolutions are decisions, contracts, tests and named future waves.

| # | Conflict | Authority analysis | Resolution | Status |
|---|---|---|---|---|
| C1 | ADR-0015 / Decision 14 names the Professional UI Constitution the sole *visual and interaction* authority; V2 makes Product Experience Architecture the interaction authority and the Constitution subordinate (gap matrix row 25) | V2 target vs accepted ADR | Superseding ADR generated without editing history: [ADR-0016](../../architecture/ARCHITECTURE_DECISION_RECORD.md). Interaction authority moves to V2 04; visual authority (typography, density, spacing, styling, motion) stays with the Constitution; content/rights/entitlement stay with `UI_CONTENT_STANDARDS.md` | **CLOSED** |
| C2 | `AUTHORITY_RECONCILIATION_PROPOSAL.md` was PROPOSED and required human review; the autonomous policy forbids `wait_human` for architecture conflicts | Governance documents | The proposal's status is historical; ADR-0016 is the accepted resolution. History preserved | **CLOSED** |
| C3 | Master prompt: "Do not proceed to Wave 2 without human review". Autonomous policy: wave gates are machine-evaluated and the programme continues | Programme governance | Wave 1 is delivered as the authorised first scope; the hold below was honoured at the time, and Wave 2 was subsequently entered and delivered ([W2-01](W2-01_EFFECTIVE_ACCESS_AND_EXPERIENCE_PROFILE.md)), as the conflict table's own C6 row records | **SUPERSEDED (status corrected 2026-09).** The original entry read "Wave 2 was **not** entered — **HELD**", which was true when written and became misleading as the programme advanced: the register is read as current state, and a hold that has since been released must say so rather than leave a reader to reconcile it against the C6 row two lines below. Nothing about the gate decision changed; only its currency did |
| C4 | Roadmap: "Stop gate after every wave" vs autonomous "checkpoint, commit, advance" | Programme governance | Each wave ends with recorded evidence, a checkpoint update and a commit; continuation is a separate, explicit decision. Wave 1 evidence is in this document and the execution state | **RESOLVED (process)** |
| C5 | In the `development` and `internal` API profiles no authentication dependency is installed app-wide, and the code default profile is `development`; the compatibility principal then receives unrestricted row/derived filtering for `auth_method == "legacy_public_token"` ([W0-02](W0-02_BACKEND_ACCESS_INVENTORY.md) sections 1.2, 1.5) | Constitution rules 18-20 (backend enforcement is authoritative; explicit deny/licence restriction overrides grants) vs current implementation, and it is **test-pinned** (`tests/security/test_identity_row_entitlement.py`) | **Deferred to Wave 2 with a security review.** This slice neither widens nor narrows access. The finding is recorded as a Wave 2 prerequisite because changing it changes a pinned contract and touches entitlement semantics | **OPEN, and now visible at runtime.** The posture is no longer document-only: `GET /api/health` and `GET /api/health/live` report `authentication: "enforced" \| "not_installed"`, derived from the route profile's own `require_auth` rather than restated per endpoint (`api/route_profiles.py::authentication_posture`, pinned by `tests/api/test_health_api.py`), so an operator can see that this deployment trusts its network instead of identifying its callers. **The behaviour change stays open by decision**: installing app-wide authentication in `development`/`internal`, or changing the code default profile, would change a pinned contract and the entitlement semantics of the compatibility principal, so it needs the owner's call rather than a worker's. The enforcement status is unchanged: `release` is the profile that identifies callers |
| C6 | `ROLE_PERMISSIONS[ADMIN]` holds every capability, and the same admin surface can grant data scopes including to itself, with no separation of duties ([W0-02](W0-02_BACKEND_ACCESS_INVENTORY.md) findings 2 and 5) | V2 06 section 7: platform administration is not a commercial super-user | **RESOLVED in Wave 2**: `ROLE_PERMISSIONS[ADMIN]` is now the platform-administration bundle, and `api/dependencies/commercial_access.py` refuses commercial paths (403 `commercial_access_not_granted`) to an administration-only identity. See [W2-01](W2-01_EFFECTIVE_ACCESS_AND_EXPERIENCE_PROFILE.md). The remaining separation-of-duties question - who may grant commercial entitlement - is tracked as C6b | **RESOLVED** |
| C6b | The administration surface can still write `data_scopes` for any principal, including itself | V2 06 sections 5-7 (entitlement is granted, not assumed) | Open policy decision with its own ADR: whether entitlement grants require a second approver, and whether an administrator may grant their own scopes. Not implemented in Wave 2 | **PARTLY RESOLVED — self-service closed.** `PATCH /api/access/users/{principal_id}` now refuses a caller that would change **its own** roles or data scopes (403 `entitlement_self_grant_forbidden`, audited as a denial and committed, so the attempt is visible), while another principal's grants are still administered normally, a request that merely repeats the current grants stays a no-op, and lifecycle fields that are not authority (status, email) remain editable (`api/routes/public/access.py`, pinned by `tests/security/test_access_self_grant.py`). **OPEN — the policy half**: whether any entitlement grant requires a second approver (a four-eyes rule rather than a self-grant refusal) is still an ADR decision |
| C7 | `require_entitlement` is declared but referenced by no route; `EntitlementScope.LICENSED` and `Permission.WRITE` are unreachable ([W0-02](W0-02_BACKEND_ACCESS_INVENTORY.md) finding 3) | V2 07 requires a first-class entitlement service | Wave 2/4: either wire it into the routes that need it or remove the dead contract in the same change that adds the real one. No silent deletion now | **DECIDED — left unwired, deliberately, and tested.** The enforced control on the governed reads is the per-family *and per-row* filter (`row_entitlement.py`, `identity.principal_allows_source_family`); `require_entitlement` is a *route-level* gate on one declared family, so mounting it on a route that composes several families would refuse a partially entitled principal the whole route - a coarser and wrong answer where the row filter is already right. Wiring it belongs with the first-class entitlement service V2 07 asks for, which models per-dataset licences (`EntitlementScope.LICENSED`) rather than one family per route. The decision is recorded in the dependency's own docstring and its fail-closed behaviour is now pinned by `tests/security/test_entitlement_dependency.py`, so it is decided code rather than dead code |
| C8 | MCP runs under an environment pseudo-principal with `*` scopes while `docs/agents/SECURITY_AND_ENTITLEMENT.md` claims the normal principal is inherited; two direct LLM routes re-authorise nothing against user authority ([W0-02](W0-02_BACKEND_ACCESS_INVENTORY.md) finding 7) | Constitution rule 22: AI inherits user authority and has no super-user bypass | Wave 2 (authority) + Wave 7 (AI convergence) with a security review. Wave 1's AI contract already forbids a bypass and requires re-authorisation per call | **PARTLY RESOLVED — caller-driven LLM routes and the MCP default scope.** `api/dependencies/ai_authority.py` re-authorises every **caller-driven** direct provider invocation against the caller's own `analysis.query` capability (403 `ai_authority_not_granted`), the alert-analysis path is declared policy-gated instead of READ, the analysis provider path fails closed with `AI_AUTHORITY_DENIED` and an audit record, and the alert run is attributed to the identity it ran under. MCP's pseudo-principal no longer defaults to `*` scopes: an unconfigured server holds no commercial grant and only the public baselines, with a deployment required to grant families deliberately (`mcp/server.py`, pinned by `tests/unit/test_mcp_capability_adapter.py`). Every MCP tool now **declares its authorisation posture** and publishes it in `tools/list`: registry-backed tools are `runtime-authorised` (re-authorised per call by `CapabilityRuntime`), the eighteen legacy read/sandbox tools are `deployment-principal`, and every call of the latter is audited as running outside the capability runtime (`governance.access` / `mcp.tool.invoked`, warning severity, best-effort). **OPEN**: MCP still cannot inherit the calling user across its transport, and re-homing the legacy tools onto the capability runtime is a behaviour change with consumers this repository cannot see, so it stays recorded rather than guessed at. The agent documentation states each limit instead of overstating it. **A third path is open and is a decision, not a defect to fix silently**: the deployed `monitoring-worker` service (`deploy/runtime/compose.yaml` → `scripts/ops/run_monitoring_worker.py` → `application/monitoring_service.py`, `enrich_with_llm`) also calls the provider. It has no caller identity to inherit, so "the caller's own capability" cannot literally apply to it, and it is neither guarded nor audited as an AI invocation. It is recorded as **D7** in section 9 (a service-identity posture for headless provider use) rather than closed by inventing an authority model for a process that has no user. The documented single-trust-domain deployment token keeps its previous posture, which is finding C5 |
| C9 | `network` is intercepted by the shell rather than composed through the market primary ([W0-01](W0-01_CLIENT_INVENTORY.md) section 2.4) | V2 04 sections 3-4 (one shell composition for every work mode) | Wave 9 migration. Wave 1 records the pattern (`EXPLORE`) and the shell contract without moving the mount site | **RESOLVED.** The shell no longer branches on a page: it renders the control-plane refusal or `WorkspaceRenderer`, and nothing else. The map-first network route is composed by the market primary, which already resolved that page to its network task (`marketTaskFromLocation`), so the route needed no URL change and the surface, its resource-pool path ladder and its evidence stack are wired where the composition lives. The scenario hand-off moved with the mount, so the selected or highlighted route is still carried. `AppShell` now mounts no workspace surface of its own; the page's single heading comes from `WorkspaceHeader`, the one component that renders an `<h1>` for a page |
| C10 | `orders` page id resolves to the Overview task on a bare deep link ([W0-01](W0-01_CLIENT_INVENTORY.md) section 2.4) | Deep-link compatibility vs one canonical owner per URL (RFC-0001 acceptance cases) | Wave 9 navigation migration. The finding stays recorded as a compatibility/UX risk; no runtime change is made in Wave 1 | **RESOLVED.** The legacy `orders` page id names the market-positioning view, so a bare link to it opens that view (`portfolioTaskFromLocation` returns `exposure` for `?workspace=orders`) instead of the overview. An explicit `?task=` still wins, and every other portfolio page keeps resolving to the overview, so the change adds no second owner for the URL: it makes the page and the surface it names agree |
| C11 | 26 shared-client methods have no call-site reference, and one legacy terminal plus its transitively referenced sections are unmounted ([W0-01](W0-01_CLIENT_INVENTORY.md) sections 2.8, 4.7) | V2 04 rule: a capability does not earn a page; dead surfaces are maintenance risk | Wave 7/9 decision with owner confirmation. Reachability, not static reference, is the evidence | **RE-MEASURED 2026-09 — one half corrected, one half stands.** *The unmounted terminal is still unmounted.* The earlier conclusion ("every `.tsx` under `src` is referenced by source or by a test, so the unmounted-terminal half is closed") passed the stated scan but drew the wrong conclusion from it, because two of those references are tests that read the file's **text** (`uiPrimitives.test.ts`, `evidencePresentation.test.ts`): `StrategyShadowRunTerminal.tsx` (838 lines) has no import and no render anywhere in `src`, and `StrategyShadowRunSections.tsx` is reachable only through it. By this row's own standard - reachability, not static reference - the half is **OPEN**, and the choice is to mount the terminal on a task, to retire it with its sections, or to record it as a compatibility artefact; it needs the owner's call, so it stays recorded. *The client-method census is stale and is restated.* Re-running the scan at the current tree (entries of the `api` object literal in `clients/web/src/api/client.ts:2166-2674`, identifier scan over the other `.ts`/`.tsx` under `clients/web/src`) gives **134 methods**, **20 never mentioned** anywhere outside that file, and **51 never invoked by name** in any other file (`name(`, which counts a method passed into a controller and called there). The register's earlier 131/21/52 was measured before the Wave 7 capability-invoke surface landed, and its enumerated list still names `invokeCapability` as a method with no surface - it is called at `AgentsWorkspace.tsx:189` today, so the set is the earlier list minus that one, which is exactly the 20 measured now. The decision-relevant set is the smaller one, because a mention through the loader seam is a surface using the method: access administration (`accessDataScopes`, `accessRoles`, `createAccessApiKey`), agents and capabilities (`agentProfiles`, `agentRun`, `searchCapabilities`), the strategy lifecycle (`backtestExperiment(s)`, `createBacktestExperiment`, `strategyRegistryRun`, `updateStrategyMetadata`), the shadow runtime (`shadowEvaluation`, `shadowMonitor`), reference and data reads (`capacityContracts`, `facilities`, `marketHubs`, `routeCost`), `researchCapabilities`, `portfolioLiveSummary` and `recordDecisionCaseDecisionOutcome`. Each is a declared backend capability whose surface does not exist yet, so the decision is *not* a deletion: it is whether to build those surfaces or to retire the routes, and it is carried forward as **D3**. *DELIVERED 2026-09 — slices A-F of the D3 decision are built.* The same scan over the current tree gives **133 methods**, **5 never mentioned** (`capacityContracts`, `facilities`, `marketHubs`, `portfolioLiveSummary`, `routeCost` — slice D) and **36 never invoked by name**, so every family the re-measurement listed except slice D now has a caller |
| C12 | Map-tile third-party requests and the client-held API token / operator principal in `localStorage` ([W0-01](W0-01_CLIENT_INVENTORY.md) sections 6.5, 7) | Licence/entitlement interpretation and security scope | Deferred: licence review and a security decision, not a worker judgement. No provider access was expanded or modified | **DEFERRED** |
| C13 | A review decision's actor is a **request-body field**, and the review route used it as the persisted actor *and* as the audit event's principal, while the Decision Case path already resolved its actor from the authenticated identity ([`review.py`](../../../src/eurogas_nexus/api/routes/public/review.py), audit rows) | V2 08 and the Decision Case rule: a governance act names who actually decided; an audit trail that repeats a typed claim is not evidence. Invariant 7 ("work mode/persona never grants backend authority") in spirit: a caller cannot attribute a decision to another person | Fixed on discovery — the two paths answered "who decided" differently, and the answer that repeated a typed name was the one writing the audit trail | **RESOLVED.** The rule now has one home, `api/dependencies/acting_actor.py`, and both the review-decision path and the Decision Case path call it. The review request's `actor` is retained only for compatibility, is never used as the actor, and a claim that disagrees with the identity comes back as an `ACTOR_CLAIM_IGNORED:<claim>` envelope warning instead of being believed; a deployment with no verified identity records its own public-API principal, because that is who acted. Both writers of the decision's audit rows (the repository's decision event and the route's governance action) now name the identity, which `tests/api/test_review_decision_actor.py` asserts over every row. The client surfaces follow: the review workspace offers no actor field and sends none, and the agent review gate sends none either |

## 4. Consolidated current-to-target map

Summary of the two inventories, using the V2 decision vocabulary. Detailed rows are in
[W0-01](W0-01_CLIENT_INVENTORY.md) section 7 and [W0-02](W0-02_BACKEND_ACCESS_INVENTORY.md) section 9.

| Area | Decision | First wave that acts |
|---|---|---|
| FastAPI boundary, PostgreSQL, Alembic, SDK/CLI, release engineering | KEEP | — |
| React single business UI, Tauri thin host | KEEP | — |
| Route/page-id identity and deep links | KEEP (compatibility) | Wave 9 (composition REFACTOR) |
| Permission registry + role floors | KEEP/EVOLVE | Wave 2 |
| Capability, scope, entitlement as distinct concepts | ADD | Wave 2 |
| Admin vs commercial access separation | REFACTOR | Wave 2 |
| Source Center (provider vs data product) | REFACTOR | Wave 4 |
| Control-plane surfaces in business navigation | REFACTOR | Wave 3 |
| Client business-state reconstruction / timestamp joins | REFACTOR | Wave 5 |
| Reproducibility (Analysis Snapshot) | ADD/EVOLVE | Wave 4 |
| Decision Case and Decision Record | ADD | Wave 6 |
| Unified Job, error taxonomy, business health | REFACTOR | Wave 8 |
| Shell, patterns, panels, Inspector, palette, HostCapabilities | ADD (contracts) | Wave 1 (delivered), Wave 9 (migration) |
| Desktop workstation capability | EVOLVE | Wave 10 |
| Microservices, Kafka, Kubernetes, service mesh, second datastore | KEEP ABSENT | — unless an ADR with measured need says otherwise |
| Trade execution, order entry, nomination, settlement | KEEP ABSENT | — |

## 5. Architecture fitness functions

[W0-03_FITNESS_GAPS.md](W0-03_FITNESS_GAPS.md) records, for each of the ten fitness functions that
V2 10 section 7 names, whether it is already covered, implemented in this slice, or an open gap with
evidence. The implemented checks live in `tests/contract/test_architecture_v2_fitness.py` and are
static (standard library only), so they run without PostgreSQL or heavy dependencies; the client-side
half (single native boundary, shell-region honesty, registry completeness, AI authority invariants)
runs in `clients/web/tests/experienceArchitecture.test.ts`.

## 6. Wave 0 gate evaluation

Roadmap Wave 0 requires: current-to-target code map; conflicts with accepted ADRs; route / workspace /
API / permission / provider / admin inventory; architecture fitness tests; implementation plan. No
broad feature or UI redesign.

| Gate item | Evidence | Result |
|---|---|---|
| Current-to-target code map | W0-01 section 7, W0-02 section 9, this document section 4 | PASS |
| Conflicts with accepted ADRs identified and resolved | Conflict register section 3; ADR-0016 accepted | PASS |
| Route / workspace / panel / navigation inventory | W0-01 sections 2-3 (16/16 pages traced, panels and detail patterns). The primary count has since changed: Wave 3 split the control plane out of business navigation, so `productNavigation.ts` declares **six** primaries (market, portfolio, strategy, decision, system, administration) - the "5 primaries" the gate was evaluated against is the Wave 0/1 baseline, not the current tree | PASS (baseline recorded, count superseded by Wave 3) |
| Client API dependency inventory | W0-01 sections 4-5 (client path literals cross-checked against the pinned `/api` surface; unresolved items marked) | PASS |
| Role / permission / entitlement inventory | W0-02 sections 1-4 | PASS |
| Provider / source / admin / runtime control inventory | W0-02 sections 5-7 | PASS |
| Architecture fitness tests | `tests/contract/test_architecture_v2_fitness.py`, `clients/web/tests/experienceArchitecture.test.ts` | PASS |
| Implementation plan | This document, the execution checkpoint and the Wave 1 contract set | PASS |
| No broad UI redesign in Wave 0/1 | Wave 1 adds contracts, registries and a seam; no page is redesigned, merged or retired | PASS |

**Wave 0 gate: PASSED.** Wave 1 is delivered on top of it (see
[W1-01](W1-01_SHELL_AND_ACTIVE_CONTEXT_CONTRACT.md) to [W1-05](W1-05_CANONICAL_EXPERIENCE_SPECS.md)).

## 7. Product and security invariants check

Per `AUTONOMOUS_EXECUTION_POLICY.md` section 3, this slice:

- introduces no trade execution, order entry/routing, nomination or settlement behaviour;
- grants no permission, scope or entitlement, and widens no access to commercial data;
- adds no client-side provider credential or secret handling;
- adds no client-to-database or client-to-vendor path;
- keeps deterministic engines authoritative for numeric output;
- adds no microservice, broker, datastore, Kubernetes or service-mesh dependency.

No STOP condition from [CODEX_ENTRYPOINT.md](CODEX_ENTRYPOINT.md) was triggered by this work. The two
findings that touch security (C5, C6) are recorded as Wave 2 prerequisites with a required security
review; they were discovered, not created, and changing them is explicitly out of this slice.

## 8. Deferred items and the next bounded tasks

| Next task | Scope | Gate |
|---|---|---|
| Wave 2 preparation | Capability + scope + entitlement model; `ExperienceProfile` contract; admin/commercial separation; resolve C5-C8 with a security review | Requires an explicit decision to enter Wave 2 (conflict C3) |
| Wave 3 preparation | Control-plane surface boundary; move provider/credential/runtime/access out of business navigation | After Wave 2 |
| Wave 4 preparation | Data Product abstraction; Analysis Snapshot v1 (closes the reproducibility gap named in W1-01) | After Wave 2/3 |
| Wave 9 preparation | Migrate workspaces onto the Wave 1 contracts: shell composition, Inspector, palette, action geography; resolve C9-C11 | After Waves 2-8 as sequenced by the roadmap |

## 9. Decisions the owner must take

Everything the migration can decide for itself has been decided, implemented, tested and recorded.
What is left is a short list of questions that are **the owner's, not a worker's**, because each one
changes a security posture, a licence obligation or a product surface rather than fixing a
contradiction. They are written here as options with consequences so they can be answered in one
pass instead of being rediscovered per round. Nothing below is decided silently, and no work has
been done that presumes an answer.

### D1 — C5: should the `development` and `internal` profiles authenticate their callers?

**Today.** `authentication: enforced | not_installed` is reported at runtime by `/api/health` and
`/api/health/live`, derived from the route profile's own `require_auth`; the private-network posture
is documented, published and tested. The `development`/`internal` profiles do not install
authentication, so every request in those profiles acts as the compatibility public-API principal.

**Why it is not a worker decision.** Turning authentication on in those profiles changes a pinned
contract (the route-profile contract and the compatibility principal's entitlement semantics), so it
is a profile/behaviour change with a deployment consequence, not a bug fix.

**Options.** (a) Install app-wide authentication in `development`/`internal` as well, keeping the
private-network posture only as an explicit, documented deployment choice; (b) keep the code default
and require operators to change the profile in deployment configuration; (c) keep as-is and rely on
the runtime posture report plus network controls.

**Consequence of (a).** Every local/dev script, seed, benchmark and integration harness that relies
on the compatibility principal must present a credential; the acceptance script's
`deployment_posture_defaults_private` expectation stays, but the "private network" claim becomes a
deployment statement rather than a code default. **Recommendation: (a)**, because a code default that
trusts the network is the one security posture the programme has repeatedly had to publish *because*
it is surprising; the work is roughly a day including harness updates.

### D2 — C6b: what is the second-approver policy for role and data-scope grants?

**Today.** A principal cannot change its own roles or data scopes (self-service half closed, tested).
Granting a role or a data scope to *somebody else* is a single-operator action recorded in the audit
trail; there is no second approver.

**Options.** (a) Require two-person approval for role grants above a threshold (e.g. ADMIN or a
commercial data scope) with the first approver recorded as pending; (b) require approval only for
commercial-scope grants, on the grounds that they carry the entitlement risk; (c) keep single-operator
with audit only.

**Consequence.** (a)/(b) add a pending state to the access model and an approval surface, i.e. a
schema change plus an admin UI. **Recommendation: (b)** as the smallest control that addresses the
real risk (commercial data entitlement), with the ADR recording why ADMIN-role grants stay
single-operator.

### D3 — C11: build the surfaces for the client methods with no caller, or retire the routes?

**Today.** Re-measured 2026-09 in the current tree: 134 methods in the `api` object literal of
`api/client.ts`, of which **20 are never mentioned** anywhere outside the client and **51 are never
invoked by name** in any other file; the clusters are the strategy lifecycle, the shadow runtime,
access administration and a handful of reference reads. Each is a declared backend capability whose
surface does not exist. The register's earlier 131/21/52 was measured before the Wave 7
capability-invoke surface landed (its list still names `invokeCapability` as surfaceless, and it is
called from the agents workspace today), and the earlier conclusion that no component is unmounted is
also corrected there: `StrategyShadowRunTerminal.tsx` is referenced only by two tests that read its
text. `W0-01` section 2.8 holds the original inventory; the re-measurement and its method are in the
conflict table above. **Current state, re-measured after slice F:** 133 methods, **5 never mentioned**
(slice D's reference reads: `capacityContracts`, `facilities`, `marketHubs`, `portfolioLiveSummary`,
`routeCost`) and 36 never invoked by name. The rows below state each slice's own movement.

**Options.** (a) Build the surfaces for the families an operator actually needs (strategy freeze/fork
and shadow monitors look like the strongest candidates, since their routes are tested and the
surfaces' absence forces operators to the API); (b) retire the routes and the methods for the rest,
so "declared" means "reachable"; (c) leave them and record the gap (status quo). **A fourth question
joins them from the re-measurement**: `StrategyShadowRunTerminal.tsx` (838 lines) and the sections
only it references are unmounted, so they are either mounted on a task, retired with their methods,
or recorded as a compatibility artefact rather than left to look like a surface.

**Consequence of (b).** Removing public paths is a breaking change for SDK/CLI callers and needs the
contract-evolution policy procedure; the paths are pinned in
`tests/contract/test_api_surface_stability.py`, so this is a deliberate, visible change.
**Recommendation (superseded by the decision above): (a) for the strategy lifecycle and shadow
runtime, (b) for access administration, (c) for the reference reads until a surface wants them.** The
owner chose to build all of them, so (b) and (c) are not taken; slice C therefore builds the access
reads rather than retiring them, and slice D builds the reference reads.

**DECIDED 2026-09-18 — the owner chose (a): build every missing surface.** The work is sliced by
family, each slice carrying its own rule, tests, bilingual vocabulary and record, and the census is
re-measured after each one so this register states the *remaining* set rather than the opening one:

| Slice | Methods that gained a surface | Where | State |
|---|---|---|---|
| A: strategy lifecycle | `updateStrategyMetadata`, `createBacktestExperiment`, `backtestExperiments`, `backtestExperiment`, `strategyRegistryRun` | Strategy Lab — a backtest-experiment panel in the Backtest task (create, list, open, and read a grouped run the bounded history has not loaded) and a strategy-identity metadata editor in the Design task | **Delivered**: never-mentioned set 20 → 15 |
| B: shadow runtime | `shadowEvaluation`, `shadowMonitor` | Strategy Lab — the Shadow task now opens one evaluation (the only read that carries its **risk checks**, so a blocked candidate's controls are finally visible) and re-reads the monitor it belongs to, whose current state the list entry cannot be fresher than | **Delivered**: never-mentioned set 15 → 13. The monitor list, alerts, drift, lifecycle actions and runtime status were already surfaced by the CR-06 slice |
| C: access administration | `accessRoles`, `accessDataScopes`, `createAccessApiKey` | Access & Identity — a **Roles and scopes** tab (the role → permission catalogue and the declared scope families) and an issue-key form on the api-keys view | **Delivered**: never-mentioned set 13 → 10 |
| D: reference and data reads | `facilities`, `marketHubs`, `capacityContracts`, `routeCost`, `portfolioLiveSummary` | market / network / capacity / portfolio surfaces | Not started |
| E: agent and capability reads | `agentProfiles`, `agentRun`, `searchCapabilities`, `researchCapabilities` | Agents workspace — the **declared profile catalogue** (the vocabulary a run's label is checked against, and what a `PROFILE_STAGES_NOT_REACHED` warning refers to), a **run lookup by id** (the run list is bounded, so a run cited by a Decision Case could not be opened at all) and a **capability search** through the route that owns the search (it reads the description, domain, tags and input concepts, which a client filter over the rendered rows cannot see); Research workspace — the **capability catalogue** (`GET /api/research/capabilities`: read/write class, determinism, side-effect class, permission, provenance behaviour) | **Delivered**: never-mentioned set 9 → 5 |
| F: decision outcome | `recordDecisionCaseDecisionOutcome` | Decision Case panel — the decision is recorded through the `apiOutcome` variant, so a 409 `case_not_decidable` renders its blockers as a governed answer instead of a thrown failure. Its unused throwing twin (`recordDecisionCaseDecision`, same route) was deleted rather than left as a second way to handle one refusal | **Delivered**: never-mentioned set 10 → 9 |

Two things the slices do not change: no new page is created (V2 rule 9 — each surface completes a task
that already exists), and no route, permission or payload changes. The unmounted terminal stays open
until its own family's slice decides it.

### D4 — C12: map tiles — which provider, under whose licence and token?

**Today.** The client can request third-party map tiles and the deployment selects a provider in
Settings; the licence question and the client-held token were deferred to a security/licence review.
No provider access was expanded or modified.

**Options.** (a) A licensed provider with a deployment-held token served through a backend proxy (no
client-held token); (b) a self-hosted/offline tile set for the preview posture; (c) keep the current
selection with the token held by the operator.

**Consequence of (a).** A new backend route and a cache, i.e. a small service addition with its own
ADR; (b) removes the third-party request entirely. **Recommendation: (b) for the private-network
posture and (a) only if a licensed provider is bought**, because the product's map is reference
geometry rather than licensed market data.

### D6 — C8 remainder: what should the MCP surface do about the calling user?

**Today.** MCP runs under a deployment-configured service identity, not the calling user, and its
tools declare and publish that posture; a call that runs outside the capability runtime is audited
rather than silent, and the pseudo-principal no longer defaults to a wildcard data scope. What
remains is a real question rather than a defect: an MCP client (typically an LLM agent acting for a
person) reads rows filtered by the *service* identity's scopes, so a tool can return data the human
behind the call is not entitled to.

**Options.** (a) Require a per-call caller identity that the MCP server verifies against the
identity store, and re-authorise each tool call as that principal - the strongest posture, and a
breaking change for any MCP client that has none; (b) keep the service identity but bound its data
scopes to the intersection of the tools' declared needs (no behavioural change for clients, a
narrower blast radius for a misconfigured deployment); (c) leave as declared and audited.

**Consequence of (a).** Every MCP tool gains a required identity argument, the server needs the
identity store at hand, and existing clients stop working until they pass one. **Consequence of
(b).** A deployment that today reads broad data through MCP would read less; the change is
configuration-visible and reversible. **Recommendation: (b) now**, plus a documented trigger for
(a): if an MCP client is ever used by more than one human identity, the service identity becomes an
authority-laundering path and (a) is required. Neither is decided here.



### D7 — C8: what authority does the headless `monitoring-worker` invoke the provider under?

**Today.** Every *caller-driven* provider invocation is re-authorised against the caller's own
`analysis.query` capability. The deployed `monitoring-worker` service is not: it is started by
compose (`deploy/runtime/compose.yaml`), runs `scripts/ops/run_monitoring_worker.py`, and reaches
`invoke_deepseek` through `application/monitoring_service.py` when LLM enrichment is enabled. The
module contains no principal, permission or authority reference at all, so C8's earlier wording
("every direct provider invocation") overstated what is guarded. This is not a missing check that
can be dropped in: the worker has **no caller identity**, so "the caller's own capability" has
nothing to bind to, and deciding what *should* bind is a design question about service identities
rather than a repair.

**Options.** (a) Declare a named service principal for the worker (a capability set, an audit
identity, and its own `analysis.query` grant) and re-authorise every worker enrichment against it -
the worker becomes attributable and revocable like any other actor, at the cost of an identity to
provision and a new configuration surface; (b) keep the worker credential-bound and record the
posture explicitly, as the legacy MCP tools now are (declared, published and audited rather than
implied), with the worker's enrichment counted as deployment-level automation rather than a user
act; (c) require an operator to pass a principal when starting the worker, so a scheduled run is
attributed to the human or role that scheduled it.

**Consequence of (a).** A new principal and grant to provision, and a deployment that forgets it
gets no enrichment (fail-closed, which is the right failure). **Consequence of (b).** The deepest
honest statement available today - what the deployment does is what its operator configured - with
the gap named where an operator will read it. **Recommendation: (b) now, (a) when more than one
service invokes providers headlessly**, because two headless callers is where a shared posture stops
being describable and a real identity earns its keep. Neither is decided here.


### What no decision here can unblock

Neither of the two remaining wave halves can be finished in this environment, and neither is a
defect: **Wave 10's native half**
(window creation, multi-monitor restore, notifications, protocol registration, tray, file dialogs)
needs a machine with the Rust toolchain and platform packaging; **Wave 11** needs the external items
an operator owns (IdP acceptance against a real issuer, provider certification, a real UAT, a
production restore drill, signing/notarisation). The contract, the capability model, the diagnostics
consumer and the fail-soft host boundary are delivered and tested; the honest statement is that the
native implementation is *declared and unverified* rather than done.

## 10. Validation evidence for this slice

The numbers below are the evidence **Wave 0/1 was delivered on**, kept as the historical record. They
are not the current tree's counts: the suite has grown since (see the execution checkpoint for the
current figures), and reading a stale count as a present claim is the failure this register's own
C3/C11 corrections are about.

- `clients/web`: `npm run build` (tsc + vite) — exit 0; `node --test "tests/*.test.ts"` — 236 tests,
  236 pass, including the 15 new experience-architecture tests and the migrated host-boundary
  assertions in `authGate.test.ts`.
- `python -m pytest tests -q --ignore=tests/integration` — 1469 passed, 1 skipped, 0 failed.
- `tests/contract/test_architecture_v2_fitness.py` — new static fitness tests (28 cases); exact
  command and result recorded in [W0-03_FITNESS_GAPS.md](W0-03_FITNESS_GAPS.md).
- `python -m pytest tests/contract/test_markdown_links.py` — local Markdown links resolve.
- Three pinned source-text contract tests were updated because the code they pin moved
  (`tests/contract/test_client_release_surface.py`, `tests/release/test_deployment_roles.py`,
  `clients/web/tests/uiPrimitives.test.ts`, plus `clients/web/tests/authGate.test.ts`); each keeps its
  original guarantee asserted against the new single owner, and none was weakened or deleted.
- `git diff --check` — no whitespace errors introduced.
- Not run and not claimed: PostgreSQL-backed integration suites, packaging/installer evidence,
  visual/accessibility/UAT review, provider and licence validation.
- No runtime, schema, API, permission, numerical, release or DR behaviour was changed by Wave 0/1.
