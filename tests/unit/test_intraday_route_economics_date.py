"""Focused tests for explicit tariff dates in intraday route economics.

``_route_economics`` previously derived the tariff applicability date from the
scan's valuation instant (``at_utc.date()``). These tests pin the corrected
contract: an explicit delivery date selects (or refuses) tariff rows, and
without one the legacy selection is disclosed as not assessed rather than being
presented as verified against the clock.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import RouteCandidateRecord, TsoTariffRecord
from eurogas_nexus.db.repositories.market_intelligence import _route_economics
from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    TariffDirection,
    TariffStatus,
)
from eurogas_nexus.domain.route_cost.tariff_selection import (
    TARIFF_APPLICABILITY_AMBIGUOUS,
    TARIFF_APPLICABILITY_NOT_ASSESSED,
    TARIFF_NOT_EFFECTIVE_ON_DATE,
)

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def _tariff(
    *,
    tariff_id: str,
    effective_from: date,
    effective_to: date | None,
    value: float,
) -> TsoTariffRecord:
    return TsoTariffRecord(
        tariff_id=tariff_id,
        document_id=f"doc-{tariff_id}",
        country="NL",
        tso="BBL Company",
        market_area="BBL",
        gas_year="2025+",
        point_id="bbl-forward-nl-gb",
        source_point_name="BBL Forward Flow NL to GB",
        direction=TariffDirection.EXIT.value,
        capacity_product=CapacityProduct.ANNUAL.value,
        firmness=Firmness.FIRM.value,
        tariff_value=value,
        currency="GBP",
        unit="GBP/MWh",
        effective_from=datetime.combine(effective_from, datetime.min.time(), UTC),
        effective_to=(
            datetime.combine(effective_to, datetime.min.time(), UTC)
            if effective_to is not None
            else None
        ),
        tariff_status=TariffStatus.FINAL.value,
        source_table="synthetic intraday applicability table",
        source_refs=["test:synthetic-intraday-tariff"],
        manual_review_required=False,
        created_at_utc=NOW,
    )


def _seed_route(session: Session) -> None:
    session.add(
        RouteCandidateRecord(
            route_id="intraday-bbl",
            route_name="TTF -> BBL -> NBP",
            start_point_name="TTF",
            target_point_name="NBP",
            business_model="CROSS_BORDER_TRANSFER",
            route_legs=[
                {
                    "leg_id": "bbl-forward",
                    "country": "NL",
                    "tso": "BBL Company",
                    "market_area": "BBL",
                    "point_name": "BBL Forward Flow NL to GB",
                    "direction": "EXIT",
                    "gas_year": "2025+",
                    "capacity_product": "ANNUAL",
                    "firmness": "FIRM",
                    "available_capacity_mwh_per_day": 1_000.0,
                }
            ],
            required_entry_point_name=None,
            required_exit_point_name=None,
            required_tso_access=[],
            source_systems=["public_route_template"],
            active=True,
            created_at_utc=NOW,
        )
    )


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_explicit_date_selects_covering_intraday_tariff() -> None:
    with _session() as session:
        _seed_route(session)
        session.add_all(
            [
                _tariff(
                    tariff_id="jan",
                    effective_from=date(2026, 1, 1),
                    effective_to=date(2026, 1, 31),
                    value=1.0,
                ),
                _tariff(
                    tariff_id="feb",
                    effective_from=date(2026, 2, 1),
                    effective_to=date(2026, 2, 28),
                    value=2.0,
                ),
            ]
        )
        session.commit()

        routes = _route_economics(
            session,
            NOW,
            tariff_applicability_date=date(2026, 1, 31),
        )

    assert len(routes) == 1
    assert routes[0].total_cost == 1.0
    assert routes[0].missing_inputs == []
    assert TARIFF_APPLICABILITY_NOT_ASSESSED not in routes[0].warnings
    assert routes[0].cost_components[0]["tariff_id"] == "jan"


def test_explicit_date_gap_blocks_intraday_route_without_clock_fallback() -> None:
    with _session() as session:
        _seed_route(session)
        session.add(
            _tariff(
                tariff_id="jan",
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 1, 31),
                value=1.0,
            )
        )
        session.commit()

        routes = _route_economics(
            session,
            NOW,
            tariff_applicability_date=date(2026, 6, 15),
        )

    assert len(routes) == 1
    assert routes[0].total_cost is None
    assert (
        f"{TARIFF_NOT_EFFECTIVE_ON_DATE}:bbl-forward"
        in routes[0].missing_inputs
    )


def test_explicit_date_overlap_blocks_intraday_route() -> None:
    with _session() as session:
        _seed_route(session)
        session.add_all(
            [
                _tariff(
                    tariff_id="overlap-a",
                    effective_from=date(2026, 1, 1),
                    effective_to=date(2026, 1, 31),
                    value=1.0,
                ),
                _tariff(
                    tariff_id="overlap-b",
                    effective_from=date(2026, 1, 15),
                    effective_to=date(2026, 2, 28),
                    value=2.0,
                ),
            ]
        )
        session.commit()

        routes = _route_economics(
            session,
            NOW,
            tariff_applicability_date=date(2026, 1, 20),
        )

    assert len(routes) == 1
    assert routes[0].total_cost is None
    assert (
        f"{TARIFF_APPLICABILITY_AMBIGUOUS}:bbl-forward"
        in routes[0].missing_inputs
    )


def test_without_explicit_date_uses_legacy_selection_and_discloses_not_assessed() -> None:
    """The July valuation instant must not filter an un-declared delivery date."""

    with _session() as session:
        _seed_route(session)
        session.add(
            _tariff(
                tariff_id="jan",
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 1, 31),
                value=1.0,
            )
        )
        session.commit()

        routes = _route_economics(session, NOW)

    assert len(routes) == 1
    # The January row is still selected by the disclosed legacy path; the July
    # scan instant did not become a January-expiry filter or a delivery date.
    assert routes[0].total_cost == 1.0
    assert TARIFF_APPLICABILITY_NOT_ASSESSED in routes[0].warnings
