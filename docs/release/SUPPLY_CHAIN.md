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
dependencies, plus `THIRD_PARTY_NOTICES.md`. `sbom-manifest.json` records the
component files, the SHA-256 and package count of every lock input, the
inventory scope, and every lock entry excluded from the package lists. Purls
follow the purl type conventions (npm names and scopes are lowercased with the
scope `@` percent-encoded; PyPI names use the PEP 503 canonical form; Cargo
crate names keep their case and underscores). Only the exact canonical
crates.io index sources count as crates.io, so git, path, alternate-registry
and lookalike registry URLs keep their raw `source` string instead of being
labelled as crates.io packages. Missing, malformed or empty lock inputs fail
the generator instead of emitting partial documents: a Cargo
`source`/`checksum` of the wrong type or shape, a malformed npm entry,
and any Python lock line that is not a fully parsed hash-pinned `name==version`
requirement all refuse the run. npm `link: true` workspace links and this
repository's own project entries are never silently dropped; they are recorded
under the input's `excluded_entries`.

This is a lock-derived inventory, not artifact-complete SBOM acceptance. It
over-covers shipped artifacts (dev/build and non-target packages), Cargo.lock
and the Python lock carry no license metadata, license texts are not included,
and container-image OS packages and native/installer binaries are outside the
inventory. The release manifest's per-artifact `sbom_ref` mapping is still
empty and no CI job records G10 evidence from this generator; G10 stays open
until artifact-complete evidence exists.

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

The build pushes only a run-attempt-unique staging tag
(`candidate-<run_id>-<attempt>`). The customer-facing channel tag
(`X.Y.Z` / `X.Y.Z-<channel>`) is written only after the release was published
and post-publish verification passed, by a gate-first job that copies the
tested digest (`scripts/release/promote_image.py`) and then re-verifies the
exact digest and both platforms - no rebuild, no deletion, and an observed
conflicting tag is refused by the tool's policy (the job's registry credential
itself could overwrite; an external writer racing the inspect/copy pair is not
excluded). Promotion serializes repository-wide with cancellation off and must
remain the exclusive writer of the package; GHCR check-then-write is not
atomic. Exact index-digest preservation by `imagetools create` against GHCR is
not yet verified by a controlled registry rehearsal, so the tool fails closed
instead of assuming it. The former `sha-<commit>` alias naming is retired; the
immutable identity is the `@sha256:` digest above.

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
