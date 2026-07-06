#!/usr/bin/env bash
set -euo pipefail

SKIP_TESTS=0
INSTALL_DEPENDENCIES=0
BUNDLE="deb"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests)
      SKIP_TESTS=1
      shift
      ;;
    --install-dependencies)
      INSTALL_DEPENDENCIES=1
      shift
      ;;
    --bundle)
      BUNDLE="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEB_DIR="${REPO_ROOT}/clients/web"
DESKTOP_DIR="${REPO_ROOT}/clients/desktop"

cd "${REPO_ROOT}"

step() {
  echo "==> $1"
}

step "Verify release-safe repo state"
git -C "${REPO_ROOT}" diff --check

if [[ "${SKIP_TESTS}" == "0" ]]; then
  step "Run Ruff"
  ruff check "${REPO_ROOT}"

  step "Run targeted Python release tests"
  pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security

  step "Verify API import safety"
  python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
fi

if [[ "${INSTALL_DEPENDENCIES}" == "1" ]]; then
  step "Install Web dependencies"
  npm --prefix "${WEB_DIR}" ci

  step "Install desktop dependencies"
  npm --prefix "${DESKTOP_DIR}" ci
fi

step "Build Web client"
npm --prefix "${WEB_DIR}" run build

step "Build desktop bundle (${BUNDLE})"
npm --prefix "${DESKTOP_DIR}" run build -- --bundles "${BUNDLE}"

step "Release artifacts"
find "${DESKTOP_DIR}/src-tauri/target/release/bundle" -type f \
  \( -name "*.exe" -o -name "*.msi" -o -name "*.deb" -o -name "*.AppImage" \) \
  -print
