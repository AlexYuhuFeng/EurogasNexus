# Release Engineering Specification — CR-12

Status: normative for the CR-12 supply-chain and distribution milestone.
Repository truth wins over this document; when they diverge, open a repair
change, do not edit the document to hide the divergence.

## 1. Release principles

1. Build once; identify precisely.
2. Stable releases are immutable.
3. Version is not hard-coded in five places; one consistency gate proves all
   surfaces agree.
4. Every distributed artifact has integrity evidence.
5. Signing and attestation are different concepts.
6. Code signing is not Tauri updater signing.
7. SBOM is not provenance.
8. A GitHub Release alone is not a trust chain.
9. Preview, RC, and stable have different promotion rules.
10. An unsigned preview is never described as a signed commercial build.
11. A published stable artifact is never overwritten.

## 2. Current release audit (CR-12 start)

Classification: `IMPLEMENTED`, `PARTIAL`, `MISSING`,
`EXTERNAL_CREDENTIAL_REQUIRED`, `EXTERNAL_REPOSITORY_SETTING_REQUIRED`.

| Capability | State | Evidence / gap |
| --- | --- | --- |
| Release triggers | PARTIAL | `workflow_dispatch` existed with a stable option from any ref; CR-12 removes stable from dispatch and adds semantic tag triggers. |
| Channel semantics | MISSING -> IMPLEMENTED | `docs/release/RELEASE_CHANNELS.md`, tag parser, channel-aware UI/API metadata. |
| Canonical version | MISSING -> IMPLEMENTED | `pyproject.toml` canonical; `scripts/release/check_version_consistency.py` gate. |
| Hard-coded versions | PARTIAL -> IMPLEMENTED | Hard-coded `0.5.0` filenames/tags removed; docs use `{VERSION}` templates. |
| Tag generation | PARTIAL | Legacy `v0.5-preview-<run>-<sha>` tags are historical; new tags use `vX.Y.Z[-rc.N|-preview.N.<sha>]`. |
| Artifact naming | PARTIAL -> IMPLEMENTED | Names derive from `release-context.json`: `Eurogas-Nexus-Client-{release_version}-windows-x64-setup.exe`, etc. |
| Mutable tags | PARTIAL | `0.5-preview` legacy tag no longer published; new images also carry `sha-<commit>`. |
| Workflow permissions | PARTIAL -> IMPLEMENTED | Top-level `contents: read`; write only in publish/runtime-image/attestation jobs. |
| Action pinning | MISSING -> IMPLEMENTED | Every release workflow action is pinned to a full commit SHA with the reviewed version in a comment. |
| Runner pinning | PARTIAL -> IMPLEMENTED | Release jobs use `ubuntu-24.04`, `ubuntu-24.04-arm`, `windows-2025`. |
| Toolchain pinning | PARTIAL -> IMPLEMENTED | Python `3.11.12`, Node `24.13.1`, Rust `1.94.0` via root `rust-toolchain.toml`; no `rustup install stable`. |
| Python dependency pinning | IMPLEMENTED | `requirements*.lock` with `--require-hashes`. |
| Node dependency pinning | IMPLEMENTED | `package-lock.json` + `npm ci`. |
| Rust dependency pinning | IMPLEMENTED | `Cargo.lock` + explicit `cargo check --locked`. |
| Docker base image | PARTIAL | `python:3.11-slim` mutable tag; runtime non-root, no dev tools. |
| Desktop packaging | IMPLEMENTED | Tauri v2 NSIS (perMachine) and architecture-specific DEB. |
| Deployment bundles | IMPLEMENTED | Server operator ZIP; no embedded client or image. |
| Checksums | MISSING -> IMPLEMENTED | `SHA256SUMS` computed after final signing/packaging and covering `release-manifest.json`. |
| SBOM | MISSING -> IMPLEMENTED | SPDX 2.3 component set from enforced locks. |
| Code signing | PARTIAL | Policy-aware signer exists; no organization credential. |
| Updater signing | MISSING -> NOT SHIPPED | Tauri updater is intentionally not enabled in CR-12; see `UPDATE_POLICY.md`. |
| Container provenance | MISSING -> IMPLEMENTED | `docker/build-push-action` with `provenance: true` and `sbom: true`; immutable digest recorded. |
| Container signing | MISSING / EXTERNAL | BuildKit provenance baseline; keyless cosign not configured. |
| Artifact attestations | MISSING -> IMPLEMENTED | `actions/attest-build-provenance` after final bundle assembly. |
| Release notes | PARTIAL | Draft generator for preview/RC; stable notes require reviewed file with mandatory sections. |
| Rollback | IMPLEMENTED (CR-11) | `docs/operations/RELEASE_ROLLBACK.md`; container digest rollback identity added below. |
| Installer tests | PARTIAL | Local NSIS build/package test path exists; clean-Windows install/upgrade/uninstall evidence remains deployment acceptance. |
| Update tests | NOT_APPLICABLE | No updater ships; managed/offline path is documented. |
| Compatibility checks | PARTIAL -> IMPLEMENTED | `/api/runtime/release`, client blocking screen, version-gate script. |
| Stable promotion safeguards | MISSING -> IMPLEMENTED | `validate_stable_release.py`, fail-closed external gates, tag-only stable trigger. |
| Post-publish verification | MISSING -> IMPLEMENTED | `post_publish_verify.py` verifies assets, checksums, attestations and container digest. |
| GitHub Environment protection | EXTERNAL_REPOSITORY_SETTING_REQUIRED | Workflow targets `environment: production`; reviewer/approval configuration cannot be proven from code. |
| Code Owners enforcement | EXTERNAL_REPOSITORY_SETTING_REQUIRED | `CODEOWNERS` covers release/security paths; branch protection remains a repository setting. |
| Live pipeline run | EXTERNAL_REPOSITORY_SETTING_REQUIRED | CR-12 is validated by the local dry-run; a hosted run requires a push/tag authorized by the owner. |

