# Vendor remediation acceptance record

Date: 2026-10-07. Baseline: the working tree carrying revisions
`0039_identity_api_key_hash_width` and the configuration-contract change set.

This is the working record of an engineering review of Eurogas Nexus against the
disposition in the [commercial acceptance audit](../engineering/Architecture-V2/19_COMMERCIAL_ACCEPTANCE_AUDIT.md).
It exists so that the vendor and the reviewing firm can work from one list where
every item names **the finding, the change, and the command that proves the
change** — rather than from prose.

It is an engineering record. It is not legal advice, certification, a vendor
comparison, or an approval to deploy.

## How to use this document

Three columns matter for every item: what was found, what changed, and how to
check it without trusting this document.

Everything below was executed on the reviewing machine, which had no system
Python, Node or PostgreSQL. The environment was built from the repository's own
lock files; the local scaffolding (a hash-locked dependency target, an embedded
PostgreSQL, a local npm) is machine-local and regenerable, and is not part of the
deliverable.

Status vocabulary:

| Status | Meaning |
| --- | --- |
| **Fixed and verified** | Reproduced, changed, and re-verified here with the recorded command. |
| **Fixed, evidence pending** | Changed and covered by tests here; the acceptance evidence requires a customer environment. |
| **Open** | Not resolved by this change set, and not resolvable by engineering alone. |

## Status of the review findings

| Finding | Status |
| --- | --- |
| B2 release pipeline could not produce an artefact | **Fixed and verified** (dependency locking, template generation, toolchain pinning) |
| B3 supply chain (unlocked CI installs, no container scan, hashless npm) | **Partly fixed and verified**; container CVE scanning is **open** |
| B5 identity and configuration defects (PKCE, cookie, missing preflight) | **Fixed and verified**; a real IdP acceptance test is **evidence pending** |
| B8 drawdown metric reported zero for losing strategies | **Fixed and verified** |
| `key_hash` column could not hold the value the code writes | **Fixed and verified** (found during this review; not in the original list) |
| B1 no licensed market data | **Open** — commercial |
| B4 no execution, ETRM or risk integration | **Open** — product scope |
| B6 licence forbids deployment; no SLA or support terms | **Open** — legal and commercial |
| B7 single-author vendor on a personal account | **Open** — commercial |

## Fixed and verified

### 1. CI installed dependencies from the index, not from the lock

**Finding.** The `validate` job — which produces the G1 evidence the release gate
trusts — installed with `pip install -e ".[dev]"`: no `--require-hashes`, no lock
file. The build whose green result authorises publication was therefore not
reproducible and could drift. Two other jobs did the same. The browser-acceptance
job installed Playwright with `npm install --no-package-lock`, pinning versions
but verifying no integrity.

**Change.** Every Python job installs
`--require-hashes -r requirements-build.lock -r requirements.lock` and then
`--no-deps --no-build-isolation -e .`. The browser tools install from a committed
`pnpm-lock.yaml` with `--frozen-lockfile`.

**Files.** [ci.yml](../../.github/workflows/ci.yml),
[ci-manual.yml](../../.github/workflows/ci-manual.yml),
[scripts/ci/browser-acceptance](../../scripts/ci/browser-acceptance/).

**Verify.** `grep -n "pip install" .github/workflows/*.yml` shows only
hash-checked installs. To prove the sequence works from scratch:

```bash
python -m pip install --require-hashes -r requirements-build.lock -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
```

Both steps were run into an empty target and exited 0, installing 67 packages with
hash verification, including the build backend the second step needs.

**Vulnerability coverage, stated precisely.** `pip-audit` runs in the CI
dependency-audit job. It previously audited only the installed environment, which
says nothing about the set a customer receives, so the job now also audits
`requirements-runtime.lock` (what the image installs) and `requirements.lock`.
All three report no known vulnerabilities.

