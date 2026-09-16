# Architecture V2 Execution State

Last updated: 2026-09-15
Repository HEAD: f12f8f5 (merge of `origin/main` into `main`: Wave 0/1 delivery `ec60d35` plus the 68 commits main had advanced by since `c7f3010`)
Working tree: Wave 0 closure and Wave 1 delivery are committed on `main` and pushed to `origin/main`. Pre-existing modifications to `.automation/prompts/orchestrator_slice.md`, `.automation/scripts/deepseek_worker.py` and `.automation/scripts/supervisor.py` remain uncommitted and are **not** accepted or reverted by this slice; they are outside its scope.
V2 pack version: 2026-09 autonomous runner
Current wave: Wave 1 delivered on top of a passed Wave 0 gate; Wave 2 not entered.
Wave status: WAVE_0_GATE_PASSED; WAVE_1_DELIVERED; WAVE_2_GATED (see risks).

## Accepted architecture decisions

- V2 documents under `docs/engineering/Architecture-V2/` define target direction; repository truth defines current implemented behaviour.
- Modular monolith + worker runtime remains the default product architecture.
- **ADR-0016 (Decision 15) accepted**: Architecture V2 is the binding target architecture and the product-experience **interaction** authority. The Professional UI Constitution keeps visual authority (typography, density, spacing, styling, motion) and is subordinate to the V2 interaction contracts where they overlap; `UI_CONTENT_STANDARDS.md` keeps content/time-basis/rights/provenance/entitlement/no-execution authority; domain/API/data/security contracts keep their precedence. RFC-0001 and Decision 14 remain accepted and their history is preserved; only the "sole interaction authority" clause is superseded. Generated under `AUTONOMOUS_EXECUTION_POLICY.md` section 2.
- Functional assignment and work mode never grant backend authority; composition is not permission.
- The Wave 1 interaction contracts are machine-readable (`clients/web/src/app/experience/**`, `clients/web/src/app/host/**`) and enforced by focused tests, not prose.

## Completed tasks

- [x] W0-01 — client inventory (routes, workspaces, panels, navigation, client API dependencies), delivered and repaired through W0-01-R1 — **ACCEPTED** after independent re-review against sources (five findings verified: `orders`/Exposure route semantics, shadow-surface reachability, KEEP vs REFACTOR classification, preserved historical whitespace evidence, semantic citations). Evidence: `docs/engineering/Architecture-V2/W0-01_CLIENT_INVENTORY.md`; review record in `W0-03_ARCHITECTURE_RECONCILIATION.md` section 2.
- [x] W0-02 — backend access / entitlement / provider / control-plane inventory — **DELIVERED**. Evidence: `W0-02_BACKEND_ACCESS_INVENTORY.md` (499 lines, path:line citations, explicit coverage limits).
- [x] W0-03 — conflict register, current-to-target map, fitness gaps, Wave 0 gate — **DELIVERED**. Evidence: `W0-03_ARCHITECTURE_RECONCILIATION.md`, `W0-03_FITNESS_GAPS.md`.
- [x] ADR-0016 appended to `docs/architecture/ARCHITECTURE_DECISION_RECORD.md` with an index row; Decision 14 text untouched.
- [x] Architecture fitness tests — `tests/contract/test_architecture_v2_fitness.py` (static, standard library only; 28 cases over FF1-FF10) plus the client-side invariants in `clients/web/tests/experienceArchitecture.test.ts`. Nine residual gaps with evidence and remediation are recorded in `W0-03_FITNESS_GAPS.md`; FF6-G1 is partially closed by the Wave 1 `HOST_COMMAND_CAPABILITIES` classification.
- [x] Wave 1 contracts — W1-01 shell + Active Context, W1-02 workspace patterns + panel registry, W1-03 Inspector + AI actions + command palette, W1-04 HostCapabilities, W1-05 canonical experience specifications, with `clients/web/src/app/experience/**` and `clients/web/src/app/host/hostCapabilities.ts` as the executable form.
- [x] Wave 1 seam migrations (behaviour-preserving): header composition now comes from the pattern registry instead of a local primary list (`WorkspaceRenderer.tsx`); shell regions carry `data-shell-region` markers; desktop detection and the native bridge moved into the single HostCapabilities boundary (`api/client.ts`, `stores/api.ts`), closing the duplicated-detection finding in W0-01.
- [x] Documentation registration — V2 programme artefacts registered in `docs/README.md`, `docs/README-CN.md` and the pack index `00_README.md`.

