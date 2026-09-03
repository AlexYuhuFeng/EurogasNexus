#!/usr/bin/env bash
set -euo pipefail

ruff check .
pytest -q tests
python -c "from apps.api.main import app; print('app import ok'); print(len(app.openapi()['paths']))"