What is **not** covered: the **container image is not CVE-scanned**. No workflow
installs or runs trivy, grype or any equivalent; the `container-acceptance` job
inspects the immutable digest and runs the licence-notice verifier inside the
image. The scanner script's container entry said the scan "must run against the
final pushed digest in release CI", which read as though such a step existed, and
that text now states the gap plainly. `policy_ok` blocks `stable` on the
`TOOL_UNAVAILABLE` status, so a stable promotion cannot be granted while the gap is
open. [tests/contract/test_vulnerability_scan_coverage.py](../../tests/contract/test_vulnerability_scan_coverage.py)
pins all of it: that no scanner is installed, that the recorded status stays
honest, that an unavailable scanner blocks `stable`, and that the Python and npm
audits stay wired up. Adding a scanner fails the test, which is the intended
signal to update both the claim and the coverage together.

### 2. `.env.example` did not describe the deployment

**Finding.** The code read 69 environment variables; the shipped template
mentioned 9. The runtime DB URL, the credential-encryption key, the internal API
token and all 12 OIDC variables were undocumented. Conversely,
`EUROGAS_NEXUS_ALLOW_FILE_FALLBACK` was documented at length and set to `false` by
`deploy/runtime/compose.yaml` while **no code read it at all** — an operator would
believe a safety control was active.

**Change.** One declaration per variable in
[config_contract.py](../../src/eurogas_nexus/core/config_contract.py); the
templates are generated from it; the dead flag is removed from the template and
the compose file.

**Files.** [src/eurogas_nexus/core/config_contract.py](../../src/eurogas_nexus/core/config_contract.py),
[.env.example](../../.env.example),
[deploy/runtime/env.server.example](../../deploy/runtime/env.server.example),
[scripts/ci/generate_env_template.py](../../scripts/ci/generate_env_template.py),
[scripts/ci/check_config_contract.py](../../scripts/ci/check_config_contract.py).

**Verify.**

```bash
python scripts/ci/check_config_contract.py        # declares == reads, no dead entries
python scripts/ci/generate_env_template.py --check # templates match the contract
```

The gate fails on three distinct defects, each demonstrated by a test in
[tests/contract/test_verification_gates_fail_closed.py](../../tests/contract/test_verification_gates_fail_closed.py):
an undeclared read, a template variable nothing reads, and a stale template.

### 3. A misconfigured deployment failed silently

**Finding.** A missing credential-encryption key raised only when the first
provider credential was written. A half-configured OIDC block answered `503` only
when a user clicked sign-in. A mistyped variable name was ignored entirely.

**Change.** [preflight.py](../../src/eurogas_nexus/core/preflight.py) plus
[check_config.py](../../scripts/ops/check_config.py). It reports missing required
settings, placeholder secrets, unknown variable names (naming the likely intended
one), development-only switches left enabled in a release deployment, a partially
configured OIDC block, a credential key that cannot be rotated deliberately, and an
undeclared trusted proxy hop. The deployment stack now runs it before the migration
and the API, so a misconfigured environment does not start.

**Files.** [deploy/runtime/compose.yaml](../../deploy/runtime/compose.yaml),
[scripts/ops/check_config.py](../../scripts/ops/check_config.py),
[scripts/ci/fixtures/release.env](../../scripts/ci/fixtures/release.env).

**Verify.**

```bash
python scripts/ops/check_config.py --env-file scripts/ci/fixtures/release.env --strict
```

A complete release-shaped environment reports no findings. Against that same file
with one variable misspelled, the run exits 1 and prints:

```
ERROR [unknown_variable] EUROGAS_NEXUS_OIDC_ISUER: set but not part of the
      configuration contract, so it has no effect
      fix: did you mean EUROGAS_NEXUS_OIDC_ISSUER? Nothing reads the name as written
```

### 4. PKCE challenge was not RFC 7636 conformant, and no test covered it

