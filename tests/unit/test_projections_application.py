"""Application-layer projection tests (Architecture V2 Wave 5).

These tests exercise the projection builders directly against a SQLite runtime
database (the unit-test database), so the coherent read model is verified
without HTTP. They cover:

- one time basis and one as-of instant across data and envelope;
- per-slice freshness in the repository's existing state vocabulary;
- entitlement that is never wider than the underlying read;
- explicit empty/degraded states (no zero that reads as a measurement);
- a stable payload shape for ``data``, ``meta`` and every slice.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.projections import (
    GasDayInputError,
    build_market_context,
    build_portfolio_snapshot,
    build_review_context,
    build_scenario_context,
    resolve_projection_context,
    source_freshness_expectations,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FxObservationRecord,
    GeneratedReportRecord,
    IntradayOpportunityRecord,
    MarketObservationRecord,
    MarketQuoteRecord,
    MonitoringAlertRecord,
    PortfolioPnlSnapshotRecord,
    ReviewDecisionRecord,
    RouteCandidateRecord,
    ScreenOrderObservationRecord,
    StrategyRunRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal

AS_OF = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
GAS_DAY = "2026-06-01"

#: The envelope contract every projection must return.
ENVELOPE_KEYS = {"data", "meta"}
META_KEYS = {
    "projection",
    "projection_version",
    "as_of_utc",
    "time_basis",
    "research_only",
    "human_review_required",
    "source_references",
    "warnings",
    "table_lineage",
}
DATA_KEYS = {
    "projection",
    "projection_version",
    "as_of_utc",
    "time_basis",
    "active_context",
    "slices",
    "warnings",
    "research_only",
    "human_review_required",
}
SLICE_KEYS = {
    "available",
    "source_references",
    "row_count",
    "rows",
    "payload",
    "freshness",
    "entitlement",
    "context_filter",
    "limits",
    "warnings",
    "notes",
}
FRESHNESS_KEYS = {
    "state",
    "basis",
    "evaluated_at_utc",
    "last_observed_at_utc",
    "expected_within_minutes",
    "expectation_source",
    "measured",
    "derived_from",
}


def _principal(
    *,
    scopes: tuple[str, ...] = ("*",),
    auth_method: str = "identity_key",
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="fixture-principal",
        name="fixture-principal",
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=scopes,
        roles=("ANALYST",),
        auth_method=auth_method,
    )


def _legacy_principal() -> AuthenticatedPrincipal:
    return _principal(scopes=(), auth_method="legacy_public_token")


def _session(tmp_path, name: str = "projections.sqlite") -> Session:
    database_url = f"sqlite+pysqlite:///{(tmp_path / name).as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _observation(
    observation_id: str,
    source_system: str,
    *,
    observed_at: datetime,
    venue: str = "EEX",
    product: str = "NBP Day-Ahead",
    hub: str = "NBP",
) -> MarketObservationRecord:
    return MarketObservationRecord(
        observation_id=observation_id,
        market_venue=venue,
        product=product,
        price=31.0,
        unit="EUR/MWh",
        currency="EUR",
        period_start_utc=observed_at,
        period_end_utc=observed_at + timedelta(days=1),
        observed_at_utc=observed_at,
        source_system=source_system,
        source_reference=f"fixture:{source_system}",
        source_record_id=f"{source_system}-1",
        freshness="live",
        quality_score=0.9,
        research_only=True,
        metadata_json={"hub": hub, "tenor": "day-ahead"},
    )


def _quote(
    quote_id: str,
    *,
    observed_at: datetime,
    hub: str = "NBP",
    product: str = "within-day",
) -> MarketQuoteRecord:
    return MarketQuoteRecord(
        quote_id=quote_id,
        source_system="EEX_Sim",
        source_record_id=f"{quote_id}-src",
        venue="EEX",
        instrument_id=f"{hub}-{product}",
        hub=hub,
        product=product,
        delivery_start_utc=observed_at,
        delivery_end_utc=observed_at + timedelta(days=1),
        bid_price=30.0,
        ask_price=31.0,
        last_price=30.5,
        bid_quantity_mwh=100.0,
        ask_quantity_mwh=120.0,
        currency="GBP",
        unit="GBP/MWh",
        observed_at_utc=observed_at,
        received_at_utc=observed_at,
        source_reference=f"fixture:{quote_id}",
        freshness="live",
        quality_score=0.9,
        simulated=True,
        metadata_json={},
    )


def _opportunity(
    opportunity_id: str,
    *,
    detected_at: datetime,
    buy_hub: str = "NBP",
    sell_hub: str = "TTF",
    product: str = "within-day",
) -> IntradayOpportunityRecord:
    return IntradayOpportunityRecord(
        opportunity_id=opportunity_id,
        scan_id="scan-1",
        opportunity_type="CROSS_HUB_SPREAD",
        status="ACTIONABLE_REVIEW",
        buy_quote_id="q-buy",
        sell_quote_id="q-sell",
        route_id="route-1",
        route_name="NBP -> TTF",
        buy_venue="EEX",
        sell_venue="ICE OCM",
        buy_hub=buy_hub,
        sell_hub=sell_hub,
        product=product,
        delivery_start_utc=detected_at,
        delivery_end_utc=detected_at + timedelta(days=1),
        comparison_currency="GBP",
        comparison_unit="GBP/MWh",
        buy_ask=30.0,
        sell_bid=33.0,
        gross_spread=3.0,
        route_cost=1.0,
        trading_cost=0.2,
        risk_buffer=0.1,
        net_margin=1.7,
        max_quantity_mwh=1000.0,
        indicative_net_value=1700.0,
        quote_age_seconds=12.0,
        confidence_score=0.8,
        cost_components=[],
        source_refs=["fixture:quotes"],
        assumptions=["fixture assumption"],
        missing_inputs=[],
        warnings=["FIXTURE_WARNING"],
        detected_at_utc=detected_at,
        valid_until_utc=detected_at + timedelta(hours=4),
        simulated=True,
        human_review_required=True,
    )


def _market_fixture(session: Session) -> None:
    """Seed a runtime DB with fresh, stale and restricted market rows."""

    session.add_all(
        [
            # EEX expectation is 1 minute -> stale at AS_OF.
            _observation("obs-eex-stale", "EEX_Sim", observed_at=AS_OF - timedelta(minutes=10)),
            # ENTSOG expectation is 60 minutes -> fresh at AS_OF.
            _observation(
                "obs-entsog-fresh",
                "ENTSOG",
                observed_at=AS_OF - timedelta(minutes=10),
                venue="ENTSOG",
                product="NBP flows",
            ),
            _quote("q-eex", observed_at=AS_OF - timedelta(minutes=10)),
            _opportunity("opp-1", detected_at=AS_OF - timedelta(minutes=5)),
        ]
    )
    session.commit()


def _alert(alert_id: str, *, detected_at: datetime) -> MonitoringAlertRecord:
    return MonitoringAlertRecord(
        alert_id=alert_id,
        fingerprint=f"fp-{alert_id}",
        category="market",
        alert_type="SPREAD_MOVE",
        severity="warning",
        status="open",
        title_en="Spread moved",
        title_zh_cn="价差变动",
        message_en="NBP/TTF spread moved.",
        message_zh_cn="NBP/TTF 价差变动。",
        entity_type="route",
        entity_id="route-1",
        event_time_utc=detected_at,
        detected_at_utc=detected_at,
        updated_at_utc=detected_at,
        occurrence_count=1,
        evidence_snapshot={},
        source_refs=["fixture:quotes"],
        warnings=[],
        llm_provider_id="DEEPSEEK",
        llm_status="not_requested",
        simulated=True,
        human_review_required=True,
    )


# ---------------------------------------------------------------------------
# Context and time basis
# ---------------------------------------------------------------------------


def test_context_resolves_one_gas_day_from_the_as_of_instant() -> None:
    context = resolve_projection_context(as_of_utc=AS_OF)

    assert context.gas_day == GAS_DAY
    assert context.gas_day_calendar == "EU-CAM-UTC-2025"
    assert context.time_basis_payload()["basis"] == "as_of_instant"
    assert context.time_basis_payload()["as_of_utc"] == AS_OF.isoformat()
    assert context.gas_day_start_utc < context.gas_day_end_utc


def test_context_rejects_a_malformed_gas_day() -> None:
    with pytest.raises(GasDayInputError):
        resolve_projection_context(gas_day="01/06/2026", as_of_utc=AS_OF)


def test_repository_declares_freshness_expectations_per_source_family() -> None:
    expectations = source_freshness_expectations()

    assert expectations["EEX"] == 1
    assert expectations["ENTSOG"] == 60


# ---------------------------------------------------------------------------
# MarketContext
# ---------------------------------------------------------------------------


def test_market_context_uses_one_as_of_instant_across_every_slice(tmp_path) -> None:
    with _session(tmp_path) as session:
        _market_fixture(session)
        session.add(_alert("alert-1", detected_at=AS_OF - timedelta(minutes=2)))
        session.commit()

        payload = build_market_context(
            _legacy_principal(),
            session=session,
            as_of_utc=AS_OF,
        )

    assert set(payload) == ENVELOPE_KEYS
    assert set(payload["meta"]) == META_KEYS
    assert set(payload["data"]) == DATA_KEYS
    assert payload["meta"]["as_of_utc"] == AS_OF.isoformat()
    assert payload["data"]["as_of_utc"] == AS_OF.isoformat()
    assert payload["data"]["time_basis"] == payload["meta"]["time_basis"]
    assert payload["data"]["time_basis"]["gas_day"] == GAS_DAY

    slices = payload["data"]["slices"]
    assert set(slices) == {
        "market_observations",
        "normalized_quotes",
        "quotes",
        "intraday_opportunities",
        "spreads",
        "monitoring",
        "data_sources",
    }
    for name, item in slices.items():
        assert set(item) == SLICE_KEYS, name
        assert set(item["freshness"]) == FRESHNESS_KEYS, name
        # One evaluation clock for the whole payload.
        assert item["freshness"]["evaluated_at_utc"] == AS_OF.isoformat(), name


def test_market_context_reports_per_slice_freshness_from_declared_expectations(tmp_path) -> None:
    with _session(tmp_path) as session:
        _market_fixture(session)
        payload = build_market_context(_legacy_principal(), session=session, as_of_utc=AS_OF)

    slices = payload["data"]["slices"]
    # EEX declares a 1-minute expectation, so a 10-minute-old tick is stale.
    observations = slices["market_observations"]["freshness"]
    assert observations["state"] == "STALE"
    assert observations["expected_within_minutes"] == 1
    assert observations["expectation_source"] == "source_registry"
    assert observations["last_observed_at_utc"] == (AS_OF - timedelta(minutes=10)).isoformat()
    assert "SOURCE_STALE" in payload["meta"]["warnings"]

    # The per-source summary keeps the ENTSOG row (fresh) and the EEX row (stale)
    # apart instead of collapsing them into one verdict.
    by_source = {
        row["source_system"]: row for row in slices["data_sources"]["rows"]
    }
    assert by_source["EEX_Sim"]["freshness"]["state"] == "STALE"
    assert by_source["EEX_Sim"]["source_family"] == "EEX"
    assert by_source["EEX_Sim"]["simulated"] is True
    assert by_source["ENTSOG"]["freshness"]["state"] == "FRESH"
    assert by_source["ENTSOG"]["freshness"]["expected_within_minutes"] == 60


def test_market_context_spreads_are_derived_from_the_reported_opportunity_rows(tmp_path) -> None:
    with _session(tmp_path) as session:
        _market_fixture(session)
        payload = build_market_context(_legacy_principal(), session=session, as_of_utc=AS_OF)

    slices = payload["data"]["slices"]
    assert [row["spread_id"] for row in slices["spreads"]["rows"]] == ["opp-1"]
    assert slices["spreads"]["rows"][0]["spread_eur_mwh"] == 3.0
    assert slices["spreads"]["freshness"]["derived_from"] == "intraday_opportunities"
    assert (
        slices["spreads"]["freshness"]["last_observed_at_utc"]
        == slices["intraday_opportunities"]["freshness"]["last_observed_at_utc"]
    )


def test_market_context_applies_entitlement_never_wider_than_the_market_route(tmp_path) -> None:
    scoped = _principal(scopes=("ENTSOG",))
    with _session(tmp_path) as session:
        _market_fixture(session)
        scoped_payload = build_market_context(scoped, session=session, as_of_utc=AS_OF)
        legacy_payload = build_market_context(
            _legacy_principal(), session=session, as_of_utc=AS_OF
        )

    scoped_slice = scoped_payload["data"]["slices"]["market_observations"]
    legacy_slice = legacy_payload["data"]["slices"]["market_observations"]
    scoped_ids = {row["observation_id"] for row in scoped_slice["rows"]}
    legacy_ids = {row["observation_id"] for row in legacy_slice["rows"]}

    assert legacy_ids == {"obs-eex-stale", "obs-entsog-fresh"}
    assert scoped_ids == {"obs-entsog-fresh"}
    assert scoped_ids <= legacy_ids
    assert scoped_slice["entitlement"]["row_filter_applied"] is True
    assert scoped_slice["entitlement"]["filtered_out"] == 1
    assert "ENTITLEMENT_FILTERED" in scoped_payload["meta"]["warnings"]
    # A restricted family is never named in the data-source summary.
    assert (
        {row["source_system"] for row in scoped_payload["data"]["slices"]["data_sources"]["rows"]}
        == {"ENTSOG"}
    )
    # The unscoped legacy principal keeps the single-trust-domain view.
    assert legacy_slice["entitlement"]["row_filter_applied"] is False


def test_market_context_hub_and_product_context_filter_is_declared_and_exact(tmp_path) -> None:
    with _session(tmp_path) as session:
        session.add(_quote("q-nbp", observed_at=AS_OF, hub="NBP", product="within-day"))
        session.add(_quote("q-ttf", observed_at=AS_OF, hub="TTF", product="within-day"))
        session.commit()
        payload = build_market_context(
            _legacy_principal(),
            session=session,
            as_of_utc=AS_OF,
            hub="NBP",
            delivery_product="within-day",
        )

    quotes = payload["data"]["slices"]["quotes"]
    assert [row["quote_id"] for row in quotes["rows"]] == ["q-nbp"]
    assert quotes["context_filter"]["applied"] == ["hub", "delivery_product"]
    assert payload["data"]["active_context"]["hub"] == "NBP"
    # A slice with no backend hub field says so instead of pretending to filter.
    observations = payload["data"]["slices"]["market_observations"]
    assert observations["context_filter"]["applied"] == []


def test_market_context_without_runtime_db_is_an_explicit_unknown() -> None:
    payload = build_market_context(_legacy_principal(), session=None, as_of_utc=AS_OF)

    assert payload["meta"]["source_references"] == ["runtime-db-not-configured"]
    assert "RUNTIME_DB_NOT_CONFIGURED" in payload["meta"]["warnings"]
    for name, item in payload["data"]["slices"].items():
        assert item["available"] is False, name
        assert item["freshness"]["state"] == "MISSING", name
        assert item["freshness"]["measured"] is False, name
        assert item["rows"] in (None, []), name
    assert payload["data"]["slices"]["monitoring"]["payload"] is None


def test_market_context_empty_runtime_db_keeps_zero_rows_and_no_fabricated_values(tmp_path) -> None:
    with _session(tmp_path, "empty.sqlite") as session:
        payload = build_market_context(_legacy_principal(), session=session, as_of_utc=AS_OF)

    for name, item in payload["data"]["slices"].items():
        assert item["available"] is True, name
        assert item["row_count"] == 0, name
        assert item["freshness"]["state"] == "MISSING", name
        assert item["freshness"]["measured"] is False, name


def _observation_page_fixture(
    session: Session,
    sources: tuple[str, ...] = (
        "EEX_Sim",
        "ENTSOG",
        "ICIS",
        "EEX_Sim",
        "ICIS",
        "ENTSOG",
        "EEX_Sim",
    ),
) -> list[str]:
    """Seed one observation per source, newest first (ENTSOG is a public baseline family)."""

    identifiers = [f"obs-{index:02d}-{source}" for index, source in enumerate(sources)]
    session.add_all(
        [
            _observation(
                identifiers[index],
                source,
                observed_at=AS_OF - timedelta(minutes=index),
            )
            for index, source in enumerate(sources)
        ]
    )
    session.commit()
    return identifiers


@pytest.mark.parametrize("observation_limit", [1, 3, 7, 50])
def test_market_context_observation_slice_matches_the_unbounded_reference_read(
    tmp_path, monkeypatch, observation_limit: int
) -> None:
    """The bounded observation read composes the payload the unbounded read produced.

    The reference page is the composition the projection used before the read was
    bounded: read every observation row, filter entitlement in Python, then slice.
    Whole payloads are compared, so the returned rows and their order, the
    entitlement counts (raw and kept, before the cap), the ``truncated`` flag and
    every derived slice are pinned to that reference. The limits cover a cap
    below, at and above both the entitled and the total row count.
    """

    from eurogas_nexus.application.projections import market_context as market_context_module
    from eurogas_nexus.application.projections import market_reads

    with _session(tmp_path, "observation-page.sqlite") as session:
        _observation_page_fixture(session)
        scoped = _principal(scopes=("EEX",))

        def reference_page(_session, principal, *, limit):
            rows = market_reads.market_observations(_session)
            kept = market_reads.filter_entitled_rows(principal, rows)
            return market_reads.ObservationPage(
                rows=kept[:limit],
                raw_count=len(rows),
                entitled_count=len(kept),
            )

        with monkeypatch.context() as patcher:
            patcher.setattr(
                market_context_module, "market_observation_page", reference_page
            )
            reference_scoped = build_market_context(
                scoped, session=session, as_of_utc=AS_OF, observation_limit=observation_limit
            )
            reference_legacy = build_market_context(
                _legacy_principal(),
                session=session,
                as_of_utc=AS_OF,
                observation_limit=observation_limit,
                hub="NBP",
                delivery_product="within-day",
            )

        bounded_scoped = build_market_context(
            scoped, session=session, as_of_utc=AS_OF, observation_limit=observation_limit
        )
        bounded_legacy = build_market_context(
            _legacy_principal(),
            session=session,
            as_of_utc=AS_OF,
            observation_limit=observation_limit,
            hub="NBP",
            delivery_product="within-day",
        )

    assert bounded_scoped == reference_scoped
    assert bounded_legacy == reference_legacy


def test_market_context_observation_rows_are_the_newest_entitled_rows_at_the_cap(tmp_path) -> None:
    """The cap keeps the newest entitled rows in the route's own order."""

    with _session(tmp_path, "observation-cap.sqlite") as session:
        identifiers = _observation_page_fixture(session)
        bounded_scoped = build_market_context(
            _principal(scopes=("EEX",)), session=session, as_of_utc=AS_OF, observation_limit=3
        )
        bounded_legacy = build_market_context(
            _legacy_principal(), session=session, as_of_utc=AS_OF, observation_limit=3
        )

    # The scoped principal sees the EEX_Sim rows plus the public-baseline ENTSOG
    # row, so the newest three rows it may see are EEX_Sim, ENTSOG, EEX_Sim: the
    # restricted ICIS rows are filtered out *before* the cap, never after it.
    scoped_slice = bounded_scoped["data"]["slices"]["market_observations"]
    assert [row["observation_id"] for row in scoped_slice["rows"]] == [
        identifiers[0],
        identifiers[1],
        identifiers[3],
    ]
    assert scoped_slice["entitlement"]["row_filter_applied"] is True
    # The two restricted ICIS rows are counted as filtered out, and the three
    # visible rows are not all of the five the principal may see.
    assert scoped_slice["entitlement"]["filtered_out"] == 2
    assert scoped_slice["limits"] == {"row_limit": 3, "truncated": True}

    legacy_slice = bounded_legacy["data"]["slices"]["market_observations"]
    assert [row["observation_id"] for row in legacy_slice["rows"]] == identifiers[:3]
    assert legacy_slice["entitlement"]["row_filter_applied"] is False
    assert legacy_slice["limits"] == {"row_limit": 3, "truncated": True}


