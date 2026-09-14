#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)";PYTHON="$(command -v python3)";USER_NAME="${SUDO_USER:-$USER}";T="$REPO/.automation/linux/eurogas-codex-supervisor.service.template";OUT=/etc/systemd/system/eurogas-codex-supervisor.service
sed -e "s|__REPO__|$REPO|g" -e "s|__PYTHON__|$PYTHON|g" -e "s|__USER__|$USER_NAME|g" "$T"|sudo tee "$OUT">/dev/null
if [[ ! -f /etc/eurogas-codex-runner.env ]];then sudo sh -c "printf '%s\n' 'EUROGAS_ORCHESTRATOR_NODE_ID=linux-standby' 'DEEPSEEK_API_KEY=' > /etc/eurogas-codex-runner.env";sudo chmod 600 /etc/eurogas-codex-runner.env;fi
sudo systemctl daemon-reload;sudo systemctl enable eurogas-codex-supervisor.service
echo 'Installed as standby. Put DEEPSEEK_API_KEY in /etc/eurogas-codex-runner.env. Do not activate Linux while Windows is active.'
