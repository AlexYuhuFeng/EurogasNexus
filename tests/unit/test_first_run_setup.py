"""First-run setup: every registered source has a page, and every page entry has words.

A new connector manifest without a step fails here, so a new source appears in the welcome
flow instead of silently missing from it; an entry without EN and ZH words fails too.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from eurogas_nexus.application import first_run_setup as setup
from eurogas_nexus.domain.connectors.registry import connector_manifests

ROOT = Path(__file__).resolve().parents[2]


def _locale(name: str) -> dict[str, str]:
    return json.loads((ROOT / "clients/web/src/i18n" / f"{name}.json").read_text("utf-8"))


def test_every_registered_source_has_a_step_or_a_stated_exclusion():
    registered = {manifest.source_id for manifest in connector_manifests()}
    missing = sorted(registered - set(setup.SOURCE_STEPS))
    assert missing == [], f"connector manifests with no first-run setup step: {missing}"
    stale = sorted(set(setup.SOURCE_STEPS) - registered)
    assert stale == [], f"setup steps for sources that no longer exist: {stale}"
    for source_id, step in setup.SOURCE_STEPS.items():
        assert step is None or step in setup.STEPS, source_id
        if step is None:
            # Only simulated demo sources are left out of a customer's set-up.
            assert source_id.endswith("-sim") or source_id.startswith("src-demo-"), source_id
            assert setup.EXCLUDED_REASONS[source_id]


def test_a_source_without_a_step_is_refused(monkeypatch):
    monkeypatch.delitem(setup.SOURCE_STEPS, "src-ecb")
    with pytest.raises(setup.SetupError, match="src-ecb"):
        setup.setup_catalogue()


def test_the_catalogue_states_how_each_source_connects_today():
    catalogue = setup.setup_catalogue()
    assert [step["step"] for step in catalogue["steps"]] == list(setup.STEPS)
    by_id = {item["item_id"]: item for step in catalogue["steps"] for item in step["items"]}
    assert by_id["src-entsog"]["connection"] == "approval"
    assert by_id["src-gie"]["connection"] == "approval_and_key"
    assert by_id["src-gie"]["credential_provider"] == "GIE"
    for source_id, provider in {"src-eia": "EIA", "src-entsoe": "ENTSOE"}.items():
        assert by_id[source_id]["connection"] == "key"
        assert by_id[source_id]["key_registration_url"].startswith("https://")
        assert by_id[source_id]["credential_provider"] == provider
    # No licensed connector is invented: licensed prices are imports, or nothing yet.
    assert by_id["src-trayport"]["connection"] == "licensed_import"
    assert any("import_market_quotes.py" in tool for tool in by_id["src-trayport"]["import_tools"])
    assert by_id["src-icis"]["connection"] == "licensed_none"
    assert by_id["src-icis"]["import_tools"] == []
    assert by_id["src-kpler"]["import_tools"] == ["scripts/ops/import_lng_positions.py"]
    assert by_id["src-lng-terminal-tariffs"]["connection"] == "public_tariffs"
    assert by_id["src-deepseek"]["connection"] == "model"
    assert {item["connection"] for item in by_id.values()} <= {
        *setup.CONNECTION_ORDER, "import", "api_key", "admin"
    }
    assert not any(item_id.endswith("-sim") or item_id.startswith("src-demo-") for item_id in by_id)
    # Every import tool the flow names exists.
    for item in by_id.values():
        for tool in item.get("import_tools", []):
            assert (ROOT / tool.split()[0]).exists(), tool


def test_every_entry_page_and_connection_has_words_in_both_languages():
    en, zh = _locale("en"), _locale("zh")
    catalogue = setup.setup_catalogue()
    keys = [f"setup.step.{step}.title" for step in setup.STEPS]
    keys += [f"setup.step.{step}.intro" for step in setup.STEPS]
    for step in catalogue["steps"]:
        for item in step["items"]:
            keys += [f"setup.item.{item['item_id']}.name", f"setup.item.{item['item_id']}.purpose",
                     f"setup.how.{item['connection']}"]
    missing = sorted({key for key in keys if key not in en or key not in zh})
    assert missing == [], missing


def test_migration_0066_up_down_and_model_match():
    from eurogas_nexus.db.models import InstallationSetupRecord
    from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0068", ROOT / "alembic/versions/0068_installation_setup.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0067_opportunities"
    assert DB_SCHEMA_REVISION == "0078_lng_cargo_hedges"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        columns = {c["name"] for c in inspect(connection).get_columns("installation_setup")}
        assert columns == set(InstallationSetupRecord.__table__.columns.keys())
        assert "key" not in " ".join(columns)  # never a key
        module.downgrade()
        assert "installation_setup" not in inspect(connection).get_table_names()
