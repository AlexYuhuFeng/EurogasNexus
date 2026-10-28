# Multi-surface development

This document is the developer workflow for the shared backend, Python SDK, Web
client and thin Tauri host. It describes the installed-wheel acceptance pipeline
added by `sdk-acceptance.yml` and the manual synchronisation rule that keeps the
surfaces honest.

## One backend, shared UI, thin host

The supported architecture is:

```text
                     +---------------------------+
                     |  same FastAPI backend     |
                     |  /api (typed contracts)   |
                     +-------------+-------------+
                                   |
              +--------------------+--------------------+
              |                                         |
     shared React Web client                    Python SDK wheel
     clients/web                               eurogas_nexus_sdk
              |                                         |
     browser and Tauri webview                 SDK/CLI automation
              |
     thin Tauri host: window, updater and native capabilities only
```

* The Web client and the Tauri host render the **same** `clients/web` build and
  call the **same** backend. The host is thin: it owns desktop lifecycle and
  native integration, not business rules, numerical calculation, contract
  semantics or a second API adapter.
* The Python SDK is a typed client, not a second backend. It ships inside the one
  customer wheel, from `packages/python-sdk/src`, together with
  `eurogas_nexus`. There is no separate SDK distribution and no editable-install
  shortcut in the installed-wheel gate.
* `apps/` deployment wrappers are not package code and are not installed into the
  customer wheel. The installed-wheel gate therefore starts the API from source
  in a separate process while the SDK smoke runs outside the checkout from the
  isolated venv. That is deliberate: it tests the installed SDK, not a bundled
  deployment wrapper.

## Feature synchronisation is manual and typed

The product does **not** autogenerate SDK or Web clients from OpenAPI. There is
no accepted generator, and a generated client would not by itself prove that
DTOs, HTTP status handling, exact decimals, refusal codes, authorisation or
point-in-time semantics agree with the backend.

For every feature change, the same reviewed commit must carry the manually typed
changes for all affected surfaces:

1. **Backend contract** — route, request/response DTOs, domain calculation,
   validation/refusal codes, auth/permission declarations, OpenAPI census where
   applicable, and point-in-time (PIT) semantics.
2. **Typed SDK** — the corresponding models and client methods in
   `packages/python-sdk/src/eurogas_nexus_sdk`, with no local financial
   arithmetic and no hidden defaulting.
3. **Shared Web adapters** — the transport, mapping and presentation used by
   both browser and Tauri through `clients/web`. Do not fork a Tauri-only
   business implementation.
4. **Focused tests** — DTO round-trips, HTTP method/path and status handling,
   exact decimal strings, refusal codes, auth/permission boundaries, and PIT
   behaviour. Existing API/contract tests remain the primary backend gate.
5. **Installed-wheel smoke** — `scripts/ci/check_installed_sdk.py` proves the
   built wheel imports outside the checkout, every SDK module imports, typed
   missing-field errors stay stable, and the existing synthetic capacity/LNG
   example passes its six actual HTTP checks.
6. **Web evidence** — the existing Web build/test/browser acceptance commands
   remain authoritative for browser and Tauri-webview behaviour.
7. **Installed native UAT** — rebuilt Windows/Linux artifacts must be launched and
   exercised by a human or approved automation. A successful native **build** is build-only evidence; it
   is not GUI, installer, signing or customer acceptance.
8. **Reviewed artifacts** — upload/review the JSON record and other bounded
   evidence. No surface is declared customer-ready from one green job.

The rule is intentionally conservative: if a backend contract changes and the
typed SDK/shared Web adapter is not updated in the same reviewed slice, the
feature is incomplete even if the backend tests pass.

## Installed-wheel acceptance

`.github/workflows/sdk-acceptance.yml` is reusable (`workflow_call`) and manually
dispatchable (`workflow_dispatch`). It is read-only (`contents: read`) and runs
two x64 jobs:

