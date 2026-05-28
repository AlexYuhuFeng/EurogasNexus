"""DB foundation contract tests for milestone 2."""

from pathlib import Path

import pytest

from eurogas_nexus.core.config import Settings, parse_env_bool

ROOT = Path(__file__).resolve().parents[2]


def test_db_engine_factory_fails_closed_without_dsn() -> None:
    from eurogas_nexus.db import DatabaseSettings, create_db_engine

    settings = DatabaseSettings()

    with pytest.raises(ValueError, match="DSN"):
        create_db_engine(settings)


def test_importing_api_does_not_import_db_or_sqlalchemy() -> None:
    import importlib
    import sys

    # Ensure prior tests do not leak modules into this check.
    for module_name in list(sys.modules):
        if module_name == "eurogas_nexus.db" or module_name.startswith("eurogas_nexus.db."):
            sys.modules.pop(module_name, None)
        if module_name == "sqlalchemy" or module_name.startswith("sqlalchemy."):
            sys.modules.pop(module_name, None)

    importlib.import_module("apps.api.main")

    assert "eurogas_nexus.db" not in sys.modules
    assert "sqlalchemy" not in sys.modules


def test_alembic_baseline_files_exist() -> None:
    assert (ROOT / "alembic.ini").is_file()
    assert (ROOT / "alembic" / "env.py").is_file()
    assert (ROOT / "alembic" / "script.py.mako").is_file()
    assert (ROOT / "alembic" / "versions" / "0001_m2_baseline.py").is_file()


def test_parse_env_bool_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="Invalid boolean value"):
        parse_env_bool("not-a-bool", default=True)


def test_settings_from_env_treats_blank_dsn_as_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_DB_DSN", "   ")
    settings = Settings.from_env()

    assert settings.db.dsn is None


def test_settings_from_env_rejects_invalid_db_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_DB_ECHO", "sometimes")

    with pytest.raises(ValueError, match="Invalid boolean value"):
        Settings.from_env()
