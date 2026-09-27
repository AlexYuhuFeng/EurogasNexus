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
CA-02/CA-03/CA-06 were re-checked in code at `308797e` by PILOT-B; the other
rows are the `42d8144` reconciliation.

| ID | Sev | Accountable role | Evidence inspected now | Verification / exercise | Exit condition | Dependency | Status |
| -- | --- | ---------------- | ---------------------- | ----------------------- | -------------- | ---------- | ------ |
| CA-02 | P1 | Release engineering | PILOT-B replaced `load_evidence`: every gate evidence file must now be a schema-version 2 envelope (gate id, full 40-hex tested commit, typed subject with precise digest(s), producer workflow/job/run identity, environment, UTC timestamp) verified against the release context and the actual bundle, never against values declared in the same file; status-only/v1, non-object JSON, wrong gate id, foreign/short SHA, artifact relabelling, stale/future timestamps, unapproved producers and unapproved `NOT_APPLICABLE` fail closed, missing files stay PENDING_EXTERNAL | `python -m pytest tests/release -q` (149 passed, 3 Windows-symlink skips), including the new `tests/release/test_evidence_envelope.py` malformed/foreign/stale/unapproved/valid matrix and the writer CLI; focused Ruff passed | Gate evidence carries a versioned envelope binding commit SHA, artifact/bundle digest and workflow identity; mismatches fail closed | PILOT-A (identity exists first) | Fixed in code, engineering acceptance only: binding and negative cases pass; producer/approval fields are self-declared text (not cryptographic provenance) and external approval identities remain unconfigured |
| CA-02 | P1 | Release engineering | PILOT-B replaced `load_evidence`: every gate evidence file must now be a schema-version 2 envelope (gate id, full 40-hex tested commit, typed subject with precise digest(s), producer workflow/job/run identity, environment, UTC timestamp) verified against the release context and the actual bundle, never against values declared in the same file; status-only/v1, non-object JSON, wrong gate id, foreign/short SHA, artifact relabelling, stale/future timestamps, unapproved producers and unapproved `NOT_APPLICABLE` fail closed, missing files stay PENDING_EXTERNAL. PILOT-B2 additionally re-derives G1's claimed CI run from the read-only GitHub API (`scripts/release/ci_run_verification.py`) | `python -m pytest tests/release -q` (196 passed, 3 Windows-symlink skips), including the PILOT-B2 matrix in `tests/release/test_ci_run_verification.py`; focused Ruff passed; one live read-only API verification of commit `4d30987` run `36345939410` observed (see the PILOT-B2 record) | Gate evidence carries a versioned envelope binding commit SHA, artifact/bundle digest and workflow identity; mismatches fail closed | PILOT-A (identity exists first); API binding for the other CI producers is still open | Partially fixed, engineering acceptance only: G1's claim is API-verified, but G2/G3/G4/G12/G19 producer run identity is still self-declared text (not cryptographic provenance) and external approval identities remain unconfigured |
| CA-03 | P1 | Release engineering | `release.yml` web job runs `npm test` before build and packaging and records a same-SHA G4 envelope. PILOT-B2 makes the `validate` job record G1 from the read-only GitHub API for the exact commit's `ci.yml` push run and makes `validate_stable_release.py` re-derive it: completed/successful run, matching attempt, and all five required jobs - including `Browser acceptance (EN/ZH, 3 viewports)` - successful, never skipped. PILOT-C runs that same validator in `publish-preview-rc` before its `gh release create` and makes G1 required for every published channel | `tests/release/test_ci_run_verification.py` (wrong repo/workflow/SHA, failed/incomplete/skipped/missing jobs, pagination, stale attempt, malformed/API error, forged copy, local-dry-run bypass, writer round trip); policy/workflow job-name contract test; live read-only verification of run `36345939410`; `tests/release/test_publication_gate_enforcement.py` (channel inheritance, parsed publish-step ordering and credentials, executed gate command fails without evidence, replayed step sequence never reaches the mocked release write) | Publication consumes browser/critical acceptance evidence for its own SHA, verified via authoritative GitHub run metadata | CA-02 envelope (done); release-run exercise of the writer/validator (not yet performed) | Partially fixed - same-SHA browser-acceptance binding exists, and PILOT-C makes every publish job consume the gate before writing a release; preview/RC now block on their mandatory evidence instead of publishing ungated; no release run has exercised the writer or gate |
| CA-05 | P1 | Platform security | `src/eurogas_nexus/mcp/server.py` builds principal/role/scopes from `EUROGAS_NEXUS_AGENT_*` environment values and its own docstring declares calls are not re-authorised per user; checkpoint still lists organisation/portfolio/market/region scope as unsupported | Read module + `GET /api/me` scope report; pilot decision record | Pilot is single-customer, MCP is disabled or recorded as not offered; persisted service identity (D7) implemented or explicitly deferred | Pilot decision; ADR for service identity | Open - pilot-scope mitigation only, not closed |
| CA-06 | P1 | Release engineering | `container-acceptance` inspects the immutable digest and platforms and now writes a G19 envelope binding that image digest; the validator recomputes it against `image-metadata.json` and `release-manifest.json`, and `assemble` waits for the job so the evidence is inside the bundle | Read jobs at `release.yml` assemble/container-acceptance plus the new envelope tests; boot/migration/smoke exercise still absent | Immutable digest boots, Alembic upgrades to head, authenticated read smoke passes, evidence assembled end to end in CI | PILOT-A identity; populated tenant not required | Partially fixed - digest inspection and binding done (G19 required for RC/stable); boot/migration/smoke acceptance depth open |
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