def test_market_context_observation_read_is_bounded_before_it_reaches_python(
    tmp_path, monkeypatch
) -> None:
    """No observation row is read or shaped beyond the slice's own cap.

    The projection used to read and shape every row of ``market_observations``
    before applying ``observation_limit``. This pins the replacement: the rows are
    fetched under a SQL ``LIMIT``, only ``observation_limit`` rows are shaped, and
    the counts the payload reports come from an aggregate rather than from rows.
    """

    from sqlalchemy import event

    from eurogas_nexus.application.projections import market_reads

    with _session(tmp_path, "observation-bounded.sqlite") as session:
        session.add(
            # Present so the normalized slice uses the FX table rather than its
            # ECB fallback, keeping this test about the observation reads.
            FxObservationRecord(
                observation_id="fx-eur-gbp",
                pair="EURGBP",
                base_currency="EUR",
                quote_currency="GBP",
                rate=0.85,
                rate_type="reference",
                value_date=GAS_DAY,
                observed_at_utc=AS_OF,
                source_system="ECB",
                source_reference="ecb-eurofxref-daily",
                source_record_id="2026-06-01-GBP",
                freshness="live",
                research_only=True,
                metadata_json={"dataset": "eurofxref-daily"},
            )
        )
        session.add_all(
            [
                _observation(
                    f"obs-{index:03d}",
                    "EEX_Sim",
                    observed_at=AS_OF - timedelta(minutes=index),
                )
                for index in range(40)
            ]
        )
        session.commit()

        shaped: list[str] = []
        original_row = market_reads.market_observation_row

        def counting_row(row):
            shaped.append(row.observation_id)
            return original_row(row)

        statements: list[str] = []
        event.listen(
            session.get_bind(),
            "before_cursor_execute",
            lambda conn, cursor, statement, parameters, context, executemany: (
                statements.append(statement)
            ),
        )
        monkeypatch.setattr(market_reads, "market_observation_row", counting_row)
        payload = build_market_context(
            _principal(scopes=("EEX",)),
            session=session,
            as_of_utc=AS_OF,
            observation_limit=5,
        )

    observation_slice = payload["data"]["slices"]["market_observations"]
    assert len(shaped) == 5
    assert len(observation_slice["rows"]) == 5
    assert observation_slice["limits"] == {"row_limit": 5, "truncated": True}
    # The counts are aggregates and the entitlement probe reads source values
    # only; every statement that loads observation rows carries a LIMIT. The
    # normalized view's per-source coverage read loads rows too - it is bounded
    # by its own ``source_rank`` window predicate instead, and is unchanged here.
    full_row_statements = [
        statement
        for statement in statements
        if "market_observations_observation_id" in statement
        and "row_number" not in statement.lower()
    ]
    assert full_row_statements
    assert all("LIMIT" in statement.upper() for statement in full_row_statements)
    assert any("DISTINCT" in statement.upper() for statement in statements)


