#!/usr/bin/env bash
# Thin wrapper: the customer file allowlist, the staging tree and the ZIP are
# owned by package_deployment_bundle.py and its policy manifest. This script
# must not select files itself, so the Linux CI job and the local dry run build
# byte-identical member sets.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_DIR="${1:-${REPO_ROOT}/dist/releases}"
if [[ "${OUTPUT_DIR}" != /* ]]; then
  OUTPUT_DIR="${REPO_ROOT}/${OUTPUT_DIR}"
fi

PYTHON_BIN="${PYTHON:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "python3 is required to package the deployment bundle." >&2
    exit 1
  fi
fi

"${PYTHON_BIN}" "${REPO_ROOT}/scripts/release/package_deployment_bundle.py" "${OUTPUT_DIR}"