## Current / next task

- Task ID: WAVE-2-PREPARATION (not started; gated).
- Objective: capability + scope + entitlement as distinct concepts; `ExperienceProfile` contract; platform-admin separated from commercial access; AI invocation re-authorised against user authority on every path.
- Assigned worker: DeepSeek Flash V4.1 implementation under an architecture review; findings C5-C8 in `W0-03_ARCHITECTURE_RECONCILIATION.md` section 3 are the required starting evidence.
- Relevant contracts: `06_IDENTITY_ACCESS_CONTROL_PLANE.md`, `07_DATA_PLATFORM.md`, ADR-0016, `W0-02_BACKEND_ACCESS_INVENTORY.md`.
- Focused validation expected: authorization/entitlement contract tests (including the test-pinned legacy-principal behaviour), plus the existing security suite; a security review is required before any enforcement change.
- Exact next action: obtain the explicit Wave 2 authorisation required by `13_DEEPSEEK_HARNESS_MASTER_PROMPT.md` ("Do not proceed to Wave 2 without human review"); conflict C3 in `W0-03_ARCHITECTURE_RECONCILIATION.md` records why this programme keeps that gate even though `AUTONOMOUS_EXECUTION_POLICY.md` would allow continuation.

## Deferred / known gaps

- C5 — `development`/`internal` profiles install no app-wide authentication and the code default profile is `development`; the compatibility principal then receives unrestricted row/derived filtering for `auth_method == "legacy_public_token"` (test-pinned). Wave 2, with security review.
- C6 — `ROLE_PERMISSIONS[ADMIN]` holds every capability and the admin surface can grant its own data scopes without separation of duties. Wave 2.
- C7 — `require_entitlement`, `EntitlementScope.LICENSED` and `Permission.WRITE` are declared but unreachable. Wave 2/4.
- Fitness gaps FF2-G1, FF3-G1, FF3-G2, FF4-G1, FF5-G1, FF6-G1, FF7-G1..FF7-G4, FF9-G1 (see `W0-03_FITNESS_GAPS.md`): recorded with evidence and remediation. FF7-G1/G2 (`application`→`api`, `domain`→`db`) and FF3-G1/G2 (`/api/internal/*` outside the registry, registry enforced only in the release profile) are the ones that overlap the Wave 2 authority work and should be scheduled with it.
- C8 — MCP runs as an environment pseudo-principal with `*` scopes; two direct LLM routes re-authorise nothing against user authority. Wave 2 (authority) + Wave 7 (AI convergence).
- C9/C10 — `network` shell interception and the `orders` deep-link mismatch. Wave 9 navigation migration, with evidence.
- C11 — 26 shared-client methods without call sites; one unmounted legacy terminal plus its transitively referenced sections. Wave 7/9 decision.
- C12 — map-tile third-party requests and the client-held API token/operator principal in `localStorage`: licence review and security decision, deferred.
- Inspector region and activity row are declared `planned`/`partial` in the shell contract and are not implemented: Wave 8/9.
- No Analysis Snapshot exists, so `activeContextIsReproducible()` is `false` and surfaces must not claim reproducibility from context alone: Wave 4.
- Python runtime dependencies are not installed in the local environment beyond the core set; test suites that need PostgreSQL were not run in this slice and no result is claimed for them.

## Compatibility

- API: unchanged. No endpoint, payload, pinned `/api` surface entry or client call semantics changed.
- DB: unchanged. No schema, migration, datastore or persistence change; no new datastore.
- Client: behaviour preserved. Header composition, routes, deep links, labels, host detection outcome, SSO and sign-out sequences are unchanged; the pattern registry and HostCapabilities are seam extractions. Two pinned source-text tests were updated to follow the moved code (`uiPrimitives.test.ts`, `authGate.test.ts`) with the same guarantees asserted at the new location.
- Security: unchanged. No permission, role, scope, entitlement, credential or gate was widened or narrowed; no secret was read or printed.
- Release: unchanged. No version, packaging, release, DR or compatibility change; `dist/` output is git-ignored.
- Numerics: unchanged. No calculation, model, solver or golden-scenario behaviour was touched.