def test_market_context_observation_slice_fails_closed_without_an_entitled_source(
    tmp_path,
) -> None:
    """A principal with no grant for the sources present sees none of them, and is told so."""

    from eurogas_nexus.application.projections.market_reads import ENTITLEMENT_RULE_SOURCE_FAMILY

    with _session(tmp_path, "observation-unentitled.sqlite") as session:
        _observation_page_fixture(session, sources=("EEX_Sim", "ICIS", "EEX_Sim"))
        payload = build_market_context(
            _principal(scopes=("Trayport",)),
            session=session,
            as_of_utc=AS_OF,
            observation_limit=3,
        )

    observation_slice = payload["data"]["slices"]["market_observations"]
    assert observation_slice["rows"] == []
    assert observation_slice["row_count"] == 0
    assert observation_slice["entitlement"] == {
        "row_filter_applied": True,
        "filtered_out": 3,
        "reason": ENTITLEMENT_RULE_SOURCE_FAMILY,
    }
    assert observation_slice["limits"] == {"row_limit": 3, "truncated": False}
    assert observation_slice["freshness"]["state"] == "MISSING"
    assert "ENTITLEMENT_FILTERED" in payload["meta"]["warnings"]


# ---------------------------------------------------------------------------
# PortfolioSnapshot
# ---------------------------------------------------------------------------