* `linux-x64` on `ubuntu-24.04`, with the pinned `actions/setup-python` action
  and canonical Python `3.11.12`;
* `windows-x64` on `windows-2025`, reusing
  `scripts/ci/install_windows_canonical_python.ps1`.

Linux ARM native coverage stays in the existing native pipeline; it is not
silently claimed by this workflow. Both `ci.yml` and `ci-manual.yml` invoke this
same workflow without inputs. Main pushes, pull requests and manual CI therefore
exercise the installed SDK alongside Web and native builds:

```yaml
jobs:
  sdk-installed:
    uses: ./.github/workflows/sdk-acceptance.yml
```

The job sequence is:

1. Check out `github.sha`; refuse a different HEAD or dirty tracked worktree.
2. Install `requirements-build.lock` and `requirements.lock` with
   `--require-hashes`.
3. Build exactly one wheel from the repository with
   `--no-build-isolation --no-deps`. Setuptools finds both package roots
   (`src` and `packages/python-sdk/src`), so `eurogas_nexus` and
   `eurogas_nexus_sdk` are in the same wheel.
4. Create an isolated venv and install `requirements-runtime.lock` with
   `--require-hashes`.
5. Install the built wheel with `--no-index --no-deps`.
6. Run the bounded helper. It starts the source backend on an ephemeral loopback
   port, waits at most 30 seconds for `/api/health`, copies the existing
   `scripts/examples/lng_capacity_economics.py` into a temp runtime, and runs it
   plus an import smoke with the venv Python `-I`. The smoke process runs outside
   the checkout. The helper terminates only the child process it started, in
   `finally`; it never discovers and kills a process by port or PID.
7. Upload the JSON record as review evidence.

The helper uses only existing test configuration names (`EUROGAS_NEXUS_ENV=test`,
the development route profile used by existing CI, the public API token,
principal header, artifact root and external-provider flag). It introduces no
new environment contract, reads no provider credential, and needs no database:
the two economics endpoints are stateless `POST` calls with synthetic inputs.
The token is generated at runtime for the owned loopback process and is not
written to the report or logs.

### What the record contains

`artifacts/sdk-acceptance/<surface>.json` contains only non-secret fields:

* schema/status and `synthetic_inputs: true`;
* canonical Python version and implementation;
* SDK version and origin, expressed relative to the isolated venv;
* built wheel SHA-256;
* the source commit passed by the caller;
* counts: SDK modules imported, typed missing-field cases, six HTTP cases
  (three capacity, one LNG, two refusals).

Failures contain only a stage and a stable error code. Raw response bodies,
child stdout/stderr, environment contents and exception text are not emitted.
The artifact is evidence for review, not a customer release, package
certification, signature, native GUI proof or provider/DB acceptance claim.

### What the example proves

`scripts/examples/lng_capacity_economics.py` is reused, not reimplemented. It
sends synthetic caller inputs to the actual loopback API through the typed SDK
and asserts the backend's exact decimal results:

* capacity 23 h: `460.0000` / `4.0000`;
* capacity 25 h: `500.0000` / `4.0000`;
* capacity pence 24 h: `85.9848` / `0.7165`;
* LNG cargo margin `550.0000` EUR, NPV `482.5000` EUR, consumed `7` MWh,
  physical loss `3` MWh, total reduction `10` MWh and
  `physical_readiness=NOT_ASSESSED`;
* stable `422` refusals for inconsistent billed capacity energy and broken LNG
  stage conservation.

The helper does not duplicate those financial or energy calculations. It also
checks typed missing-field errors (`billing_start` and `valuation_date`) through
Pydantic's field locations, without printing values.

## Local developer commands

Use canonical Python `3.11.12` and a temp root **outside the checkout** so the
smoke's source-import rejection is meaningful.

### Linux/macOS shell

