# Re-evaluation verdict

Date: 2026-10-07. Baseline: the working tree carrying revisions through
`0039_identity_api_key_hash_width` plus this round's remediation.

This is an interim remediation record. Engineering work and end-to-end acceptance
remain open. Historical measurements below apply only to their recorded scope;
see [the current contract workflow recheck](05_CONTRACT_FLOW_RECHECK.md) for fresh
UI persistence evidence and unresolved lifecycle and layout defects.

It is an engineering document. It is not legal advice, certification, or an approval to
deploy.

## The verdict in one line

**The software is now materially better than it was, and it still must not be deployed to
a customer**. Both engineering/acceptance gaps and external evidence remain unresolved.

The vendor's own disposition is unchanged and correct:
[RELEASE_READINESS.md](../RELEASE_READINESS.md) records `NOT APPROVED FOR CUSTOMER
PRODUCTION`, and
[FUNCTIONAL_ACCEPTANCE_REPORT.md](../FUNCTIONAL_ACCEPTANCE_REPORT.md) records `NOT ACCEPTED`.
Nothing in this remediation overturns either. Open engineering gates include
workflow completion, frontend validation, image scanning and operations evidence.
External agreements and signatory/entitlement evidence also need verification;
a personal GitHub account does not establish that a contracting entity is absent.

## Gate status

| Gate | Before | Now | Basis |
| --- | --- | --- | --- |
| Reproducible build environment | absent | **closed** | three hash-pinned locks install with `--require-hashes`; `uv` regenerates them; toolchain pins agree across 8 declaration sites |
| Dependency vulnerability audit | environment only | **closed** | `pip-audit` against the running environment, the shipped runtime lock and the full lock; all report no known vulnerabilities |
| Container image CVE scan | none | **open, recorded** | no scanner runs in any workflow; `policy_ok` blocks `stable` on that status, and a test pins the gap so it cannot be quietly assumed closed |
| Configuration correctness | 9 of 69 variables documented; a dead flag taught operators a control that did not exist | **closed** | a 69-entry contract, generated templates, a preflight that refuses to start a misconfigured deployment, and a BOM fail-open fixed |
| Schema/DB correctness | a 69-character digest written into `VARCHAR(64)` | **closed** | migration `0039`; the deployed column and the model agree; a test walks the migration chain, and a live PostgreSQL run is 143/143 |
| Authentication and session security | hex PKCE, `Secure` cookie suppressed behind a TLS-terminating proxy | **closed** | base64url per RFC 7636; an explicit cookie policy that forces `Secure` on production profiles regardless of observed scheme |
| Trader-visible market data correctness | a hub spread showing the opposite sign, varying with API row order | **closed** | one resolution module with a stated convention; verified in a real browser at +2.16 EUR/MWh, stable across reload |
| Dataset build reliability | a repeat build returned HTTP 500 `IntegrityError` with an empty explanation panel | **closed** | content-addressed snapshots are idempotent; a genuine conflict returns 409 with structured issues |
| Backtest honesty | a headline return over a period the engine could price on 16% of days | **closed** | `PARTIAL_PERIOD_COVERAGE` warning below 50% coverage, carried in the persisted metric set |
| Dataset split declarations | `split_specs` declared and never read | **closed** | splits are validated (inside period, non-overlapping, non-negative embargo) and their row coverage is reported in the snapshot metadata |
| Frontend suite | 864 tests, 2 failures | **1 defect remaining** | 879 tests, 2 failures, both the same Node/Windows `readdirSync(recursive)` artefact; `release.yml` gates packaging on this suite, so it must be resolved on a runner before a stable release |
| Operations handover | P0 defects on the documented install and DR paths | **closed, conditional** | the installer writes the public API token; the DR drill runs end to end; 5 P1 items remain (image digest pinning, an `.env` BOM guard, token-in-query-string logging, a Prometheus sample, a probe-key path) |
| Browser acceptance | never run | **partial; full workflows open** | Historical 96-scope rendering/accessibility sweep is not complete CRUD/strategy/dataset acceptance. Current contract create/edit/reload passed, and the discovered library alignment defect was repaired and visually rechecked. Retirement and other workflows remain open; see report 05. |
| Python suite | 3,260 collected | **closed** | 3,162 passed, 6 skipped, 0 failed across 15 directories; 143/143 integration against live PostgreSQL |
| Coverage measurement | not measured | **closed as evidence** | 75.2% of 27,943 statements; no threshold is enforced, deliberately |
| Legal entity, licence, SLA, signing, hosting | — | **open, external** | see below |