## PILOT-B implementation record (engineering evidence only, 2026-09-28)

Baseline `308797e`. Bounded change; no release, tag, publish, deployment,
database migration, credential, commit or push. What the code now does:

- `scripts/release/evidence_envelope.py` defines the schema-version 2 envelope:
  gate id, status, full tested commit SHA, typed subject (`source` / `artifact`
  / `image`) with precise digests, producer workflow/job/environment/run
  identity, `produced_at_utc`, and an optional approval block.
- `scripts/release/validate_stable_release.py` verifies each envelope against
  the trusted release context and the actual bundle: commit SHA equality,
  subject kind matching the policy declaration, artifact digests recomputed
  from the shipped files, image digest compared with `image-metadata.json` and
  `release-manifest.json`, producer profile allowlist, GitHub run identity for
  CI producers, and a 30-day freshness window with 15-minute future skew.
  Missing files stay PENDING_EXTERNAL; old-format/status-only and non-object
  JSON, wrong gate id, foreign or short SHA, source/artifact relabelling,
  unapproved `NOT_APPLICABLE`, unapproved producers and unauthorised external
  PASS all fail closed.
- `scripts/release/policy/stable_gate_policy.json` (schema 2) declares the
  subject kind, producer profiles and `not_applicable_allowed: false` for every
  gate, adds G19 (image-digest-bound container acceptance, RC/stable), and
  keeps `authorized_external_approvals` empty, so no external gate can pass
  until the organisation configures a real approval identity.
- `scripts/release/write_gate_evidence.py` is the single CI writer.
  `release.yml` writers (validate, reliability, dependency-scan, web, assemble,
  container-acceptance) all emit envelopes bound to `$GITHUB_SHA`; `assemble`
  now waits for `container-acceptance` so the bound evidence is inside the
  assembled bundle; the stable gate invocation does not pass the local-only
  flag (contract-tested).
- `scripts/release/run_release_dry_run.py` writes local-only envelopes
  (`run_release_dry_run.py`, environment `local-dry-run`) that strict
  validation rejects, so local evidence can never authorise publication. The
  dry run no longer records PASS for checks it does not perform: the Python
  suite and the PostgreSQL migration drill are PENDING_EXTERNAL locally, and
  the security-tests status now comes from actually running
  `scripts/security/run_security_acceptance.py`.

Focused validation: `python -m pytest tests/release -q` -> 149 passed, 3
Windows-symlink skips (including the new `tests/release/test_evidence_envelope.py`
matrix: malformed/non-object JSON, wrong gate/SHA/digest, missing metadata,
expired/future timestamps, unapproved producer and external approval,
NOT_APPLICABLE bypass, valid scoped evidence, missing files); focused
`ruff check scripts/release tests/release tests/contract` passed. No CI run,
release publication, installation or deployment was performed, so this is code
and focused-test evidence only - the first RC/release run must be observed
before CI-level acceptance is claimed.

Trust boundary and residual work (not claimed as solved):

- Envelope producer/approval fields are self-declared text. The validator binds
  them to policy-declared profiles and to a run-URL shape for this repository,
  but an actor who can write into the evidence directory could still copy an
  authorised identity string. Signed attestation and authoritative GitHub-run
  metadata verification remain open.
- CA-03's same-SHA browser result is deliberately not integrated as a file
  check: publication must not infer CI success from an arbitrary artifact.
  Consuming the `ci.yml` browser-acceptance result for the tagged SHA requires
  GitHub API run metadata and is recorded as the separate submilestone
  PILOT-B2. Publication stays blocked meanwhile (G1/G6/G7/G13 have no CI
  evidence source yet and every external gate is PENDING_EXTERNAL).