```bash
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
runtime_root="$(mktemp -d)"

python --version   # must be 3.11.12
python -m pip install --require-hashes -r requirements-build.lock -r requirements.lock
python -m pip wheel . --no-deps --no-build-isolation \
  --wheel-dir "$runtime_root/wheelhouse"

python -m venv "$runtime_root/venv"
"$runtime_root/venv/bin/python" -m pip install --require-hashes -r requirements-runtime.lock
"$runtime_root/venv/bin/python" -m pip install --no-index --no-deps \
  "$runtime_root"/wheelhouse/*.whl

python scripts/ci/check_installed_sdk.py \
  --checkout-root "$repo_root" \
  --wheel-dir "$runtime_root/wheelhouse" \
  --venv-python "$runtime_root/venv/bin/python" \
  --work-dir "$runtime_root" \
  --report artifacts/sdk-acceptance/local-linux.json \
  --source-commit "$(git rev-parse HEAD)"
```

### Windows PowerShell

```powershell
$ErrorActionPreference = 'Stop'
$repoRoot = (git rev-parse --show-toplevel).Trim()
$runtimeRoot = Join-Path $env:TEMP ("eurogas-sdk-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runtimeRoot | Out-Null

python --version   # must be 3.11.12
python -m pip install --require-hashes -r requirements-build.lock -r requirements.lock
python -m pip wheel . --no-deps --no-build-isolation `
  --wheel-dir (Join-Path $runtimeRoot 'wheelhouse')

python -m venv (Join-Path $runtimeRoot 'venv')
$venvPython = Join-Path $runtimeRoot 'venv/Scripts/python.exe'
& $venvPython -m pip install --require-hashes -r requirements-runtime.lock
$wheels = @(Get-ChildItem (Join-Path $runtimeRoot 'wheelhouse') -Filter '*.whl' -File)
if ($wheels.Count -ne 1) { throw 'expected exactly one built wheel' }
& $venvPython -m pip install --no-index --no-deps $wheels[0].FullName

$sourceCommit = (git rev-parse HEAD).Trim()
python scripts/ci/check_installed_sdk.py `
  --checkout-root $repoRoot `
  --wheel-dir (Join-Path $runtimeRoot 'wheelhouse') `
  --venv-python $venvPython `
  --work-dir $runtimeRoot `
  --report artifacts/sdk-acceptance/local-windows.json `
  --source-commit $sourceCommit
```

The canonical Windows installer used by CI needs the runner's
`RUNNER_TEMP`/`GITHUB_PATH`; a developer machine should already have Python
`3.11.12` on `PATH`. Do not point the venv or work directory at an editable
source install.

### Focused checks

```bash
python -m pytest -q tests/unit/test_installed_sdk_pipeline.py
python -m pytest -q <affected backend/contract tests>
npm --prefix clients/web ci
npm --prefix clients/web run build
npm --prefix clients/web run test
```

Existing repository CI runs the full API/SDK suite (4k+ tests) and the browser,
database, security, release and license gates. This new workflow does not weaken
or replace any of them; it adds installed-wheel evidence for the shared Python
SDK on Windows and Linux x64.

## Boundaries and limitations

* Scope is Windows x64 and Linux x64. macOS, Windows ARM and Linux ARM are not
  proved here; Linux ARM native coverage remains in its separate pipeline.
* The API process is started from source because deployment wrappers are outside
  the wheel. The tested installed artifact is the SDK inside the shared wheel;
  this is not a customer container or installer acceptance.
* The example covers two research endpoints with six synthetic HTTP cases. It
  does not prove every SDK method, external provider access, database
  integration, production SSO, performance or commercial entitlement.
* The economics requests are stateless and synthetic. No provider, DB, external
  credential or customer data is required or used.
* Native build success is not GUI/installer/signing evidence. Manual native UAT
  on the rebuilt artifact remains required.
* No SDK or Web code is auto-generated. Feature synchronisation remains a
  reviewed, manual, typed change across backend, SDK, shared adapters and tests.
* A green workflow is review evidence. It is not by itself a customer release
  claim, and this document does not claim that the workflow has already run
  successfully in CI.