## Validation evidence

- `clients/web`: `npm run build` (`tsc && vite build`) — exit 0 (`152 modules transformed`); the only warning is the pre-existing ineffective-dynamic-import notice for `src/api/client.ts`.
- `clients/web`: `node --test "tests/*.test.ts"` — **256 tests, 256 pass, 0 fail** (221 pre-existing, 15 new experience-architecture tests, 20 from the upstream `main` merge). This includes the full baseline suite after the seam migrations.
- `python -m pytest tests -q --ignore=tests/integration` — **1470 passed, 1 skipped, 0 failed** (contract, api, security, release, unit, sdk, cli, domain, optimization, ingestion, streaming, workflow, evals, uat).
- `python -m pytest tests/contract/test_architecture_v2_fitness.py -q` — 28 passed (new static fitness tests, FF1-FF10 coverage; result table in `W0-03_FITNESS_GAPS.md`).
- `python -m pytest tests/contract/test_markdown_links.py -q` — pass; every new internal Markdown link resolves.
- Integration with upstream `main`: `git merge origin/main` merged the 68 commits main had advanced by since `c7f3010` with no conflicts; the i18n resources merged to 1730 keys per locale with the 38 new `experience.*` keys intact on both sides, and `clients/web/package.json` was unchanged (no dependency install required). Merged tree re-validated with the numbers above.
- Three pinned source-text contract tests were updated in the same change because the code they pin moved (`tests/contract/test_client_release_surface.py`, `tests/release/test_deployment_roles.py`, `clients/web/tests/uiPrimitives.test.ts`), plus `clients/web/tests/authGate.test.ts`. Each keeps its original guarantee asserted against the new single owner; none was weakened or deleted.
- `git diff --check` — no whitespace errors introduced.
- Citation and scope checks in `W0-01`/`W0-02` were performed against `dd1abe1`; `git diff --name-only d42e71b dd1abe1` shows only `.automation/*` drift, so client line references remain valid.
- Not run and not claimed: PostgreSQL-backed integration suites (`tests/integration`), packaging and installer evidence, visual/accessibility/UAT review, and any provider/licence validation.

## Risks / STOP CONDITIONS

- Wave 2 must not start without an explicit decision (master-prompt gate). Recorded as conflict C3 with the resolution "HELD".
- Findings C5-C8 touch live enforcement. Changing them narrows or redirects existing authority and is therefore never a silent refactor: each needs an ADR amendment or a superseding record plus the security suite, and the legacy-principal behaviour is pinned by `tests/security/test_identity_row_entitlement.py`.
- The Wave 1 contracts are now normative for interaction. Any page migration that contradicts them (a new top-level page for an object, a second global context owner, an AI button outside the five canonical actions) is an architecture violation, not a style preference.
- Two Wave 1 registry decisions are judgement calls that a review may revisit: the pattern assigned to `orders` (ANALYSE) and `manual` (EXPLORE), and the classification of `sources`/`runtime` as MONITOR. They are recorded in `workspacePatterns.ts` with one-line rationales and are cheap to change.
- Pre-existing uncommitted `.automation/*` modifications remain unreviewed and unaccepted; they are not part of this slice.
- No STOP condition from `CODEX_ENTRYPOINT.md` was triggered: no commercial-data access broadened, no security control weakened, no accepted ADR materially changed except by the recorded autonomous supersession (ADR-0016), no destructive migration, no new infrastructure, no Web/Desktop business divergence, no scope crossing into execution/nomination/settlement, and no release/DR/security foundation removed.

## Resume instruction

Read `CODEX_ENTRYPOINT.md`, `AUTONOMOUS_EXECUTION_POLICY.md` and this checkpoint; verify HEAD, branch and working tree; inspect drift since `dd1abe1`.
Wave 0 is closed and accepted; Wave 1 is delivered and validated. Do not re-do either.
The exact next action is the Wave 2 authorisation decision recorded under "Current / next task"; until it is taken, continue only with work that cannot change authority (documentation, fitness functions, Wave 1 conformance checks).