- Configuring a real approval identity in `authorized_external_approvals` is an
  owner/legal decision (PB-03/PB-05); this change invents neither an identity
  nor a credential.
- Local dry-run evidence cannot authorise release and the local gate report
  therefore stays red until the corresponding CI evidence exists.

## PILOT-B2 implementation record (engineering evidence only, 2026-09-28)

Baseline `75e98a5`. Bounded change; no release, tag, publish, deployment,
database migration, credential, commit or push. What the code now does:

- `scripts/release/ci_run_verification.py` is the single read-only GitHub API
  verification. It contacts only `api.github.com`, only under
  `/repos/<owner>/<repo>/`, only for the policy's trusted repository, workflow
  path, event and required-job list, with a request timeout, a bounded retry
  count for transient/5xx/429 responses, bounded pagination and no credential
  echoed into output or errors. It discovers the `ci.yml` push runs for the
  exact release commit, requires every one of them to be `completed`/`success`
  (so a pending or failed re-run blocks), and reads the verified attempt's jobs
  from the attempt-specific jobs endpoint - never `filter=latest`, which can
  switch attempt between the run read and the jobs read. After the jobs read it
  re-reads the run and refuses any change to attempt, status, conclusion or
  head SHA, so a re-run that lands mid-verification is rejected rather than
  half-accepted. Each required job must be present exactly once with
  `completed`/`success` - skipped, missing or failed jobs never count. A
  declared run id, attempt or URL that disagrees with the API is refused, so a
  stale attempt or a copied/forged envelope cannot pass. HTTP redirects are
  refused by a custom no-redirect opener (any 3xx fails closed), because
  urllib's default redirect handling re-sends the `Authorization` header to the
  `Location` target, which is not limited to `api.github.com`; tests prove no
  second request is issued for cross-host or same-host redirects.
- The claim itself is never authoritative. The envelope's `detail`, URL and
  metadata are inputs to compare against the API response, never the source of
  truth; a missing, pending, failed, malformed or unreachable result stays
  blocked and there is no offline-success fallback (test fixtures are injected
  only in unit tests).
- `scripts/release/write_ci_run_evidence.py` is the writer used by the release
  `validate` job: it records what the API reports for `$GITHUB_SHA`, writing
  `PASS` only with the verified run identity under `report.ci_run`, and
  `FAIL`/`PENDING_EXTERNAL` otherwise. `validate` (the writer) and
  `publish-stable` (the strict gate re-derivation below) are the only jobs that
  carry `actions: read`, and only their CI-verification steps receive
  `GH_TOKEN`; every other job keeps its existing permissions and channel
  inheritance.
- `validate_stable_release.py` re-derives G1 from the API whenever the evidence
  claims PASS - including under `--allow-local-dry-run-evidence`, so the local
  exception cannot bypass strict release verification. The reported
  repository/context binding is also checked: a policy or `--repo` outside the
  trusted repository fails closed.
- `scripts/release/policy/stable_gate_policy.json` (schema 2) declares the
  `ci_acceptance` contract (repository, host, workflow path, event, required
  jobs, bounds) and the `ci-verification` producer profile; `G1` keeps
  `required_for: rc` and `authorized_external_approvals` stays empty.
  Desktop packaging is deliberately not a required job: the main-branch run
  reports it as skipped and native packaging is not pilot acceptance.

Focused validation: `python -m pytest tests/release -q` -> 196 passed, 3
Windows-symlink skips, including the new `tests/release/test_ci_run_verification.py`
matrix (wrong repository/workflow/SHA; failed, incomplete, skipped and missing
jobs; multiple pages of runs and jobs; stale run attempt; the re-run race
between the run read and the attempt-pinned jobs read; malformed payload and
HTTP failures; a forged copy of a valid envelope; a policy/workflow job-name
contract that fails on drift; the writer round trip; transport host/credential/
retry bounds and redirect refusal with no second request) and the preserved
negative envelope tests. Focused
`ruff check scripts/release tests/release .github` passed. One read-only live
API verification was performed with the production transport for commit
`4d30987` (CI run `36345939410`, attempt 1): the verdict recorded the five
required jobs, including `Browser acceptance (EN/ZH, 3 viewports)`, as
successful; an unknown-SHA check and a tampered `report.ci_run.run_id` were
both refused. The redirect-refusal and attempt-pinning corrections in this pass
were validated with fixture transports only (including a real `urllib` opener
with a stubbed network leg); no new live API call was made. No release
workflow, publication or deployment was executed, so this remains code,
focused-test and read-only API evidence - the first RC/release run must be
observed before CI-level acceptance is claimed.