**Finding.** `code_challenge` was `sha256(verifier).hexdigest()`. RFC 7636 §4.2
requires `BASE64URL(SHA256(verifier))` with padding removed, so a conformant
identity provider rejects the exchange with `invalid_grant` and **browser SSO
cannot complete**. No test called `pkce_pair()`; the one test that drove the flow
constructed its challenge with `hexdigest` too, copying the implementation's own
mistake.

**Change.** base64url encoding, and a test that derives the expected challenge
independently.

**Files.** [enterprise_auth.py](../../src/eurogas_nexus/application/enterprise_auth.py),
[tests/security/test_enterprise_oidc_auth.py](../../tests/security/test_enterprise_oidc_auth.py).

**Verify.** `pytest -q tests/security/test_enterprise_oidc_auth.py`

### 5. Session cookies were issued without `Secure`

**Finding.** `Secure` was set only when `request.url.scheme == "https"`. In the
shipped topology Caddy terminates TLS and proxies to `api:8000`, and uvicorn
rewrites the scheme only for peers listed in `FORWARDED_ALLOW_IPS`, whose default
(`127.0.0.1,::1`) excludes the proxy container. The scheme was therefore always
`http` and the 12-hour session cookie was issued without `Secure`.

**Change.** An explicit policy in
[cookie_policy.py](../../src/eurogas_nexus/security/cookie_policy.py): an `https`
request is always `Secure`; a production profile or environment is **always**
`Secure` regardless of the observed scheme; only development and test may issue a
non-`Secure` cookie. `FORWARDED_ALLOW_IPS` is set in the compose environment.

**Files.** [cookie_policy.py](../../src/eurogas_nexus/security/cookie_policy.py),
[api/routes/public/auth.py](../../src/eurogas_nexus/api/routes/public/auth.py),
[deploy/runtime/compose.yaml](../../deploy/runtime/compose.yaml).

**Verify.** `pytest -q tests/security/test_cookie_policy.py`

### 6. The SDK sent no credential

**Finding.** The SDK read `EUROGAS_NEXUS_API_TOKEN`; the server reads
`EUROGAS_NEXUS_PUBLIC_API_TOKEN`. Nothing in the repository, the templates or CI
set the SDK's name, so an operator following the deployment documentation left the
SDK sending no `Authorization` header and every release-profile call was refused.

**Change.** The SDK reads the server's canonical name and falls back to the older
one.

**Files.** [packages/python-sdk/src/eurogas_nexus_sdk/_http.py](../../packages/python-sdk/src/eurogas_nexus_sdk/_http.py),
[tests/sdk/test_sdk_token_resolution.py](../../tests/sdk/test_sdk_token_resolution.py).

**Verify.** `pytest -q tests/sdk`

### 7. The max-drawdown metric reported 0.0% for losing strategies

**Finding.** In `domain/research/backtest.py` the running peak was seeded at
`0.0` and the decline was only accumulated while `peak > 0`. Any curve that never
rose above its zero starting equity contributed nothing, so a strategy that lost
money on every trade reported `max_drawdown_pct = 0.0` — indistinguishable from one
that never drew down. The value is serialised straight into the public
`POST /api/research/backtest` response. The test covering that function asserted
`total_return`, `trade_count` and `win_rate` and **never asserted either drawdown
field**.

**Change.** The amount is computed and always reported; the percentage is reported
only once a peak exists to divide by, is `None` otherwise, and a new optional
`capital_base_eur` input makes it defined for any curve. Trades are replayed in
`date` order, which the function previously ignored.

**Files.** [backtest.py](../../src/eurogas_nexus/domain/research/backtest.py),
[research.py](../../src/eurogas_nexus/api/routes/public/research.py),
[tests/domain/research/test_backtest.py](../../tests/domain/research/test_backtest.py),
[tests/api/test_research_backtest_drawdown_api.py](../../tests/api/test_research_backtest_drawdown_api.py).

**Verify.** `pytest -q tests/domain/research/test_backtest.py tests/api/test_research_backtest_drawdown_api.py`

Reproduced before and after on the same inputs:

| Input | Before | After |
| --- | --- | --- |
| `[-100, -50, -80]` | `0.0%` | 230 EUR, percent `None` |
| `[-100]` | `0.0%` | 100 EUR, percent `None` |
| `[-100, +150]` | `0.0%` | 100 EUR |
| `[100, -60, 20]` | `60.0%` | 60 EUR / 60% |

### 8. A keyed API-key digest did not fit its column

**Finding (found during this review).** `identity_api_keys.key_hash` was declared
`VARCHAR(64)`, while `hash_key_secret()` returns `'hmac:' + sha256_hex` = **69
characters** once `EUROGAS_NEXUS_SECRET_KEY` is configured. PostgreSQL enforces
the length:

```
pg8000.dbapi.ProgrammingError: {'C': '22001',
  'M': 'value too long for type character varying(64)'}
```

**Minting any API key failed on a deployment that set the credential-encryption
key** — which is exactly the configuration `deploy/runtime/compose.yaml` ships.
It survived the suite because the unit tests run on SQLite, which ignores a
declared `VARCHAR` length, and the PostgreSQL integration tests skip without a
server.

**Change.** Migration
[0039_identity_api_key_hash_width.py](../../alembic/versions/0039_identity_api_key_hash_width.py)
widens the column to 80; the model matches; the downgrade refuses to narrow while
a longer digest is stored.

**Files.** [alembic/versions/0039_identity_api_key_hash_width.py](../../alembic/versions/0039_identity_api_key_hash_width.py),
[src/eurogas_nexus/db/models/identity.py](../../src/eurogas_nexus/db/models/identity.py),
[tests/contract/test_stored_value_widths.py](../../tests/contract/test_stored_value_widths.py).

**Verify.** With a PostgreSQL 16 server configured as `RUNTIME_STORE_DATABASE_URL`:

```bash
alembic upgrade head
pytest -q tests/integration
```

Against an embedded PostgreSQL 16.2 the suite went from **114 passed / 29 skipped**
to **143 passed / 0 skipped**, and the three tests that previously failed with
`22001` now pass.

**Also established:** this was the only instance of its class. All 16 digest
producing helpers in `src` were inventoried against all 650 declared `String(n)`
columns across the 25 model files. Four helpers return a prefixed digest
(`'sha256:' + hex`, 71 characters) and each is paired with a column wide enough for
it; the rest return a bare 64-character hex digest; and no column narrower than the
digest it holds was found. The ten `String(80)` columns all live in
`db/models/identity.py` and hold identifiers, a session id, a nonce and hashes —
`key_hash` is the only one whose writer can emit the prefixed 69-character form,
and widening it did not change any of the others.

### 9. Toolchain versions were declared in eight places with no gate

**Finding.** `.python-version` and `.nvmrc` did not exist at all. The interpreter
version was hard-coded five times inside `ci.yml` alone, and `pyproject.toml`,
both client `package.json` files and the lock-file headers each carried their own
statement. Nothing compared them, so a partial bump would leave a caller on a
version the lock file was not compiled for.

**Change.** `.python-version` and `.nvmrc` added as canonical; the workflow
`env` blocks mirror them; a gate asserts every other declaration agrees.

**Files.** [.python-version](../../.python-version), [.nvmrc](../../.nvmrc),
[scripts/ci/check_toolchain_versions.py](../../scripts/ci/check_toolchain_versions.py).

**Verify.** `python scripts/ci/check_toolchain_versions.py`

Five partial-bump cases are covered by tests and each is reported, including
"bump `.python-version` only", which is caught through the `pyproject.toml`
`requires-python` mismatch.

### 10. A production instruction named a stale schema revision

**Finding.** `DB_SCHEMA_REVISION` was already asserted against the real migration
head by three tests, so the constant cannot drift silently. The documents were not:
[RELEASE_READINESS.md](RELEASE_READINESS.md) listed "Live deployment migration to
head `0032_agent_capability_layer`" as a required-before-production item while the
head was `0039_identity_api_key_hash_width` — seven revisions stale.

