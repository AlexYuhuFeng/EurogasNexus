#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_DIR="${1:-${REPO_ROOT}/dist/releases}"
if [[ "${OUTPUT_DIR}" != /* ]]; then
  OUTPUT_DIR="${REPO_ROOT}/${OUTPUT_DIR}"
fi
STAGING_ROOT="$(mktemp -d)"
BUNDLE_ROOT="${STAGING_ROOT}/eurogas-nexus-deployment"

cleanup() {
  rm -rf -- "${STAGING_ROOT}"
}
trap cleanup EXIT

mkdir -p \
  "${BUNDLE_ROOT}/deploy" \
  "${BUNDLE_ROOT}/scripts/install" \
  "${BUNDLE_ROOT}/docs" \
  "${OUTPUT_DIR}"

cp -R "${REPO_ROOT}/deploy/runtime" "${BUNDLE_ROOT}/deploy/"
cp -R "${REPO_ROOT}/scripts/install/windows" "${BUNDLE_ROOT}/scripts/install/"
cp -R "${REPO_ROOT}/docs/deployment" "${BUNDLE_ROOT}/docs/"

(cd "${STAGING_ROOT}" && zip -qr "${OUTPUT_DIR}/eurogas-nexus-deployment-windows.zip" "eurogas-nexus-deployment")
tar -czf "${OUTPUT_DIR}/eurogas-nexus-deployment-portable.tar.gz" -C "${STAGING_ROOT}" eurogas-nexus-deployment

printf '%s\n' \
  "${OUTPUT_DIR}/eurogas-nexus-deployment-windows.zip" \
  "${OUTPUT_DIR}/eurogas-nexus-deployment-portable.tar.gz"
