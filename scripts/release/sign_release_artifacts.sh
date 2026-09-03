#!/usr/bin/env bash
set -euo pipefail

# Local release-signing helper stub.
# Supports test certificate signing on Windows executables and detached GPG
# signatures for DEB files. Production signing uses real secrets in CI.
#
# Usage:
#   sign_release_artifacts.sh --artifact <path> [--cert <pfx>] [--password <pwd>]

ARTIFACT=""
CERT=""
PASSWORD=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact) ARTIFACT="$2"; shift 2 ;;
    --cert) CERT="$2"; shift 2 ;;
    --password) PASSWORD="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$ARTIFACT" || ! -f "$ARTIFACT" ]]; then
  echo "A valid --artifact path is required." >&2
  exit 2
fi

case "${ARTIFACT,,}" in
  *.exe)
    if [[ -z "$CERT" || -z "$PASSWORD" ]]; then
      echo "Windows .exe signing requires --cert and --password (test cert in local use)." >&2
      exit 2
    fi
    if command -v signtool >/dev/null 2>&1; then
      signtool sign /f "$CERT" /p "$PASSWORD" /fd sha256 /tr http://timestamp.digicert.com /td sha256 "$ARTIFACT"
    else
      echo "signtool not found; skipping actual signing. Artifact: $ARTIFACT" >&2
    fi
    ;;
  *.deb)
    if command -v gpg >/dev/null 2>&1; then
      gpg --detach-sign --armor --output "$ARTIFACT.asc" "$ARTIFACT"
    else
      echo "gpg not found; skipping detached signature. Artifact: $ARTIFACT" >&2
    fi
    ;;
  *)
    echo "Unsupported artifact type for signing helper: $ARTIFACT" >&2
    exit 2
    ;;
esac

echo "Signing helper processed: $ARTIFACT"