**Change.** That item now names the preflight command, which reads the head from
the tree instead of a document.

## CI check coverage

Every check the CI workflows assert was executed locally except where noted, so
"CI runs this" is not an assumption. All results below are from the reviewing
machine, built from the repository's own lock files.

| Check (as named in CI) | Ran here | Result |
| --- | --- | --- |
| Install package from hash-pinned locks | yes | 67 packages, hash-verified, exit 0 |
| Ruff | yes | clean |
| Markdown links | yes | 271 documents, all links resolve |
| Configuration contract | yes | 69 declared / 62 read, no dead entries |
| Environment templates are current | yes | both current |
| Toolchain versions agree | yes | every declaration agrees |
| Configuration preflight (release fixture) | yes | no findings |
| Tests | yes | 3,213 passed / 37 skipped / 0 failed |
| API load smoke (in-process) | yes | 200 ok / 0 errors, p95 14.9 ms |
| API load smoke (served over HTTP) | yes | 200 ok / 0 errors, p95 201.4 ms |
| MCP server handshake smoke | yes | `protocolVersion` returned |
| Import API | yes | 182 paths |
| License policy audit (Python) | yes | 41 packages, policy OK |
| Node license policy audit | yes | 98 npm entries across 2 locks, policy OK |
| Rust license policy audit | **no — no cargo toolchain here** | fails closed with an actionable message, as designed |
| CVE audit (pip-audit) | yes | no known vulnerabilities |
| CVE audit (shipped lock set) | yes | no known vulnerabilities |
| Python license text collection | yes | 30 of 30 locked packages, 34 files |
| Python license text verification | yes | verified against the runtime lock SHA-256 |
| PostgreSQL migrations + DB smoke | yes, by equivalent | the script's logic was reproduced against PostgreSQL 16.2; the `.sh` wrapper needs bash, which this machine lacks |
| Web client build / test | yes | `tsc` + `vite` pass; 864 tests, 859 passed |
| Browser acceptance | yes, with findings | the full sweep ran: 96 scope combinations, 0 axe violations, 0 single-h1 breaches, 0 horizontal overflow, functional gaps 0. Its reported 403 is withdrawn — see the correction below; the cause was this review's environment, not the product |

The two checks that did not run here are called out in the sections above rather
than being presented as passing.

## Fixed, evidence pending

- **Real identity provider acceptance.** The PKCE encoding is now conformant and
  unit-tested, and a real browser sign-in was completed this round through the
  development credential route, so the browser path itself is exercised. A login
  against a customer Keycloak, Entra or Okta is still not done, and that remains
  the closing evidence for B5.
- **Signed installers.** Code signing stays `unsigned_pending_external`; the
  Windows signing credential is an operator-owned artefact.
- **PostgreSQL major-version confirmation.** The integration suite and the browser
  sweep were verified against PostgreSQL 16.2 (embedded). The CI service is
  `postgres:16`; the embedded server is the same major version but not the same
  build.
- **Headless browser only.** Chromium here is Playwright's headless shell, not the
  headed build CI installs with `--with-deps`. The sweep's measurements are DOM and
  request based, so this does not affect them, but the native/Tauri shell is still
  unverified.

## Correction: a defect this review reported and then withdrew

An earlier revision of this record reported a browser-reachable product defect
here. **That report was wrong, and the cause was this review's own environment.**
It is kept, with its resolution, because a review that quietly deletes its errors
is not auditable.

**What was observed.** The browser acceptance sweep recorded 101 console errors,
and the API log showed one 403 repeated 56 times:

```
POST /api/route-cost/resource-pool/optimize  ->  403
{"error": "origin_not_allowed", "message": "Cookie-authenticated request blocked."}
```

The client fires that call automatically when the Decision workspace loads
([usePortfolioDecisionModel.ts:412-415](../../clients/web/src/app/model/usePortfolioDecisionModel.ts)).