def test_portfolio_snapshot_keeps_unknown_totals_and_per_slice_freshness(tmp_path) -> None:
    with _session(tmp_path, "portfolio.sqlite") as session:
        session.add(
            PortfolioPnlSnapshotRecord(
                pnl_snapshot_id="pnl-1",
                portfolio_id="portfolio-demo",
                resource_id="resource-1",
                strategy_id="strategy-1",
                valuation_time_utc=AS_OF - timedelta(minutes=5),
                realized_pnl_gbp=100.0,
                unrealized_pnl_gbp=200.0,
                indicative_pnl_gbp=300.0,
                cash_value_gbp=400.0,
                market_value_gbp=5000.0,
                quantity_mwh=1000.0,
                valuation_basis="fixture-mark",
                source_system="EEX_Sim",
                source_reference="fixture:pnl",
                warnings=["FIXTURE_VALUATION_WARNING"],
                research_only=True,
                human_review_required=True,
            )
        )
        session.add(
            ScreenOrderObservationRecord(
                order_observation_id="ord-1",
                provider_id="ICE_OCM",
                venue="ICE OCM",
                account_label="demo",
                external_order_id="ext-1",
                side="SELL",
                order_type="LIMIT",
                hub="NBP",
                product="Within-day",
                contract_code="NBP-WD",
                delivery_start_utc=AS_OF,
                delivery_end_utc=AS_OF,
                price=30.0,
                currency="GBP",
                unit="GBP/MWh",
                quantity_mwh=500.0,
                filled_quantity_mwh=100.0,
                remaining_quantity_mwh=400.0,
                status="WORKING",
                observed_at_utc=AS_OF - timedelta(minutes=2),
                source_system="ICE_OCM_Sim",
                source_reference="fixture:order",
                research_only=True,
                human_review_required=True,
            )
        )
        session.commit()

        payload = build_portfolio_snapshot(
            _legacy_principal(),
            session=session,
            as_of_utc=AS_OF,
        )

    assert set(payload) == ENVELOPE_KEYS
    assert set(payload["meta"]) == META_KEYS
    assert set(payload["data"]) == DATA_KEYS | {"portfolio_id"}
    slices = payload["data"]["slices"]
    assert set(slices) == {
        "summary",
        "screen_orders",
        "pnl_snapshots",
        "contracts",
        "resources",
        "data_sources",
    }
    for name, item in slices.items():
        assert set(item) == SLICE_KEYS, name
        assert item["freshness"]["evaluated_at_utc"] == AS_OF.isoformat(), name

    summary = slices["summary"]["payload"]
    assert summary["portfolio_id"] == "portfolio-demo"
    assert summary["total_indicative_pnl_gbp"] == 300.0
    assert summary["open_order_count"] == 1
    assert "FIXTURE_VALUATION_WARNING" in payload["meta"]["warnings"]
    assert slices["summary"]["freshness"]["derived_from"] == "pnl_snapshots"
    assert slices["pnl_snapshots"]["freshness"]["last_observed_at_utc"] == (
        AS_OF - timedelta(minutes=5)
    ).isoformat()
    # Portfolio resources are composed by the same application-layer code
    # GET /api/route-cost/resource-pool/options calls (Wave 5 follow-up). This
    # session holds no contract and no candidate, so the slice is honest about
    # the missing inputs instead of fabricating an empty resource list.
    resources = slices["resources"]
    assert resources["available"] is True
    assert resources["payload"]["scope"] == "RESOURCE_POOL_ROUTE_OPTIONS"
    assert resources["payload"]["data_source"] == "runtime-postgresql"
    assert resources["payload"]["portfolio_resources"] == []
    assert resources["payload"]["counts"] == {"portfolio_resources": 0, "sale_options": 0}
    assert resources["payload"]["blockers"] == [
        "UPSTREAM_CONTRACTS_MISSING",
        "ROUTE_CANDIDATES_MISSING",
    ]
    assert resources["rows"] == []


