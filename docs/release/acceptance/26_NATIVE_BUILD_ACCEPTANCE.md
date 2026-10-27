# Native build-only acceptance workflow

Status: **implemented, not dispatched, unsigned, unreviewed, build-only.**

This document describes `.github/workflows/native-acceptance.yml` and
`scripts/uat/write_native_build_evidence.py`. It does not assert that a hosted run
has passed, that an installer was installed, that the native UI was launched, or
that any artifact is signed or customer-ready.

## Why this workflow exists

The authoritative desktop matrix is already defined by the release workflow:
Windows x64 NSIS, Linux x64 DEB and Linux ARM64 DEB. The ordinary CI desktop job
runs only for pull requests, so a pushed `main` commit or a manual CI run does not
produce native packages. This workflow adds a manual **build-only** path for one
exact committed source revision without turning CI or release policy into a
publishing path.

It is intentionally separate from [release.yml](../../../.github/workflows/release.yml):

- no release, tag, package registry, GHCR, attestation, deployment or publishing
  job;
- no write permission, no organization secret and no environment approval;
- no repository mutation and no arbitrary shell input; and
- no claim that a package is signed, installed, launched or customer-accepted.

## Trigger and source identity

The only trigger is `workflow_dispatch` and it declares no inputs. The job checks
out `github.sha` directly, with persisted credentials disabled, so a dispatch from
a moving branch still builds the commit that was dispatched. The evidence writer
then independently runs local `git rev-parse HEAD` and refuses the run when HEAD
differs from `github.sha`, when tracked files changed after the build, or when the
worktree is not a repository. Untracked and ignored generated outputs (the Cargo
target tree, the Web `dist` and the evidence directory) are intentionally not
treated as source changes: the check is
`git status --porcelain=v1 --untracked-files=no`.

## Authoritative platforms and commands

The matrix copies the release desktop job's OS, bundle, pinned actions, pinned
toolchain, lockfiles and Linux dependency script:

| Platform | Runner | Bundle | Package output | Portable output |
| --- | --- | --- | --- | --- |
| Windows x64 | `windows-2025` | NSIS | `clients/desktop/src-tauri/target/release/bundle/nsis/*.exe` | `clients/desktop/src-tauri/target/release/eurogas-nexus-desktop.exe` |
| Linux x64 | `ubuntu-24.04` | DEB | `clients/desktop/src-tauri/target/release/bundle/deb/*.deb` | `clients/desktop/src-tauri/target/release/eurogas-nexus-desktop` |
| Linux ARM64 | `ubuntu-24.04-arm` | DEB | `clients/desktop/src-tauri/target/release/bundle/deb/*.deb` | `clients/desktop/src-tauri/target/release/eurogas-nexus-desktop` |

Canonical toolchain declarations are mirrored in the workflow:

- Python `3.11.12` (`.python-version`);
- Node `24.13.1` (`.nvmrc`); and
- Rust `1.94.0` (`rust-toolchain.toml`).

`scripts/ci/check_toolchain_versions.py` scans every workflow, so this new file is
part of the existing drift gate rather than a parallel version source. The
workflow also runs `python scripts/ci/check_toolchain_versions.py` after setting
up Python, so declaration drift fails before dependencies or build outputs exist.

Each job runs the same build sequence as the release desktop job:

1. `bash scripts/ci/install_linux_tauri_dependencies.sh` on Linux, using the
   existing retrying dependency installer;
2. `npm ci` in `clients/web` and `clients/desktop`;
3. `cargo check --manifest-path src-tauri/Cargo.toml --locked`;
4. `npm run build -- --bundles <nsis|deb> -- --locked` in `clients/desktop`; the
   first `--` makes npm forward the remaining arguments and the second `--` makes
   the Tauri CLI forward `--locked` to the Cargo runner; and
5. `cargo build --manifest-path src-tauri/Cargo.toml --release --locked` to build
   the portable native binary from the same locked source.

