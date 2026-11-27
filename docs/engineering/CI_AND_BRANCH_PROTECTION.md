# CI and branch protection

## What CI runs (`.github/workflows/ci.yml`)

| Job | Gate |
|---|---|
| validate | required check; passes only when `validate checks` and every `validate tests` shard passed (on a docs-only pull request: the checks and the documentation-reading tests) |
| validate checks | ruff, markdown links, config contract, env templates, toolchain agreement, config preflight, lock completeness, both load smokes, MCP handshake, API import; once per run, docs-only changes included |
| validate tests (unit / api-security / rest) | the whole of `tests/` in three shards, each `pytest -q -n auto` (pytest-xdist, one worker per CPU); `rest` is `tests` minus the other shards' directories, so a new test directory is never left out |
| Dependency licence & CVE audit | fail-closed licence policy over Python, both npm locks and the desktop crate graph; pip-audit |
| PostgreSQL integration | migrations and DB-backed tests against PostgreSQL 16 |
| web-client-build | web tests and production build |
| Python license text evidence | the runtime lock installed into a clean venv; every applicable entry yields a license text (entries whose marker excludes the interpreter are disclosed) |
| Browser acceptance (EN/ZH, 3 viewports) | required check; passes only when the acceptance client build and every shard passed |
| Browser acceptance shard (desk / network-and-data / reference / interactions) | the whole-product sweep split by page group (`scripts/uat/browser_shards.json`): every workspace in EN/ZH at three viewports with axe, overflow and read-to-render checks, the phone overflow sweep, the interaction checks, the map host check and the geometry audit, each in exactly one shard; each shard has its own seeded PostgreSQL and serves the one shared client build |
| Browser acceptance client build | one development-mode build of the Web client (React's development warnings still reach the sweep's console check), shared by the shards |
| Native desktop build | Windows x64, Linux x64 and Linux ARM64 Tauri bundles |
| SDK installed-wheel acceptance | the shipped wheel on Linux and Windows |
| Weather model numerical acceptance | science-lock numerical tests |

**Cancellation.** A newer push to a pull request (or a newer manual run on the same non-main
branch) cancels the older run. Runs on `main` are grouped by commit and never cancelled: each
one is release evidence (G1) for its own commit, and AGENTS.md rule 16 judges every pushed
commit by its own run, so cancelling a superseded `main` run would leave a pushed commit
without a verdict. Python jobs cache pip downloads; `--require-hashes` still verifies every
package.

**Docs-only pull requests.** The `Change scope` job diffs the pull request's test merge commit
against its base (plain `git diff`, no third-party action). When every changed file is under
`docs/` or ends in `.md`, the test shards, the browser shards and their client build, the
dependency audit, PostgreSQL integration and the Web build are skipped; `validate checks`
(markdown links included) still runs, and so do the test files that read documentation
(`validate tests (documentation readers)`), because many contract tests assert what the docs
say. `validate` and `Browser acceptance` still report success, and a skipped job counts as
passed for a required check. Pushes to `main` and manual runs are never treated as docs-only:
a release-notes commit is docs-only and is still the commit a release is tagged on, and G1
needs its full run. The native, SDK and weather-model reusable workflows always run: a skipped
reusable call reports under the caller's name, not the leaf names the required checks use.

**Timings (2026-11-27).** Measured on a 4-core development container; the hosted figures are
estimates (see below).

| | Before | After |
|---|---|---|
| Python suite, one process | 28 min on 8 cores; 41 min here for eight of the directories (7,364 tests); about 40 min on a hosted runner | — |
| Python suite, `pytest -n auto tests`, 4 cores | — | 15.5 min (8,668 passed, 264 skipped) |
| validate shards, `-n auto`, 4 cores | — | unit 5.1 min, api-security 6.1 min, rest 5.1 min (same 8,668 / 264 together) |
| Browser sweep | 16.6 min in one process + 3.6 min geometry audit | largest shard 6 min |
| Hosted `ci.yml`, whole run | 40 to 53 min | estimated 13 to 15 min (see below) |
| Release `validate` test step | about 40 min | estimated 15 min (the security evidence step after it is unchanged, a few minutes) |
| `scripts/ci/pre_push_check.sh` | about 28 min | 13 min on 4 cores (its pytest step 11.4 min, 6,115 tests); estimated 7 to 8 min on 8 cores |

