# Windows AllInOne Installer

## Use this package

For a Windows evaluation workstation that already has Docker Desktop, download
`Eurogas-Nexus-AllInOne-<version>-<commit>-x64-setup.exe` from the GitHub
Release. Do not combine the Client-only installer with deployment ZIP files.

## Prerequisites

- 64-bit Windows 10 or Windows 11;
- administrator access;
- Docker Desktop with Docker Compose v2 installed;
- 8 GB RAM and 10 GB free disk;
- internet access on first installation for the official PostgreSQL image and
  optional current public-source ingestion.

Windows 11 normally includes the Evergreen WebView2 Runtime. The Client
installer invokes Microsoft's WebView2 bootstrapper only when the runtime is
missing.

No Python, Node.js, Rust, Git, local PostgreSQL, source checkout, domain name,
TLS certificate, or licensed market-data key is required for the preview.

## Result

The installer deploys the desktop frontend, a loopback-only FastAPI container,
PostgreSQL 16, explicit Alembic migration, DB-resident preview inputs,
DB-resident `_Sim` market feeds, and public-source workers. The Client reads all
runtime data through `http://127.0.0.1:8765/api`; it never connects to PostgreSQL.

Install logs are stored at
`%ProgramData%\Eurogas Nexus\Logs\all-in-one-install.log`. They do not contain
the generated database password or backend keys.

## Operations

The Start menu contains Open, Start services, Stop services, Runtime status,
Runtime logs, and Uninstall commands. Normal uninstall removes the application
and stops containers but preserves the PostgreSQL Docker volume. Permanent data
deletion is available only through the explicit `PurgeData` management action,
which requires typing `PURGE`. The uninstaller also offers a destructive data
purge prompt with **No** as the safe default.

Licensed price feeds, GIE, weather, and LLM services remain disabled until the
customer stores its own credentials through backend-owned source settings.

Preview installers may trigger Windows SmartScreen until the project release
pipeline is connected to an approved Authenticode code-signing certificate.
Production customer delivery must be signed; the preview warning must not be
misrepresented as a successful production-signing state.
