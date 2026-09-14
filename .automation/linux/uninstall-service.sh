#!/usr/bin/env bash
set -euo pipefail
sudo systemctl disable --now eurogas-codex-supervisor.service 2>/dev/null||true;sudo rm -f /etc/systemd/system/eurogas-codex-supervisor.service;sudo systemctl daemon-reload;echo 'Service removed; /etc/eurogas-codex-runner.env preserved.'
