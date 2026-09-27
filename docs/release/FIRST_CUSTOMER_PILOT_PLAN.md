# First Customer Pilot Plan

Date: 2026-09-28. Baseline: `42d8144` (repository HEAD when this was written).
This was a planning and read-only reconciliation pass: no source behaviour was
changed, no database was read or written, no credentials were used.
Disposition: **pilot not yet approved; production not approved.**

This is the single current scope, acceptance and blocker register for the first
controlled customer pilot. It reuses the existing release gates
([GA release gates](GA_RELEASE_GATES.md), `scripts/release/policy/stable_gate_policy.json`,
`python scripts/release/validate_stable_release.py`) and the existing CI and
browser-acceptance workflows. It creates no competing approval system, adds no
new gate IDs for existing gates and expands no product scope; it is not legal
advice, certification or vendor comparison.

Evidence classes: **engineering acceptance** (focused suites, builds and CI jobs
here, on the stated fixtures and SHA); **controlled pilot approval** (a written
decision by the accountable role that the named boundary may run with customer
data, supported by the populated and external evidence each blocker names - CI
alone never grants it); **production approval** (unchanged and out of scope:
stable promotion stays fail-closed, and the audit disposition **NOT APPROVED FOR
CUSTOMER PRODUCTION**, audit 19, remains current).

No `PASS` may be written into a gate evidence file without the named exercise.
Simulation output (`_Sim` provenance, `-EnableSimulatedPrices`) is test evidence
only and is never provider or live-market acceptance.

## Delivery decision (proposed - owner decision required)

- **D-PILOT-1 (proposed): browser-first pilot.** Deliver the server runtime, the
  operator ZIP and a supported browser client; the Tauri desktop client joins
  only after actual native evidence exists (no Rust toolchain here, Wave 10
  native work unimplemented, packaging only in release CI). Choosing desktop
  adds G5 plus clean-machine install/upgrade evidence as hard dependencies.
- Accountable role: product owner. Exit: decision recorded; the milestone
  dependencies move with it. This plan does not silently approve desktop scope.

## Provisional pilot boundary (conservative)

- One customer, one isolated deployment (single tenant). **No shared
  multi-organisation or desk-isolation claim**: organisation/portfolio scope
  kinds remain unsupported and are reported as such by
  `ExperienceProfile.unsupported_scope_kinds`.
- European gas decision support only: market evidence to portfolio, constrained
  alternative review, reproducible strategy comparison. Power is deferred, and
  expensive model training is deferred and must not appear as pilot acceptance.
- Retained architecture: FastAPI backend, React web client, PostgreSQL/Alembic
  store, thin Tauri host. No execution, order entry/routing, nomination
  submission, settlement or ETRM behaviour; the product boundary in
  [Release readiness](RELEASE_READINESS.md) stays binding.
- Licensed external data only through backend ingestion under the customer's
  rights; undecided rights mean public/entitled sources only, stated as such.

## Pilot workflows (must be populated, not seeded-only)

Current evidence is dominated by seeded/CI fixtures. Each workflow states what
is proven today and the exercise that closes the gap.

### WF-1 - market evidence to portfolio

- Surfaces: market cockpit over `GET /projections/market-context` and portfolio
  over `GET /projections/portfolio-snapshot`
  (`src/eurogas_nexus/api/routes/public/projections.py`).
- Proven: scoped hub-board price evidence with bid/ask units from the
  authenticated projection; portfolio read lifecycle; EN/ZH three-viewport
  browser sweep on seeded fixtures.
- Not proven: populated physical rows (capacity/orders/PnL), later pages, sort
  correctness, or coverage beyond the six declared hubs and displayed tenor.
- Exercise: read-only walk-through on the populated deployment that compares
  displayed gas day, product and hub against both underlying reads, keeps as-of
  instants explicit, and records what an empty/unread read looks like.

### WF-2 - constrained alternative review

- Surfaces: route-cost what-if, resource-pool optimisation
  (`src/eurogas_nexus/application/resource_pool.py`,
  `tests/optimization/test_portfolio_network_optimizer.py`), review task over
  `GET /projections/review-context`, decision cases with evidence.
- Proven: exact min-cost flow with persisted run/snapshot identity; constraint
  and infeasibility disclosure; review task rejects superseded responses.
- Not proven: populated attribution rows, capacity joined-row coverage on
  filtered or later pages, populated storage/LNG views.
- Exercise: challenge one proposed allocation end to end, reproduce its evidence
  by re-reading recorded references, and confirm stale/restricted inputs block
  recommendations and the audit chain names an independent decision actor.