Residual and limits (not claimed as solved):

- The other release-run envelopes (G2/G3/G4/G12/G19) still carry self-declared
  producer run identity; only G1's subject is re-derived from the API. CA-02 is
  not claimed closed.
- This verifies the *source commit's* CI run - including browser acceptance on
  the exact commit - not acceptance of the packaged artifact, image or
  installed bundle, and not populated, provider, live-market or native-desktop
  acceptance.
- No release run has exercised the writer or the strict gate; release
  publication was not attempted. The preview/RC publish job still does not
  consult the gate policy, so CA-03's publication-time consumption is enforced
  for the stable path only.
- Required job names are the exact names the Actions API reports; renaming a
  `ci.yml` job requires a reviewed policy update, and the contract test fails
  until they agree.
- External approval identities remain unconfigured (`authorized_external_approvals`
  is empty), so every external gate stays PENDING_EXTERNAL and stable
  publication stays blocked.

## PILOT-C implementation record (engineering evidence only, 2026-09-28)

Baseline `efa7514`. Bounded change; no release, tag, publish, deployment,
database write, credential use, workflow dispatch, commit or push. What the
code now does:

- `publish-preview-rc` runs the same gate as `publish-stable` before its
  `gh release create`: `scripts/release/validate_stable_release.py` against the
  assembled `release-final` bundle. The job gains only `actions: read` (for
  G1's read-only API re-derivation) and the step-scoped `github.token`; there
  is no `--allow-missing-platform-artifacts`, no
  `--allow-local-dry-run-evidence`, no `continue-on-error` and no conditional
  `if:` on the gate or the publish step, so a failing gate stops the job before
  any release write.
- The gate is an exact-SHA and exact-bundle check: the envelope commit must be
  the release commit, artifact gates re-hash the shipped files, the image gate
  must match `image-metadata.json`/`release-manifest.json`, and G1's same-SHA
  CI claim is re-derived from the read-only Actions API. Preview/RC use the
  same validator and policy as stable - no parallel or weaker approval path.
- `stable_gate_policy.json` now declares `G1` with `required_for: all`, so
  preview, RC and stable each require the same-SHA browser/critical acceptance
  evidence for their own commit. Channel inheritance is unchanged: stable-only
  external gates (G15-G18) are still not demanded of preview or RC, stable
  still inherits every RC gate, and the signing policy is untouched.
- Consequence, recorded rather than worked around: preview/RC publication now
  blocks until its mandatory evidence exists. No CI job today produces G5
  (desktop packaging), G8 (security tests) or G10 (SBOM), and G11 (provenance)
  has no RC producer, so a preview/RC run fails the gate and publishes nothing.
  That is the intended fail-closed behaviour; the missing producers are
  follow-on work, and nothing was marked PASS or exempted to avoid it.

Focused validation: `python -m pytest tests/release -q` -> 203 passed, 3
Windows-symlink skips, including the new
`tests/release/test_publication_gate_enforcement.py`: policy inheritance across
all three channels (G1 required for each, stable-only externals not imposed on
preview/RC), parsed publish-step ordering and step credentials, no bypass flag
or `continue-on-error` anywhere in `release.yml`, the configured preview gate
argument vector executed for real against a fixture bundle with no evidence
(non-zero exit, G1 PENDING_EXTERNAL, mandatory-gates failure for preview), and a
replayed step sequence in which the failing gate stops the job before the
mocked `gh release create`. Required-job and permission contracts in
`tests/release/test_ci_run_verification.py` were updated for the new
`actions: read` holder. Focused `ruff check scripts/release tests/release .github`
passed. The release workflow itself was not dispatched or exercised.

Residual and limits (not claimed as solved):

- G5/G8/G10 (and G11 for RC) have no CI producer, so preview and RC remain
  blocked in practice. This change enforces policy; it does not create the
  missing evidence and does not claim desktop, security-acceptance or SBOM
  acceptance.
- The `runtime-image` job still pushes the API image to GHCR from `validate`
  alone, before the assembled-bundle gates exist. That registry write is
  outside this brief's `gh release` scope and is recorded as an open
  publication-path gap.
- G2/G3/G4/G12/G19 envelopes still carry self-declared producer run identity;
  only G1's claim is re-derived from the API.
- No release run has exercised the writer, the gate or the publish path, so
  CA-03's publication-time consumption is enforced in code and focused tests
  only.

## What this plan does not claim

Not a pilot or production approval; not legal advice; no certification. No
populated, provider, live-market or native-desktop acceptance follows from any
green CI run or unit test. Reconciliation here is code reading at `42d8144`, not
a penetration test, full source audit or customer-environment execution.
