"""Option smile series reach training datasets: entitled sources only, precedence, M1 roll."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.routes.public.research_data import _option_evidence
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import OptionSettlementRecord
from eurogas_nexus.domain.dataops.registry import source_definitions
from eurogas_nexus.domain.market.options import black76_price
from eurogas_nexus.domain.research.temporal import ObservationKind
from eurogas_nexus.ingestion.option_settlements import parse_option_settlements
from eurogas_nexus.ingestion.simulated_option_settlements import (
    generate_simulated_option_settlements,
)

FIRST, LAST = date(2026, 11, 16), date(2026, 11, 27)


def _exchange_file(trade: date) -> str:
    """ICE Endex Dec-26 (expires 26 Nov) and Jan-27 options at a flat 50 % volatility."""

    lines = ["trade_date,hub,contract,strike,option_type,settlement,underlying"]
    for label, expiry in (("Dec-26", date(2026, 11, 26)), ("Jan-27", date(2026, 12, 25))):
        tenor = (expiry - trade).days / 365.0
        if tenor <= 0:
            continue
        for step in range(-16, 17):
            strike = 31.0 + step * 0.5
            for option_type in ("C", "P"):
                price = black76_price(option_type, 31.0, strike, 0.5, tenor)
                lines.append(f"{trade},TTF,{label},{strike},{option_type},{price:.6f},31.0")
    return "\n".join(lines) + "\n"


def _seed(session: Session) -> None:
    received = datetime(2026, 11, 28, 7, tzinfo=UTC)
    for row in generate_simulated_option_settlements(FIRST, LAST, received_at_utc=received).rows:
        session.add(OptionSettlementRecord(**row))
    for trade in (date(2026, 11, 24), date(2026, 11, 26)):
        for row in parse_option_settlements(
            _exchange_file(trade),
            source_system="ICE_ENDEX",
            source_reference=f"ice:{trade}",
            received_at_utc=received,
        ).rows:
            session.add(OptionSettlementRecord(**row))
    session.commit()


def test_front_month_series_with_precedence_and_roll(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'o.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        definitions = {d.provider.casefold(): d for d in source_definitions()}
        records, sources = _option_evidence(
            session,
            {"options.atm_iv.TTF.M1", "options.rr25.TTF.M1", "storage.inventory_twh.DE"},
            definitions,
            history_start=datetime(2026, 11, 1, tzinfo=UTC),
            end=datetime(2026, 12, 1, tzinfo=UTC),
            requested_entity_ids=set(),
        )
    atm = {r.observed_at.date(): r for r in records if r.series_id == "options.atm_iv.TTF.M1"}
    # One value per business day; weekends absent, nothing filled.
    assert sorted(atm) == [d for d in (FIRST + timedelta(n) for n in range(12)) if d.weekday() < 5]
    # Exchange days use the exchange (flat 50 %), every other day the simulator.
    assert abs(atm[date(2026, 11, 24)].value - 50.0) < 1e-3
    assert atm[date(2026, 11, 24)].observation_kind is ObservationKind.ACTUAL
    assert atm[date(2026, 11, 23)].observation_kind is ObservationKind.SIMULATED
    # On 26 Nov Dec-26 expires, so M1 is Jan-27 (still the exchange's 50 %).
    assert abs(atm[date(2026, 11, 26)].value - 50.0) < 1e-3
    assert atm[date(2026, 11, 24)].observed_at == datetime(2026, 11, 24, 18, tzinfo=UTC)
    assert atm[date(2026, 11, 24)].available_at == datetime(2026, 11, 28, 7, tzinfo=UTC)
    assert {r.series_id for r in records} == {"options.atm_iv.TTF.M1", "options.rr25.TTF.M1"}
    assert sources == {"src-ice-endex", "src-ice-endex-sim"}


def test_unauthorised_sources_never_enter(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'o.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        only_sim = {
            d.provider.casefold(): d for d in source_definitions() if d.provider == "ICE_ENDEX_Sim"
        }
        records, sources = _option_evidence(
            session,
            {"options.atm_iv.TTF.M1"},
            only_sim,
            history_start=datetime(2026, 11, 1, tzinfo=UTC),
            end=datetime(2026, 12, 1, tzinfo=UTC),
            requested_entity_ids=set(),
        )
    assert records and sources == {"src-ice-endex-sim"}
    assert all(r.observation_kind is ObservationKind.SIMULATED for r in records)