def test_portfolio_snapshot_without_valuation_evidence_keeps_unknown_not_zero(tmp_path) -> None:
    with _session(tmp_path, "portfolio-empty.sqlite") as session:
        payload = build_portfolio_snapshot(
            _legacy_principal(),
            session=session,
            as_of_utc=AS_OF,
        )

    summary = payload["data"]["slices"]["summary"]["payload"]
    assert summary["total_indicative_pnl_gbp"] is None
    assert summary["total_indicative_pnl_gbp"] != 0
    assert summary["latest_valuation_time_utc"] is None
    assert "VALUATION_EVIDENCE_MISSING" in payload["meta"]["warnings"]


def test_portfolio_snapshot_entitlement_is_never_wider_than_the_portfolio_route(tmp_path) -> None:
    scoped = _principal(scopes=("ENTSOG",))
    with _session(tmp_path, "portfolio-scope.sqlite") as session:
        session.add(
            PortfolioPnlSnapshotRecord(
                pnl_snapshot_id="pnl-eex",
                portfolio_id="portfolio-demo",
                resource_id=None,
                strategy_id=None,
                valuation_time_utc=AS_OF,
                realized_pnl_gbp=1.0,
                unrealized_pnl_gbp=1.0,
                indicative_pnl_gbp=1.0,
                cash_value_gbp=1.0,
                market_value_gbp=1.0,
                quantity_mwh=1.0,
                valuation_basis="fixture",
                source_system="EEX",
                source_reference="fixture:pnl-eex",
                warnings=[],
                research_only=True,
                human_review_required=True,
            )
        )
        session.commit()

        payload = build_portfolio_snapshot(scoped, session=session, as_of_utc=AS_OF)

    slice_ = payload["data"]["slices"]["pnl_snapshots"]
    assert slice_["rows"] == []
    assert slice_["entitlement"]["row_filter_applied"] is True
    assert slice_["entitlement"]["filtered_out"] == 1


