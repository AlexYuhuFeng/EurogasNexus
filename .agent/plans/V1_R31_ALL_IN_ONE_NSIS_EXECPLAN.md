# V1 R31 Windows AllInOne NSIS Execution Plan

## 1. Goal

Publish a clearly named Windows AllInOne NSIS installer in every GitHub Release.
The installer must turn a Windows test workstation with Docker Desktop and
Docker Compose v2 into a working Eurogas Nexus preview environment in one
guided installation: desktop frontend, FastAPI backend, PostgreSQL, explicit
Alembic migration, DB-resident preview inputs, simulated market feeds, and
optional public-source ingestion.

## 2. Non-goals

- Do not install Docker Desktop, WSL, Python, Node.js, Rust, PostgreSQL, or Git.
- Do not expose the preview API outside loopback.
- Do not add authentication, SSO, trade execution, nomination submission, or
  licensed-provider credentials.
- Do not silently delete the PostgreSQL volume during uninstall or upgrade.
- Do not turn the standalone desktop-client NSIS package into a server package.

## 3. Product boundary

The Release exposes distinct packages:

- `Client-only`: desktop frontend for an existing backend.
- `AllInOne`: local evaluation stack for a workstation that already has Docker.
- `Server`: operator-managed private-network runtime requiring explicit TLS and
  network configuration.

AllInOne remains decision support. It does not place orders, submit nominations,
or execute trades. Simulated price sources use the same ingestion, PostgreSQL,
API, SDK, and client boundaries as licensed providers and retain `_Sim` lineage.

## 4. Files to create or modify

- `.github/workflows/release.yml`
- `deploy/runtime/compose.yaml`
- `installer/windows/all-in-one/EurogasNexusAllInOne.nsi`
- `scripts/install/windows/Install-EurogasNexusServerRuntime.ps1`
- `scripts/install/windows/Install-EurogasNexusAllInOne.ps1`
- `scripts/install/windows/Manage-EurogasNexusAllInOne.ps1`
- `scripts/release/build_all_in_one_installer.ps1`
- `scripts/release/package_deployment_bundle.ps1`
- `scripts/release/package_deployment_bundle.sh`
- `docs/contracts/16_RELEASE_DEPLOYMENT_CONTRACT.md`
- `docs/deployment/DEPLOYMENT_ROLES-EN.md`
- `docs/deployment/DEPLOYMENT_ROLES-CN.md`
- `README.md`
- `tests/release/test_all_in_one_installer.py`
- `tests/release/test_deployment_roles.py`

## 5. Dependency policy

Runtime prerequisites are Windows 10/11, PowerShell 5.1+, Docker Desktop or an
approved Docker Engine, Docker Compose v2, 8 GB RAM, 10 GB free disk, and
internet access for first image pull. NSIS is build-time only and is installed
on the GitHub Windows runner. The installer adds no application runtime
dependency and uses Windows PowerShell plus Docker CLI already on the host.

## 6. Data policy

- PostgreSQL is the only runtime source of truth.
- The installer generates database and backend secrets with a cryptographic RNG.
- Secrets are written under `%ProgramData%\Eurogas Nexus` with restricted ACLs
  and are never displayed in NSIS, PowerShell, logs, or release metadata.
- Preview contracts and simulated prices are inserted by backend scripts into
  PostgreSQL with explicit preview or `_Sim` provenance.
- Uninstall preserves the named PostgreSQL volume. Purge is a separate explicit
  administrator action with a confirmation prompt.

## 7. API impact

No public route changes. AllInOne writes the managed desktop endpoint as
`http://127.0.0.1:8765/api`. The API binds only to loopback on the host. Server
deployments continue to use operator-provided private-network HTTPS.

## 8. DB impact

The installer starts `postgres:16-alpine`, waits for health, and then invokes
the existing `migrate` one-shot container. It must never run migrations during
application import. In preview mode it then invokes an explicit one-shot seed
service and starts the simulated feed worker. Existing volumes survive repair,
upgrade, and normal uninstall.

## 9. Tests

- Contract-test the distinct Client and AllInOne asset names.
- Verify the AllInOne installer embeds the client package and runtime payload.
- Verify the bootstrap requires Docker but not Python, Node.js, Git, PostgreSQL,
  certificates, or a customer API key.
- Verify loopback binding, migration ordering, preview seeding, simulated feed
  startup, secret generation, ACL restriction, and non-destructive uninstall.
- Run the PowerShell bootstrap with a fake Docker executable for success and
  failure paths so CI never starts live infrastructure.
- Compile the NSIS package and inspect its output name and embedded payload.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
npm --prefix clients/web run build
powershell -File scripts/release/build_all_in_one_installer.ps1 -ClientInstallerPath <client-nsis.exe> -OutputDirectory dist/releases
```

The validation suite does not start Docker or call external providers. The
GitHub Release build publishes the already-built API image before packaging the
AllInOne installer.

## 11. Acceptance criteria

- GitHub Release contains a clearly named `AllInOne` NSIS `.exe` and a clearly
  named standalone `Client-only` NSIS `.exe`.
- A test machine with only Windows and running Docker Compose v2 needs no manual
  certificate, source checkout, Python, Node.js, Rust, Git, or PostgreSQL setup.
- Installation starts PostgreSQL, runs Alembic explicitly, seeds preview runtime
  rows, starts simulated price ingestion, starts API, installs the desktop
  client, writes the managed loopback API endpoint, and validates health.
- Failed deployment prevents a successful installer completion and points to a
  non-secret log.
- Repair is idempotent. Normal uninstall preserves data. Explicit purge removes
  the Docker volume only after confirmation.
- Full repository validation and NSIS compilation pass.

## 12. Rollback notes

Revert the R31 commit to remove the AllInOne wrapper from future Releases. The
standalone client and existing Server deployment remain usable. On a deployed
workstation, run the installed Stop command and uninstall the wrapper; the
PostgreSQL volume remains available unless the operator separately invokes the
purge command.