### WF-3 - reproducible strategy comparison

- Surfaces: Strategy Lab backtest with freeze/fork, analysis snapshots
  (`0034_analysis_snapshots`), snapshot citation verified before work and
  recorded on every run path.
- Proven: deterministic backtest contracts (`clients/web/tests/goldenWorkflow.test.ts`);
  citation verified before provider work and recorded durably.
- Not proven: populated strategy comparisons on customer data, walk-forward
  evaluation and leakage controls for a populated dataset.
- Exercise: compare two frozen versions on one populated dataset, re-read the
  recorded snapshot reference, and state uncertainty and costs, not PnL alone.

## Milestones

| # | Milestone | Entry dependency | Exit evidence | Reused gates |
| - | --------- | ---------------- | ------------- | ------------ |
| M1 | Scope freeze | this plan reviewed | recorded boundary + D-PILOT-1 decision | - |
| M2 | Three populated workflows | M1; populated deployment access | WF-1..WF-3 exercises recorded (EN/ZH), simulation labelled | G2, G3, G4, G14 + browser acceptance in `ci.yml` |
| M3 | Authority and security | M1; proceed alongside M2 | identity posture evidence, entitlement denials, elevation dual control, persisted MCP/service identity or backend-enforced disabling of affected capabilities | G8, G15, G18 |
| M4 | Artifact install/upgrade/restore + evidence binding | M1; briefs PILOT-A/B below | extracted-bundle preflight, immutable-image boot + migration, upgrade/rollback/restore drill, same-SHA/digest evidence | G1, G3, G5, G6, G7, G11, G12, G13, G17 |
| M5 | Coherent trader HMI | M2 | populated-persona sweep covering the audit's HMI contract items 1-5, including error and expiry paths | browser acceptance job |
| M6 | Customer assurance docs | M3-M5 evidence | handover pack: install/upgrade/DR runbooks, release notes and known issues, licences/notices, owner-reviewed applicability register | G9, G10, G16 + handover docs |

## Numerical reference cases

Each pilot workflow must reproduce these classes on the deployment before
numerical acceptance. Existing deterministic anchors:

| Case | Anchor today | Pilot must additionally reproduce |
| ---- | ------------ | --------------------------------- |
| FX conversion | `tests/unit/test_route_cost_fx_conversion.py`; no-currency-mixing invariant (mismatched pairs fail closed) | entitled FX rates on the deployment |
| Units and products | `tests/unit/test_route_cost_market_price_selection.py` (quote type/units) | displayed unit and quote type per populated hub/tenor |
| Gas day and DST | `tests/unit/test_gas_day.py`, `tests/unit/test_nomination_window_occurrence.py` (23/25-hour gas days, window wrapping UTC midnight) | the customer gas day boundary on the deployment calendar |
| Timezone normalization | `tests/ingestion/test_source_timezone_contract.py` (CET 06:00 to 05:00Z, CEST 06:00 to 04:00Z, DST switch days, refusal cases) | live source timestamps as delivered on the deployment |
| Cost | `tests/unit/test_route_cost_european_public_tariffs.py`, `tests/unit/test_route_cost_tariff_models.py` | populated tariff inputs and their stated basis |
| Capacity | `tests/unit/test_route_cost_capacity_requirement.py`; joined-row browser evidence from `873a9fa` | populated physical rows with both reads, filters and later pages |
| Point-in-time | `tests/api/test_research_data_api.py`, `tests/api/test_analysis_snapshot_citation_api.py`; immutable dataset snapshots | one populated dataset compared against a re-read snapshot reference |

## Blocker register

Reconciled against code at `42d8144` on 2026-09-28 by reading the cited files.
Severity: P1 blocks pilot, P2 important, P3 tracked. Accountable roles are
roles, not invented people. CA IDs are the audit's; PB IDs are pilot-specific.