## 3. Canonical version architecture

- Canonical source of truth: `pyproject.toml` `[project] version` (`0.5.0`
  during CR-12; no version bump is made merely to mark the milestone).
- Runtime copy: `src/eurogas_nexus/version.py` (import-safe).
- Client copy: `clients/web/src/app/releaseMetadata.ts`.
- Other machine surfaces: `package.json`, `package-lock.json`,
  `tauri.conf.json`, `Cargo.toml`, `Cargo.lock` (root desktop package only).
- Gate: `python scripts/release/check_version_consistency.py` fails non-zero
  on any divergence. `--write` synchronizes machine-readable files after a
  deliberate `pyproject.toml` bump.
- Documentation uses either the current version (human release history) or the
  `{VERSION}` template (operational asset names); the gate accepts only those.

## 4. Semantic versioning and release tags

| Channel | Application version | Release tag | Example |
| --- | --- | --- | --- |
| STABLE | `X.Y.Z` | `vX.Y.Z` | `v0.5.0` |
| RC | `X.Y.Z` | `vX.Y.Z-rc.N` | `v0.5.0-rc.1` |
| PREVIEW | `X.Y.Z` | `vX.Y.Z-preview.N.<shortsha>` | `v0.5.0-preview.1.033df92a856e` |

- The application always exposes version, channel, and commit as separate
  fields; no behavior is derived from an installer filename.
- Legacy `v0.5-preview-<run>-<sha>` tags are historical only and rejected by
  `parse_release_tag` for new releases.
- Stable and RC tags must match the canonical `pyproject.toml` version at the
  tagged commit.

## 5. Channel model and triggers

- PREVIEW: engineering/internal evaluation. May be `workflow_dispatch` from
  `main` only (mainline lineage is verified by the resolver).
- RC: candidate for user acceptance. May be `workflow_dispatch` from `main`
  or a pushed `vX.Y.Z-rc.N` tag.
- STABLE: commercial GA quality. **Must** originate from a pushed `vX.Y.Z`
  tag on the protected mainline. `workflow_dispatch(channel=stable)` does not
  exist. The stable publish job runs in the `production` GitHub Environment
  and passes `validate_stable_release.py --reject-existing-tag`.

## 6. Promotion model

Promotion changes release status, not application source. The preferred path
is: same source commit -> preview evidence -> RC evidence -> stable promotion.
If a promotion rebuilds artifacts for a legitimate platform reason, the new
run produces new provenance, new checksums, and a new manifest; it never
reuses the old evidence or re-tags different source as the same version.

CR-12 implements the evidence machinery and fail-closed stable gate. Automated
cross-channel promotion itself remains an operator-controlled decision.

## 7. Artifact naming

All names derive from `release-context.json`:

```text
Eurogas-Nexus-Client-{release_version}-windows-x64-setup.exe
Eurogas-Nexus-Client-{release_version}-linux-x64.deb
Eurogas-Nexus-Client-{release_version}-linux-arm64.deb
Eurogas-Nexus-Server-{release_version}-Windows.zip
eurogas-nexus-web-{release_version}.tar.gz
```

`release_version` is the full semantic tag without the leading `v`
(`0.5.0-preview.1.033df92a856e`). Stable artifacts therefore use `0.5.0`.

## 8. Release manifest

`release-manifest.json` is produced only after final artifacts, signing state,
SBOMs and checksums exist. It includes: product name, app version, release
version, channel, git SHA/ref, run id, timestamp, source repository, API
contract version, database schema revision, minimum client/server versions,
strategy/backtest/run/solver schema versions, per-artifact name/platform/arch/
type/size/SHA-256/signing state/attestation ref/SBOM ref, runtime image digest
and platforms. It never contains secrets. `SHA256SUMS` covers the manifest
itself.

## 9. Release workflow phases

