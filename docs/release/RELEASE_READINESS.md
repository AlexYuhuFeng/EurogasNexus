# Release Readiness

## Current Status

Status: `RELEASE CANDIDATE FOR TESTED LOCAL SCOPE`

Release marker: `RELEASE CANDIDATE`

Date checked: 2026-09-07 (CR-12 supply-chain and distribution hardening; local
dry-run and full local validation recorded below)

Eurogas Nexus passes the current local release-candidate shape for
backend/API/SDK/CLI, PostgreSQL runtime schema, Web workspace, Tauri desktop
shell, and the new release-evidence pipeline. This is **not** an official
production release and is **not** GA/stable. Stable promotion is fail-closed
until the external gates below have real evidence; no gate can be turned green
by a CLI flag.

## Latest Local Evidence

- Full local Python suite and Web tests/build: see `docs/product/SCHEDULED_AGENT_STATE.md`
  (updated after CR-12 validation).
- OpenAPI public surface: **141 paths** (`/api/runtime/release` added), pinned
  and permission-declared.
- Version consistency: `python scripts/release/check_version_consistency.py`
  passes across pyproject, runtime module, Web/desktop package files,
  tauri/Cargo metadata, docs, install scripts, and the release workflow.
- Release dry-run: `python scripts/release/run_release_dry_run.py` produces
  `release-assets/release-manifest.json`, SPDX SBOMs, `SHA256SUMS`, signing
  state, vulnerability evidence, and a fail-closed gate report.
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
  packages are separate artifacts, not one ambiguous Linux package. ARM Linux users do not receive the x64 DEB by mistake. ARM Linux users must not receive the x64 DEB by mistake.
- SDK and CLI remain API consumers.
- Clients do not connect directly to PostgreSQL.
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
- Preview/RC/stable channel semantics are explicit. Stable can only originate
  from a pushed `vX.Y.Z` tag on the protected mainline and runs in the
  `production` GitHub Environment.
- `release-manifest.json` records version, channel, commit, schema revision,
  engine/schema versions, final SHA-256 hashes, signing state, SBOM refs,
  attestation ref, and immutable container digest.
- SPDX 2.3 SBOMs are generated from the enforced locks; `THIRD_PARTY_NOTICES.md`
  is generated; vulnerability scan evidence is separate from SBOM.
- Release artifacts are covered by final `SHA256SUMS` (including the manifest);
  GitHub OIDC build provenance is generated over the final bundle.
- Windows code signing is policy-aware and explicitly `unsigned_pending_external`
  until an organization credential is supplied. Stable remains blocked.
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
- `Eurogas-Nexus-Server-{release_version}-Windows.zip`
- `eurogas-nexus-web-{release_version}.tar.gz`
- `release-manifest.json`, `SHA256SUMS`, SPDX SBOM set,
  `THIRD_PARTY_NOTICES.md`, and GitHub attestation metadata.

Container image tags: semantic `X.Y.Z[-channel]` and immutable `sha-<commit>`.
Deployment manifests should prefer `@sha256:<digest>`; never use `latest` as
rollback identity.

## What Runtime DB Means In The Client

`Runtime DB` means the UI is reading a backend API process that can reach the
configured PostgreSQL runtime store. It does not mean every commercial provider
has been live-called or validated.

## Required Before Production Deployment

- Provider-specific live tests and certification evidence for EEX, ICE OCM,
  Trayport, Kpler, Platts, ICIS, Argus, brokers, Weather, and LLM providers
  after credential and entitlement approval.
- Live deployment migration to head `0030_reliability_indexes` on the target
  runtime store.
- A real enterprise IdP acceptance test against the customer identity provider.
- External security acceptance, backup/restore and incident-response drills on
  a real deployment.
- Windows code-signing credential configured and verified (Authenticode +
  timestamp); stable stays blocked until this evidence exists.
- Clean-Windows install/launch/uninstall and previous-version upgrade
  acceptance on a controlled test machine.
- Real trader UAT (CR-13) and GA release-gate review.
- GitHub `production` Environment reviewer policy, branch protection for
  release/security paths, and hosted release dry-run evidence.

## Product Boundary

Release-candidate status does not authorize order entry, order routing, order
amendment/cancellation, trade capture, nomination submission, official
approvals, settlement/accounting, legal advice, official trading
recommendations, auto-trading, or ETRM replacement behavior.

All route, strategy, resource-pool, analysis, order/PnL, and report outputs are
decision support and require human review.