| ID | Sev | Accountable role | Evidence inspected now | Verification / exercise | Exit condition | Dependency | Status |
| -- | --- | ---------------- | ---------------------- | ----------------------- | -------------- | ---------- | ------ |
| CA-02 | P1 | Release engineering | `scripts/release/validate_stable_release.py::load_evidence` still accepts any syntactically valid `status` from any file; no SHA, digest, issuer, age or environment check | `python -m pytest tests/release/test_customer_release_boundary.py -q` covers only channel inheritance today; PILOT-B adds envelope tests | Gate evidence carries a versioned envelope binding commit SHA, artifact/bundle digest and workflow identity; mismatches fail closed | PILOT-A (identity exists first) | Open - re-confirmed in code, not assumed from the old audit |
| CA-03 | P1 | Release engineering | `release.yml` web job runs `npm test` before build and packaging; `tests/release/test_customer_release_boundary.py::test_release_web_tests_precede_build_and_packaging` holds the order. `release.yml` contains no browser-acceptance job, so publication is not tied to the same-SHA browser result | Inspect `release.yml` job graph; PILOT-B adds same-SHA evidence binding | Publication consumes browser/critical acceptance evidence for its own SHA | CA-02 envelope | Partially fixed - frontend suite added; same-SHA binding open |
| CA-05 | P1 | Platform security | `src/eurogas_nexus/mcp/server.py` builds principal/role/scopes from `EUROGAS_NEXUS_AGENT_*` environment values and its own docstring declares calls are not re-authorised per user; checkpoint still lists organisation/portfolio/market/region scope as unsupported | Read module + `GET /api/me` scope report; pilot decision record | Pilot is single-customer, MCP is disabled or recorded as not offered; persisted service identity (D7) implemented or explicitly deferred | Pilot decision; ADR for service identity | Open - pilot-scope mitigation only, not closed |
| CA-06 | P1 | Release engineering | `assemble` downloads `image-metadata` explicitly and validates the digest by regex; `container-acceptance` runs `docker buildx imagetools inspect` and greps platforms, then writes `release-evidence/container-acceptance.json` with status PASS ("multi-arch digest inspected") | Read jobs at `release.yml` assemble/container-acceptance; add boot/migration/smoke exercise | Immutable digest boots, Alembic upgrades to head, authenticated read smoke passes, evidence assembled end to end in CI | PILOT-A identity; populated tenant not required | Partially fixed - metadata download and digest validation done; acceptance depth open |
| CA-10 | P1 | Deployment engineering | Literal TAB removed in PILOT-A at both entry points (and the same defect in the maintainer `build_release.ps1`); the operator ZIP policy (schema 2) ships eleven members: the ten reviewed files plus one generated `release-identity.json` (schema version, app/release version, channel, full commit SHA, API image `repository@sha256:` digest); the `deployment` workflow job now needs the `runtime-image` job and packages the ZIP from the resolved `release-context.json` plus the validated image-metadata digest | `python -m pytest tests/release -q` (108 passed, 3 Windows-symlink skips): real archive identity fields, fail-closed missing/malformed/conflicting identity and digest, no literal TAB, PowerShell parse of both entry points, extracted-bundle `Preflight` on a real temporary ZIP (identity resolves, `release_identity_source=bundle`, honest host blockers) | Bundle carries explicit release identity (version, channel, commit SHA, API image digest); the final ZIP SHA-256 stays external in `SHA256SUMS`/`release-manifest.json`, never inside the archive; extracted preflight resolves it with no source checkout or manual env var | None | Fixed in code, engineering acceptance only: extracted preflight resolves identity and reports host blockers; the runtime primitive's *complete* positive preflight is unverified in this sandbox (WMI access denied, docker engine pipe unreachable - pre-existing host-probe behaviour outside PILOT-A); no installation, upgrade or production-release acceptance claimed |
| PB-01 | P1 | Engineering + data operator | Checkpoint records that capacity and market acceptance ran on empty/seeded CI fixtures and do not cover populated rows, later pages or live acceptance | WF-1..WF-3 exercises on the populated deployment, read-only, no invented runtime observations | Populated exercises recorded with both underlying reads and row identity | Customer deployment access | Open - blocked on populated environment |
| PB-02 | P1 | Owner + legal (via customer contract) | Research/data-foundation code distinguishes entitlement but no contract decision exists in-repo | Owner-reviewed per-source rights decision | View/derive/export/LLM/training rights recorded per source family | Customer contract | External decision required - no legal claim made here |
| PB-03 | P1 | Security owner + customer IT | `GET /api/health` reports enforced authentication; OIDC/JIT paths exist; no real issuer acceptance exists | Real-IdP sign-in, revocation drill, external security review on the deployment | G15/G18-style evidence produced against the customer environment | Customer IdP and environment | External - not started |
| PB-04 | P2 | HMI owner + engineering | Browser sweep is CI-honest but seeded; populated read-to-render assertions remain open | Populated-persona sweep per audit HMI contract items 1-5 | Populated walkthrough at 1440x900 and 1920x1080, EN and Mandarin, with error/expiry paths | PB-01 | Open |
| PB-05 | P2 | Release owner | Code signing is explicitly `unsigned_pending_external`; G17 stays PENDING_EXTERNAL | Supply organization signing credential and verify Authenticode | Signed installer evidence for the pilot artifact | Organization certificate | External - operator-owned |
| PB-06 | P2 | Owner + legal | Audit records CRA/GDPR/DORA/NIS2/AI Act questions as applicability-dependent | Owner-reviewed applicability register for this customer and deployment model | Register recorded; no certification or conformity claim made | Customer entity, deployment model | External decision required |
| PB-07 | P3 | Engineering | No Rust toolchain in this environment; Wave 10 native features unimplemented | Native evidence only if D-PILOT-1 chooses desktop | Desktop evidence exists, or desktop is explicitly out of pilot scope | D-PILOT-1 | Tracked |

