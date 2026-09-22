# Deployment handover index

Commercial status (2026-09-22): **not approved for production**. Source-checkout
commands below require the engineering repository and its dependencies; they are
not commands available in the small Server operator ZIP. That ZIP installs a
published image, not a source checkout. Obtain the release-specific manifest,
SBOM/notices, checksums, signed artifacts and operator runbooks separately before
customer acceptance. Never infer signing or test status from this static page.

**Audience:** the deployment IT and commercial-handover team who receive this platform.
**Purpose:** one page that says what is verifiable where, what is signed, and who owns each item
that this repository cannot close on its own. Written from the audience review's ninth-ranked next
step: the programme publishes a great deal of evidence, and nowhere in one place says *which of it a
receiving team can check for itself*.

Everything below is a statement about **this repository's own state**, not about any deployment. A
deployment's own posture is reported at runtime by `GET /api/health` and `/api/health/live`.

## 1. What you can verify without us

| Claim | How you check it | Where the record is |
|---|---|---|
| The code is what it says it is | `git log --oneline`, and the release manifest's checksums | `release-assets/release-evidence/` |
| The API answers and identifies its callers | `GET /api/health` → `authentication: enforced \| anonymous_allowed` | derived from the deployment's own configuration |
| The runtime schema is complete | `python scripts/ops/validate_runtime_db.py --json` → `missing_tables: 0`, `alembic_revision` | `docs/operations/LIVE_POSTGRESQL.md` |
| The database can be restored | `python scripts/ops/backup_restore_drill.py` | `docs/operations/BACKUP_RESTORE.md` |
| The automated security posture | `python scripts/security/run_security_acceptance.py` | `docs/release/SECURITY_ACCEPTANCE_EVIDENCE.md` |
| Dependencies carry no known critical advisory | `python scripts/release/scan_vulnerabilities.py --channel preview` | `release-assets/release-evidence/vulnerability-scan.json` |
| The product surface is bounded | `python -m pytest tests/contract/test_api_surface_stability.py -q` | `docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md` |
| The whole UI works in a browser | `node scripts/uat/browser_workflow_smoke.mjs` against a seeded runtime | `artifacts/uat-browser/summary.json` |
| Licence obligations | `python scripts/ci/audit_dependencies.py` | `THIRD_PARTY_NOTICES.md` |

Two of these need a configured environment (`RUNTIME_STORE_DATABASE_URL`), and the API's callers are
identified in every profile: present the deployment token (`EUROGAS_NEXUS_PUBLIC_API_TOKEN`) or a
session, or the check measures a refusal. The harnesses refuse to run rather than report one.

## 2. What is signed or supplied by this repository

| Artefact | State |
|---|---|
| Python package, Web client bundle, deployment bundle | built and checksummed by the release dry run |
| Container image | release workflow builds and publishes to GHCR; verify the exact digest and provenance of the selected release |
| SBOM (SPDX 2.3) | generated per release |
| Release notes and checksums/manifest | generated per release |
| Desktop bundles and installers | release workflow defines Windows x64 and Linux x64/ARM64 builds; availability, signature and install acceptance must be verified for the exact release; a developer-machine toolchain limitation is not a product delivery statement |
| Binaries signing / notarisation | **not done**: recorded as unsigned/pending-external in the release evidence |

## 3. What only you can close

Each of these is an external item by construction, not an oversight. They are the same list the
security-acceptance script prints as `External review: BLOCKED`.

| Item | Owner | What "done" looks like |
|---|---|---|
| Penetration test of the deployed system, and a dependency CVE re-run in your environment | your security team | a signed report; the platform's own automated checks are not a substitute |
| OIDC issuer/JWKS TLS review | your identity team | the issuer, client id, redirect URIs and certificate chain reviewed against your policy |
| Backup/restore and incident-response drill **on the target** | your operations team | the drill run against production data, not against the container this repository exercises |
| Provider certifications and licensed-data terms | your commercial team | the vendors' own attestations, held by you |
| Production install, network placement, VPN posture | your IT team | the deployment's posture asserted in its own configuration; the platform reports what it was told, it does not decide it |
| User acceptance | your business owners | the UAT checklist in `docs/release/` signed against a real deployment |
| Choosing whether the deployment trusts its network | your security owner | `EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS` set deliberately, or left off; the health payload then reports which |

## 4. What this repository does **not** verify, and says so

- **No production evidence.** Every database, browser and load figure in
  `docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md` comes from a local container, a local dev
  server or CI - never from a customer deployment. The document says which, per line.
- **No current customer desktop acceptance.** A build artifact is not evidence of
  window management, notifications, tray, protocol registration, upgrade or
  recovery behavior. Require platform-specific acceptance for the delivered version.
- **No real provider calls.** Provider paths are exercised against stubs and recorded fixtures; a
  live provider needs credentials this environment does not hold.
- **No unstated guarantees about your data.** Entitlement, data-scope and commercial-boundary
  behaviour is enforced and tested, but the *scopes themselves* are your configuration.

## 5. Where to start

1. `docs/operations/LIVE_POSTGRESQL.md` — point the platform at a database and prove the schema.
2. `docs/release/INSTALL_WINDOWS.md` / `INSTALL_LINUX.md` — install.
3. `docs/deployment/DEPLOYMENT_ROLES-EN.md` — who runs what, and with which capability.
4. `.env.example` — every variable that changes behaviour, with the reason it exists.
5. `docs/release/SECURITY_ACCEPTANCE_EVIDENCE.md` — the automated evidence and the external list.