## Closed by this remediation

Each item below was reproduced, changed, and re-verified. Evidence files are in
`.dnx-out/`, and the per-item record with commands is in
[VENDOR_REMEDIATION_ACCEPTANCE.md](../VENDOR_REMEDIATION_ACCEPTANCE.md).

**Severity 1 — correctness and security**

1. `identity_api_keys.key_hash` was `VARCHAR(64)` while the writer emits a 69-character
   keyed digest, so **minting any API key failed on a deployment that set the credential
   key** — the configuration the shipped compose file uses. Invisible to 3,300 unit tests
   because SQLite ignores a declared length. Fixed by migration `0039`; the PostgreSQL
   server's own log records the original `22001` refusals.
2. PKCE used a hex challenge instead of base64url, so a conformant identity provider would
   reject the exchange and browser SSO could not complete.
3. The session cookie's `Secure` attribute depended on an observed scheme that is always
   `http` behind the shipped TLS-terminating proxy.
4. The Python SDK read a token name nothing sets, so it sent no credential at all.
5. The dataset build returned HTTP 500 on a repeat, with an empty explanation panel.
6. The hub spread on the trader's market screen showed the wrong sign and varied with API
   row order.
7. A `.env` with a UTF-8 BOM silently dropped its first variable, degrading a release
   environment to `development` and skipping the production guards.

**Severity 2 — deliverability and operations**

8. CI installed dependencies from the index rather than the locks, so the build that
   authorised publication was not reproducible.
9. The installer's `.env` omitted `EUROGAS_NEXUS_PUBLIC_API_TOKEN`, so the documented
   installation path could not start.
10. `backup_restore_drill.py` replaced its child environment with `{"PGPASSWORD": ...}`,
    which removed `PATH` and made the documented disaster-recovery drill impossible on
    every platform.
11. The Prometheus exposition contained a bound method object where a number belongs, which
    makes a scrape fail entirely.
12. `split_specs` was declared and never read: a declared holdout was silently ignored.
13. A backtest over 16% of its period presented a headline result with no coverage warning.
14. Documentation stated 163 OpenAPI paths where the application publishes 182, and named a
    schema head seven revisions stale as a pre-production requirement.

**Severity 3 — hygiene that had already caused repeat failures**

15. `.dnx-*` directories were excluded from lint and Git by explicit lists, which were wrong
    three times; a local dependency tree could have been committed with `git add -A`.
    Replaced by globs, with a test.
16. A tracked file whose name ended in a private-use character carried the `.automation`
    harness listing into source archives. Removed from the index without rewriting history.
17. Thirteen tracked documents carried UTF-8 BOMs. A repository-wide gate now fails on one.

## External evidence still to verify

These evidence requests supplement the open engineering gates above. Absence from
the reviewed repository is not proof that an agreement, entity or entitlement
does not exist outside it. No legal determination is made here.