No version, action permission, test suite, license gate or security gate is
weakened. The workflow does not run release validation, and it cannot promote
anything.

## Uploaded artifacts

Each platform uploads one Actions artifact named
`eurogas-nexus-unsigned-native-acceptance-<platform>` with this fixed layout:

```text
artifacts/native-acceptance/<platform>/
  package/Eurogas-Nexus-<platform>-setup.exe     # windows-x64
  package/Eurogas-Nexus-<platform>.deb           # linux-x64 / linux-arm64
  portable/eurogas-nexus-desktop-<platform>.exe  # Windows native binary
  portable/eurogas-nexus-desktop-<platform>.tar.gz  # Linux native binary, mode 0755
  evidence/native-build-evidence.json
  checksums.sha256
```

The Linux tar contains exactly one member, `eurogas-nexus-desktop`, with mode
`0755`; the helper re-reads and hashes that member after writing the archive. The
Windows portable artifact is the built `.exe` itself.

`checksums.sha256` contains the SHA-256 of the package and portable files using
paths relative to the platform artifact root, so after extracting the downloaded
artifact directory, `sha256sum -c checksums.sha256` works from that root. The
evidence also records the repository-relative staged path for provenance.

## Evidence content and binding

`scripts/uat/write_native_build_evidence.py` writes a bounded JSON document. It
reads no environment variables, credentials, secrets or remote services. It
validates every path and runs only local `git` commands without a shell.

The document binds:

- the dispatched source SHA, the actual `git rev-parse HEAD`, and a clean tracked
  worktree;
- the run id, attempt, ref, event and repository;
- the platform label, runner OS/architecture and bundle;
- the canonical, expected and actual Python, Node and Rust versions, plus hashes
  of `.python-version`, `.nvmrc` and `rust-toolchain.toml`; the actual values are
  measured separately: Python from `sys.version_info`, Node and Rust from fixed,
  shell-free `node --version` and `rustc --version` probes, parsed as `X.Y.Z`
  before being compared with the canonical values;
- SHA-256 and byte counts for all committed dependency locks
  (`requirements*.lock`, both npm lockfiles and `Cargo.lock`);
- SHA-256 and byte counts for the build inputs, including the workflow, the Linux
  dependency installer, the two client manifests, the Tauri configuration and
  the evidence writer itself;
- the build output path, staged path, SHA-256 and byte count for both the installer
  and the portable native binary (the Linux tar's source binary and archive member
  are both recorded); and
- the SHA-256 of the checksum file that covers those staged artifact bytes.

The declarations block is deliberately explicit and machine-readable:

```json
{
  "scope": "native-build-only",
  "status": "BUILT_NOT_ACCEPTED",
  "unsigned": true,
  "unreviewed": true,
  "customer_release": false,
  "release_published": false,
  "native_ui_executed": false,
  "installed_launch_verified": false,
  "signing_performed": false
}
```

A checksum is integrity evidence, not a signature, review or certification.

## Fail-closed behaviour

The evidence step exits non-zero and uploads nothing when:

- the checked-out HEAD differs from the dispatched SHA;
- tracked files changed during the build (ignored generated outputs remain
  allowed);
- a canonical toolchain declaration disagrees with the version supplied by the
  workflow;
- the installed Python, Node or Rust version differs from the canonical value, or
  a version probe cannot start, exits non-zero or prints a non-`X.Y.Z` value;
  probe failures report only the tool and a stable reason or exit code, never
  raw stdout/stderr;
- a required lock or build-input file is missing;
- the package output is missing, ambiguous (more than one match) or is not a
  regular file;
- the portable native binary is missing or is the wrong platform shape;
- the stage directory is non-empty, so stale bytes cannot be silently mixed into
  a new artifact;
- the evidence output is outside
  `artifacts/native-acceptance/<platform>/evidence/`, escapes the repository, is
  absolute, is a symlink or already exists; or
- a path uses `..`, a drive/colon, a backslash or control characters.

