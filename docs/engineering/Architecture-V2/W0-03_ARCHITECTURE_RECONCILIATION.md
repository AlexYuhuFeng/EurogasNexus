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
| C3 | Master prompt: "Do not proceed to Wave 2 without human review". Autonomous policy: wave gates are machine-evaluated and the programme continues | Programme governance | Wave 1 is delivered as the authorised first scope; Wave 2 was **not** entered. The gate is honoured as a scope boundary and named as the next decision point | **HELD** |
| C4 | Roadmap: "Stop gate after every wave" vs autonomous "checkpoint, commit, advance" | Programme governance | Each wave ends with recorded evidence, a checkpoint update and a commit; continuation is a separate, explicit decision. Wave 1 evidence is in this document and the execution state | **RESOLVED (process)** |
| C5 | In the `development` and `internal` API profiles no authentication dependency is installed app-wide, and the code default profile is `development`; the compatibility principal then receives unrestricted row/derived filtering for `auth_method == "legacy_public_token"` ([W0-02](W0-02_BACKEND_ACCESS_INVENTORY.md) sections 1.2, 1.5) | Constitution rules 18-20 (backend enforcement is authoritative; explicit deny/licence restriction overrides grants) vs current implementation, and it is **test-pinned** (`tests/security/test_identity_row_entitlement.py`) | **Deferred to Wave 2 with a security review.** This slice neither widens nor narrows access. The finding is recorded as a Wave 2 prerequisite because changing it changes a pinned contract and touches entitlement semantics | **OPEN — Wave 2** |
| C6 | `ROLE_PERMISSIONS[ADMIN]` holds every capability, and the same admin surface can grant data scopes including to itself, with no separation of duties ([W0-02](W0-02_BACKEND_ACCESS_INVENTORY.md) findings 2 and 5) | V2 06 section 7: platform administration is not a commercial super-user | **RESOLVED in Wave 2**: `ROLE_PERMISSIONS[ADMIN]` is now the platform-administration bundle, and `api/dependencies/commercial_access.py` refuses commercial paths (403 `commercial_access_not_granted`) to an administration-only identity. See [W2-01](W2-01_EFFECTIVE_ACCESS_AND_EXPERIENCE_PROFILE.md). The remaining separation-of-duties question - who may grant commercial entitlement - is tracked as C6b | **RESOLVED** |
| C6b | The administration surface can still write `data_scopes` for any principal, including itself | V2 06 sections 5-7 (entitlement is granted, not assumed) | Open policy decision with its own ADR: whether entitlement grants require a second approver, and whether an administrator may grant their own scopes. Not implemented in Wave 2 | **OPEN - Wave 3** |
| C7 | `require_entitlement` is declared but referenced by no route; `EntitlementScope.LICENSED` and `Permission.WRITE` are unreachable ([W0-02](W0-02_BACKEND_ACCESS_INVENTORY.md) finding 3) | V2 07 requires a first-class entitlement service | Wave 2/4: either wire it into the routes that need it or remove the dead contract in the same change that adds the real one. No silent deletion now | **OPEN — Wave 2** |
| C8 | MCP runs under an environment pseudo-principal with `*` scopes while `docs/agents/SECURITY_AND_ENTITLEMENT.md` claims the normal principal is inherited; two direct LLM routes re-authorise nothing against user authority ([W0-02](W0-02_BACKEND_ACCESS_INVENTORY.md) finding 7) | Constitution rule 22: AI inherits user authority and has no super-user bypass | Wave 2 (authority) + Wave 7 (AI convergence) with a security review. Wave 1's AI contract already forbids a bypass and requires re-authorisation per call | **PARTLY RESOLVED — the direct LLM routes.** `api/dependencies/ai_authority.py` re-authorises every direct provider invocation against the caller's own `analysis.query` capability (403 `ai_authority_not_granted`), the alert-analysis path is declared policy-gated instead of READ, the analysis provider path fails closed with `AI_AUTHORITY_DENIED` and an audit record, and the alert run is attributed to the identity it ran under. The documented single-trust-domain deployment token keeps its previous posture, which is finding C5. **OPEN — MCP**: the environment pseudo-principal and its default `*` scopes, and the legacy MCP tools that bypass `CapabilityRuntime`, are unchanged and still need the security review |
| C9 | `network` is intercepted by the shell rather than composed through the market primary ([W0-01](W0-01_CLIENT_INVENTORY.md) section 2.4) | V2 04 sections 3-4 (one shell composition for every work mode) | Wave 9 migration. Wave 1 records the pattern (`EXPLORE`) and the shell contract without moving the mount site | **OPEN — Wave 9** |
| C10 | `orders` page id resolves to the Overview task on a bare deep link ([W0-01](W0-01_CLIENT_INVENTORY.md) section 2.4) | Deep-link compatibility vs one canonical owner per URL (RFC-0001 acceptance cases) | Wave 9 navigation migration. The finding stays recorded as a compatibility/UX risk; no runtime change is made in Wave 1 | **OPEN — Wave 9** |
| C11 | 26 shared-client methods have no call-site reference, and one legacy terminal plus its transitively referenced sections are unmounted ([W0-01](W0-01_CLIENT_INVENTORY.md) sections 2.8, 4.7) | V2 04 rule: a capability does not earn a page; dead surfaces are maintenance risk | Wave 7/9 decision with owner confirmation. Reachability, not static reference, is the evidence | **OPEN — Wave 7/9** |
| C12 | Map-tile third-party requests and the client-held API token / operator principal in `localStorage` ([W0-01](W0-01_CLIENT_INVENTORY.md) sections 6.5, 7) | Licence/entitlement interpretation and security scope | Deferred: licence review and a security decision, not a worker judgement. No provider access was expanded or modified | **DEFERRED** |

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
| Route / workspace / panel / navigation inventory | W0-01 sections 2-3 (16/16 pages traced, 5 primaries, panels and detail patterns) | PASS |
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

## 9. Validation evidence for this slice

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