**What was concluded, incorrectly.** That the origin guard was refusing a
legitimate browser session, so the platform's only cookie-authenticated mutation
was unusable.

**What the investigation found.** The guard was behaving exactly as designed, and
the reviewing environment — not the product — was misconfigured. Two measurements
settle it.

First, the guard's own predicate across the topologies:

| Topology | Outcome |
| --- | --- |
| Production: `Origin https://nexus.example.com`, `Host` preserved | **allowed** |
| Production behind a TLS-terminating gateway | **allowed** |
| Attacker origin against the real host | **refused (403)** |
| Vite dev server on `:3000`, backend `Host :8000` | refused (403) |

So the guard permits production and refuses a forged origin. Only the development
topology fails, because the Vite dev server serves the client on its own port while
the backend derives the expected origin from `Host`.

Second, with the origin declared, the same mutation proceeds past the guard:

```
with Origin, WITHOUT X-Eurogas-CSRF  ->  403 csrf_invalid      (guard working)
with Origin AND X-Eurogas-CSRF       ->  422 missing resources/sale_options
```

The 422 is schema validation on this probe's own placeholder body, which means the
request **passed both the origin and CSRF checks**.

**The actual cause.** `EUROGAS_NEXUS_CORS_ORIGINS` is the declared remedy, and the
CI browser-acceptance job already sets it
([ci.yml](../../.github/workflows/ci.yml)):

```yaml
EUROGAS_NEXUS_CORS_ORIGINS: http://127.0.0.1:3000
```

The reviewing environment's own environment file omitted it, so the flaw was in how
this review assembled its environment. The vendor's CI configuration is correct.

**What was changed as a result.** Nothing in the guard, and nothing to force a
green sweep. Two things were added, because the misconfiguration is easy to make
and its symptom does not name its cause:

1. A preflight warning, `dev_origin_not_declared`
   ([preflight.py](../../src/eurogas_nexus/core/preflight.py)): a development
   profile with no declared browser origin warns, naming the variable and the
   refusal it prevents. It does not fire for `release`, `internal` or any
   production environment, where the guard derives the origin from `Host`.
2. The contract note for `EUROGAS_NEXUS_CORS_ORIGINS` now says a production
   deployment needs nothing while **any development install using the Vite dev
   server does**. The previous wording — "a correctly proxied deployment usually
   needs nothing here" — is what led this review to omit it.

Both are covered by tests, including that the warning stays silent in the four cases
where it would be noise.

**Effect on the verdict.** None. The browser sweep's positive results stand; the
one failure it appeared to find was the reviewer's own, and the product's
origin+CSRF guard is confirmed to permit production topologies and refuse a forged
origin.

**Before and after, same sweep, one variable changed.** Both runs used the same
seeded database, the same 16 workspaces, 2 languages and 3 viewports.

| Measurement | Round 12 (no origin declared) | Round 15 (declared) |
| --- | --- | --- |
| Scope combinations | 96 | 96 |
| axe violations | 0 | 0 |
| Entries with `h1 != 1` | 0 | 0 |
| Horizontal overflow | 0 | 0 |
| Functional gaps | 0 | 0 |
| **Failures** | **102** | **1** |
| — console 403 | 101 | **0** |
| — agent fixture refresh | 1 | 1 |

No product code changed between the two runs. The 101 refusals disappeared when the
API was given the origin, which is the clearest possible statement that they were
this review's environment and not the product.

The one remaining failure is environmental and its own error message says so:
`spawnSync ...python.cmd EINVAL`. `spawnSync` refusing a `.cmd` on Windows is a
Node-on-Windows limitation; the shim exists only because this machine has no system
`python` on PATH, and CI runs the sweep with a real interpreter. Every product
assertion in the sweep passes here.

## Open — commercial and scope