def _seed_resource_pool_inputs(session: Session) -> None:
    """Seed the runtime rows the resource-pool composition is built from."""

    session.add_all(
        [
            UpstreamResourceContractRecord(
                contract_id="pool-ttf-2025",
                contract_name="Resource pool TTF supply 2025",
                resource_type="PIPELINE_IMPORT",
                delivery_point_name="TTF",
                gas_year="2025+",
                delivery_quantity_mwh_per_day=100.0,
                contract_price_gbp_mwh=30.0,
                settlement_frequency="monthly",
                upstream_payment_lag_days=20,
                screen_sale_cash_lag_days=1,
                delivery_tolerance_pct=2.0,
                nomination_tolerance_pct=1.0,
                tolerance_risk_allowance_gbp_mwh=0.1,
                annual_financing_rate_pct=6.0,
                owned_entry_capacity_mwh_per_day=None,
                owned_exit_capacity_mwh_per_day=None,
                allowed_exit_points=["NBP", "TTF"],
                eligible_sale_modes=["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"],
                notes="test_fixture:not_customer_data",
                created_at_utc=AS_OF,
                updated_at_utc=AS_OF,
            ),
            RouteCandidateRecord(
                route_id="route-ttf-local",
                route_name="Sell locally at TTF",
                start_point_name="TTF",
                target_point_name="TTF",
                business_model="VIRTUAL_HUB_SALE",
                route_legs=[],
                required_entry_point_name=None,
                required_exit_point_name=None,
                required_tso_access=[],
                source_systems=["public_route_template"],
                active=True,
                created_at_utc=AS_OF,
            ),
            FxObservationRecord(
                observation_id="fx-eur-gbp",
                pair="EURGBP",
                base_currency="EUR",
                quote_currency="GBP",
                rate=0.85,
                rate_type="reference",
                value_date=GAS_DAY,
                observed_at_utc=AS_OF,
                source_system="ECB",
                source_reference="ecb-eurofxref-daily",
                source_record_id="2026-06-01-GBP",
                freshness="live",
                research_only=True,
                metadata_json={"dataset": "eurofxref-daily"},
            ),
            MarketObservationRecord(
                observation_id="obs-ttf-eex-sim",
                market_venue="EEX",
                product="TTF day-ahead",
                price=31.0,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=AS_OF,
                period_end_utc=AS_OF + timedelta(days=1),
                observed_at_utc=AS_OF - timedelta(minutes=5),
                source_system="EEX_Sim",
                source_reference="fixture:EEX_Sim",
                source_record_id="eex-ttf-1",
                freshness="simulated_live",
                quality_score=0.62,
                research_only=True,
                metadata_json={
                    "hub": "TTF",
                    "tenor": "day-ahead",
                    "simulated": True,
                    "source_family": "EEX",
                },
            ),
        ]
    )
    session.commit()


def test_portfolio_snapshot_resources_slice_composes_the_same_payload_as_the_route(
    tmp_path,
) -> None:
    """The slice is real: it composes what the route composes, from one read."""

    with _session(tmp_path, "portfolio-resources.sqlite") as session:
        _seed_resource_pool_inputs(session)
        payload = build_portfolio_snapshot(
            _legacy_principal(), session=session, as_of_utc=AS_OF
        )

    resources = payload["data"]["slices"]["resources"]
    assert resources["available"] is True
    assert set(resources) == SLICE_KEYS
    assert resources["row_count"] == 1
    assert resources["payload"]["scope"] == "RESOURCE_POOL_ROUTE_OPTIONS"
    assert resources["payload"]["data_source"] == "runtime-postgresql"
    assert resources["payload"]["counts"] == {"portfolio_resources": 1, "sale_options": 1}

    resource = resources["payload"]["portfolio_resources"][0]
    assert resource["resource_id"] == "pool-ttf-2025"
    assert resource["location_point_name"] == "TTF"

    option = resources["rows"][0]
    assert option["option_id"] == "route-ttf-local"
    assert option["route_topology_kind"] == "LOCAL_MARKET_DISPOSITION"
    assert option["eligible_resource_ids"] == ["pool-ttf-2025"]
    # The EUR price is converted with as-of FX and carries its provenance.
    assert option["sale_price_currency"] == "GBP"
    assert option["sale_price_original_currency"] == "EUR"
    assert option["fx_rate_used"] == 0.85
    assert option["sale_price_gbp_mwh"] == round(31.0 * 0.85, 4)
    # No blocker survived: every input the composition needs was present.
    assert resources["payload"]["blockers"] == []
    # Freshness is measured from the observation that priced the option.
    assert resources["freshness"]["last_observed_at_utc"] == (
        AS_OF - timedelta(minutes=5)
    ).isoformat()
    assert resources["freshness"]["derived_from"] == (
        "route_candidates+market_observations"
    )
    assert resources["entitlement"]["row_filter_applied"] is False
    assert resources["entitlement"]["filtered_out"] == 0