Browser shard sweep times, measured locally against the shared development build
(`vite preview`): desk 285 s, network-and-data 276 s + map check 6 s, reference (with the
phone overflow sweep) 357 s, interactions 75 s + geometry audit 216 s.

One process here is about as fast as a hosted runner (41 min for most of the suite here, about
40 min in the hosted release job), so the local parallel figures stand for hosted ones. The
floor of every parallel run is one test, `tests/release/test_security_evidence.py::
test_actual_security_suite_runs_and_produces_pass_evidence` (about 4 to 6 minutes): it runs the
whole security suite in its own process, as the release evidence step does.

Hosted estimate: the longest chain is now the browser acceptance (client build about 2 min,
then each shard's setup of about 4 to 5 min — Python and Web dependencies, Playwright with its
system packages, migrate and seed — and at most 6 min of sweep), about 13 min; the validate
shards take setup plus a third of the suite in parallel workers, about 7 to 9 min. The native
desktop builds are unchanged and not measured here; if one of them is longer than 15 minutes,
it is the new critical path.

## Required before code reaches `main`

Run `scripts/ci/pre_push_check.sh` before pushing (install it as `.git/hooks/pre-push`).
It refuses untracked source files and runs ruff, the API import, the lock-completeness
check (`scripts/ci/check_lock_completeness.py`: every dependency in `pyproject.toml` is
pinned for the canonical Python in each lock a CI job installs from, and every lock marker
can be decided), the fast test directories (`tests/contract`, `unit`, `security`, `release`,
`evals`, `sdk`, `cli`, `docs`, `optimization`, `streaming`, `workflow`) in parallel
workers (`pytest -n auto`, as hosted CI does; `pytest-xdist` comes with `requirements.lock`),
and the web typecheck and tests.

What only hosted CI runs, and therefore can still fail after a green local gate:

| Hosted only | Why it is not in the gate | Reproduce locally |
|---|---|---|
| `tests/api`, `domain`, `ingestion`, `integration` (without a database), `db`, `uat` in `validate` | about a third of the suite's time | `pytest -q -n auto tests/<dir>` |
| A clean Python 3.11.12 installed from the locks | a developer venv has other versions and extra packages | `python3.11 -m venv v && v/bin/pip install --require-hashes -r requirements-build.lock -r requirements.lock` |
| PostgreSQL integration and the weather-model job (which runs the same `run_postgres_ci.sh` first) | needs PostgreSQL 16 | `docker run postgres:16`, then `scripts/ci/run_postgres_ci.sh` with `RUNTIME_STORE_DATABASE_URL` pointing at that scratch database only |
| Python licence text evidence | needs the runtime lock installed into a clean venv of the canonical Python | the job's two steps in `ci.yml`, with `python3.11` |
| Browser acceptance | a seeded UAT runtime, API and Vite servers and Chromium; about 20 minutes in one process | the shard job's steps in `ci.yml`; without `EUROGAS_UAT_SHARD` the sweep runs whole, against `npm run dev` or a built client served by `vite preview` |
| Native desktop builds and the installed SDK wheel | per-platform runners | — |

## Recommended repository settings (set by a repository admin in GitHub)

Settings → Branches → add a rule for `main`:

- Require a pull request before merging. Autonomous workers open PRs and enable
  auto-merge rather than pushing directly.
- Require status checks to pass: `validate`, `Dependency license & CVE audit`,
  `PostgreSQL integration`, `web-client-build`, `Browser acceptance (EN/ZH, 3 viewports)`,
  and the three native builds. These names did not change when the suite and the browser
  sweep were split into shards: `validate` and `Browser acceptance` are the summary jobs. Do
  not require the shard jobs themselves; their names follow the shard lists.
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
