# Build dependency security remediation (BUILD-CVE-REMEDIATION)

Status: **source fix prepared, not closed**. `requirements-build.in` now carries
reviewed patched floors. `requirements-build.lock` was deliberately not edited
because no real `uv` invocation was possible in this Harness session, and
hand-written hashes are prohibited.

Reported evidence: GitHub CI run `40545675072`, audit job `122335514237`, commit
`a8af2b7`. Five findings were reported in three build-only packages. This worker
did not read CI authentication logs or secrets, and did not start workers,
change grants/ACLs/sandboxing, activate sources, or touch a database.

## Findings and remediation floors

| Package | Locked | Patched floor | Findings | Build role |
| --- | --- | --- | --- | --- |
| `filelock` | 3.32.6 | **4.2.1** | CVE-2026-112940, CVE-2026-112913, CVE-2026-112907 (3) | transitive via `pip-audit` → `cachecontrol` |
| `msgpack` | 1.2.2 | **1.2.3** | CVE-2026-114613 (1) | transitive via `pip-audit` → `cachecontrol` |
| `setuptools` | 84.0.0 | **84.1.0** | GHSA-xmj3-9gf7-h52w (1) | direct build-system dependency |

Root-confirmed primary advisory sources:

- filelock: <https://github.com/advisories/GHSA-v4x8-3wr5-3wq8> and
  <https://github.com/advisories/GHSA-9vhv-jxww-xfm5>. These two sources cover
  three CVE identifiers; the exact per-CVE mapping still requires root review.
- msgpack: <https://github.com/msgpack/msgpack-python/security/advisories/GHSA-j586-36cw-2gc2>
- setuptools: <https://osv.dev/vulnerability/GHSA-xmj3-9gf7-h52w>

Only `requirements-build.lock` contains these packages; the runtime and full
locks do not. The installed-environment `pip-audit` step in
`.github/workflows/ci.yml` sees them because the dependency-audit job installs
`requirements-build.lock` together with `requirements.lock`.

## Build dependency graph inspected

- `setuptools` is the declared build backend (`[build-system]` in
  `pyproject.toml`, currently `requires = ["setuptools>=68"]`).
- `wheel` is a direct build-tool requirement and is unchanged.
- `pip-audit==2.10.1` is the direct scanner requirement. Its lock graph pulls
  `cachecontrol==0.14.4`, which in turn pulls `filelock` and `msgpack`.
- `certifi` is a direct build-side trust requirement and is unchanged.
- CI installs the hash-pinned build lock, then installs the package with
  `--no-deps --no-build-isolation`, so the build path uses the locked
  `setuptools`, not the `pyproject.toml` floor.
- `scripts/ci/freeze_lock.py` regenerates all three locks through
  `uv pip compile --universal --generate-hashes --upgrade`, including
  `requirements-build.lock` from `requirements-build.in`. It does not preserve
  unrelated pins itself.
- The security contract in `tests/security/test_dependency_audit.py` checks the
  three lock names, hash pinning, build-lock separation and CI registration. It
  does not assert these package versions, so no test edit is required or made.

## Change made

`requirements-build.in` only:

- raised the existing `setuptools` floor from `>=68` to `>=84.1.0`;
- added explicit `filelock>=4.2.1` and `msgpack>=1.2.3` floors with short
  security comments. They remain transitive in the graph but are now explicit
  inputs so a resolver cannot silently return the affected versions;
- left `wheel`, `pip-audit`, `certifi`, all runtime dependencies, the audit
  policy and every CI check untouched. No CVE exception or ignore was added.

`pyproject.toml` was not edited. Its isolated-build floor remains
`setuptools>=68`; that is a residual gap for builds that do not install
`requirements-build.lock`. CI's audited path uses the build lock. Aligning the
`pyproject.toml` floor is a separate root decision outside this bounded write
set.

## Compatibility risk

- **`filelock` 4.2.1 — highest risk: major bump 3.x → 4.x.** The resolver may
  accept it while `cachecontrol` 0.14.4 still exercises a changed API. The
  blast radius is the build/scan HTTP cache, not product runtime, but a break
  would fail the dependency-audit job. Resolution and import/runtime behaviour
  must be proven by the actual hash install and audit runs. If incompatible,
  the correct response is an explicit compatible scanner/cache update, not an
  ignore or a forced vulnerable filelock.
- **`msgpack` 1.2.3 — patch bump.** Low risk; `cachecontrol` already operates
  in the 1.x range. Still requires the real install/audit proof because the
  lock includes compiled wheels.
