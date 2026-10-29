"""Wiring checks for the PostgreSQL CI script.

SQLite fixtures do not prove PostgreSQL behaviour. These assertions keep the
native PostgreSQL schema modules in the real-PostgreSQL CI invocation and keep
that invocation bound to the runtime database URL.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_SCRIPT = REPO_ROOT / "scripts" / "ci" / "run_postgres_ci.sh"

POSTGRES_URL_BINDING = 'EUROGAS_NEXUS_TEST_POSTGRES_URL="$RUNTIME_STORE_DATABASE_URL"'
NATIVE_SCHEMA_MODULES = (
    "tests/db/test_demand_rest_schema.py",
    "tests/db/test_entsog_native_rate_schema.py",
    "tests/integration/test_entsog_bounded_persistence_postgres.py",
)
EXISTING_PATHS = (
    "tests/integration/test_postgres_backed_smoke.py",
    "tests/integration/test_monitoring_acknowledgement_postgres.py",
    "tests/integration/test_research_entitlement_postgres.py",
    "tests/integration/test_contract_revision_capture_postgres.py",
    "tests/integration/test_contract_payment_terms_acceptance_postgres.py",
)
EXISTING_OPT_INS = (
    "EUROGAS_NEXUS_ACK_INTEGRATION_TEST=1",
    "EUROGAS_NEXUS_CONTRACT_REVISION_INTEGRATION_TEST=1",
    "EUROGAS_NEXUS_PAYMENT_TERMS_INTEGRATION_TEST=1",
)


def _logical_lines(script: str) -> list[str]:
    """Join backslash continuations so checks ignore line-wrapping choices."""
    joined = re.sub(r"\\\r?\n", " ", script)
    return [re.sub(r"\s+", " ", line).strip() for line in joined.splitlines()]


def _pytest_command(script: str) -> str:
    commands = [line for line in _logical_lines(script) if "python -m pytest" in line]
    assert len(commands) == 1, f"expected exactly one pytest invocation, found {len(commands)}"
    return commands[0]


def test_postgres_ci_runs_native_schema_modules_with_runtime_database():
    command = _pytest_command(CI_SCRIPT.read_text(encoding="utf-8"))

    assert POSTGRES_URL_BINDING in command
    assert command.index(POSTGRES_URL_BINDING) < command.index("python -m pytest")

    for path in NATIVE_SCHEMA_MODULES:
        assert path in command
        assert (REPO_ROOT / path).is_file()
    for path in EXISTING_PATHS:
        assert path in command
    for opt_in in EXISTING_OPT_INS:
        assert opt_in in command

    # Guard against accidentally filtering out the native schema cases.
    assert "-k" not in command
    assert "--ignore" not in command
    assert "--deselect" not in command
