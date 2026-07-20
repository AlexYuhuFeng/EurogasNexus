# Deployment Roles

## Decision

Eurogas Nexus is delivered in exactly three device roles. The role controls
which components are installed and which secrets the device may hold.

| Role | Install on | Components | API endpoint | Database access |
| --- | --- | --- | --- | --- |
| `Server` | Dedicated server or VM | PostgreSQL, migrations, API, HTTPS gateway, ingestion workers, optional simulated price worker | Customer DNS name over HTTPS | Backend services only |
| `Client` | Trader workstation | Windows client or Linux client only | Existing server URL ending in `/api` | Never |
| `AllInOne` | Demonstration, evaluation, or single-user workstation | Full Server role plus desktop client | HTTPS endpoint on the same device | Backend services only |

There is no fourth hidden mode. A client never receives a PostgreSQL URL,
database password, provider credential, or migration capability.

## Release asset selection

The standalone Windows NSIS installer is **Client only**. Installing it creates
the desktop application and uninstaller under the user's local application
directory; it does not install PostgreSQL, the FastAPI backend, Alembic
migrations, an HTTPS gateway, or ingestion workers.

Choose release assets by role:

- `Client`: download the signed desktop installer and connect it to an existing
  reachable HTTPS endpoint ending in `/api`.
- `Server`: download the Windows deployment bundle and run
  `Deploy-EurogasNexus.ps1 -Role Server`; the desktop installer is not required.
- `AllInOne`: download both the deployment bundle and signed desktop installer,
  then run `Deploy-EurogasNexus.ps1 -Role AllInOne`.

A desktop installation showing only the application executable and uninstaller
is therefore a normal Client installation, not evidence that the database or
backend has been installed. Release notes and asset names must make this
boundary explicit; production hardening is tracked as `DEP-001` in
`docs/release/PRODUCTION_READINESS_BACKLOG.md`.

## Installation entry point

The Windows deployment bundle contains:

- `Deploy-EurogasNexus.ps1`: operator-facing role selector;
- `Install-EurogasNexusServerRuntime.ps1`: internal server-runtime primitive;
- `compose.yaml`, `Caddyfile`, and the API image reference;
- English and Mandarin operating instructions;
- the signed NSIS client installer as a separate release asset.

Run PowerShell as Administrator. Start with a non-destructive preflight:

```powershell
./Deploy-EurogasNexus.ps1 -Action Preflight -Role Client `
  -ServerApiUrl https://nexus.example.com/api `
  -ClientInstallerPath ./Eurogas-Nexus_0.5.0_x64-setup.exe
```

The preflight never installs Docker, starts containers, changes firewall rules,
or writes credentials.

## Server role

Server requires:

- Windows 10/11 or Windows Server supported by the chosen Docker/Compose runtime;
- PowerShell 5.1 or newer;
- Docker Engine and Docker Compose v2 already installed and running;
- at least 8 GB RAM and 10 GB free disk;
- customer DNS name resolving to the server;
- customer-owned PEM certificate and PEM private key for that DNS name;
- inbound HTTPS port approved by the customer administrator.
- a specific loopback or private IP assigned to the server; `0.0.0.0` is refused.

Eurogas Nexus does **not** silently download or install Docker Desktop, WSL,
PostgreSQL, certificates, or a certificate authority. Those operations affect
licensing, reboots, enterprise policy, and trust stores and therefore remain an
explicit customer prerequisite.

```powershell
./Deploy-EurogasNexus.ps1 -Action Install -Role Server `
  -ServerName nexus.example.com `
  -HttpsBindAddress 10.20.30.40 `
  -HttpsPort 8443 `
  -TlsCertificatePath C:/secure/nexus.example.com.crt `
  -TlsPrivateKeyPath C:/secure/nexus.example.com.key `
  -PrivateNetworkOnly
