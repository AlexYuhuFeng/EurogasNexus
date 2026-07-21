#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_DIR="${1:-${REPO_ROOT}/dist/releases}"
if [[ "${OUTPUT_DIR}" != /* ]]; then
  OUTPUT_DIR="${REPO_ROOT}/${OUTPUT_DIR}"
fi

STAGING_ROOT="$(mktemp -d)"
SERVER_ROOT="${STAGING_ROOT}/Eurogas-Nexus-Server-Windows"

cleanup() {
  rm -rf -- "${STAGING_ROOT}"
}
trap cleanup EXIT

copy_common_payload() {
  local destination="$1"
  mkdir -p \
    "${destination}/deploy" \
    "${destination}/scripts/install/windows" \
    "${destination}/docs"

  cp -R "${REPO_ROOT}/deploy/runtime" "${destination}/deploy/"
  cp "${REPO_ROOT}/scripts/install/windows/Deploy-EurogasNexus.ps1" "${destination}/scripts/install/windows/"
  cp "${REPO_ROOT}/scripts/install/windows/Install-EurogasNexusServerRuntime.ps1" "${destination}/scripts/install/windows/"
  cp -R "${REPO_ROOT}/docs/deployment" "${destination}/docs/"
}

mkdir -p "${OUTPUT_DIR}"
copy_common_payload "${SERVER_ROOT}"

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

# Explicit role assets for operators.
(cd "${STAGING_ROOT}" && zip -qr "${OUTPUT_DIR}/Eurogas-Nexus-Server-Windows.zip" "$(basename "${SERVER_ROOT}")")

printf '%s\n' \
  "${OUTPUT_DIR}/Eurogas-Nexus-Server-Windows.zip"
