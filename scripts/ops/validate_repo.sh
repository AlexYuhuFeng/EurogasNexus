#!/usr/bin/env bash
set -euo pipefail

ruff check .
python scripts/release/check_version_consistency.py
pytest -q tests
python -c "from apps.api.main import app; print('app import ok'); print(len(app.openapi()['paths']))"
python scripts/security/run_security_acceptance.py --json >/dev/null
