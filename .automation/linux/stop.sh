#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)";touch "$REPO/.automation/STOP";sudo systemctl stop eurogas-codex-supervisor.service||true
