#!/usr/bin/env bash
set -euo pipefail

ruff check .
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
