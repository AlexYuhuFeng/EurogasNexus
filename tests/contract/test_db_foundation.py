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


# -- hardening: parse_env_bool exhaustive edge-case tests ---------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("Yes", True),
        ("on", True),
        ("ON", True),
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("0", False),
        ("no", False),
        ("No", False),
        ("off", False),
        ("OFF", False),
    ],
)
def test_parse_env_bool_accepts_known_truthy_and_falsy_values(
    raw: str, expected: bool
) -> None:
    assert parse_env_bool(raw, default=not expected) == expected


def test_parse_env_bool_returns_default_when_value_is_none() -> None:
    assert parse_env_bool(None, default=True) is True
    assert parse_env_bool(None, default=False) is False


# -- hardening: DatabaseSettings normalization and bridge --------------------

def test_database_settings_normalizes_blank_dsn_to_none() -> None:
    from eurogas_nexus.db import DatabaseSettings

    assert DatabaseSettings(dsn="   ").dsn is None
    assert DatabaseSettings(dsn="\t\n").dsn is None
    assert DatabaseSettings(dsn="").dsn is None


def test_database_settings_preserves_valid_dsn() -> None:
    from eurogas_nexus.db import DatabaseSettings

    settings = DatabaseSettings(dsn="postgresql://db:5432/test")
    assert settings.dsn == "postgresql://db:5432/test"


def test_database_settings_from_core_config_bridge() -> None:
    from eurogas_nexus.core.config import DbRuntimeConfig
    from eurogas_nexus.db import DatabaseSettings

    core_cfg = DbRuntimeConfig(dsn="pg://host/db", echo=True, pool_pre_ping=False)
    db_settings = DatabaseSettings.from_core_config(core_cfg)

    assert db_settings.dsn == "pg://host/db"
    assert db_settings.echo is True
    assert db_settings.pool_pre_ping is False


def test_database_settings_from_core_config_with_none_dsn() -> None:
    from eurogas_nexus.core.config import DbRuntimeConfig
    from eurogas_nexus.db import DatabaseSettings

    core_cfg = DbRuntimeConfig(dsn=None)
    db_settings = DatabaseSettings.from_core_config(core_cfg)

    assert db_settings.dsn is None
