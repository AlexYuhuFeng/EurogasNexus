# Release Readiness

## Current Status

**1.0.0-beta (2026-11-20): a beta for customer acceptance**, published on the `beta`
channel as the GitHub pre-release `v1.0.0-beta.1` (package version `1.0.0b1`; see
[RELEASE_CHANNELS.md](RELEASE_CHANNELS.md)). It is the build the customer installs for
acceptance, not a production (GA) release. Three gates stay **PENDING_EXTERNAL** and are not
passed: G15 (penetration test or independent security review), G16 (certification of each
licensed source under the customer's entitlement) and G18 (customer user acceptance).
1.0.0 (stable) follows customer acceptance. What the package contains:
[DELIVERY_PACKAGE_1.0.0-beta.md](DELIVERY_PACKAGE_1.0.0-beta.md); what changed:
[the 1.0.0 beta release notes](notes/1.0.0-beta-RELEASE_NOTES.md).

2026-09-22 commercial audit override: **NOT APPROVED FOR CUSTOMER PRODUCTION**.
The evidence below is historical, scoped to its dated ref, and does not certify
Architecture V2. Current findings and acceptance requirements are recorded in
[the commercial audit](../engineering/Architecture-V2/19_COMMERCIAL_ACCEPTANCE_AUDIT.md).
First-customer pilot scope, milestones and the current blocker register are in
[the first customer pilot plan](FIRST_CUSTOMER_PILOT_PLAN.md); it is planning,
not approval, and it reuses the gates below.

Status: `RELEASE CANDIDATE FOR TESTED LOCAL SCOPE`

Release marker: `RELEASE CANDIDATE`

Date checked: 2026-11-20 (1.0.0-beta: surface figure, schema head
`0076_gas_day_nominations` and packaging below re-measured at this commit). The CR-13 UAT
and CR-15 sections below are historical evidence for their own dated refs.

Eurogas Nexus passes the current local release-candidate shape for
backend/API/SDK/CLI, PostgreSQL runtime schema, Web workspace, Tauri desktop
shell, and the new release-evidence pipeline. This is **not** an official
production release and is **not** GA/stable. Stable promotion is fail-closed
until the external gates below have real evidence; no gate can be turned green
by a CLI flag.

## CR-13 UAT Evidence

- Golden workflows A/B/E exercised in a real browser against PostgreSQL 16
  UAT fixture (`eurogas_nexus_uat`): Market → Scenario, Portfolio → Optimize →
  Review, and Strategy create/freeze/backtest all complete.
- P0 found and fixed during UAT: PostgreSQL FK ordering failed for backtest
  attribution rows; regression test now proves events are flushed before
  attribution.
- P1 fixes: legacy `?workspace=review` deep link opened Scenario; raw backend
  warning codes were shown to users; company TSO access was not propagated to
  the optimizer; heading/landmark/contrast accessibility violations existed
  on every workspace.
- Accessibility: axe-core 0 violations across 13 workspace URLs after fixes;
  keyboard workflow smoke passes.
- AI/Copilot: 13/13 critical deterministic eval cases pass
  (`tests/evals/`); live DeepSeek grading remains PENDING_EXTERNAL.
- EN/zh-CN parity: 1,247 keys each, no missing keys, no unintended fallback.
- Long-session browser smoke: 60 workspace switches, zero errors, stable JS
  heap. Performance baseline on the dense UAT fixture: p50 44.5ms /
  p95 1668ms / p99 3099.5ms (inside hard thresholds; `/api/sources` is the
  dominant path and remains post-RC performance backlog).

## Latest Local Evidence

- Full local Python suite and Web tests/build: see `docs/product/SCHEDULED_AGENT_STATE.md`
  (updated after CR-15 validation).
- OpenAPI public surface: **299 paths / 334 operations**

  (2026-11-25: `GET /api/news` and `GET /api/news/{item_id}` (READ) and
  `POST /api/news/{item_id}/note` (GOVERNED, the AI use `news_note`; the rule note without a
  model), the NEWS-1 news and events reads; 296 / 331 before, after TAR-1 and SCHED-1.

  (2026-11-25: `GET /api/desk/gas-day/{gas_day}/reconciliation` (READ, `portfolio.read` in the
  handler), the SCHED-1 reconciliation of trades, confirmations and nominations; read only,
  `format=csv` under the export decision; 295 / 330 before, after TAR-1.

  (2026-11-24: TAR-1 adds `GET /api/tariffs`, `GET /api/tariffs/publishers` and
  `GET /api/capacity/notices` (all READ, entitlement-filtered by publisher family; a terminal
  operator whose terms need the firm's permission is left out until it is recorded); 292 / 327
  before. Earlier the same day: `GET /api/imports/contracts` (READ) and `POST /api/imports/{contract_id}/validate`
  (GOVERNED, stores nothing), the DATA-1 ETRM and ERP import contracts; 290 / 325 before.

  (2026-11-24: `GET /api/market/changes` (READ), the DATA-1 change feed: digests of market
  events after a cursor, entitlement-filtered per caller; 289 / 324 before.

  (2026-11-24: `GET /api/market/prices` (READ), the monthly price strip live or as known at
  an instant, DATA-1; 288 / 323 before.

  (2026-11-24: maker-checker (P-17), `GET /api/portfolio/change-requests` (READ; each person
  sees the proposals they made or may decide) and `POST
  /api/portfolio/change-requests/{change_id}/approve`, `.../reject`, `.../withdraw` (REVIEW; the
  handler requires a different authorised person, audited in the same transaction); 284 / 319
  before.
  2026-11-24: `GET /api/portfolio/credit-lines/{counterparty_id}` (REVIEW, risk function only)
  so the edit form reads every stored field before it saves; 284 / 318 before.
  2026-11-24: personal API keys, `GET`/`POST /api/me/api-keys` and
  `POST /api/me/api-keys/{key_id}/revoke` (READ; the handler limits each person to their own
  keys, an interactive sign-in creates them); 282 / 315 before.
  2026-11-24: LNG cargo in transit, `GET /api/lng/cargoes/plans`, `GET
  /api/lng/cargoes/{cargo_id}/plan`, `POST /api/lng/cargoes/{cargo_id}/plan/what-if` (READ) and
  `PUT /api/lng/cargoes/{cargo_id}/hedges` (GOVERNED, PORTFOLIO_WRITE); 278 / 311 before.
  2026-11-20: forward balance `GET /api/fundamentals/forward-balance` (READ); 277 / 310
  before)

  (2026-11-19: reviewed public transmission tariffs: `GET`/`POST /api/route-cost/tariff-entries`
  (READ; recording OPERATOR) and `POST .../{entry_id}/review` and `.../{entry_id}/withdraw`
  (OPERATOR, four eyes on review, audited); 273 / 305 before)

  (2026-11-19: My gas day checklist, `POST /api/desk/gas-day/status` (WRITE; portfolio.write
  held in the handler; a status of a step in the caller's own gas day, entered by hand,
  labelled and audited; nothing is nominated); 276 / 309 before)
  (2026-11-20: a contract's price for a delivery month, `GET
  /api/contracts/{contract_id}/price`, READ, book scope; +1 path / +1 operation.)

  (2026-11-19: tracked strategies and the intraday feed path: `GET`/`POST
  /api/research/strategy-tracks`, `GET /api/research/strategy-tracks/{track_id}`, `POST
  /api/research/strategy-tracks/{track_id}/stop` (GOVERNED family; strategy.read /
  strategy.shadow.manage held in the handler, owner-only), `POST /api/market/ticks` (OPERATOR,
  source.run) and `GET /api/market/prompt` (READ, market.read); paper only, no order;
  267 / 298 before)
  (2026-11-19: the deferred capabilities' routes are no longer served by default, design basis
  2 I.3 and decision L4: the dataset builder and the agents workspace, 21 paths / 22 operations
  behind `EUROGAS_NEXUS_DEFERRED_CAPABILITIES`; 287 / 319 before)

  (2026-11-18: `GET`/`PUT /api/reports/schedules`, scheduled reports; 284 / 315 before)
  (2026-11-18: LNG cargo economics, CP-12: `GET`/`PUT /api/lng/freight-routes[/{route_id}]`
  (READ; the PUT GOVERNED, versioned and audited) and `POST /api/lng/cargo-economics` (READ:
  computes, stores nothing); 280 / 311 before)
  (2026-11-18: the LNG terminal tariff register, four paths under `/api/lng/terminal-tariffs`
  (two READ, review OPERATOR, operator permission ADMIN); 276 / 307 before)
  (2026-11-18: `POST /api/research/spreads/interpret` and `/evaluate`, CP-16/CP-23 backend,
  GOVERNED like the rest of `/api/research/`; 274 / 305 before)
  (2026-11-18: `GET /api/market/instruments`, the instrument catalogue of CP-02, one READ path
  and operation; 272 / 303 before)
  (2026-11-17: assumption sets, firm marks and valuation snapshots, CP-07 of the commercial
  design basis 2: six paths and eight operations under `/api/assumption-sets` and
  `/api/market/`; 256 / 282 before)
  (2026-11-17: comparable prices — `GET /api/market/fx-forward` and `POST /api/market/normalise`,
  two READ paths and operations; 256 / 282 before)
  (2026-11-18: opportunities, CP-08 of the commercial design basis 2: seven paths and nine
  operations under `/api/opportunities`; 262 / 290 before)
  (2026-11-17: assumption sets, firm marks and valuation snapshots, CP-07 of the commercial
  design basis 2: six paths and eight operations under `/api/assumption-sets` and
  `/api/market/`; 256 / 282 before)
  (2026-11-18: first-run setup, `GET`/`PUT /api/setup` (ADMIN); 256 / 282 before)
  (2026-11-17: assumption sets, firm marks and valuation snapshots, CP-07 of the commercial
  design basis 2: six paths and eight operations under `/api/assumption-sets` and
  `/api/market/`; 256 / 282 before)
  (2026-11-17: local accounts and SSO pre-provisioning, four paths and six operations under
  `/api/auth/`, `/api/me/` and `/api/access/users`; 252 / 276 before)
  (2026-11-17: report library — delete, rename and bulk delete of stored reports — and the
  revoke of a public-source approval; 251 / 272 before)
  (2026-11-16: market reports, five paths under `/api/reports/`; 244 / 264 before)
  (2026-11-15: `GET /api/desk/today`, the Today read, added as a reviewed READ path)
  (functional branch adds task/model operations; no new release acceptance).
  (`/api/runtime/release`, CR-14 research data routes, CR-15 agent/capability
  routes, and the development-only `/api/dev/auth/login` added), pinned and
  permission-declared. Measure it rather than quoting this line:

  ```
  python -c "import sys; sys.path.insert(0, '.'); from apps.api.main import app; print(len(app.openapi()['paths']), sum(len(o) for o in app.openapi()['paths'].values()))"
  ```

  This line said 163 until 2026-10-07; the surface had grown by 19 paths and
  nothing compared the claim with the application, so a reviewer counting them
  found a discrepancy instead of a figure. The command above is the authority,
  and tests/contract/test_openapi_surface_claim.py fails when the two disagree.
- Version consistency: `python scripts/release/check_version_consistency.py`
  passes across pyproject, runtime module, Web/desktop package files,
  tauri/Cargo metadata, docs, install scripts, and the release workflow.
- Release dry-run: `python scripts/release/run_release_dry_run.py` produces
  `release-assets/release-manifest.json`, SPDX SBOMs, `SHA256SUMS`, signing
  state, vulnerability evidence, and a fail-closed gate report. The Server
  operator bundle is packaged only when the published repository manifest
  digest is supplied explicitly (`--image-digest sha256:...`):
  `--build-container` records the local image config id as a diagnostic only
  and never substitutes it for that published digest.
- Gate evidence is a schema-version 2 envelope (PILOT-B): gate id, full tested
  commit SHA, tested subject digest(s), producing workflow/job/run identity,
  environment and a UTC production timestamp, all re-verified against the
  release context and the actual bundle by
  `scripts/release/validate_stable_release.py`. Status-only, old-format,
  foreign, stale, future-dated, malformed, relabelled or unapproved evidence
  fails closed; a missing file stays PENDING_EXTERNAL; `NOT_APPLICABLE` and
  external PASS require explicit policy allowances (no approval identity is
  configured today, so all external gates stay PENDING_EXTERNAL). Local
  dry-run evidence is recorded with a local-only producer identity and is
  rejected unless the maintainer passes the local-only flag; it never
  authorises publication.
- Container runtime image remains non-root and is built with BuildKit
  provenance/SBOM in CI; local Docker acceptance recorded in the dry-run.

## Validated Gates

- App import remains DB-free and network-free.
- Release API profile disables docs/openapi endpoints.
- No development-only routes enabled in release profile.
- No silent local file fallback in trial or release mode.
- Stable client prefix is `/api`.
- PostgreSQL runtime validation can report connected, missing-table, and
  unavailable states without printing secrets.
- Web client builds and uses `/api` through the backend boundary.
- Windows desktop packages the same Web workspace through Tauri NSIS
  (perMachine); offline WebView2 configuration is provided and documented.
- Linux desktop release packaging is architecture-specific: x64 and ARM64 DEB
  packages are separate artifacts, not one ambiguous Linux package.
  ARM Linux users must not receive the x64 DEB by mistake. Both are built for every
  release channel (the desktop matrix in `.github/workflows/release.yml` has no channel
  condition).
- SDK and CLI remain API consumers.
- Clients do not connect directly to PostgreSQL.
- Authentication-first entry: the terminal no longer mounts before
  authentication. `/api/me` answers 401 when no credential is presented, the Web
  workspace resolves identity before any protected read and otherwise renders a
  dedicated sign-in screen, deep links/reload/session expiry/history stay gated,
  and just-in-time SSO provisioning registers a `PENDING` identity instead of
  granting access.
- Provider credentials are backend-owned: clients can submit keys to the
  backend, but plaintext keys are not returned or stored in client state.
- CR-10 adds Authorization Code + PKCE OIDC login, issuer+subject identity
  mapping, pre-provisioned default with optional approved-domain JIT,
  VIEWER/REVIEWER/ANALYST/OPERATOR/ADMIN RBAC, fine-grained permissions,
  server-side sessions, CSRF/origin protection, API-key lifecycle and audit
  hooks for identity/strategy/shadow/dataops/review actions.
- External LLM providers are disabled in trial/release environments; LLM
  payloads exclude contract financial fields unless explicitly opted in, and
  snapshot sources are entitlement-checked before any provider call.
- Economic decisions never mix currencies; mismatched resource/sale pairs fail
  closed.
- Gas-day boundaries follow CAM Article 3(16) through the corrected versioned
  calendar `EU-CAM-UTC-2025`.
- Resource-pool allocation is an exact min-cost flow; results persist input
  snapshots with `run_id`/`snapshot_id` evidence.
- Dependency versions are hash-pinned (`requirements*.lock`, npm
  `package-lock.json`, Rust `Cargo.lock` + `--locked`).
- CI runs migrations and DB-backed smoke tests against PostgreSQL 16 plus an
  in-process API load smoke with latency percentiles.
- CR-11 separates process liveness from mandatory readiness; dependency matrix,
  pool policy, restore drill, migration preflight, performance baseline/budget
  are operational evidence.
- CR-12 adds one canonical version contract with an automated consistency gate;
  hard-coded release filenames/tags were removed.
- CR-14 adds the research data foundation: executable energy ontology,
  point-in-time temporal semantics, versioned feature/target registries,
  bounded resampling, leakage validation, immutable dataset snapshots,
  Parquet/CSV export, and typed MCP-free agent capability contracts.
- CR-15 adds the agent-native capability layer: first-class capability
  registry, governed invocation runtime, registry-driven MCP adapter,
  ResearchPlan/StrategyIR/orchestrator/risk-challenger artifacts, AgentRun
  replay, and human-review gates. No execution capability exists.
- Preview/beta/RC/stable channel semantics are explicit; a beta publishes as an RC does. Stable can only originate
  from a pushed `vX.Y.Z` tag on the protected mainline and runs in the
  `production` GitHub Environment.
- `release-manifest.json` records version, channel, commit, schema revision,
  engine/schema versions, final SHA-256 hashes, signing state, SBOM refs,
  attestation ref, and immutable container digest.
- SPDX 2.3 SBOMs are generated from the enforced locks with lock-input hashes
  and scope disclosures in `sbom-manifest.json`; `THIRD_PARTY_NOTICES.md`
  states that license texts and container-image OS packages are out of scope;
  vulnerability scan evidence is separate from SBOM. Artifact-complete SBOM
  acceptance (G10) remains open.
- Release artifacts are covered by final `SHA256SUMS` (including the manifest);
  GitHub OIDC build provenance is generated over the final bundle.
- Windows code signing is not a release requirement (owner decision, 2026-10-31): each
  firm decides whether to sign the installers with its own certificate. The release
  records the signing state of every artifact; the optional signing hook stays available.
- Tauri updater is not shipped; managed/offline update policy is documented.
- `/api/runtime/release` exposes compatibility metadata and the client blocks
  incompatible client/server/API-contract states before partially-broken
  screens.
- Release workflow permissions are least privilege; actions/runners/toolchains
  are pinned according to `docs/release/RELEASE_ENGINEERING_SPEC.md`.
- Post-publication verification re-downloads the release and verifies
  checksums, attestations, and the container digest.

## Release Packaging

Every successful release workflow publishes:

- `Eurogas-Nexus-Client-{release_version}-windows-x64-setup.exe`
- `Eurogas-Nexus-Client-{release_version}-linux-x64.deb` (Linux DEB package for x64 Linux users)
- `Eurogas-Nexus-Client-{release_version}-linux-arm64.deb` (Linux DEB package for ARM64 Linux users)
- `Eurogas-Nexus-Server-{release_version}.zip`
- `eurogas-nexus-web-{release_version}.tar.gz`
- API container image for `linux/amd64` and `linux/arm64` (one multi-platform digest)
- `release-manifest.json`, `SHA256SUMS`, SPDX SBOM set,
  `THIRD_PARTY_NOTICES.md`, and GitHub attestation metadata.

Container image tags: the build pushes only a run-attempt-unique staging tag
(`candidate-<run_id>-<attempt>`); the customer-facing `X.Y.Z[-channel]` tag is
written only by the gate-first promotion job after a successful publish and
post-publication verification, by copying the tested multi-platform digest
(no rebuild), and the former `sha-<commit>` alias is retired. Deployment
manifests should prefer `@sha256:<digest>`; never use `latest` as rollback
identity. The Server operator ZIP carries one generated
`release-identity.json` (schema version, application/release version, channel,
full commit SHA, API image `repository@sha256:` digest) built from the resolved
release context and the published image digest; both Windows entry points
resolve the version from it and refuse a missing, malformed or conflicting
identity. The ZIP's own checksum is deliberately external (`SHA256SUMS`,
`release-manifest.json`) because an archive cannot hash itself.

## What Runtime DB Means In The Client

`Runtime DB` means the UI is reading a backend API process that can reach the
configured PostgreSQL runtime store. It does not mean every commercial provider
has been live-called or validated.

## Required Before Production Deployment

Status 2026-10-31. Automated in the release workflow (recorded per release, PASS or FAIL):
desktop packaging (G5), clean Windows install/launch/uninstall (G6), upgrade from the
previous release (G7), dependency and container CVE scans (G9), SBOM (G10), provenance
(G11), checksums (G12), backup/restore drill (G13), performance (G14), container
acceptance (G19). Code signing is not a requirement: each firm decides.

Still needed, and only people outside engineering can provide them:

- **External security acceptance (G15)** on a real deployment: penetration test or
  security review by the customer or an independent tester.
- **Commercial provider certification (G16)**: live tests of each licensed source the
  customer subscribes to (EEX, ICE, Trayport, Kpler, Platts, ICIS, Argus...) under the
  customer's entitlement.
- **User acceptance (G18)**: traders, analysts and risk staff work through the
  acceptance scripts on a release candidate and sign off.
- An approver identity for those external gates in `authorized_external_approvals`
  (scripts/release/policy/stable_gate_policy.json), the GitHub `production` environment
  with required reviewers, and branch protection on `main`.
- On the customer's side, at first run: an administrator approves the public sources
  ENTSOG and GIE for the firm (Admin → Data sources, or
  `scripts/ops/approve_public_source.py --list` / `--all-open --accept-terms`), after
  reading the terms summary; `/api/health/ready` lists them under `attention` until then.
  Held by `tests/release/test_public_source_approval_release.py` (fresh database: refused
  with `source_not_approved` before any fetch; approval; the same read stores rows).
- On the customer's side: enterprise IdP acceptance against their identity provider,
  deployment migration to head `0076_gas_day_nominations`, and an incident-response drill.

## Product Boundary

Release-candidate status does not authorize order entry, order routing, order
amendment/cancellation, trade capture, nomination submission, official
approvals, settlement/accounting, legal advice, official trading
recommendations, auto-trading, or ETRM replacement behavior.

All route, strategy, resource-pool, analysis, order/PnL, and report outputs are
decision support and require human review.
