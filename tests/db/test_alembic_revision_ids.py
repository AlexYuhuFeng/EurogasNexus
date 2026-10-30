"""Alembic revision IDs must fit the PostgreSQL ``alembic_version.version_num`` column."""

import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
REVISION = re.compile(r'^revision = "([^"]+)"', re.MULTILINE)


def test_revision_ids_fit_alembic_version_varchar_32():
    # alembic_version.version_num is VARCHAR(32). A longer ID passes on SQLite and fails
    # on PostgreSQL only when the migration records itself, after its DDL already ran.
    too_long = {
        path.name: match.group(1)
        for path in VERSIONS.glob("*.py")
        if (match := REVISION.search(path.read_text(encoding="utf-8")))
        and len(match.group(1)) > 32
    }
    assert too_long == {}
