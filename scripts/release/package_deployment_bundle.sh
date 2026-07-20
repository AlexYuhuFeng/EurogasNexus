#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_DIR="${1:-${REPO_ROOT}/dist/releases}"
if [[ "${OUTPUT_DIR}" != /* ]]; then
  OUTPUT_DIR="${REPO_ROOT}/${OUTPUT_DIR}"
fi

STAGING_ROOT="$(mktemp -d)"
TOOLKIT_ROOT="${STAGING_ROOT}/eurogas-nexus-deployment"
SERVER_ROOT="${STAGING_ROOT}/Eurogas-Nexus-Server-Windows"
ALL_IN_ONE_ROOT="${STAGING_ROOT}/Eurogas-Nexus-AllInOne-Windows"

cleanup() {
  rm -rf -- "${STAGING_ROOT}"
}
trap cleanup EXIT

copy_common_payload() {
  local destination="$1"
  mkdir -p \
    "${destination}/deploy" \
    "${destination}/scripts/install" \
    "${destination}/docs"

  cp -R "${REPO_ROOT}/deploy/runtime" "${destination}/deploy/"
  cp -R "${REPO_ROOT}/scripts/install/windows" "${destination}/scripts/install/"
  cp -R "${REPO_ROOT}/docs/deployment" "${destination}/docs/"
}

mkdir -p "${OUTPUT_DIR}"
copy_common_payload "${TOOLKIT_ROOT}"
copy_common_payload "${SERVER_ROOT}"
copy_common_payload "${ALL_IN_ONE_ROOT}"

cat > "${SERVER_ROOT}/START-HERE.txt" <<'EOF'
EUROGAS NEXUS SERVER FOR WINDOWS

This package installs the backend runtime only:
- PostgreSQL container
- FastAPI runtime
- Alembic migrations
- HTTPS gateway
- ingestion workers

Prerequisites:
- Windows 10/11 or Windows Server
- PowerShell 5.1+
- Docker Engine/Desktop with Docker Compose v2 already installed and running
- administrator PowerShell
- a private-network hostname or loopback name
- PEM TLS certificate and private key

Start with a non-destructive preflight from this extracted folder:

  powershell -ExecutionPolicy Bypass -File .\scripts\install\windows\Deploy-EurogasNexus.ps1 `
    -Action Preflight `
    -Role Server `
    -ServerName nexus.example.com `
    -HttpsBindAddress 127.0.0.1 `
    -TlsCertificatePath C:\secure\nexus.crt `
    -TlsPrivateKeyPath C:\secure\nexus.key `
    -PrivateNetworkOnly

Then replace Preflight with Install after resolving every blocking item.
See docs\DEPLOYMENT_ROLES-CN.md or docs\DEPLOYMENT_ROLES-EN.md.
EOF

cat > "${ALL_IN_ONE_ROOT}/START-HERE.txt" <<'EOF'
EUROGAS NEXUS ALL-IN-ONE FOR WINDOWS

This package contains the Server/AllInOne deployment tooling. The Windows desktop
NSIS installer is published as a separate Release asset because it is built and
signed independently.

Download both assets from the SAME GitHub Release:
1. Eurogas-Nexus-AllInOne-Windows.zip
2. the Windows x64 NSIS .exe installer

Place the .exe inside this extracted folder, then run an administrator PowerShell
preflight such as:

  powershell -ExecutionPolicy Bypass -File .\scripts\install\windows\Deploy-EurogasNexus.ps1 `
    -Action Preflight `
    -Role AllInOne `
    -ServerName localhost `
    -HttpsBindAddress 127.0.0.1 `
    -TlsCertificatePath C:\secure\nexus-local.crt `
    -TlsPrivateKeyPath C:\secure\nexus-local.key `
    -ClientInstallerPath .\Eurogas-Nexus_0.5.0_x64-setup.exe `
    -EnableSimulatedPrices `
    -PrivateNetworkOnly `
    -AllowUnsignedPreview

Then replace Preflight with Install after resolving every blocking item.
The preview switch is for internal preview builds only. Customer delivery requires
a valid signed installer.
See docs\DEPLOYMENT_ROLES-CN.md or docs\DEPLOYMENT_ROLES-EN.md.
EOF

# Explicit role assets for operators.
(cd "${STAGING_ROOT}" && zip -qr "${OUTPUT_DIR}/Eurogas-Nexus-Server-Windows.zip" "$(basename "${SERVER_ROOT}")")
(cd "${STAGING_ROOT}" && zip -qr "${OUTPUT_DIR}/Eurogas-Nexus-AllInOne-Windows.zip" "$(basename "${ALL_IN_ONE_ROOT}")")

# Compatibility assets retained for existing automation and documentation links.
(cd "${STAGING_ROOT}" && zip -qr "${OUTPUT_DIR}/eurogas-nexus-deployment-windows.zip" "$(basename "${TOOLKIT_ROOT}")")
tar -czf "${OUTPUT_DIR}/eurogas-nexus-deployment-portable.tar.gz" -C "${STAGING_ROOT}" "$(basename "${TOOLKIT_ROOT}")"

printf '%s\n' \
  "${OUTPUT_DIR}/Eurogas-Nexus-Server-Windows.zip" \
  "${OUTPUT_DIR}/Eurogas-Nexus-AllInOne-Windows.zip" \
  "${OUTPUT_DIR}/eurogas-nexus-deployment-windows.zip" \
  "${OUTPUT_DIR}/eurogas-nexus-deployment-portable.tar.gz"
