"""CLI command tests (SDK-backed, no live server needed)."""

import pytest

from eurogas_nexus.sdk.glossary import GlossaryTerm
from eurogas_nexus.sdk.market import MarketObservation
from eurogas_nexus.sdk.physical import FlowObservation
from eurogas_nexus.sdk.reference_network import NodeDTO
from eurogas_nexus.sdk.sources import SourceSystem


def test_cmd_health_uses_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurogas_nexus.cli.commands import cmd_health
    from eurogas_nexus.sdk.health_client import HealthPayload

    def fake_fetch(base_url: str) -> HealthPayload:
        return HealthPayload(status="ok", service="test", version="0.1", profile="dev")

    monkeypatch.setattr("eurogas_nexus.cli.health.fetch_health", fake_fetch)
    result = cmd_health("http://localhost:8000")
    assert "status=ok" in result


def test_cmd_runtime_db_formats_sdk_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurogas_nexus.cli.commands import cmd_runtime_db
    from eurogas_nexus.sdk.runtime import RuntimeConnectivity, RuntimeDbStatus

    def fake_fetch(base_url: str) -> RuntimeDbStatus:
        return RuntimeDbStatus(
            database_url_present=True,
            redacted_database_url="postgresql://user:***@localhost/db",
            connectivity=RuntimeConnectivity(ok=True),
            alembic_revision="rev-1",
            required_tables=["alembic_version"],
            missing_tables=[],
            warnings=[],
        )

    monkeypatch.setattr("eurogas_nexus.cli.commands.fetch_runtime_db_status", fake_fetch)
    result = cmd_runtime_db("http://localhost:8000")
    assert '"alembic_revision": "rev-1"' in result
    assert "***" in result


def test_cmd_nodes_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurogas_nexus.cli.commands import cmd_nodes

    def fake_fetch(base_url, *, country=None, node_type=None):
        return [NodeDTO(id="n1", name="Test", node_type="hub", country="NL", lat=1.0, lon=2.0)]

    monkeypatch.setattr(
        "eurogas_nexus.cli.commands.fetch_nodes", fake_fetch,
    )
    result = cmd_nodes("http://localhost:8000")
    assert len(result) == 1
    assert result[0].id == "n1"


def test_cmd_sources_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurogas_nexus.cli.commands import cmd_sources

    def fake_fetch(base_url):
        return [SourceSystem(source_id="s1", source_system="ENTSOG")]

    monkeypatch.setattr("eurogas_nexus.cli.commands.fetch_sources", fake_fetch)
    result = cmd_sources("http://localhost:8000")
    assert len(result) == 1


def test_cmd_market_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurogas_nexus.cli.commands import cmd_market

    def fake_fetch(base_url):
        return [MarketObservation(
            observation_id="m1", market_venue="TTF", product="month-ahead",
            price=42.5, unit="EUR/MWh", currency="EUR",
            period_start_utc="2026-06-01", period_end_utc="2026-07-01",
        )]

    monkeypatch.setattr("eurogas_nexus.cli.commands.fetch_market_observations", fake_fetch)
    result = cmd_market("http://localhost:8000")
    assert len(result) == 1


def test_cmd_flows_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurogas_nexus.cli.commands import cmd_flows

    def fake_fetch(base_url):
        return [FlowObservation(
            observation_id="f1", point_id="n1", point_name="Test",
            direction="entry", flow_mcm_d=85.0,
            period_start_utc="2026-05-29", period_end_utc="2026-05-30",
        )]

    monkeypatch.setattr("eurogas_nexus.cli.commands.fetch_flows", fake_fetch)
    result = cmd_flows("http://localhost:8000")
    assert len(result) == 1


def test_cmd_glossary_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurogas_nexus.cli.commands import cmd_glossary

    def fake_fetch(base_url, *, lang="en"):
        return [GlossaryTerm(term="TTF", definition="Test definition.")]

    monkeypatch.setattr("eurogas_nexus.cli.commands.fetch_glossary", fake_fetch)
    result = cmd_glossary("http://localhost:8000", lang="en")
    assert len(result) == 1


def test_cmd_to_json_outputs_string(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurogas_nexus.cli.commands import cmd_node

    def fake_fetch(base_url, node_id):
        return NodeDTO(id="n1", name="Test", node_type="hub", country="NL", lat=1.0, lon=2.0)

    monkeypatch.setattr("eurogas_nexus.cli.commands.fetch_node", fake_fetch)
    result = cmd_node("http://localhost:8000", "n1")
    assert '"id": "n1"' in result


def test_cli_uses_sdk_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI must not import backend internals."""
    import sys
    before = set(sys.modules.keys())
    import eurogas_nexus.cli.commands  # noqa: F401
    after = set(sys.modules.keys())
    forbidden = {"eurogas_nexus.db", "eurogas_nexus.runtime_store",
                 "eurogas_nexus.workflows", "eurogas_nexus.ingestion",
                 "eurogas_nexus.observations", "eurogas_nexus.governance"}
    leaked = (after - before) & forbidden
    assert not leaked, f"CLI imported backend modules: {leaked}"