def test_portfolio_snapshot_resources_slice_is_never_wider_than_the_route(tmp_path) -> None:
    """A scoped principal cannot reach a licensed price through the slice."""

    with _session(tmp_path, "portfolio-resources-scoped.sqlite") as session:
        _seed_resource_pool_inputs(session)
        payload = build_portfolio_snapshot(
            _principal(scopes=("ENTSOG",)), session=session, as_of_utc=AS_OF
        )

    resources = payload["data"]["slices"]["resources"]
    assert resources["available"] is True
    assert resources["rows"] == []
    assert resources["entitlement"]["row_filter_applied"] is True
    # Both the EEX-priced candidate and its market observation were removed.
    assert resources["entitlement"]["filtered_out"] == 2
    # Operator-owned contract facts are not licensed rows and stay visible.
    assert resources["payload"]["counts"]["portfolio_resources"] == 1
    # The restricted source family is absent from the whole slice.
    assert "EEX" not in str(resources)


def test_portfolio_snapshot_resources_slice_without_runtime_db_matches_the_route() -> None:
    payload = build_portfolio_snapshot(_legacy_principal(), session=None, as_of_utc=AS_OF)

    resources = payload["data"]["slices"]["resources"]
    assert resources["available"] is False
    # The identical block GET /api/route-cost/resource-pool/options returns.
    assert resources["payload"] == {
        "scope": "RESOURCE_POOL_ROUTE_OPTIONS",
        "data_source": "runtime-db-not-configured",
        "portfolio_resources": [],
        "sale_options": [],
        "blockers": ["RUNTIME_DB_NOT_CONFIGURED"],
        "warnings": [],
    }
    assert resources["rows"] == []


def test_portfolio_snapshot_without_runtime_db_is_an_explicit_unknown() -> None:
    payload = build_portfolio_snapshot(_legacy_principal(), session=None, as_of_utc=AS_OF)

    assert payload["meta"]["source_references"] == ["runtime-db-not-configured"]
    assert payload["data"]["slices"]["summary"]["payload"]["total_cash_value_gbp"] is None
    for name, item in payload["data"]["slices"].items():
        assert item["available"] is False, name


# ---------------------------------------------------------------------------
# ReviewContext
# ---------------------------------------------------------------------------


def _review_fixture(session: Session) -> None:
    session.add(
        ReviewDecisionRecord(
            decision_id="dec-1",
            entity_type="intraday_opportunity",
            entity_id="opp-1",
            actor="operator-a",
            decision="needs_attention",
            note="check capacity",
            created_at_utc=AS_OF - timedelta(minutes=3),
        )
    )
    session.add(
        ReviewDecisionRecord(
            decision_id="dec-2",
            entity_type="generated_report",
            entity_id="report-1",
            actor="operator-b",
            decision="accepted",
            note=None,
            created_at_utc=AS_OF - timedelta(minutes=1),
        )
    )
    session.add(
        ReviewDecisionRecord(
            decision_id="dec-3",
            entity_type="strategy_run",
            entity_id="run-missing",
            actor="operator-c",
            decision="accepted",
            note=None,
            created_at_utc=AS_OF - timedelta(minutes=2),
        )
    )
    session.add(
        _opportunity("opp-1", detected_at=AS_OF - timedelta(minutes=5))
    )
    session.add(
        GeneratedReportRecord(
            report_id="report-1",
            report_type="PORTFOLIO",
            title="Portfolio review pack",
            status="success",
            duration_start_utc=AS_OF - timedelta(days=1),
            duration_end_utc=AS_OF,
            input_snapshot={},
            sections=[{"title": "summary"}],
            source_refs=["runtime-postgresql"],
            warnings=["REPORT_WARNING"],
            created_at_utc=AS_OF - timedelta(minutes=4),
            research_only=True,
            human_review_required=True,
        )
    )
    session.commit()


def test_review_context_resolves_decisions_evidence_and_warnings(tmp_path) -> None:
    with _session(tmp_path, "review.sqlite") as session:
        _review_fixture(session)
        payload = build_review_context(_legacy_principal(), session=session, as_of_utc=AS_OF)

    assert set(payload) == ENVELOPE_KEYS
    assert set(payload["meta"]) == META_KEYS
    assert set(payload["data"]) == DATA_KEYS | {"review_target"}
    slices = payload["data"]["slices"]
    assert set(slices) == {"decisions", "evidence", "monitoring"}
    for name, item in slices.items():
        assert set(item) == SLICE_KEYS, name
        assert item["freshness"]["evaluated_at_utc"] == AS_OF.isoformat(), name

    decisions = slices["decisions"]
    assert [row["decision_id"] for row in decisions["rows"]] == ["dec-2", "dec-3", "dec-1"]
    assert decisions["payload"]["needs_attention_count"] == 1

    evidence = {entry["entity_id"]: entry for entry in slices["evidence"]["rows"]}
    assert evidence["opp-1"]["available"] is True
    assert evidence["opp-1"]["artifact"]["opportunity_id"] == "opp-1"
    assert evidence["report-1"]["available"] is True
    assert evidence["report-1"]["artifact"]["section_count"] == 1
    assert evidence["run-missing"]["available"] is False
    assert evidence["run-missing"]["unavailable_reason"] == "EVIDENCE_NOT_FOUND"
    assert "REVIEW_DECISION_NEEDS_ATTENTION" in payload["meta"]["warnings"]
    assert "REVIEW_EVIDENCE_INCOMPLETE" in payload["meta"]["warnings"]