| What is missing | Why code cannot supply it | Who provides it | How it will be verified |
| --- | --- | --- | --- |
| **Contracting identity and authority** | The reviewed repository does not supply sufficient evidence of the proposed contracting party or signatory authority. GitHub account type cannot settle this question. | Vendor or proposed contracting party | Appropriate identity/entity and signatory evidence; an agreement naming the party |
| **Deployment authorization evidence** | [`LICENSE`](../../../LICENSE) refers to a separate written agreement for deployment. No executed agreement was supplied in this review; this does not prove one does not exist. | Copyright holder, with counsel as appropriate | Supplied agreement reviewed against intended use |
| **An EULA / terms of supply** | No document states the customer's rights, warranty, liability cap or acceptable use. | Counsel | Executed terms |
| **An SLA, support and vulnerability-response commitment** | No response times, escalation path, support hours or EOL policy exist. `SECURITY.md` names only "the repository owner's private channel", with no address and no time limit. | Vendor management, with counsel | A signed support schedule; a monitored security contact |
| **A code-signing certificate** | Signing is `unsigned_pending_external` by its own record. A certificate is an operator-owned artefact and cannot be generated in a repository. | The customer's PKI or a commercial CA | A signed installer whose signature verifies on the target platform |
| **Source hosting and continuity** | A single author with 659 commits on a personal account, no escrow, no succession plan. | Commercial arrangement | Escrow agreement or a hosting arrangement with named maintainers |
| **Licensed market data** | Simulated fixtures and connector code do not establish commercial entitlement. Applicable provider agreements were not supplied for this review. | The customer's data vendors, or the vendor where applicable | Entitlement evidence naming view/derive/export/LLM/training rights |
| **A decision on product scope** | No execution, ETRM or risk integration exists — excluded deliberately by the architecture. This is a positioning decision, not a defect. | Product owner | A written scope decision |
| **Container scan evidence** | A scan against the exact delivered image digest remains missing. Whether credentials or procurement are needed depends on the chosen registry/tool; this is still an engineering acceptance task. | Release/platform team | Actual scan report bound to the delivered digest |

## What a reviewer should do next

1. **Read [VENDOR_REMEDIATION_ACCEPTANCE.md](../VENDOR_REMEDIATION_ACCEPTANCE.md) before the
   four perspective reports.** It contains the correction of a defect this review reported
   and withdrew; a reader should know the standard applied before relying on the rest.
2. **Treat the four reports in `acceptance/` as input, not verdict.** Each was written from
   one seat and each has a stated scope limit. `01` did not run the product;
   `03` ran it and could not use it for decisions; `04` could not start the container stack
   because registry access is unavailable here.
3. **Commit before relying on any of this.** The work sits uncommitted in a dirty working
   tree, so the reviewed state has no tag and no commit that reproduces it. This is the
   reproducible acceptance target. The user has authorized a push after review and
   validation; that authorization does not make the unreviewed changes accepted.
4. **Resolve the frontend suite on a CI runner.** Two tests fail here for a platform reason
   that `release.yml` would not reproduce, but the file gating packaging on `npm test` means
   this must be confirmed rather than assumed.

## Scope limits of this verdict

- Every measurement was taken on this machine and this working tree. It is not a statement
  about any published release: all 51 published tags are `prerelease`, and the most recent
  artefact predates the current head by 438 commits.
- The container stack was never started, and the reason is narrower than "the registry is
  unreachable". The Docker engine answers (29.8.1) and is empty. A blob request resolves and
  redirects correctly, but the redirect target `production.cloudfront.docker.com` is
  unreachable from this host **both directly and through the local proxy**, so layer bytes
  cannot be fetched and `docker pull` cannot complete for any image. The registry API itself
  is reachable through the proxy (`registry-1.docker.io` answers 401, `auth.docker.io`
  answers 200). The two Docker Hub images the stack needs are ordinary public images and
  exist; the vendor's API image is published to `ghcr.io` by `release.yml`, which is
  reachable from here, and whether a tag was ever pushed cannot be checked anonymously. So
  `docker compose up`, image boot, migration-on-start and authenticated smoke are unverified
  **because this host cannot fetch Docker Hub layer blobs**, not because the vendor failed to
  publish anything.
- The PostgreSQL serving this verification is not a container: it is a PyPI-installed
  `pgserver` PostgreSQL 16.2 running as a Windows process, chosen when Docker Hub was
  believed unreachable. `docker ps -a` is therefore empty, and no database appears in Docker
  Desktop, because no database container was ever created.
- No test ran against a customer identity provider, and no native/Tauri installation was
  performed. Chromium here is Playwright's headless shell.
- Coverage is reported as evidence, not as a quality score, and no threshold is enforced.
  The lowest-covered modules are the persistence and projection layers, none of which is the
  highest-risk area, which is one reason a threshold would reward the wrong tests.
