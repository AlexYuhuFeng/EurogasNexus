# Deployment Roles

## Decision

Eurogas Nexus is delivered in exactly two device roles. The role controls
which components are installed and which secrets the device may hold.

| Role | Install on | Components | API endpoint | Database access |
| --- | --- | --- | --- | --- |
| `Server` | Dedicated server or VM | PostgreSQL, migrations, API, HTTPS gateway, ingestion workers, optional simulated price worker | Customer DNS name over HTTPS | Backend services only |
| `Client` | Trader workstation | Windows client or Linux client only | Existing server URL ending in `/api` | Never |

There is no fourth hidden mode. A client never receives a PostgreSQL URL,
database password, provider credential, or migration capability.

## Explicit deployment posture switch

The backend reads `EUROGAS_NEXUS_DEPLOYMENT_POSTURE`:

- `private_network_preview` (default): current posture; Server remains
  behind a customer firewall or VPN allowlist.
- `security_accepted`: only effective when
  `EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE` points to an existing
  operator-reviewed acceptance evidence file.

`public_network_deployment_allowed()` returns false unless both conditions are
true. The Windows deployment preflight remains unchanged in this repository
until a real deployment completes external security acceptance.

## Deployment environment profile

The runtime definition in this bundle sets `EUROGAS_NEXUS_ENV=release` and
`EUROGAS_NEXUS_API_PROFILE=release` for every service. These values are part of
the customer-facing posture, not decoration:

- they keep development-only surfaces out of a customer deployment. In
  particular the model-context-protocol (MCP) tool surface is refused in
  `trial`/`release` profiles until a persisted service identity exists, and the
  refusal is enforced by the backend and the MCP adapter - not by documentation
  alone;
- an unset profile defaults to `development`, the developer default, which says
  nothing about whether a deployment is safe to face a customer.

Do not remove or override these two variables in a customer deployment. A
deployment that really is a development or test worktree should say so
explicitly instead of leaving the profile unset.

## Release asset selection

The standalone Windows NSIS installer is **Client only**. Installing it creates
the desktop application and uninstaller; it does not install PostgreSQL, the FastAPI backend, Alembic
migrations, an HTTPS gateway, or ingestion workers.

Choose release assets by role:

- `Client`: download `Eurogas-Nexus-Client-{VERSION}-windows-x64-setup.exe` and connect it to an existing
  reachable HTTPS endpoint ending in `/api`.
- `Server`: download `Eurogas-Nexus-Server.zip` and run
  `Deploy-EurogasNexus.ps1 -Role Server`; the desktop installer is not required.
A desktop installation showing only the application executable and uninstaller
is therefore a normal Client installation, not evidence that the database or
backend has been installed. Release notes and asset names must make this
boundary explicit; production hardening is tracked as `DEP-001` in
`docs/release/RELEASE_READINESS.md`.

## Installation entry point

The Windows deployment bundle contains:

- `Deploy-EurogasNexus.ps1`: operator-facing role selector;
- `Install-EurogasNexusServerRuntime.ps1`: internal server-runtime primitive;
- `compose.yaml`, `Caddyfile`, and the API image reference;
- `release-identity.json`: the release identity (schema version, application and
  release version, channel, full commit SHA, and the API image repository
  pinned by `sha256` digest);
- English and Mandarin operating instructions.

The Client-only NSIS installer is published as a separate GitHub Release asset;
it is not included in the Server operator ZIP.

Both Windows entry points resolve version, channel and image reference from
`release-identity.json`; no source checkout and no manually set
`EUROGAS_NEXUS_VERSION` are required, and a conflicting value for that variable
or `EUROGAS_NEXUS_RELEASE_CHANNEL` is refused. A ZIP whose identity is missing,
malformed or internally inconsistent fails closed instead of guessing. The API
image is pinned by digest from that record - the installer does not silently
fall back to a moving tag, and an explicitly supplied image that contradicts
the pinned reference is refused instead of overriding it. A repository field
that carries a tag on its final path component is refused as malformed (a
registry port earlier in the reference is allowed). The ZIP's own SHA-256 is
deliberately **not** stored inside the archive (an archive cannot hash itself);
verify it against the release's `SHA256SUMS` and `release-manifest.json`
instead.

Run PowerShell as Administrator. Start with a non-destructive preflight:

```powershell
./Deploy-EurogasNexus.ps1 -Action Preflight -Role Client `
  -ServerApiUrl https://nexus.example.com/api `
  -ClientInstallerPath ./Eurogas-Nexus-Client-{VERSION}-windows-x64-setup.exe
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
7. ECB ingestion, and ENTSOG once approved (see "First run"), unless `-SkipPublicData` is set;
8. end-to-end API and database revision validation.

After the initial load, the `public-ingestion-worker` runs the product's data-ops scheduler
(`scripts/ops/run_dataops_scheduler.py`, the same path the reference store runs). Each
public source runs on its own schedule and read bounds, fails on its own, is retried by the
scheduler's policy and is shown with its state on Admin → Data sources. Provider failures
remain visible in `ingestion_runs` and the Source Center; the worker never manufactures
replacement data.

| Source | Schedule | Needs |
|---|---|---|
| ECB FX reference | daily 16:10 CET | nothing |
| ENTSOG flows, capacity (rolling 7 gas days), reference network (at most daily) | hourly | administrator approval (see "First run") |
| GIE AGSI storage, ALSI LNG (Europe and NW Europe countries, newest 30 gas days) | daily | approval and the firm's GIE key |
| GIE IIP REMIT storage and LNG outages | every 30 min | the GIE key |
| ENTSOG REMIT transmission outages | hourly | nothing |
| EIA Henry Hub | daily | the firm's EIA key |
| ENTSO-E day-ahead price, load, generation (NL, DE-LU, BE, FR; 7 days) | hourly | the firm's ENTSO-E token |
| Elexon GB generation, demand, market index | every 30 min | nothing |
| National Gas GB storage, LNG (5 days) and demand (8 days) | 3-hourly / 6-hourly | nothing |
| SONIA, €STR, SOFR fixings | daily | nothing |

Keys are stored on Admin → Data sources (Credentials; encrypted with
`EUROGAS_NEXUS_SECRET_KEY`), or provided as `GIE_API_KEY`/`GIE_API_KEY_FILE`, `EIA_API_KEY`
and `ENTSOE_SECURITY_TOKEN` in the runtime environment. Without its key a keyed source's
run is recorded as `credential_missing` and nothing is fetched; once the key is stored, an
off-by-default keyed source (GIE, GIE IIP, ENTSO-E) is switched on at the next scheduler
scan unless an operator switched it off. Licensed providers remain disabled until customer
credentials and data scopes are configured.

### First run: approve the public sources

ENTSOG and GIE are read only after an administrator approves them for the firm (a
fail-closed gate: their terms require attribution, and the product records who accepted
them). The installer does not approve anything: accepting a provider's terms is the
customer's decision. Until approved, the ingestion run is refused with the stable reason
`source_not_approved` (in Source Center, Data feeds and the run history), the desk screens
say "ENTSOG flows: source not approved — Admin → Connectors", and `/api/health/ready`
lists the sources under `attention` (readiness itself stays `ready`).

With a browser: Admin → Data sources → *Public sources that need your approval*, see
[ADMIN.md](../user/manual/ADMIN.md). Headless (idempotent; repeating an approval in force
changes nothing):

```bash
docker compose run --rm public-ingestion python scripts/ops/approve_public_source.py --list
docker compose run --rm public-ingestion python scripts/ops/approve_public_source.py \
  --all-open --operator <your id> --reason "<ticket or reason>" --accept-terms
```

`--revoke --source entsog --operator <id> --reason "<why>"` withdraws an approval (reads stop
at the next scheduled run; stored data is kept). `--list` prints each source's state and its
terms summary; `--accept-terms` states that
you read it and accept it for the firm (without it nothing is recorded). The approval is
audited (`source.approval`) and runs a bounded live check. GIE approved before its key
exists reads "approved, waiting for key" and is checked at the first read after the key
is stored.

Package version `0.8.0` on the `preview` channel has no multi-user login or SSO.
Server therefore requires `-PrivateNetworkOnly`, must sit behind a customer
firewall/VPN allowlist and must not be exposed to the public internet. HTTPS
protects transport; it
does not provide user authorization. Public or multi-tenant deployment is
blocked until backend authentication and authorization are implemented.

## Client role

Client requires the signed NSIS installer and an existing HTTPS server URL:

```powershell
./Deploy-EurogasNexus.ps1 -Action Install -Role Client `
  -ServerApiUrl https://nexus.example.com/api `
  -ClientInstallerPath ./Eurogas-Nexus-Client-{VERSION}-windows-x64-setup.exe
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
