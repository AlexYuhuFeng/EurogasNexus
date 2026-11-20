# Delivery package: Eurogas Nexus 1.0.0 beta

What the customer receives for acceptance of Eurogas Nexus 1.0.0 beta, how to check it, and
the order to install it. Release `v1.0.0-beta.1` (package version `1.0.0b1`), a GitHub
pre-release on the `beta` channel; not a production (GA) release. 1.0.0 (stable) follows
customer acceptance. What changed: [the release notes](notes/1.0.0-beta-RELEASE_NOTES.md).

Support: [support contact]

## 1. What is in the package

All files are assets of the GitHub pre-release `v1.0.0-beta.1`, built by
`.github/workflows/release.yml` from one commit (named in `release-manifest.json`).

| File | What it is | Who needs it |
|---|---|---|
| `Eurogas-Nexus-Server-1.0.0-beta.1.zip` | Server operator bundle: Compose file, HTTPS gateway configuration, configuration template (`env.server.example`), Windows deployment scripts, deployment guides (EN/CN) and `release-identity.json` naming the exact server image digest | IT, the server host |
| Server image `ghcr.io/alexyuhufeng/eurogasnexus-api@sha256:…` | The API, migrations and ingestion workers, one multi-platform image for `linux/amd64` and `linux/arm64`; pulled by the digest in `release-identity.json` | The server host (pulled, not downloaded by hand) |
| `Eurogas-Nexus-Client-1.0.0-beta.1-windows-x64-setup.exe` | Windows x64 desktop client (NSIS, per machine) | Trader and analyst workstations |
| `Eurogas-Nexus-Client-1.0.0-beta.1-linux-x64.deb` | Linux x64 desktop client | Linux workstations (amd64) |
| `Eurogas-Nexus-Client-1.0.0-beta.1-linux-arm64.deb` | Linux arm64 desktop client | Linux workstations (arm64) |
| `eurogas-nexus-web-1.0.0-beta.1.tar.gz` | The browser client as static files | Optional: firms that serve the web client themselves |
| `eurogas-nexus-sboms-1.0.0-beta.1.tar.gz` | SPDX software bills of materials (Python, npm, Rust, container) and `THIRD_PARTY_NOTICES.md` | Security and legal review |
| `release-manifest.json` | Version, channel, commit, schema revision, image digest, the SHA-256 of every file, signing state | IT, audit |
| `SHA256SUMS` | Checksums of every file above, the manifest included | Everyone who downloads a file |
| `signing-state.json` | Whether each file is signed (for this beta: unsigned) | IT |
| `release-notes.md` | Generated release notes | Everyone |

Desktop clients contain no server, no database and no credentials. The server bundle contains
no client. There is no all-in-one installer.

**Not in the package.** Demo or test accounts, demo data and simulated price sources are not
part of a customer installation: the release image and bundle are checked for their absence
(`tests/release/test_demo_test_accounts_boundary.py`, `test_demo_image_boundary.py`,
`test_customer_artifact_exclusion.py`), and simulated sources are off in trial and release
profiles. Licensed market data is not included; it arrives only through the customer's own
entitlement and credentials.

## 2. Check what you downloaded

Checksums, on Linux:

```bash
sha256sum -c SHA256SUMS --ignore-missing
```

On Windows (PowerShell), compare with the line for the file in `SHA256SUMS`:

```powershell
Get-FileHash .\Eurogas-Nexus-Client-1.0.0-beta.1-windows-x64-setup.exe -Algorithm SHA256
```

Build provenance: every file carries a GitHub artifact attestation from the release run.
With the GitHub CLI:

```bash
gh attestation verify Eurogas-Nexus-Client-1.0.0-beta.1-linux-x64.deb --repo AlexYuhuFeng/EurogasNexus
```

