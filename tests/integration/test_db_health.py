"""DB health helper tests."""

import pytest

from eurogas_nexus.db.health import check_db_connectivity, get_alembic_revision


def test_check_db_connectivity_handles_missing_url_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    status = check_db_connectivity()

    assert status.ok is False
    assert status.database_url_present is False
    assert "missing" in (status.error or "").lower()


def test_check_db_connectivity_uses_select_one_without_writes() -> None:
    status = check_db_connectivity("sqlite:///:memory:")

    assert status.ok is True
    assert status.database_url_present is True
    assert status.error is None


def test_check_db_connectivity_redacts_url_on_failure() -> None:
    status = check_db_connectivity("postgresql://user:secret@127.0.0.1:1/eurogas")

    assert status.ok is False
    assert status.database_url_present is True
    assert status.redacted_database_url is not None
    assert "secret" not in status.redacted_database_url


def test_get_alembic_revision_returns_none_when_version_table_is_absent() -> None:
    assert get_alembic_revision("sqlite:///:memory:") is None
