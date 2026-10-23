# Backend runtime acceptance — 2026-10-22

## Verdict

The Linux amd64 backend runtime passed the local functional and security checks
below. This is a reviewable local candidate, **not production delivery approval**.
The current checkout contains uncommitted work; no image, package or repository
change was pushed, signed or published.

## Functional fixes and verification

- Strategies are owner-private by default, with owner-controlled deployment-local
  PUBLIC or explicit GROUPS sharing. See [role/privacy acceptance](16_LINUX_ROLE_PRIVACY_ACCEPTANCE.md).
- Jobs bind a separate stable owner identity in migration 0041. Name-only legacy
  jobs remain quarantined; attribution strings cannot confer authority.
- Review-pack access follows its actual owning agent run, fixing confirmation and
  replay without expanding another user's access.
- Compose now expects the API's actual `ready` readiness status. Previously its
  `ok` comparison kept a healthy API unhealthy and blocked the dependent gateway.
- API and CLI readiness require the expected Alembic revision, not just table
  names. Revision 0040 lacks job-owner columns despite containing all table names;
  it now returns 503 rather than falsely passing as a 0041 runtime.
- Release smoke forwards an explicitly configured named identity, and still fails
  on authorization refusal. It does not turn a deployment token into ownership.
- The restore drill now probes `/api/health/ready` against the restored target and
  requires the current revision. Its former liveness-only check could pass without
  exercising the restored database. The source configuration is restored afterwards.

| Evidence | Result |
| --- | --- |
| Full API + SDK regression | 552 passed before final packaging/dependency remediation; subsequent SDK suite: 68 passed. |
| Full security + contract regression | 952 passed before final readiness/packaging remediation; affected readiness, packaging and restore checks rerun below. |
| Release/readiness selection | 450 passed, 35 skipped. Skips are platform/tool-dependent; not counted as native acceptance. |
| Final readiness/probe/smoke subset | 20 passed, 15 platform-dependent skips. |
| Final artifact exclusion/license tests | 23 passed. Real wheel payload and copied runtime tool inventory verified. |
| Restore-target readiness regression | 2 passed: current target succeeds, stale target fails, source remains untouched. |
| Actual final release-image smoke | 8/8 HTTP checks passed on image `8cacf6d651fb…`; UID 100, schema 0041, build CA absent, setuptools absent. |
| Actual PostgreSQL role workflows | 77/77, plus strategy sharing25/25 and trader contract15/15, repeated on Alpine release image before the final restore-helper-only rebuild. |
| Job isolation on PostgreSQL | 7/7, including legacy name/ID collision and refused cancellation preserving foreign state. |
| Installed wheel API/SDK | API6 and SDK6 HTTP checks; additionally the readiness-fixed installed API passed release smoke8/8. |
| Local backup/restore | Fresh isolated PostgreSQL target, revision0041, no missing tables, restored API readiness200; 4.0s observed. Source database preserved. |
| Web | Production build passed; 935 tests passed, 3 skipped. |

Suite counts overlap; they must not be added as a unique-test count. Full-repository
Ruff and local Markdown links pass. Dependency deprecation warnings remain.

## Image and dependency security

The first Debian-based image failed the current HIGH/CRITICAL gate with 46 HIGH
and 1 CRITICAL package findings. These were retained as failure evidence, not
suppressed. Runtime Python findings included certifi GHSA-6q48-6c7w-9gw2 and two
vulnerable vendored packages in unnecessary base-image setuptools.

The final Dockerfile uses the official Python 3.11 Alpine image pinned in both
stages to manifest digest
`sha256:03c8e956bf1eee7763faf3a9fbb24b3ff9c0496cc2dbc5bcb0d6ac1f6268a287`
(observed Alpine3.24.3). It retains the application stack and locked Python runtime,
uses Alpine's non-root user creation, and removes setuptools/wheel after installing
the project. `certifi>=2026.10.19` is enforced in inputs and refreshed hashed locks.
Full development-lock regeneration also reconciled already-declared pytest-cov
and its dependencies; no runtime feature was added by those development entries.

Managed-proxy CA trust is supplied only through an optional BuildKit secret for
package installation. No TLS verification is disabled; that CA file is absent
from the running image. Runtime license-text collection and artifact exclusion
checks execute during the real image build and pass.

Final local runtime image:
`sha256:8cacf6d651fb5253bb81fafaa93ef92fd2901fc7fe2ac9751fdee1d77295bae3`.
This identifies the locally built amd64 image, not a published manifest.

- Trivy0.76.1 was checked against its official release SHA-256. A fresh vulnerability
  database came from official `ghcr.io/aquasecurity/trivy-db:2`; the default mirror
  was denied by environment network policy. Final image scan with
  `--scanners vuln --severity HIGH,CRITICAL --exit-code 1` passed with zero findings
  at those severities. No ignore-unfixed option or new suppression was used.
- pip-audit of `requirements-runtime.lock`: zero known vulnerabilities.
- npm audit of production Web dependencies: zero known vulnerabilities.
- Lower OS severity findings are outside the HIGH/CRITICAL scan's claim. These
  results are dated evidence and require refreshing for a future release.

The final wheel is retained privately in `.local-runtime/backend-release/` with
SHA-256 `0bea081e2ad4666c23ee52f4e9800a568d7de503ec20d259edbb5cc507ac68c9`.
Scan JSON and local evidence are in that directory and
`.local-runtime/strategy-sharing/`. No credentials are included in tracked reports.

## Bounded performance evidence

Strategy-list audiences are fetched once for the visible limited page rather than
once per owned strategy. A real SQL-count regression compares one and three GROUPS
rows, preserves sorted audiences, and checks detail parity and reader redaction.

A loopback HTTP baseline against the final release image used 60 authenticated GETs
with concurrency4, synthetic local PostgreSQL and 20 samples per path. All returned
200; total time was1.55s. Observed p95 latency was147.52ms for `/api/strategies`,
155.56ms for `/api/jobs` and153.98ms for `/api/me/groups`. This bounds this small
local workload only; it is not a production capacity or latency commitment.

## Remaining delivery gates

Customer identity-provider acceptance, licensed-provider certification, production
backup/restore placement and deployment-specific security/operational approval
remain external requirements. Native desktop installer/signing and other operating
systems have not been revalidated for this tree. The local image test covered amd64;
no arm64 execution or full customer gateway/TLS deployment is claimed.

Broader UI overflow/design work remains deferred under the backend-first scope.
Regional exchange remains disabled and last in priority. Canada (`CA`) replaces
North America; the provisional envelope establishes no lawful transfer basis or
residency assurance. Applicable regulations and provider licences must be reviewed
before selecting established cross-region mechanisms.
