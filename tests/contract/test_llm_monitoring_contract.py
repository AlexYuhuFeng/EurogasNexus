"""Contract checks for the visible LLM monitoring increment."""

from pathlib import Path

from eurogas_nexus.db.registry import list_required_tables

ROOT = Path(__file__).resolve().parents[2]


def test_monitoring_migration_and_registry_are_aligned() -> None:
    migration = (
        ROOT / "alembic" / "versions" / "0015_llm_monitoring_alerts.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0015_llm_monitoring_alerts"' in migration
    assert 'down_revision: str | None = "0014_intraday_decision_feed"' in migration
    assert '"monitoring_alerts"' in migration
    assert "monitoring_alerts" in list_required_tables()


def test_web_and_runtime_surface_monitoring_without_client_db_access() -> None:
    topbar = (ROOT / "clients" / "web" / "src" / "components" / "AlertCenter.tsx").read_text(
        encoding="utf-8"
    )
    client = (ROOT / "clients" / "web" / "src" / "api" / "client.ts").read_text(
        encoding="utf-8"
    )
    compose = (ROOT / "deploy" / "runtime" / "compose.yaml").read_text(
        encoding="utf-8"
    )

    assert "/monitoring/alerts" in client
    assert "Ask DeepSeek" in topbar
    assert "monitoring-worker:" in compose
    assert "RUNTIME_STORE_DATABASE_URL" not in topbar
    assert "sqlalchemy" not in topbar.lower()
