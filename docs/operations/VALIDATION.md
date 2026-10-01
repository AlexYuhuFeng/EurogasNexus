# Validation

Run validation from the repository root.

## Prerequisites

```powershell
docker compose up -d        # start PostgreSQL when runtime DB checks are needed
pip install -e ".[dev]"     # install project + dev dependencies
```

## Required Commands

```powershell
ruff check .
pytest -q tests
python scripts/ci/check_markdown_links.py
npm --prefix clients/web run test
npm --prefix clients/web run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.openapi()['paths']))"
python scripts/ops/load_smoke.py --requests 200 --concurrency 8 --p95-threshold-ms 1000
bash scripts/ops/run_served_load_smoke.sh
python scripts/ops/migration_preflight.py --json
python scripts/release/compatibility_check.py
python scripts/release/check_version_consistency.py
python scripts/security/run_security_acceptance.py --json
```

## Environment Setup

Use a local virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Dependency Lock Regeneration

Hash-pinned locks are generated from `pyproject.toml` with `uv`:

```powershell
python scripts/ci/freeze_lock.py
```

This writes `requirements.lock`, `requirements-runtime.lock`, and
`requirements-build.lock`. Commit all three whenever dependencies change.

## Expected Result

- Ruff exits with code 0.
- All tests pass (pre-existing failures noted separately).
- App import prints:

```text
app import ok
<route-count>
```

## BLOCKED Conditions

Report validation as `BLOCKED` if Python, FastAPI, pytest, or Ruff are not
available and dependency installation is not permitted.

Report validation as `PARTIAL` if only a subset of checks can run.

## One-command Validation

```bash
./scripts/ops/validate_repo.sh
```

## Release Engineering Validation

```bash
python scripts/release/check_version_consistency.py
python scripts/release/run_release_dry_run.py --channel preview \
  --image-digest sha256:<published-image-digest>
python scripts/release/package_deployment_bundle.py dist/releases \
  --release-context dist/releases/release-context.json \
  --image-digest sha256:<published-image-digest>
python scripts/release/validate_release_artifacts.py --context release-assets/release-context.json --artifacts-dir release-assets
python scripts/release/validate_stable_release.py --context release-assets/release-context.json --artifacts-dir release-assets
python scripts/release/scan_vulnerabilities.py --channel preview
```

The dry-run builds/assembles the release candidate without publishing. Stable
validation is deliberately fail-closed while external evidence is pending. The
Server operator bundle requires the resolved release context and the published
image digest; it fails closed without them instead of fabricating an identity.
The dry run needs the same explicit `--image-digest`: `--build-container` builds
and can smoke-test a local image, but the local image config id
(`docker image inspect .Id`) is recorded as a diagnostic only and is never
substituted for the published repository manifest digest in the bundle identity
or the release manifest.

Every release publish job (preview, RC and stable) runs the same
`validate_stable_release.py` gate before its `gh release create`, with
`actions: read` and the step-scoped workflow token, and never with
`--allow-missing-platform-artifacts`, `--allow-local-dry-run-evidence` or
`continue-on-error`. A failing gate stops the job, so preview/RC publication
blocks until their own channel's mandatory evidence (same-SHA CI acceptance
included) exists.

## UAT Validation

```bash
python scripts/uat/check_i18n_parity.py
python scripts/uat/seed_uat_fixture.py          # development/test only, explicit env gate
python -m pytest tests/evals tests/uat -q
# Browser workflows (optional; requires Playwright and running dev servers):
#   see scripts/uat/browser_workflow_smoke.mjs
# Live read-only board capture (optional; requires Playwright + chromium, a preauthenticated
# storage state file and an explicit target URL - see the pilot plan's WF-1 section):
#   node scripts/uat/captureLiveBoard.mjs
# Offline comparison of a capture an operator already made (no browser, no network):
#   node scripts/uat/compareCapturedBoard.mjs <capture.json>
```

Axe/Playwright evidence for CR-13 is recorded in
`docs/uat/ACCESSIBILITY_REPORT.md` and `docs/uat/RC_ACCEPTANCE_REPORT.md`.

