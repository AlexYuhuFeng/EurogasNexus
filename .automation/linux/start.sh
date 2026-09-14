#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)";rm -f "$REPO/.automation/STOP";python3 "$REPO/.automation/scripts/set_control.py" RUNNING;sudo systemctl start eurogas-codex-supervisor.service
