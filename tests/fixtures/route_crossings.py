"""Test tariffs for the market-area legs of the TTF -> BBL -> NBP crossing.

Route pricing now prices a network route along its proven interconnection path
(``domain/route_cost/route_adjacency.py``): TTF -> NBP through BBL is the GTS exit at
Julianadorp/Balgzand, the BBL forward-flow charge, and the National Gas entry at Bacton (BBL).
The tariff register holds only the BBL charge, so a fixture that wants the route *priced* (to
test something downstream of pricing) must also hold the two market-area legs. These are
synthetic test rows, a zero charge each, so the BBL-only totals the tests assert stay the same.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import TsoTariffRecord

#: (tariff id suffix, country, tso, market area, point name, direction)
BBL_CROSSING_LEGS = (
    ("gts-exit-balgzand", "NL", "GTS", "TTF", "Julianadorp (GTS) /Balgzand (BBL)", "EXIT"),
    ("ng-entry-bacton-bbl", "GB", "National Gas TSO", "NBP", "Bacton (BBL)", "ENTRY"),
)


def add_bbl_crossing_tariffs(session: Session) -> None:
    """Clone every BBL forward-flow row into the crossing's two market-area legs (zero charge)."""

    session.flush()
    rows = (
        session.query(TsoTariffRecord)
        .filter(TsoTariffRecord.source_point_name == "BBL Forward Flow NL to GB")
        .all()
    )
    existing = {tariff_id for (tariff_id,) in session.query(TsoTariffRecord.tariff_id).all()}
    for row in rows:
        if "synthetic-bbl-crossing" in str(row.source_refs):
            continue
        for suffix, country, tso, area, point, direction in BBL_CROSSING_LEGS:
            values = {
                column.name: getattr(row, column.name)
                for column in TsoTariffRecord.__table__.columns
            }
            values.update(
                tariff_id=f"{row.tariff_id}-{suffix}",
                country=country,
                tso=tso,
                market_area=area,
                point_id=f"{row.point_id}-{suffix}",
                source_point_name=point,
                direction=direction,
                tariff_value=0.0,
                source_table="synthetic test row: market-area leg of the BBL crossing",
                source_refs=["test:synthetic-bbl-crossing-leg"],
            )
            values.pop("id", None)
            if values["tariff_id"] in existing:
                continue
            existing.add(values["tariff_id"])
            session.add(TsoTariffRecord(**values))