## Next two implementation briefs (bounded; parent reviews the schema)

### PILOT-A - extracted deployment bundle identity and preflight (do first)

- Why first: every later evidence record needs a stable artifact identity, and
  CA-10 is reproducible today on this Windows machine.
- Objective: the operator ZIP carries one machine-readable release identity
  (version, channel, commit SHA, API image digest). The final ZIP SHA-256 lives in
  an external checksum/provenance record; it cannot hash itself inside the ZIP.
  Both Windows
  entry points resolve the package version from that identity, fail closed with
  a clear message when it is missing or inconsistent, and never read a
  source-checkout-only path. Remove the literal TAB defect. Extracted-bundle
  `Preflight` must resolve identity with no source checkout and no manually set
  `EUROGAS_NEXUS_VERSION`, then report its real remaining blockers.
- Files: `scripts/install/windows/Deploy-EurogasNexus.ps1`,
  `scripts/install/windows/Install-EurogasNexusServerRuntime.ps1`,
  `scripts/release/package_deployment_bundle.policy.json`,
  `scripts/release/package_deployment_bundle.py` (identity entry validation and
  generation), `scripts/release/package_deployment_bundle.START-HERE.txt`,
  the ZIP assembly in `.github/workflows/release.yml` and the already-resolved
  context from `scripts/release/resolve_release_context.py`.
- Focused tests: extend `tests/release/test_deployment_bundle_policy.py`
  (identity file present in the real archive with exact fields; no literal TAB;
  every shipped path resolves inside the bundle) and
  `tests/release/test_deployment_roles.py` (version resolution), then
  `python -m pytest tests/release -q`, a PowerShell parse check of both scripts
  and one real preflight run over the extracted archive as a manual exercise.
- Non-goals: no new infrastructure, no silent Docker installation, no secrets in
  the bundle, no installer behaviour change beyond identity resolution, no
  claim that the ZIP is installation-approved.

### PILOT-B - same-SHA/digest gate evidence binding (do second)

- Why second: it binds evidence to the identity PILOT-A creates; it is the
  enabler for CA-02, the CA-03 remainder, CA-06 depth and every M4 gate record.
- Objective: versioned evidence envelopes for gate evidence files, carrying at
  least: schema version, gate id, commit SHA, artifact/bundle digest, workflow
  run identity (id/URL where available), producing environment and produced-at
  time. `load_evidence` validates the envelope against the release context:
  missing, malformed, old-format or mismatched SHA/digest evidence can never
  read as PASS (external gates stay PENDING_EXTERNAL). Evidence writers emit v2
  envelopes; web build evidence ties to the same-SHA CI/browser result.
- Files: `scripts/release/validate_stable_release.py`,
  `scripts/release/policy/stable_gate_policy.json` (declare required envelope
  fields per gate type), `.github/workflows/release.yml` (writers near the
  postgres/performance, vulnerability and container-acceptance steps, and the
  assembly call), `.github/workflows/ci.yml` only if a same-SHA artifact must be
  consumed by the release run.
- Focused tests: new `tests/release/test_evidence_envelope.py` covering
  present/absent/mismatched SHA, missing digest, malformed and old-format
  envelopes, and a valid envelope; keep `tests/release` green.
- Non-goals: never fabricate PASS, do not flip any external gate, do not change
  channel inheritance (CA-01 behaviour), no new infrastructure or datastore.

## What this plan does not claim

Not a pilot or production approval; not legal advice; no certification. No
populated, provider, live-market or native-desktop acceptance follows from any
green CI run or unit test. Reconciliation here is code reading at `42d8144`, not
a penetration test, full source audit or customer-environment execution.