- **`setuptools` 84.1.0 — patch bump over 84.0.0.** Low-to-moderate risk to
  package build/install only. It must be proven by building/installing the
  project, not by a version string.

No test is claimed here. In particular, no "test" was performed that only
asserts a version string, and no check was skipped or marked ignored.

## Lock state and required root action

`requirements-build.lock` still pins `filelock==3.32.6`, `msgpack==1.2.2` and
`setuptools==84.0.0`. **Therefore CI will still report the same five findings
until the lock is regenerated.** Changing the `.in` file alone does not change
what CI installs.

A real `uv` command was not available: Harness shell execution failed on the
temporary ACL lock (`CreateFileW ... dsh-acl-locks ...`). This was not bypassed,
and no lock hash was invented or hand-edited. Root is preparing a separate
ignored audit venv with `uv`.

Operator sequence, to be run by root:

1. Regenerate `requirements-build.lock` from the updated `.in` with universal
   hashes, minimizing unrelated pin churn, for example:

   ```text
   uv pip compile --python-version 3.11 --universal --generate-hashes \
     --upgrade-package filelock --upgrade-package msgpack \
     --upgrade-package setuptools \
     requirements-build.in -o requirements-build.lock
   ```

2. Inspect the diff. Expected changes are the three versions, their hash blocks
   and `# via` attribution. Reject unrelated pin churn; do not paste hashes from
   another platform or version.
3. In the ignored audit venv, install with
   `--require-hashes -r requirements-build.lock -r requirements.lock`, then
   run the actual installed-environment `pip-audit` and the shipped-lock audits
   (`requirements-runtime.lock`, `requirements.lock`) as CI does. Also build and
   import the project so the build-backend change is exercised.
4. Only a fresh actual CI run on the regenerated lock can close the reported
   audit job. This document must not be used as evidence that CI is green.

## Evidence limits and root-required verification

These five findings are **build/scan dependency findings, not runtime product
proof**. `filelock` and `msgpack` are not runtime distribution dependencies;
`setuptools` is build-time only. Removing them from the audit environment does
not prove that no runtime vulnerability exists, and the reverse is also true:
the current audit failure does not by itself prove an exploitable runtime path.

Root must independently verify:

- the advisory-to-package ranges and that the stated fixed versions actually
  cover all five identifiers;
- that `cachecontrol` 0.14.4 is compatible with `filelock` 4.x at runtime, not
  merely resolvable;
- license/redistribution metadata for the changed versions. No license
  clearance is claimed here; the repository's dependency audit is
  review-required detection, not a legal determination;
- the regenerated lock hashes, actual install, actual audit and final CI result.

No product runtime test, deployment, source activation, grant/ACL change or
release approval is claimed by this remediation.

## Changed files

- `requirements-build.in`
- `docs/release/acceptance/25_BUILD_DEPENDENCY_SECURITY_REMEDIATION.md`

`requirements-build.lock`, `requirements.lock`, `requirements-runtime.lock`,
`pyproject.toml` and CI/audit policy were not changed.

## Independent root verification (2026-10-28)

Regenerated universal SHA256 lock with uv0.13.6; only three package versions
changed: filelock3.32.6→4.2.1, msgpack1.2.2→1.2.3,
setuptools84.0.0→84.1.0. No runtime/full lock or vulnerability exception changed.
Clean isolated Windows Python3.12 hash install of build+full locks succeeded.
Actual installed-environment pip-audit: no known vulnerabilities (exercising
cachecontrol/filelock4 compatibility). Direct fully pinned runtime/full lock
audits with `--no-deps --disable-pip` also report no known vulnerabilities;
complete dependency closure was separately verified by the hash install.
The pip-resolving audit invocation on this Windows scratch setup did not finish;
it is not reported as passing. Fresh exact-source CI Python3.11 audits remain
required, with their original resolver-enabled commands and no policy bypass.

Metadata license policy scan:69packages, no restricted license terms found;
this is not redistribution/legal clearance. Setuptools84.1 PEP517 build_wheel
succeeded, and the unified backend+SDK wheel installed and imported in isolated
Python (`-I`) with189OpenAPI paths. Its installed SDK example passed six real
loopback HTTP golden/refusal checks against dedicated synthetic PostgreSQL.
A pip-wheel attempt hit Windows' deeply nested temporary-path limit; the direct
PEP517 backend build avoids that path and does not establish final native or
final-source release acceptance. The SDK is packaged in the root distribution,
not a separately installable `packages/python-sdk` project.
