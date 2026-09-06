# Software Supply Chain

## Source integrity

- Protected mainline: `main`. Release resolver verifies mainline lineage for
  dispatch/tag runs (`git merge-base --is-ancestor`).
- Stable trigger: pushed semantic tag `vX.Y.Z` only; tag mismatch with
  `pyproject.toml` fails; existing stable tag is never overwritten.
- `pull_request_target` is not used for any release/secret path. PR workflows
  run with `contents: read` and no signing secrets.

## Dependency locks

| Ecosystem | Lock | Install rule |
| --- | --- | --- |
| Python | `requirements.lock`, `requirements-runtime.lock`, `requirements-build.lock` | `pip install --require-hashes` |
| Web/desktop Node | `package-lock.json` (both) | `npm ci` |
| Rust | `Cargo.lock` | `cargo check --locked` before Tauri build |

Release-time dependency resolution is not allowed to float.

## Build environment

- Runners: `ubuntu-24.04`, `ubuntu-24.04-arm`, `windows-2025`.
- Toolchains: Python `3.11.12`, Node `24.13.1`, Rust `1.94.0`
  (`rust-toolchain.toml`; no `rustup install stable`).
- Every release action is pinned to a full commit SHA; the reviewed major
  version is kept in an adjacent comment.

## SBOM

`scripts/release/generate_sboms.py` produces SPDX 2.3 documents from the
enforced locks for Python runtime, Web Node, Desktop Node, and Desktop Rust
dependencies. `sbom-manifest.json` maps SBOMs to artifact families and
`THIRD_PARTY_NOTICES.md` is generated from lock license metadata.

## Checksums

`SHA256SUMS` is generated **after** final signing/packaging and covers every
distributed asset plus `release-manifest.json`. Verification:
`sha256sum -c SHA256SUMS` (Windows: `Get-FileHash`).

## Signing

- Windows: policy-aware Authenticode path (`signtool` sign + verify + trusted
  timestamp). Without credentials the manifest records
  `unsigned_pending_external` and stable remains blocked.
- Linux: checksum/attestation baseline; optional verified GPG detached
  signature. No APT repository is published.
- Tauri updater signing is separate and not shipped (see `UPDATE_POLICY.md`).

## Attestation and provenance

The release workflow runs `actions/attest-build-provenance` with OIDC over the
final bundle after all hashes exist. Verify after publication:

```bash
gh attestation verify --repo AlexYuhuFeng/EurogasNexus --tag <release-tag>
```

Provenance links artifacts to repository, commit, workflow, and run. It is not
a SLSA level claim.

## Container provenance and digest

`docker/build-push-action` builds with `provenance: true` and `sbom: true`.
The multi-arch digest (`sha256:...`) is recorded in `release-manifest.json`
and `image-metadata.json`. Deploy by digest, not by `latest`. Verify:

```bash
docker buildx imagetools inspect ghcr.io/alexyuhufeng/eurogasnexus-api@sha256:<digest>
```

Keyless cosign container signing is not configured in CR-12 and is explicitly
listed as an external gap.

## Release immutability

Published stable tags/assets are never overwritten or re-tagged. A wrong
stable artifact implies a new patch version and new provenance.

## Verification commands for operators

```bash
python scripts/release/check_version_consistency.py
python scripts/release/verify_checksums.py --artifacts-dir <release>
python scripts/release/validate_release_artifacts.py --context <ctx> --artifacts-dir <release>
python scripts/release/validate_stable_release.py --context <ctx> --artifacts-dir <release>
gh attestation verify --repo AlexYuhuFeng/EurogasNexus --tag <tag>
docker buildx imagetools inspect ghcr.io/alexyuhufeng/eurogasnexus-api@sha256:<digest>
```

## Known external dependencies

- GitHub-hosted runners and action images.
- Microsoft WebView2 runtime/bootstrapper for Windows first install.
- PyPI/npm/crates.io/GHCR at build time (pinned/locked inputs).
- Organization code-signing credential and production GitHub Environment.