The workflow is statically checked by, and explicitly runs, the repository's
existing toolchain gate. The focused unit tests exercise source mismatch, dirty
tracked worktree, missing and ambiguous outputs, missing locks, declared and
actual toolchain drift, probe failure without raw output, unsafe output paths,
stale stages and Linux archive member hashes:

```bash
pytest -q tests/unit/test_native_build_evidence.py
python scripts/ci/check_toolchain_versions.py
python scripts/ci/check_markdown_links.py
```

This document does not claim those commands were run in the implementation
session; the local execution shell is known to fail before command execution in
this environment, so the repository owner runs the gates.

## Owner dispatch and review procedure

The owner, not an implementation worker, reviews and commits the workflow, then
dispatches `Native build-only acceptance` at the intended commit and retrieves the
three artifacts with the GitHub connector or UI. A suggested review sequence is:

1. Confirm the run's `source.git_sha` equals the reviewed commit and all three
   declarations are the intended ones.
2. Download each platform artifact and verify `checksums.sha256` from the
   artifact root.
3. Confirm the evidence names the expected package and portable binary and that
   the recorded SHA-256 values equal the downloaded bytes.
4. Install the NSIS package on a disposable Windows VM (or the DEB on a disposable
   Linux VM) and launch the application against the intended API; record the
   result separately. This workflow does not perform that step and must not be
   described as if it did.
5. Inspect Authenticode/Linux package signing state before making any distribution
   statement. These artifacts are unsigned.

## Remaining gates

This workflow closes no release, signing, installation or customer gate. Still
required, and deliberately left outside this change:

- **Installed Windows UI:** clean-VM NSIS per-machine install, WebView2 bootstrap,
  start-menu/uninstall behaviour, native window/backend connectivity, EN/zh-CN
  workflows and keyboard accessibility.
- **Installed Linux UI:** DEB install/remove on x64 and ARM64, desktop entry,
  WebView runtime dependencies, native window/backend connectivity and the same
  UI workflow checks.
- **Signing:** organization-controlled Windows Authenticode identity/HSM and the
  applicable Linux package/repository signing and trust distribution. The
  existing policy-aware signer in the release workflow remains the authority; this
  workflow neither uses nor weakens it.
- **Release publication:** [release.yml](../../../.github/workflows/release.yml),
  the stable gate in
  [RELEASE_ENGINEERING_SPEC.md](../RELEASE_ENGINEERING_SPEC.md), artifact
  attestations, SBOM/checksum assembly, release notes and post-publish
  verification remain separate and unchanged.
- **Customer acceptance:** provider rights/certification, production issuer,
  security review, legal/license clearance, practitioner acceptance and the
  release-readiness gates in
  [RELEASE_READINESS.md](../RELEASE_READINESS.md) are not implied by a green build.

See [RELEASE_SIGNING.md](../../operations/RELEASE_SIGNING.md),
[INSTALL_WINDOWS.md](../INSTALL_WINDOWS.md) and
[INSTALL_LINUX.md](../INSTALL_LINUX.md) for the existing operator guidance.

## Policy boundary

This is an internal acceptance artifact builder. It is not a release-publishing
policy change, not a new release channel and not a bypass of the stable gate. It
grants no new permissions, uses no secrets, does not query provider or customer
state, and does not produce a stable release. The RFC process is not engaged
because this change follows the existing release engineering and client-platform
contracts without changing a normative boundary; if a future change makes these
artifacts part of release promotion, that change requires the normal policy and
RFC/ADR review.

## Independent root verification

2026-10-28: **26 focused tests passed**, including actual-version drift refusal,
source identity, expected artifacts, staged-byte hashes and unsafe paths. Ruff
and canonical declaration consistency pass. Root checked the installed locked
Tauri CLI2.11.2 help: runner arguments follow the second `--`, so the workflow
uses `npm run build -- --bundles <bundle> -- --locked`. These checks do not claim
a hosted native build, installation, launch, signing or customer acceptance.
