"""Release-route entitlement tests for the normalized market view."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.dependencies import identity as identity_dependency
from eurogas_nexus.api.routes.public import market as market_routes
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db import session as db_session
from eurogas_nexus.db.models import FxObservationRecord, MarketObservationRecord
from eurogas_nexus.db.repositories import market_intelligence
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    principal_allows_source_family,
)

PUBLIC_API_TOKEN = "fixture-public-api-token"


def _principal(scopes: tuple[str, ...]) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="fixture-principal",
        name="fixture-principal",
        principal_type="USER",
        role="VIEWER",
        status="ACTIVE",
        data_scopes=scopes,
        roles=("VIEWER",),
        auth_method="identity_key",
    )


def _normalized_row(observation_id: str, source_system: str) -> dict:
    return {
        "observation_id": observation_id,
        "source_system": source_system,
        "market_venue": source_system,
        "product": "NBP day-ahead",
        "price": 33.0,
        "currency": "EUR",
        "unit": "EUR/MWh",
        "metadata_json": {"hub": "NBP", "tenor": "day-ahead"},
    }


def _install_route_fixtures(monkeypatch, principal: AuthenticatedPrincipal) -> None:
    raw_rows = [
        _normalized_row("ice-restricted-new", "ICE_OCM"),
        _normalized_row("eex-entitled", "EEX"),
        _normalized_row("entsog-public-old", "ENTSOG"),
    ]
    raw_warnings = {
        "ice-restricted-new": "FX conversion unavailable for observation ICE_OCM/restricted.",
        "eex-entitled": "FX conversion unavailable for observation EEX/entitled.",
        "entsog-public-old": "FX conversion unavailable for observation ENTSOG/public.",
    }

    def fake_normalized_market_view(
        _session,
        *,
        limit: int = 500,
        source_filter=None,
    ) -> dict:
        visible_rows = [
            row
            for row in raw_rows
            if source_filter is None or source_filter(row["source_system"])
        ]
        selected_rows = visible_rows[:limit]
        return {
            "rows": selected_rows,
            "warnings": [raw_warnings[row["observation_id"]] for row in selected_rows],
        }

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", PUBLIC_API_TOKEN)
    monkeypatch.setattr(market_routes, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        db_session,
        "get_session_factory",
        lambda: (lambda: SessionContext()),
    )
    monkeypatch.setattr(
        market_intelligence,
        "list_normalized_market_view",
        fake_normalized_market_view,
    )
    monkeypatch.setattr(identity_dependency, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        identity_dependency,
        "_authenticate_identity_key",
        lambda _bearer: principal,
    )


def _get_normalized(client: TestClient, *, identity: bool, limit: int = 2):
    headers = {"X-Eurogas-Api-Key": PUBLIC_API_TOKEN}
    if identity:
        headers["X-Eurogas-Identity"] = "nexus_fixture_scope"
    return client.get(f"/api/market/normalized?limit={limit}", headers=headers)


def test_scoped_identity_filters_restricted_rows_warnings_and_preserves_source_coverage(
    monkeypatch,
) -> None:
    _install_route_fixtures(monkeypatch, _principal(("EEX",)))

    response = _get_normalized(
        TestClient(create_app(Settings(api_profile="release"))),
        identity=True,
    )

    assert response.status_code == 200
    body = response.json()
    assert [row["observation_id"] for row in body["data"]] == [
        "eex-entitled",
        "entsog-public-old",
    ]
    assert "ICE_OCM" not in response.text
    assert "ice-restricted-new" not in response.text


def test_unknown_scope_cannot_read_restricted_normalized_rows_or_warnings(monkeypatch) -> None:
    _install_route_fixtures(monkeypatch, _principal(("UnknownVendor",)))

    response = _get_normalized(
        TestClient(create_app(Settings(api_profile="release"))),
        identity=True,
    )

    assert response.status_code == 200
    body = response.json()
    assert [row["observation_id"] for row in body["data"]] == ["entsog-public-old"]
    assert "EEX" not in response.text
    assert "ICE_OCM" not in response.text


def test_wildcard_identity_and_legacy_public_token_retain_full_normalized_reads(
    monkeypatch,
) -> None:
    _install_route_fixtures(monkeypatch, _principal(("*",)))
    client = TestClient(create_app(Settings(api_profile="release")))

    wildcard_response = _get_normalized(client, identity=True, limit=3)
    legacy_response = _get_normalized(client, identity=False, limit=3)

    assert wildcard_response.status_code == 200
    assert legacy_response.status_code == 200
    expected = {"ice-restricted-new", "eex-entitled", "entsog-public-old"}
    assert {row["observation_id"] for row in wildcard_response.json()["data"]} == expected
    assert {row["observation_id"] for row in legacy_response.json()["data"]} == expected


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def distinct(self):
        return self

    def filter(self, *criteria):
        for criterion in criteria:
            values = getattr(getattr(criterion, "right", None), "value", None)
            if values is not None and self.rows and hasattr(self.rows[0], "source_system"):
                self.rows = [row for row in self.rows if row.source_system in values]
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self, market_sources, fx_sources, fx_rows):
        self.market_sources = market_sources
        self.fx_sources = fx_sources
        self.fx_rows = fx_rows

    def query(self, target):
        if target is MarketObservationRecord.source_system:
            return _Query([(source,) for source in self.market_sources])
        if target is FxObservationRecord.source_system:
            return _Query([(source,) for source in self.fx_sources])
        if target is FxObservationRecord:
            return _Query(self.fx_rows)
        raise AssertionError(f"unexpected repository query target: {target!r}")


def test_repository_filters_observation_and_fx_inputs_before_normalization(monkeypatch) -> None:
    from datetime import UTC, datetime, timedelta

    observed_at = datetime(2026, 9, 10, 10, tzinfo=UTC)
    market_row = SimpleNamespace(
        observation_id="eex-usd",
        market_venue="EEX",
        product="NBP day-ahead",
        price=33.0,
        currency="USD",
        unit="USD/MWh",
        period_start_utc=observed_at,
        period_end_utc=observed_at + timedelta(days=1),
        observed_at_utc=observed_at,
        source_system="EEX",
        source_reference="fixture:eex",
        source_record_id="eex-usd",
        freshness="fresh",
        quality_score=1.0,
        research_only=True,
        metadata_json={"hub": "NBP", "tenor": "day-ahead"},
    )
    fx_rows = [
        SimpleNamespace(
            pair="USDGBP",
            base_currency="USD",
            quote_currency="GBP",
            rate=0.8,
            observed_at_utc=observed_at,
            source_system="ICE_OCM",
        ),
        SimpleNamespace(
            pair="EURGBP",
            base_currency="EUR",
            quote_currency="GBP",
            rate=0.85,
            observed_at_utc=observed_at,
            source_system="ECB",
        ),
    ]
    session = _Session(
        market_sources={"EEX", "ENTSOG", "ICE_OCM"},
        fx_sources={"ECB", "ICE_OCM"},
        fx_rows=fx_rows,
    )
    captured = {}

    def fake_source_coverage(_session, *, limit, per_source_limit, source_systems=None):
        captured["source_systems"] = source_systems
        captured["limit"] = limit
        captured["per_source_limit"] = per_source_limit
        return [market_row]

    monkeypatch.setattr(
        market_intelligence,
        "list_market_observations_with_source_coverage",
        fake_source_coverage,
    )
    principal = _principal(("EEX",))
    view = market_intelligence.list_normalized_market_view(
        session,
        limit=2,
        source_filter=lambda source: principal_allows_source_family(principal, source),
    )

    assert captured == {
        "source_systems": {"EEX", "ENTSOG"},
        "limit": 2,
        "per_source_limit": 40,
    }
    assert view["rows"][0]["source_system"] == "EEX"
    assert view["rows"][0]["price_gbp_mwh"] is None
    assert any("USD->GBP" in warning for warning in view["warnings"])
