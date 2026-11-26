# CI and branch protection

## What CI runs (`.github/workflows/ci.yml`)

| Job | Gate |
|---|---|
| validate | ruff, markdown links, config contract, toolchain agreement, full pytest, load smoke, API import |
| Dependency licence & CVE audit | fail-closed licence policy over Python, both npm locks and the desktop crate graph; pip-audit |
| PostgreSQL integration | migrations and DB-backed tests against PostgreSQL 16 |
| web-client-build | web tests and production build |
| Python license text evidence | the runtime lock installed into a clean venv; every applicable entry yields a license text (entries whose marker excludes the interpreter are disclosed) |
| Browser acceptance | whole-product sweep in EN/ZH at three viewports, axe WCAG checks, interaction checks |
| Native desktop build | Windows x64, Linux x64 and Linux ARM64 Tauri bundles |
| SDK installed-wheel acceptance | the shipped wheel on Linux and Windows |
| Weather model numerical acceptance | science-lock numerical tests |

Pull-request runs are cancelled when a newer push supersedes them; `main` runs never are,
because each one is release evidence for its own commit. Python jobs cache pip downloads;
`--require-hashes` still verifies every package.

## Required before code reaches `main`

Run `scripts/ci/pre_push_check.sh` before pushing (install it as `.git/hooks/pre-push`).
It refuses untracked source files and runs ruff, the API import, the lock-completeness
check (`scripts/ci/check_lock_completeness.py`: every dependency in `pyproject.toml` is
pinned for the canonical Python in each lock a CI job installs from, and every lock marker
can be decided), the fast test directories (`tests/contract`, `unit`, `security`, `release`,
`evals`, `sdk`, `cli`, `docs`, `optimization`, `streaming`, `workflow`), and the web
typecheck and tests.

What only hosted CI runs, and therefore can still fail after a green local gate:

| Hosted only | Why it is not in the gate | Reproduce locally |
|---|---|---|
| `tests/api`, `domain`, `ingestion`, `integration` (without a database), `db`, `uat` in `validate` | most of the job's 50 minutes | `pytest -q tests/<dir>` |
| A clean Python 3.11.12 installed from the locks | a developer venv has other versions and extra packages | `python3.11 -m venv v && v/bin/pip install --require-hashes -r requirements-build.lock -r requirements.lock` |
| PostgreSQL integration and the weather-model job (which runs the same `run_postgres_ci.sh` first) | needs PostgreSQL 16 | `docker run postgres:16`, then `scripts/ci/run_postgres_ci.sh` with `RUNTIME_STORE_DATABASE_URL` pointing at that scratch database only |
| Python licence text evidence | needs the runtime lock installed into a clean venv of the canonical Python | the job's two steps in `ci.yml`, with `python3.11` |
| Browser acceptance | a seeded UAT runtime, API and Vite servers and Chromium; about 20 minutes | the job's steps in `ci.yml` |
| Native desktop builds and the installed SDK wheel | per-platform runners | — |

## Recommended repository settings (set by a repository admin in GitHub)

Settings → Branches → add a rule for `main`:

- Require a pull request before merging. Autonomous workers open PRs and enable
  auto-merge rather than pushing directly.
- Require status checks to pass: `validate`, `Dependency license & CVE audit`,
  `PostgreSQL integration`, `web-client-build`, `Browser acceptance (EN/ZH, 3 viewports)`,
  and the three native builds.
- Require branches to be up to date before merging.
- Do not allow force pushes or deletions.

These settings cannot be committed to the repository; they live in GitHub. Without
them, a red `main` can only be caught after the fact. CI on `main` was red from
`d97fd56` until the fixes on 2026-10-30.

## Repository profile (About, topics, releases)

The About panel is what a visitor reads first; it is also set in GitHub, not in a file.
Repository home → About (gear icon):

- **Description:** `Decision-support workstation for European gas trading desks: hub
  prices, fundamentals (ENTSOG, GIE, ENTSO-E, REMIT), forward curves, positions and
  research on the customer's licensed data. No order entry.`
- **Website:** leave empty, or the customer-facing documentation site once one exists.
- **Topics:** `natural-gas`, `energy-trading`, `commodities`, `european-gas`, `ttf`,
  `nbp`, `market-data`, `risk-management`, `fastapi`, `react`, `tauri`, `postgresql`.
- Show **Releases**; hide Packages and Deployments unless they are used.

Settings → General: keep Issues on, Wikis off (documentation lives in `docs/`), and turn
on "Automatically delete head branches". Settings → Tags → add a tag protection (ruleset)
for `v*` so only release maintainers can create or delete release tags.

Releases follow [RELEASE_CHANNELS.md](../release/RELEASE_CHANNELS.md): only release
candidates (`vX.Y.Z-rc.N`) and stable versions (`vX.Y.Z`) appear on the Releases page.
The legacy 0.5 preview pre-releases can be removed with
`scripts/release/prune_legacy_prereleases.sh` (dry run first).
