#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "WARNING: build_v1_release.sh is deprecated; use build_release.sh instead." >&2
exec "${SCRIPT_DIR}/build_release.sh" "$@"