def test_review_context_withholds_evidence_from_an_unentitled_principal(tmp_path) -> None:
    scoped = _principal(scopes=("ENTSOG",))
    with _session(tmp_path, "review-scope.sqlite") as session:
        session.add(
            StrategyRunRecord(
                run_id="run-1",
                strategy_id="strategy-1",
                strategy_version_id=None,
                run_type="EVALUATION",
                run_mode="BACKTEST",
                status="SUCCEEDED",
                started_at_utc=AS_OF - timedelta(hours=1),
                input_snapshot={},
                result_snapshot={"source_systems": ["EEX", "ENTSOG"]},
                source_refs=["fixture:run"],
                warnings=["RUN_WARNING"],
                missing_inputs=[],
                research_only=True,
                human_review_required=True,
            )
        )
        session.add(
            ReviewDecisionRecord(
                decision_id="dec-1",
                entity_type="strategy_run",
                entity_id="run-1",
                actor="operator-a",
                decision="accepted",
                note=None,
                created_at_utc=AS_OF,
            )
        )
        session.commit()
        payload = build_review_context(scoped, session=session, as_of_utc=AS_OF)

    entry = payload["data"]["slices"]["evidence"]["rows"][0]
    # The run declares contributing source systems (EEX is not granted); the
    # principal gets an explicit denial instead of the evidence payload.
    assert entry["entity_type"] == "strategy_run"
    assert entry["available"] is False
    assert entry["unavailable_reason"] == "ENTITLEMENT_DENIED"
    assert entry["artifact"] is None
    assert "ENTITLEMENT_DENIED" in entry["warnings"]
    assert "REVIEW_EVIDENCE_INCOMPLETE" in payload["meta"]["warnings"]


def test_review_context_reports_unknown_entity_types_instead_of_guessing(tmp_path) -> None:
    with _session(tmp_path, "review-unknown.sqlite") as session:
        payload = build_review_context(
            _legacy_principal(),
            session=session,
            entity_type="not_a_review_entity",
            entity_id="whatever",
            as_of_utc=AS_OF,
        )

    entry = payload["data"]["slices"]["evidence"]["rows"][0]
    assert entry["available"] is False
    assert entry["unavailable_reason"] == "ENTITY_TYPE_NOT_RESOLVABLE"
    assert entry["resolver"] is None


def test_review_context_without_runtime_db_is_an_explicit_unknown() -> None:
    payload = build_review_context(_legacy_principal(), session=None, as_of_utc=AS_OF)

    assert payload["meta"]["source_references"] == ["runtime-db-not-configured"]
    assert payload["data"]["slices"]["decisions"]["available"] is False
    assert payload["data"]["slices"]["evidence"]["rows"] == []


# ---------------------------------------------------------------------------
# ScenarioContext
# ---------------------------------------------------------------------------


def test_scenario_context_declares_what_a_read_model_does_not_provide(tmp_path) -> None:
    with _session(tmp_path, "scenario.sqlite") as session:
        payload = build_scenario_context(_legacy_principal(), session=session, as_of_utc=AS_OF)

    assert set(payload) == ENVELOPE_KEYS
    assert set(payload["meta"]) == META_KEYS
    assert set(payload["data"]) == DATA_KEYS | {"not_included"}
    slices = payload["data"]["slices"]
    assert set(slices) == {"route_candidates", "tso_tariffs", "upstream_contracts"}
    for name, item in slices.items():
        assert set(item) == SLICE_KEYS, name
        assert item["freshness"]["evaluated_at_utc"] == AS_OF.isoformat(), name

    surfaces = {item["surface"] for item in payload["data"]["not_included"]}
    assert "POST /api/route-cost/resource-pool/optimize" in surfaces
    assert "GET /api/route-cost/resource-pool/options" in surfaces
    for item in payload["data"]["not_included"]:
        assert item["reason"]
        assert item["detail"]


def test_scenario_context_without_runtime_db_is_an_explicit_unknown() -> None:
    payload = build_scenario_context(_legacy_principal(), session=None, as_of_utc=AS_OF)

    assert payload["meta"]["source_references"] == ["runtime-db-not-configured"]
    for name, item in payload["data"]["slices"].items():
        assert item["available"] is False, name
        assert item["freshness"]["state"] == "MISSING", name


def test_every_projection_shares_the_same_envelope_and_time_basis(tmp_path) -> None:
    with _session(tmp_path, "all.sqlite") as session:
        payloads = {
            "market-context": build_market_context(
                _legacy_principal(), session=session, as_of_utc=AS_OF
            ),
            "portfolio-snapshot": build_portfolio_snapshot(
                _legacy_principal(), session=session, as_of_utc=AS_OF
            ),
            "review-context": build_review_context(
                _legacy_principal(), session=session, as_of_utc=AS_OF
            ),
            "scenario-context": build_scenario_context(
                _legacy_principal(), session=session, as_of_utc=AS_OF
            ),
        }

    for name, payload in payloads.items():
        assert payload["meta"]["projection"] == name
        assert payload["data"]["projection"] == name
        assert payload["meta"]["projection_version"] == payload["data"]["projection_version"]
        assert payload["meta"]["research_only"] is True
        assert payload["meta"]["human_review_required"] is True
        assert payload["meta"]["as_of_utc"] == AS_OF.isoformat()
        assert payload["meta"]["time_basis"]["basis"] == "as_of_instant"
        assert payload["meta"]["time_basis"]["gas_day"] == GAS_DAY
        assert payload["meta"]["table_lineage"]
        assert payload["meta"]["source_references"] == ["runtime-postgresql"]