## Reliability Validation

With `RUNTIME_STORE_DATABASE_URL` configured:

```bash
python scripts/ops/performance_baseline.py --requests 200 --concurrency 10 --json
python scripts/ops/backup_restore_drill.py --target-database-url <isolated-target-dsn>
python scripts/ops/recover_stale_jobs.py --commit
```

## Served-instance Load Smoke

The in-process smoke drives the ASGI app through httpx without opening a socket.
The served smoke starts a real uvicorn process, waits for `/api/health/live`,
and sends the same workload over HTTP, so server startup, sockets, and middleware
order are exercised too:

```bash
bash scripts/ops/run_served_load_smoke.sh
```

`SERVED_LOAD_SMOKE_PORT` selects the port (default `8765`). Set
`RUNTIME_STORE_DATABASE_URL` to smoke a PostgreSQL-backed instance; without it
the server runs DB-less like the in-process CI job.

## Cold-Start Initialization

CI run `36878083383` (baseline `58afd8a`) failed the in-process API load smoke
in a CPython 3.11 `_ModuleLock('sqlalchemy.exc')` import deadlock: eight
concurrent first requests reached the lazily imported runtime database layer
from FastAPI worker threads at the same time. The application lifespan startup
now imports that graph once, on one thread, before the server accepts requests
(`src/eurogas_nexus/api/runtime_dependencies.py`, invoked from the lifespan in
`src/eurogas_nexus/api/app.py`). The in-process smoke runs the same lifespan,
so it exercises the deployed lifecycle (uvicorn runs it too) instead of a
lifecycle no deployment has.

Initialization is import-only. It does not require
`RUNTIME_STORE_DATABASE_URL`, does not create an engine, open a connection, run
migrations or write state, and importing `apps.api.main` still loads neither
SQLAlchemy nor the database package. The behavior is pinned by the
fresh-process tests in `tests/contract/test_cold_start_initialization.py`.

Evidence and limits: three cold in-process trials of
`python scripts/ops/load_smoke.py --requests 200 --concurrency 8
--p95-threshold-ms 1000` reported 200 ok / 0 errors each with p95 between 21.7
and 26.1 ms, and a served uvicorn trial reported 120 ok / 0 errors. The
original deadlock requires CPython 3.11; these local trials ran on CPython
3.14, so they reproduce the cold-start import order (first sight of the
database graph on the startup thread, never on a request worker) rather than
the 3.11 deadlock itself. A harness that never runs the ASGI lifespan startup
does not get this initialization and is not covered by the gate.

## Runtime DB Validation

Command:

```powershell
python scripts/ops/validate_runtime_db.py --json
```

This script is read-only. It does not write data or run migrations. It is the
standard live local PostgreSQL validation path when a safe DB URL is configured.
Default tests remain DB-free.

See `docs/operations/LIVE_POSTGRESQL.md` for the live PostgreSQL policy.

### Running the suite against live PostgreSQL

Default validation stays DB-free *even when the machine has a database configured*:
`tests/conftest.py` removes `RUNTIME_STORE_DATABASE_URL`, `DATABASE_URL` and
`EUROGAS_NEXUS_DB_DSN` for every test outside `tests/integration`, so a suite that
asserts "no runtime store is configured" keeps asserting that instead of silently
reading whatever deployment the workstation happens to point at (the fixtures that
do want a store set it themselves, after that).

`tests/integration` is the live path, and it skips unless a URL is present:

```powershell
$env:RUNTIME_STORE_DATABASE_URL = "postgresql+pg8000://user:pass@127.0.0.1:5432/scratch"
python -m alembic upgrade head          # apply the chain to the scratch database
ruff check .
pytest -q tests                         # everything, with the integration suite live
pytest -q tests/integration             # the live half on its own
```

The integration suite is re-runnable against a persistent database (CI's service
container is throw-away, a developer's is not), and `python scripts/ops/migration_preflight.py`
reports the source-tree head next to the database's current revision before you migrate.
