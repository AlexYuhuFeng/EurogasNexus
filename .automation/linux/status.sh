#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)";python3 "$REPO/.automation/scripts/status.py";systemctl status eurogas-codex-supervisor.service --no-pager||true