**Signatures.** The installers of this beta are **unsigned**: no Authenticode signature on
the Windows installer and no GPG signature on the `.deb` files (`signing-state.json` says so
per file). Signing is the deploying firm's decision; a firm whose policy requires it signs the
installers with its own certificate before distributing them. Until then, Windows shows the
publisher as unknown, and the Windows deployment tool needs `-AllowUnsignedPreview` (see
[DEPLOYMENT_ROLES-EN.md](../deployment/DEPLOYMENT_ROLES-EN.md#client-role)). Checksums and
attestations are the integrity check for this beta.

The server image is identified by its `sha256:` digest, never by a tag; the digest in
`release-identity.json` (inside the server zip) and in `release-manifest.json` must match.

## 3. Install order

1. **Server.** On a Docker host with Compose v2 on the firm's private network: unpack
   `Eurogas-Nexus-Server-1.0.0-beta.1.zip`, read `START-HERE.txt`, fill the configuration
   template, and run the deployment tool's `Preflight`, then `Install`
   ([DEPLOYMENT_ROLES-EN.md](../deployment/DEPLOYMENT_ROLES-EN.md),
   [中文](../deployment/DEPLOYMENT_ROLES-CN.md)). The server must stay behind the firm's
   firewall or VPN (`-PrivateNetworkOnly`) until the penetration test (G15) has passed.
   Migrations run to `0076_gas_day_nominations`; `/api/health/ready` answers `ready`.
2. **First administrator and people.** Create the first administrator from the server
   (`python -m eurogas_nexus.cli.accounts create --admin`), or configure company SSO
   ([SSO_OIDC.md](../operations/SSO_OIDC.md)) and pre-provision people under Admin → Access &
   Identity.
3. **Data sources.** An administrator approves the public sources (ENTSOG, GIE) for the firm
   after reading their terms (Admin → Data Sources), enters the firm's keys for GIE, ENTSO-E
   and EIA, and connects licensed sources under the firm's entitlement.
4. **Clients.** Install the desktop client on each workstation (Windows: the setup file;
   Linux: `sudo apt install ./Eurogas-Nexus-Client-1.0.0-beta.1-linux-<arch>.deb`, choosing
   `x64` or `arm64`) and point it at the server's HTTPS `/api` address
   ([INSTALL_WINDOWS.md](INSTALL_WINDOWS.md), [INSTALL_LINUX.md](INSTALL_LINUX.md)). The
   browser client in `eurogas-nexus-web-1.0.0-beta.1.tar.gz` is optional; the shipped gateway
   configuration forwards only `/api`, so serving the browser client needs the firm's own web
   server on the same HTTPS origin.

Upgrading from 0.8.0: back up the PostgreSQL volume first; the deployment tool's `Repair`
applies the new image and migrations without deleting data.

## 4. Versions you will see

| Where | Shows |
|---|---|
| About box, sign-in screen, `/api/health` | `1.0.0-beta` |
| File names, `/api/runtime/release`, Windows Installed apps | `1.0.0-beta.1` |
| Debian package version (`dpkg -s eurogas-nexus`) | `1.0.0~beta1` (sorts before 1.0.0, so 1.0.0 installs as an upgrade) |
| Python package metadata | `1.0.0b1` |

## 5. Where the manuals are

- In the product: Help & Settings → **Manual** and **Glossary** (English and Chinese).
- In the server zip: `docs/deployment/DEPLOYMENT_ROLES-EN.md`, `DEPLOYMENT_ROLES-CN.md`,
  `HANDOVER_INDEX.md` and `deploy/runtime/README-EN.md` / `README-CN.md`.
- In the source repository at tag `v1.0.0-beta.1`: the role manuals
  ([docs/user/manual](../user/manual/README.md)), the client guides
  ([docs/guides](../guides/README.md)), the install guides above, and the release status
  ([RELEASE_READINESS.md](RELEASE_READINESS.md)).

## 6. Acceptance still to do together

G15 (independent penetration test of the customer's deployment), G16 (certification of each
licensed source under the customer's entitlement) and G18 (acceptance by the customer's
traders, analysts and risk staff) are open. Nothing in this package marks them passed.