1. RESOLVE metadata (`release-context.json`).
2. VALIDATE (version consistency, ruff, full tests, API import).
3. RELIABILITY (PostgreSQL migrations, DB smoke, performance, load smoke).
4. DEPENDENCY SCAN (pip-audit, npm audit, cargo audit, container scan later).
5. BUILD/PACKAGE (Web, NSIS, DEB x64/arm64, deployment bundle).
6. CONTAINER (multi-arch push, provenance, SBOM, digest metadata).
7. SIGN (policy-aware Authenticode/GPG; absent credentials are recorded).
8. ASSEMBLE (SBOM, signing state merge, manifest, final SHA256SUMS).
9. ATTEST (GitHub OIDC build provenance over the final bundle).
10. CONTAINER ACCEPTANCE (immutable digest + platform inspection).
11. STABLE GATE (fail-closed for stable tags).
12. PUBLISH (preview/RC prerelease; stable in `production` environment).
13. POST-PUBLISH VERIFY (download, checksums, attestation, digest).

## 10. Signing matrix

Actual state as of CR-12; no pending capability is marked `yes`.

| Artifact | Integrity | Provenance | Update sig | OS code sig |
| --- | --- | --- | --- | --- |
| Windows EXE (NSIS) | SHA256 | yes (GitHub OIDC) | n/a (updater not shipped) | pending external credentials |
| Windows MSI | not produced | n/a | n/a | n/a |
| Linux x64 DEB | SHA256 | yes | n/a | checksum/attestation baseline |
| Linux ARM64 DEB | SHA256 | yes | n/a | checksum/attestation baseline |
| Web bundle | SHA256 | yes | n/a | n/a |
| Server bundle | SHA256 | yes | n/a | optional |
| Container | digest | BuildKit provenance+SBOM | n/a | keyless cosign not configured |

Authenticode, when credentials exist, must be timestamped and verified with
`Get-AuthenticodeSignature` after signing. Linux DEB does not claim APT
repository signing because no APT repository is published.

## 11. SBOM, vulnerability scan, provenance

- SBOM: SPDX 2.3 documents generated from `requirements-runtime.lock`, both
  npm lockfiles, and `Cargo.lock`. `sbom-manifest.json` and the release
  manifest map artifacts to SBOMs. `THIRD_PARTY_NOTICES.md` is generated.
- Vulnerability scan: separate evidence (`vulnerability-scan.json`) from
  pip-audit, npm audit, and cargo audit. Known exploitable CRITICAL/HIGH
  runtime findings block stable unless listed in
  `scripts/release/policy/vulnerability_exceptions.json`.
- Provenance: GitHub `actions/attest-build-provenance` OIDC attestation links
  artifacts to repository, commit, workflow, and run. The repository does not
  claim a SLSA level merely because provenance exists.
- Reproducibility terminology: build **inputs** (commit, locks, pinned
  toolchains/runners) are reproducible; signed installers contain timestamps
  and are not claimed to be bit-for-bit reproducible.

## 12. Container release

- Semantic tag policy: stable `X.Y.Z`; preview/RC `X.Y.Z-<channel>`;
  every build also receives immutable `sha-<commit>`.
- Deployment manifests must prefer `image@sha256:<digest>`; mutable tags are
  convenience labels, not rollback identity.
- Runtime image: non-root `eurogas` user, build-stage dependencies excluded
  from runtime, no secrets in build context, readiness healthcheck in Compose.

## 13. Desktop update and offline installation policy

- No Tauri updater is shipped in CR-12. Updates are managed/offline:
  signed installer + `SHA256SUMS` + `release-manifest.json` + documented
  deployment procedure. See `UPDATE_POLICY.md`.
- Windows WebView2 default: `downloadBootstrapper` (online workstations,
  ~0MB extra). Offline/restricted workstations build with
  `src-tauri/tauri.offline.conf.json` (`offlineInstaller`, ~127MB extra) or
  prepare the documented fixed-runtime variant. No hidden internet dependency:
  `INSTALL_WINDOWS.md` states the requirement explicitly.

## 14. Client/server and database compatibility

- `GET /api/runtime/release` returns application version, channel, commit,
  `api-contract/v1`, database schema revision, minimum supported client/server,
  and engine/schema versions.
- The Web/Desktop client fetches this contract at startup and blocks
  partially-broken workspace screens with "Client update required" /
  "Server upgrade required" / "API contract mismatch".
- Readiness already validates DB schema at startup (CR-11); the manifest
  records the same Alembic head.

## 15. Immutable release and rollback

- Never overwrite a published stable asset or tag; publish a new patch version.
- Never replace a container semantic tag with different source without an
  incident policy; rollback uses the immutable `sha-*` digest.
- Desktop rollback: signed previous installer + documented compatibility;
  auto-updater rollback is intentionally not claimed.
- Server/DB rollback follows `docs/operations/RELEASE_ROLLBACK.md`.

## 16. External repository settings

These cannot be proven from workflow code and remain
`EXTERNAL_REPOSITORY_SETTING_REQUIRED`:

- GitHub `production` Environment with reviewer/approval policy.
- Branch protection requiring CODEOWNERS review for
  `.github/workflows/`, `scripts/release/`, `deploy/`, `src/eurogas_nexus/release/`.
- Organization code-signing certificate or approved cloud signing identity.
- Commercial provider certification and external security acceptance evidence.
- Real trader UAT.
