"""DB runtime configuration tests."""

import pytest

from eurogas_nexus.db import get_engine, get_session_factory, resolve_database_url


def test_resolve_database_url_prefers_runtime_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", "postgresql://runtime/db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://database/db")
    monkeypatch.setenv("EUROGAS_NEXUS_DB_DSN", "postgresql://legacy/db")

    assert resolve_database_url() == "postgresql://runtime/db"


def test_resolve_database_url_falls_back_to_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://database/db")
    monkeypatch.setenv("EUROGAS_NEXUS_DB_DSN", "postgresql://legacy/db")

    assert resolve_database_url() == "postgresql://database/db"


def test_resolve_database_url_uses_legacy_dsn_last(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("EUROGAS_NEXUS_DB_DSN", "postgresql://legacy/db")

    assert resolve_database_url() == "postgresql://legacy/db"


def test_resolve_database_url_treats_blank_values_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", "  ")
    monkeypatch.setenv("DATABASE_URL", "\t")
    monkeypatch.setenv("EUROGAS_NEXUS_DB_DSN", "")

    assert resolve_database_url() is None


def test_get_engine_fails_closed_without_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    with pytest.raises(ValueError, match="Database URL"):
        get_engine()


def test_get_session_factory_can_use_explicit_import_safe_engine() -> None:
    engine = get_engine("sqlite:///:memory:")

    session_factory = get_session_factory(engine=engine)

    assert session_factory.kw["bind"] is engine
