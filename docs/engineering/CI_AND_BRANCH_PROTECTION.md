# CI and branch protection

## What CI runs (`.github/workflows/ci.yml`)

| Job | Gate |
|---|---|
| validate | ruff, markdown links, config contract, toolchain agreement, full pytest, load smoke, API import |
| Dependency licence & CVE audit | fail-closed licence policy over Python, both npm locks and the desktop crate graph; pip-audit |
| PostgreSQL integration | migrations and DB-backed tests against PostgreSQL 16 |
| web-client-build | web tests and production build |
| Browser acceptance | whole-product sweep in EN/ZH at three viewports, axe WCAG checks, interaction checks |
| Native desktop build | Windows x64, Linux x64 and Linux ARM64 Tauri bundles |
| SDK installed-wheel acceptance | the shipped wheel on Linux and Windows |
| Weather model numerical acceptance | science-lock numerical tests |

Pull-request runs are cancelled when a newer push supersedes them; `main` runs never are,
because each one is release evidence for its own commit. Python jobs cache pip downloads;
`--require-hashes` still verifies every package.

## Required before code reaches `main`

Run `scripts/ci/pre_push_check.sh` before pushing (install it as `.git/hooks/pre-push`).
It refuses untracked source files and runs ruff, the API import, the contract and unit
suites, and the web typecheck and tests.

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
