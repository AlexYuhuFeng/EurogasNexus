# V1 R13 CLI Release Surface ExecPlan

## 1. Goal

Expand the CLI to cover all released `/api/v1` route groups via the Python SDK.
Each command calls SDK/API, outputs human-readable or JSON formats, and is
read-only by default.

## 2. Internet: no (Python-only, uses SDK)

## 3. Files

- `src/eurogas_nexus/cli/__init__.py`
- `src/eurogas_nexus/cli/commands.py` — health, network, sources, market, physical,
  lng, storage, weather, contracts, glossary, research
- `tests/cli/test_commands.py`

## 4. Acceptance

- CLI calls SDK/API only (no backend internal imports).
- Read-only by default.
- JSON output supported.
- No secrets in output.