```

Installation performs, in order:

1. prerequisite, port, certificate, and Compose checks;
2. random database and backend secret generation;
3. restricted server configuration under `%ProgramData%\Eurogas Nexus`;
4. PostgreSQL startup and health check;
5. explicit `alembic upgrade head` in a one-shot container;
6. API and HTTPS gateway startup;
7. ECB and ENTSOG ingestion unless `-SkipPublicData` is set;
8. end-to-end API and database revision validation.

After the initial load, the runtime refreshes ECB, ENTSOG operational/capacity,
and keyed GIE observations every 30 minutes and ENTSOG reference topology every
24 hours. Provider failures remain visible in `ingestion_runs` and Source Center;
the worker does not manufacture replacement infrastructure data.

GIE ingestion remains disabled until the customer stores its own GIE key via
the backend-managed Data Sources workflow. Licensed providers remain disabled
until customer credentials are configured.

`v0.5-preview` has no multi-user login or SSO. Server and AllInOne therefore
require `-PrivateNetworkOnly`, must sit behind a customer firewall/VPN allowlist,
and must not be exposed to the public internet. HTTPS protects transport; it
does not provide user authorization. Public or multi-tenant deployment is
blocked until backend authentication and authorization are implemented.

## Client role

Client requires the signed NSIS installer and an existing HTTPS server URL:

```powershell
./Deploy-EurogasNexus.ps1 -Action Install -Role Client `
  -ServerApiUrl https://nexus.example.com/api `
  -ClientInstallerPath ./Eurogas-Nexus_0.5.0_x64-setup.exe
```

The tool validates `/api/health` before installing, runs the signed NSIS package,
and writes only this client deployment record:

```json
{
  "schema_version": 1,
  "role": "Client",
  "api_base_url": "https://nexus.example.com/api"
}
```

The desktop shell reads that record on first start. The user can later test and
change the endpoint in Settings. Web deployments set
`VITE_EUROGAS_API_BASE_URL` at build/deployment time and must use the same HTTPS
policy.

The deployment tool rejects an invalid or unsigned installer. Internal preview
testing may use `-AllowUnsignedPreview`; customer delivery must not use that
switch.

## AllInOne role

AllInOne is Server plus Client on one device. It has the same certificate and
Docker requirements as Server and also requires the NSIS installer:

```powershell
./Deploy-EurogasNexus.ps1 -Action Install -Role AllInOne `
  -ServerName nexus-workstation.example.com `
  -HttpsBindAddress 127.0.0.1 `
  -HttpsPort 8443 `
  -TlsCertificatePath C:/secure/nexus-workstation.example.com.crt `
  -TlsPrivateKeyPath C:/secure/nexus-workstation.example.com.key `
  -ClientInstallerPath ./Eurogas-Nexus_0.5.0_x64-setup.exe `
  -EnableSimulatedPrices `
  -PrivateNetworkOnly
```

`-EnableSimulatedPrices` is opt-in. Simulated feeds use the same ingestion,
normalization, PostgreSQL persistence, API, SDK, and client path as licensed
feeds, while retaining `_Sim` provenance. Replacing a simulated provider with a
licensed connector does not change client workflow or storage boundaries.

## Internet requirements

Internet is required to pull container images and ingest current public data.
Client installation needs network access to its configured API. Fully offline
installation requires a separately prepared image archive and package bundle;
the bootstrapper never performs an undisclosed internet search or download.

## Operations

- `Repair` reapplies Compose configuration and migrations without deleting data.
- `Validate` checks API health, PostgreSQL connectivity, required tables, and
  Alembic revision.
- `Uninstall` stops the server runtime but preserves the PostgreSQL volume.
- `Uninstall -PurgeServerData` is the only path that deletes the runtime volume.
- Remove the desktop client through Windows Apps after disconnecting its managed
  endpoint configuration.

Back up the PostgreSQL volume before upgrades or purge. Never copy `.env` files,
private keys, vendor payloads, or customer data into support tickets or the
public repository.
