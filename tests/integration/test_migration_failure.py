"""Migration failure/recovery integration test against configured PostgreSQL."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL"),
    reason="RUNTIME_STORE_DATABASE_URL not configured; run via scripts/ci/run_postgres_ci.sh",
)

ROOT = Path(__file__).resolve().parents[2]


def test_missing_migration_revision_fails_without_partial_apply() -> None:
    """A nonexistent Alembic target must fail cleanly and not change head."""

    from eurogas_nexus.db.health import get_alembic_revision

    before = get_alembic_revision(os.environ["RUNTIME_STORE_DATABASE_URL"])
    assert before is not None

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "9999_missing_revision",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    assert result.returncode != 0
    after = get_alembic_revision(os.environ["RUNTIME_STORE_DATABASE_URL"])
    assert after == before