| Item | Why it is open | Who decides |
| --- | --- | --- |
| **B1 — no licensed market data** | Every commercial connector is a mock shell; the only real paths are ECM/ENTSOG/GIE public sources and a price simulator with hardcoded hub levels. The vendor has no data rights to grant. | Commercial and legal |
| **B4 — no execution, ETRM or risk integration** | Deliberately out of scope by architecture (`AGENTS.md` rule 8). This is a product-positioning decision, not a defect. | Product scope |
| **B6 — licence forbids deployment; no SLA** | [LICENSE](../../LICENSE) grants no right to deploy or host. No support, warranty, upgrade or EOL commitment exists, and no breach-notification channel. | Legal and commercial |
| **B7 — single-author vendor** | 659 commits by one author over four months, hosted on a personal account. No entity, no escrow, no continuity plan. | Commercial |
| **B3 remainder — container CVE scanning** | `scripts/release/scan_vulnerabilities.py` records `TOOL_UNAVAILABLE` for the container and **no workflow installs or runs a container scanner**; the `container-acceptance` job inspects the digest and verifies license notices, not CVEs. `policy_ok` blocks `stable` on that status, so a stable promotion cannot happen while the gap is open. The remaining work is to install a scanner in the release workflow and record its result against the pushed digest. | Engineering, next iteration |

## The commands

```bash
# Documentation and configuration
python scripts/ci/check_markdown_links.py
python scripts/ci/check_config_contract.py
python scripts/ci/generate_env_template.py --check
python scripts/ci/check_toolchain_versions.py
python scripts/ops/check_config.py --env-file scripts/ci/fixtures/release.env --strict
python scripts/release/check_version_consistency.py

# Code
ruff check .
pytest -q tests
python -c "from apps.api.main import app; print(len(app.openapi()['paths']))"

# Web client
npm --prefix clients/web ci
npm --prefix clients/web run test
npm --prefix clients/web run build

# Database (needs a PostgreSQL 16 the code may migrate)
alembic upgrade head
pytest -q tests/integration
```

## Verification recorded for this change set

| Check | Result |
| --- | --- |
| `ruff check .` | clean |
| `check_markdown_links.py` | 271 documents, all local links resolve |
| `check_config_contract.py` | 69 declared, 62 read by the Python side, templates consistent |
| `generate_env_template.py --check` | both templates current |
| `check_toolchain_versions.py` | every declaration agrees |
| `check_config.py --strict` on a release fixture | no findings |
| `check_version_consistency.py` | all surfaces consistent |
| `pip-audit -r requirements-runtime.lock` | no known vulnerabilities (the shipped dependency set) |
| `pip-audit -r requirements.lock` | no known vulnerabilities (the full development set) |
| `python -m pip_audit` (installed environment) | no known vulnerabilities |
| Container image CVE scan | **not performed — no scanner runs**; pinned by `tests/contract/test_vulnerability_scan_coverage.py` |
| Python suite | **3,260 collected; 3,225 passed and 35 skipped, 0 failed** in default mode (no database, no opt-in variables). The 35 skips are 6 in `tests/release` plus 29 environment-gated integration tests. With PostgreSQL 16.2 at schema `0039` and the three opt-in variables, `tests/integration` contributes **143 passed / 0 skipped** and the whole-run figure becomes **3,254 passed / 6 skipped**. Counts per directory are in the note below. |
| `tests/integration` with PostgreSQL 16 | 143 passed, 0 skipped |
| Web tests | 864 collected, 859 passed, 3 skipped, 2 failures |
| Web build | `tsc` and `vite` pass, 240 modules |

Two caveats stated plainly, because they matter to anyone re-running this:

1. **The two Web failures are a platform artefact, not a product defect.** Both
   tests walk `src` with `readdirSync(dir, { withFileTypes: true, recursive: true })`
   and keep `entry.isFile()`. On the reviewing machine (Node v24.21.0, Windows)
   that call reports every real file as a symbolic link, so the walk returns zero
   files and the tests assert against an empty set. `lstatSync` on the same path
   reports a regular file, `git ls-files -s` records mode `100644`, and the rules
   the two tests assert were independently confirmed to hold by scanning 204 files
   with a `statSync`-based walk. CI pins Node 24.13.1 on ubuntu-latest, where the
   behaviour may differ, so no workaround was applied to the tests.

