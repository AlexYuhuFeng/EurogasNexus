#!/usr/bin/env bash
set -euo pipefail
python -m pip install --require-hashes -r requirements-runtime.lock
npm --prefix clients/web ci
npm --prefix clients/web run build
