# Windows Installation

## Online workstation (default installer)

1. Download `Eurogas-Nexus-Client-{VERSION}-windows-x64-setup.exe` and
   `SHA256SUMS` from the authorized release.
2. Verify: `Get-FileHash .\Eurogas-Nexus-Client-{VERSION}-windows-x64-setup.exe -Algorithm SHA256`
   and compare with `SHA256SUMS`.
3. Check Authenticode if the release is signed:
   `Get-AuthenticodeSignature .\Eurogas-Nexus-Client-{VERSION}-windows-x64-setup.exe`
   must report `Valid`. Preview/RC assets may be explicitly `UNSIGNED`.
4. Install per-machine. The default Tauri NSIS configuration is `perMachine`.
5. Point the client at an existing HTTPS `/api` server in Settings or via the
   operator deployment file.

## WebView2 policy

- Default build: `downloadBootstrapper` (requires internet on first install
  when WebView2 is absent; Windows 10 April 2018+ / Windows 11 normally have
  it). This is not hidden: the installer downloads only the Microsoft
  WebView2 bootstrapper.
- Offline/restricted workstation: build or obtain the offline variant with
  `src-tauri/tauri.offline.conf.json`:
  `npm --prefix clients/desktop run build:offline`
  This embeds the Microsoft WebView2 offline installer (~127MB) and has no
  first-install internet requirement.
- Fixed-runtime variant (enterprise-pinned WebView2) is documented by Tauri and
  remains an operator option; it is not built by default.

## Installer/upgrade/uninstall test path

`scripts/release/run_release_dry_run.py` packages the NSIS bundle and records
what it can verify locally. Clean-Windows install -> launch -> uninstall, and
previous-version upgrade, are deployment acceptance gates (G6/G7) that require
a controlled Windows test machine; their evidence remains `PENDING_EXTERNAL`
until executed.

## Server role

See `docs/deployment/DEPLOYMENT_ROLES-EN.md`. Server deployment uses the
operator ZIP and never installs the desktop client or embeds the API image.