2. **One dev-only dependency advisory is open.** `npm audit` reports one high
   severity item, `source-map-js` 1.2.1 (`GHSA-68fv-2mgg-jv7q`), reached only
   through `vite → postcss → source-map-js`. It is not referenced in the built
   `dist/assets` bundles and `npm audit --omit=dev` reports zero. A lock-file bump
   resolves it.

## Per-directory test counts

Collected with `pytest --collect-only -q tests/<dir>`; executed with
`pytest -q tests/<dir>` in default mode, meaning no `RUNTIME_STORE_DATABASE_URL`
and none of the three opt-in variables.

| Directory | Collected | Passed | Skipped |
| --- | --- | --- | --- |
| `tests/unit` | 805 | 805 | 0 |
| `tests/contract` | 516 | 516 | 0 |
| `tests/api` | 471 | 471 | 0 |
| `tests/release` | 433 | 427 | 6 |
| `tests/security` | 367 | 367 | 0 |
| `tests/domain` | 256 | 256 | 0 |
| `tests/integration` | 143 | 114 | 29 |
| `tests/uat` | 81 | 81 | 0 |
| `tests/sdk` | 58 | 58 | 0 |
| `tests/ingestion` | 50 | 50 | 0 |
| `tests/optimization` | 36 | 36 | 0 |
| `tests/evals` | 20 | 20 | 0 |
| `tests/cli` | 19 | 19 | 0 |
| `tests/streaming` | 3 | 3 | 0 |
| `tests/workflow` | 2 | 2 | 0 |
| **Total** | **3,260** | **3,225** | **35** |

3,225 + 35 = 3,260, so the executed figures account for every collected test.

An earlier revision of this record stated 3,250 collected and 3,213 passed / 37
skipped for the same suite. Those figures were not reproducible at a single moment:
the collected total has since grown to 3,260, and the pass/skip split is 3,225/35.
The table above is the version that reconciles — collected equals passed plus
skipped — and every number in it was re-run rather than carried forward.

Two notes for anyone re-running this:

- `tests/api` must be split across invocations. All 55 files in one run exceeds the
  reviewing machine's limits and the process is killed; two batches of 28 and 27
  give 189 and 282 passing.
- The 29 integration skips are environment gates, not gaps: with a migrated
  PostgreSQL 16 and `EUROGAS_NEXUS_ACK_INTEGRATION_TEST`,
  `EUROGAS_NEXUS_CONTRACT_REVISION_INTEGRATION_TEST` and
  `EUROGAS_NEXUS_PAYMENT_TERMS_INTEGRATION_TEST` all set to `1` — the same three
  variables [`scripts/ci/run_postgres_ci.sh`](../../scripts/ci/run_postgres_ci.sh)
  exports — the same directory reports 143 passed and no skips. The intermediate
  states are consistent: setting two of the three gives 140 passed / 3 skipped, and
  setting none gives 133 passed / 10 skipped, each step moving exactly the file its
  variable gates.

## What this record does not claim

- It does not change the vendor's own disposition. The audit at
  [19_COMMERCIAL_ACCEPTANCE_AUDIT.md](../engineering/Architecture-V2/19_COMMERCIAL_ACCEPTANCE_AUDIT.md)
  records `NOT APPROVED FOR CUSTOMER PRODUCTION`, and the open items above are the
  reason that remains true.
- It does not claim the product is fit for a trading desk. B1 and B4 above are
  unchanged: the system has no licensed market data and no execution, ETRM or risk
  integration, and its own README states it is a decision-support workspace rather
  than an ETRM replacement.
- It does not verify anything on a customer environment. Every result above comes
  from the reviewing machine against locally built dependencies.
