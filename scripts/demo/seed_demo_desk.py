"""Seed a fictional demo trading desk for sales demonstrations and user training.

Everything this writes is invented: the firm (Northwind Gas Trading), its counterparties
(Aldermoor Energy, Nordvik Petroleum, Rhinmark Handel), contracts, trades, deliveries and
LNG terminal terms. No real company appears, so no real firm is ever shown in breach.

Prices are written as simulated (``DEMO_Sim``, ``metadata.simulated = true``). They value
positions, credit and mandates only when the operator also sets
``EUROGAS_NEXUS_DEMO_MARKS=true``, and every such response then warns that its marks are
demo prices (AGENTS.md rule 17). The script refuses to run where simulated sources are not
allowed (trial and release environments).

Credit limits are not typed in: the script values the demo book with the same credit
function the API uses and sizes each limit from that, so on whatever day it runs risk sees
one comfortable line, one on watch and one breach with a stated cause.

A demo "working day" also needs a market around the book: the script loads the shipped NWE
reference network (real ENTSOG reference metadata, ``eurogas_nexus.reference_data``) and
writes 400 gas days of simulated pipeline landings, storage and LNG, a week of simulated
flows at map points, a month of simulated power-system fundamentals (load and generation,
never a power price) and 400 days of simulated month-ahead history. Their shapes come from
``demo_profiles.json`` (monthly or hourly means of public series, see
``build_demo_profiles.py``); every row is ``DEMO_Sim`` with ``metadata.simulated = true``
where the table has metadata.

Usage (local PostgreSQL or SQLite runtime store, migrations already applied):

    RUNTIME_STORE_DATABASE_URL=... python scripts/demo/seed_demo_desk.py

Re-running replaces the demo rows (ids start with ``demo-`` or belong to the demo
counterparties); it touches nothing else.

``--roll-forward`` only appends what a paused server missed (``roll_forward``): the series
end at the current gas day again, and nothing stored, including testers' edits, is
rewritten. ``--now`` overrides the clock for rehearsals and tests.
"""

from __future__ import annotations

import json
import math
import random
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from eurogas_nexus.application.pipeline_supply import LANDING_POINTS
from eurogas_nexus.application.position_inputs import gas_year_window
from eurogas_nexus.core.config import simulated_sources_allowed
from eurogas_nexus.db.models import (
    ContractDeliveryRecord,
    CreditLineRecord,
    FlowObservationRecord,
    FxObservationRecord,
    InterestRateObservationRecord,
    HedgeApprovalRecord,
    LngTerminalTermsRecord,
    MarketObservationRecord,
    RemitUmmRecord,
    RouteCandidateRecord,
    ScreenOrderObservationRecord,
    TraderMandateRecord,
    TradingBookRecord,
    TsoTariffRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.models.lng_positions import LngCargoRecord
from eurogas_nexus.db.models.observation import LngObservationRecord, StorageObservationRecord
from eurogas_nexus.db.models.power import PowerObservationRecord
from eurogas_nexus.db.session import get_session_factory
from eurogas_nexus.domain.market.gas_day import gas_day_start_utc
from eurogas_nexus.domain.risk.limits import CounterpartyLeg, CreditLine, credit_exposure
from eurogas_nexus.reference_data.network_bundle import seed_reference_bundle

SOURCE = "DEMO_Sim"
PROFILES = Path(__file__).with_name("demo_profiles.json")
HISTORY_DAYS = 400  # more than a gas year, so the balance has a seasonal normal
MAP_FLOW_DAYS = 7
POWER_DAYS = 31
STORAGE_NAMES = {
    "BE": "Belgium", "DE": "Germany", "DK": "Denmark", "FR": "France", "NL": "Netherlands",
    "EU": "EU total",
}
HORIZON_MONTHS = 38  # covers the 36-month risk horizon from any day of the month
CREDIT_HORIZON_MONTHS = 36

# Fictional desk: (id, name, point, hub, MWh/d, price, currency, gas year, book, counterparty)
CONTRACTS = (
    (
        "demo-haldor-24",
        "Haldor supply (Easington)",
        "NBP Easington",
        "NBP",
        24_000.0,
        29.50,
        "GBP",
        "open",
        "demo-uk-nbp",
        "NVK",
    ),
    (
        "demo-brae-10",
        "Brae North supply (St Fergus)",
        "NBP St Fergus",
        "NBP",
        10_000.0,
        30.20,
        "GBP",
        "current",
        "demo-uk-nbp",
        "ALD",
    ),
    (
        "demo-kestrel-18",
        "Kestrel supply (TTF)",
        "TTF",
        "TTF",
        18_000.0,
        36.80,
        "EUR",
        "current",
        "demo-nl-ttf",
        "RHM",
    ),
)

# Counterparty: (id, name, legal entity, rating, currency, target utilisation, collateral, why)
COUNTERPARTIES = (
    (
        "ALD",
        "Aldermoor Energy plc",
        "NWG-UK",
        "BBB+",
        "GBP",
        0.55,
        0.0,
        "comfortable: short fixed-term supply, sales netted against it",
    ),
    (
        "NVK",
        "Nordvik Petroleum ASA",
        "NWG-UK",
        "AA-",
        "GBP",
        0.86,
        0.0,
        "on watch: large evergreen supply bought well below the curve",
    ),
    (
        "RHM",
        "Rhinmark Handel GmbH",
        "NWG-NL",
        "BBB",
        "EUR",
        1.12,
        2_000_000.0,
        "breach: the TTF curve rallied after the line was set; a 2m letter of credit is held",
    ),
)


def _month_start(day: date, offset: int) -> date:
    month = day.month - 1 + offset
    return date(day.year + month // 12, month % 12 + 1, 1)


def _curve_price(hub: str, month: date) -> float:
    """A smooth winter-premium curve; invented, never a market price."""

    base, swing = (38.0, 2.4) if hub == "TTF" else (33.6, 2.1)
    season = math.cos((month.month - 1) / 12 * 2 * math.pi)  # +1 in January, -1 in July
    return round(base + swing * season, 3)


def _gas_year_label(kind: str, today: date) -> str:
    current = today.year if today.month >= 10 else today.year - 1
    if kind == "open":
        return f"{current - 1}+"
    return f"{current}/{(current + 1) % 100:02d}"


#: A cross-border position for the demo map and the route pricing: gas bought at TTF and sold
#: at NBP through BBL, the one TTF -> NBP crossing (GTS exit at Balgzand, BBL forward flow,
#: National Gas entry at Bacton). Fictional, like the rest of the desk.
CROSS_BORDER_CONTRACT = "demo-kestrel-uk-6"
CROSS_BORDER_ROUTE = "demo-route-ttf-nbp-bbl"
#: Simulated tariffs for that crossing, one per leg, for a demo without published tariffs.
#: SIMULATOR_ONLY (the lowest status: a published row always wins the selection) and removed
#: by ``retire_simulated_series`` once a published row names the same operator, point and
#: direction. Magnitudes are of the order the published GTS and BBL rows show; not market data.
SIMULATED_TARIFF_DOCUMENT = "demo-simulated-tariffs"
SIMULATED_TARIFFS = (
    ("NL", "GTS", "ITP-00063", "Julianadorp (GTS) /Balgzand (BBL)", "EXIT", 0.56),
    ("GB", "BBL company", "ITP-00207", "Bacton (BBL)", "EXIT", 1.20),
    ("GB", "National Gas TSO", "ITP-00207", "Bacton (BBL)", "ENTRY", 0.12),
)


#: Simulated market LNG vessels, so the vessel layer and its link to terminal send-out can be
#: shown without a licensed feed. ``Kpler_Sim``: the simulated twin of the licensed family, so
#: they follow the same entitlement as real vessels and carry the simulated mark; removed by
#: ``retire_simulated_series`` once a real vessel feed delivers. Names and voyages fictional.
SIMULATED_VESSEL_SOURCE = "Kpler_Sim"
SIMULATED_VESSELS = (
    # id, vessel, load port, (lat, lon), terminal, country, (lat, lon), now (lat, lon), days to ETA
    ("demo-vsl-1", "Demo Aurora", "Sabine Pass", (29.73, -93.87), "Gate Terminal", "NL",
     (51.96, 4.04), (46.9, -14.2), 3),
    ("demo-vsl-2", "Demo Borealis", "Hammerfest", (70.67, 23.68), "Eemshaven", "NL",
     (53.45, 6.83), (62.4, 4.1), 2),
    ("demo-vsl-3", "Demo Cassiopeia", "Ras Laffan", (25.90, 51.55), "Zeebrugge LNG", "BE",
     (51.33, 3.20), (36.1, -9.6), 5),
    ("demo-vsl-4", "Demo Dorado", "Corpus Christi", (27.80, -97.40), "Isle of Grain", "GB",
     (51.44, 0.72), (49.2, -6.9), 1),
    ("demo-vsl-5", "Demo Eridanus", "Bonny", (4.42, 7.15), "Dunkerque LNG", "FR",
     (51.03, 2.21), (43.6, -10.4), 4),
)


def _seed_simulated_vessels(session, now: datetime) -> None:
    for cid, vessel, port, load, terminal, country, dest, here, days in SIMULATED_VESSELS:
        departed = now - timedelta(days=12 - days)
        midway = ((load[0] + here[0]) / 2, (load[1] + here[1]) / 2)
        session.add(
            LngCargoRecord(
                cargo_id=cid,
                vessel_name=vessel,
                vessel_imo=None,
                status="laden",
                load_port=port,
                load_country=None,
                load_lat=load[0],
                load_lon=load[1],
                departed_at_utc=departed,
                destination_terminal=terminal,
                destination_country=country,
                destination_lat=dest[0],
                destination_lon=dest[1],
                eta_utc=now + timedelta(days=days),
                position_lat=here[0],
                position_lon=here[1],
                position_at_utc=now - timedelta(hours=2),
                track=[
                    [load[1], load[0], departed.isoformat()],
                    [midway[1], midway[0], (departed + (now - departed) / 2).isoformat()],
                    [here[1], here[0], (now - timedelta(hours=2)).isoformat()],
                ],
                volume_m3=170_000.0,
                energy_gwh=1_150.0,
                book_id=None,
                source_system=SIMULATED_VESSEL_SOURCE,
                source_reference="demo:simulated-vessel",
                updated_at_utc=now,
            )
        )


def _clear(session) -> None:
    ids = [row[0] for row in CONTRACTS] + [CROSS_BORDER_CONTRACT]
    session.query(LngCargoRecord).filter(
        LngCargoRecord.source_system == SIMULATED_VESSEL_SOURCE
    ).delete(synchronize_session=False)
    session.query(TsoTariffRecord).filter(
        TsoTariffRecord.document_id == SIMULATED_TARIFF_DOCUMENT
    ).delete(synchronize_session=False)
    session.query(ContractDeliveryRecord).filter(
        ContractDeliveryRecord.contract_id.in_(ids)
    ).delete(synchronize_session=False)
    session.query(UpstreamResourceContractRecord).filter(
        UpstreamResourceContractRecord.contract_id.in_(ids)
    ).delete(synchronize_session=False)
    session.query(MarketObservationRecord).filter(
        MarketObservationRecord.source_system == SOURCE
    ).delete(synchronize_session=False)
    session.query(ScreenOrderObservationRecord).filter(
        ScreenOrderObservationRecord.order_observation_id.like("demo-%")
    ).delete(synchronize_session=False)
    session.query(HedgeApprovalRecord).filter(HedgeApprovalRecord.contract_id.in_(ids)).delete(
        synchronize_session=False
    )
    session.query(CreditLineRecord).filter(
        CreditLineRecord.counterparty_id.in_([row[0] for row in COUNTERPARTIES])
    ).delete(synchronize_session=False)
    session.query(TraderMandateRecord).filter(TraderMandateRecord.mandate_id.like("DEMO-%")).delete(
        synchronize_session=False
    )
    session.query(TradingBookRecord).filter(TradingBookRecord.book_id.like("demo-%")).delete(
        synchronize_session=False
    )
    session.query(FxObservationRecord).filter(FxObservationRecord.source_system == SOURCE).delete(
        synchronize_session=False
    )
    session.query(InterestRateObservationRecord).filter(
        InterestRateObservationRecord.source_system == SOURCE
    ).delete(synchronize_session=False)
    session.query(RemitUmmRecord).filter(RemitUmmRecord.source_system == "DEMO").delete(
        synchronize_session=False
    )
    session.query(LngTerminalTermsRecord).filter(
        LngTerminalTermsRecord.terminal_id.like("demo-%")
    ).delete(synchronize_session=False)
    session.query(RouteCandidateRecord).filter(
        RouteCandidateRecord.route_id.like("demo-%")
    ).delete(synchronize_session=False)
    for model in (
        FlowObservationRecord,
        StorageObservationRecord,
        LngObservationRecord,
        PowerObservationRecord,
    ):
        session.query(model).filter(model.source_system == SOURCE).delete(
            synchronize_session=False
        )



def _native(hub: str, price_per_mwh: float) -> dict:
    """The quote as the desk reads it, kept beside the stored per-MWh price.

    A real NBP feed quotes pence per therm, and the imports store it per MWh in GBP with the
    native value in the metadata (``ingestion/commodity_settlements.py``); the demo does the
    same, through the unit authority, so a demo row is shaped like a settlement row.
    """

    from eurogas_nexus.domain.market.units import (
        HUB_NATIVE_PRICE_UNIT,
        PRICE_UNITS,
        convert_price,
    )

    native = HUB_NATIVE_PRICE_UNIT.get(hub)
    if not native or native.endswith("/MWh"):
        return {}
    major = PRICE_UNITS[native][0]
    return {"native": {"price": round(convert_price(price_per_mwh, f"{major}/MWh", native), 4),
                       "unit": native}}

def seed(session, now: datetime, history_days: int = HISTORY_DAYS) -> dict[str, dict]:
    """Write the demo desk and return each credit line's sizing, for the caller to print.

    ``history_days`` shortens the daily history (tests); the demo default is a gas year+.
    """

    rng = random.Random(20261107)
    today = now.date()
    _clear(session)

    for book_id, name, entity, currency in (
        ("demo-uk-nbp", "Demo UK NBP", "NWG-UK", "GBP"),
        ("demo-nl-ttf", "Demo NL TTF", "NWG-NL", "EUR"),
    ):
        session.add(
            TradingBookRecord(
                book_id=book_id,
                name=name,
                legal_entity=entity,
                region="europe",
                business="NW Europe gas (demo)",
                base_currency=currency,
                active=True,
                updated_by="demo-seed",
                updated_at_utc=now,
            )
        )

    # Prices: a full monthly curve for the risk horizon and 400 days of month-ahead history.
    marks: dict[tuple[str, str], float] = {}
    for hub, currency in (("TTF", "EUR"), ("NBP", "GBP")):
        for offset in range(HORIZON_MONTHS):
            first = _month_start(today, offset)
            price = _curve_price(hub, first)
            marks[(hub, f"{first.year:04d}-{first.month:02d}")] = price
            session.add(
                MarketObservationRecord(
                    observation_id=f"demo-{hub}-{first:%Y-%m}",
                    market_venue="Demo",
                    product=f"{hub} {first:%b-%y}",
                    price=price,
                    unit=f"{currency}/MWh",
                    currency=currency,
                    period_start_utc=datetime(first.year, first.month, 1, tzinfo=UTC),
                    period_end_utc=datetime.combine(
                        _month_start(first, 1), datetime.min.time(), tzinfo=UTC
                    ),
                    observed_at_utc=now - timedelta(hours=1),
                    source_system=SOURCE,
                    source_reference="demo:curve",
                    freshness="end_of_day",
                    quality_score=0.0,
                    research_only=True,
                    metadata_json={"hub": hub, "tenor": f"{first:%Y-%m}", "simulated": True,
                                   **_native(hub, price)},
                )
            )
        # A random walk around the seasonal curve; each day's month-ahead is the month after it.
        drift = 0.0
        for back in range(history_days, 0, -1):
            front = _month_start(today - timedelta(days=back), 1)
            drift = 0.97 * drift + rng.gauss(0, 0.35)
            price = round(_curve_price(hub, front) + drift - back * 0.003, 3)
            session.add(
                MarketObservationRecord(
                    observation_id=f"demo-{hub}-ma-{today - timedelta(days=back):%Y%m%d}",
                    market_venue="Demo",
                    product=f"{hub} month-ahead",
                    price=price,
                    unit=f"{currency}/MWh",
                    currency=currency,
                    period_start_utc=datetime(front.year, front.month, 1, tzinfo=UTC),
                    period_end_utc=datetime.combine(
                        _month_start(front, 1), datetime.min.time(), tzinfo=UTC
                    ),
                    observed_at_utc=now - timedelta(days=back),
                    source_system=SOURCE,
                    source_reference="demo:history",
                    freshness="end_of_day",
                    quality_score=0.0,
                    research_only=True,
                    metadata_json={"hub": hub, "tenor": "month-ahead", "simulated": True,
                                   **_native(hub, price)},
                )
            )

    # Demo FX (EUR base), used only with demo marks on; a real ECB fixing always wins.
    for quote, rate in (("GBP", 0.853), ("USD", 1.087)):
        session.add(
            FxObservationRecord(
                observation_id=f"demo-fx-{quote}",
                pair=f"EUR{quote}",
                base_currency="EUR",
                quote_currency=quote,
                rate=rate,
                rate_type="reference",
                value_date=(today - timedelta(days=1)).isoformat(),
                observed_at_utc=now,
                source_system=SOURCE,
                source_reference="demo:fx",
                freshness="daily",
                research_only=True,
            )
        )

    # A daily FX and benchmark-rate history, so a demo price of any day converts at that day's
    # (simulated) rates and a forward month at the derived forward (CP-01); labelled simulated.
    session.add_all(_new_rows_only(session, _demo_rate_rows(now, history_days)))

    horizon_end = _month_start(today, CREDIT_HORIZON_MONTHS) - timedelta(days=1)
    legs_by_counterparty: dict[str, list[CounterpartyLeg]] = {row[0]: [] for row in COUNTERPARTIES}
    for cid, name, point, hub, dcq, price, currency, kind, book, cpty in CONTRACTS:
        label = _gas_year_label(kind, today)
        session.add(
            UpstreamResourceContractRecord(
                contract_id=cid,
                contract_name=name,
                resource_type="PIPELINE_IMPORT",
                delivery_point_name=point,
                gas_year=label,
                delivery_quantity_mwh_per_day=dcq,
                contract_price_gbp_mwh=price,
                contract_price_currency=currency,
                settlement_frequency="monthly",
                upstream_payment_lag_days=20,
                screen_sale_cash_lag_days=1,
                delivery_tolerance_pct=5.0,
                nomination_tolerance_pct=2.0,
                tolerance_risk_allowance_gbp_mwh=None,
                annual_financing_rate_pct=5.0,
                owned_entry_capacity_mwh_per_day=dcq * 1.1,
                owned_exit_capacity_mwh_per_day=None,
                allowed_exit_points=[hub],
                eligible_sale_modes=["LOCAL_MARKET_SALE"],
                notes="Demo contract (fictional).",
                book_id=book,
                created_at_utc=now,
                updated_at_utc=now,
            )
        )
        first, last = gas_year_window(label, horizon_end)
        legs_by_counterparty[cpty].append(
            CounterpartyLeg(
                cid,
                "supply_contract",
                hub,
                currency,
                first,
                last,
                dcq,
                price,
                open_ended=label.endswith("+"),
            )
        )
        # 90 gas days of nominations and allocations; Haldor under-delivers lately.
        for back in range(1, 91):
            day = today - timedelta(days=back)
            nominated = dcq * (1 + rng.uniform(-0.04, 0.04))
            allocated = nominated * (1 + rng.gauss(0, 0.01))
            if cid == "demo-haldor-24" and back <= 7:
                allocated = nominated * 0.88
            session.add(
                ContractDeliveryRecord(
                    contract_id=cid,
                    gas_day=day,
                    nominated_mwh=round(nominated, 1),
                    allocated_mwh=None if back == 1 else round(allocated, 1),
                    tso="Demo TSO",
                    point=point,
                    source_system="DEMO",
                    source_reference="demo:deliveries",
                    updated_at_utc=now,
                )
            )

    # Trades: bilateral sales booked in the ETRM against the counterparty's name, and
    # exchange hedges on the demo trader's own account.
    front = datetime.combine(_month_start(today, 1), datetime.min.time(), tzinfo=UTC).replace(
        hour=5
    )

    def trade(oid, provider, account, side, hub, currency, price, mwh, start, days, book,
              linked=None):
        session.add(
            ScreenOrderObservationRecord(
                order_observation_id=oid,
                provider_id=provider,
                venue="Demo ETRM" if provider == "ETRM" else "Demo exchange",
                account_label=account,
                external_order_id=oid,
                side=side,
                order_type="LIMIT",
                hub=hub,
                product="Month",
                contract_code=f"{hub}-M",
                delivery_start_utc=start,
                delivery_end_utc=start + timedelta(days=days),
                price=price,
                currency=currency,
                unit=f"{currency}/MWh",
                quantity_mwh=mwh,
                filled_quantity_mwh=mwh,
                remaining_quantity_mwh=0,
                status="FILLED",
                observed_at_utc=now - timedelta(days=2),
                source_system=provider,
                source_reference="demo",
                linked_strategy_id=None,
                linked_resource_id=linked,
                research_only=True,
                human_review_required=True,
                book_id=book,
            )
        )
        days_whole = max(1, days)
        return CounterpartyLeg(
            oid,
            "otc_trade",
            hub,
            currency,
            start.date(),
            start.date() + timedelta(days=days_whole - 1),
            (1 if side == "BUY" else -1) * mwh / days_whole,
            price,
        )

    legs_by_counterparty["ALD"].append(
        trade(
            "demo-etrm-ald-1",
            "ETRM",
            "Aldermoor Energy plc",
            "SELL",
            "NBP",
            "GBP",
            33.10,
            6_000 * 60,
            front - timedelta(days=40),
            60,
            "demo-uk-nbp",
        )
    )
    trade(
        "demo-hedge-nbp-1",
        "DEMO_EXCHANGE",
        "demo.trader",
        "SELL",
        "NBP",
        "GBP",
        33.40,
        12_000 * 30,
        front,
        30,
        "demo-uk-nbp",
        linked="demo-haldor-24",  # the hedge of Haldor's front month (hedge-gap demo)
    )
    trade(
        "demo-hedge-ttf-1",
        "DEMO_EXCHANGE",
        "demo.nl.trader",
        "SELL",
        "TTF",
        "EUR",
        38.20,
        8_000 * 31,
        front,
        31,
        "demo-nl-ttf",
    )

    def mark(hub: str, month: str) -> float | None:
        return marks.get((hub, month))

    sizing: dict[str, dict] = {}
    for cpty, name, entity, rating, currency, target, collateral, why in COUNTERPARTIES:
        probe = CreditLine(
            counterparty_id=cpty,
            name=name,
            limit_amount=1.0,
            currency=currency,
            collateral_amount=collateral,
            receivable_days=50,
        )
        exposure = credit_exposure(
            probe,
            legs_by_counterparty[cpty],
            today=today,
            mark=mark,
            fx=lambda source, target_currency: 1.0 if source == target_currency else None,
        )
        net = exposure.net_exposure
        limit = max(500_000.0, round(net / target / 250_000) * 250_000)
        sizing[cpty] = {"name": name, "net": round(net), "limit": limit, "why": why}
        session.add(
            CreditLineRecord(
                counterparty_id=cpty,
                name=name,
                aliases=[name.upper()],
                legal_entity=entity,
                limit_amount=limit,
                currency=currency,
                collateral_amount=collateral,
                rating=rating,
                contract_ids=[
                    leg.reference
                    for leg in legs_by_counterparty[cpty]
                    if leg.kind == "supply_contract"
                ],
                receivable_days=50,
                valid_until=date(today.year + 1, 9, 30),
                updated_by="demo-seed",
                updated_at_utc=now,
            )
        )

    session.add(
        TraderMandateRecord(
            mandate_id="DEMO-UK-1",
            trader="demo.trader",
            display_name="Demo NBP desk trader",
            book_ids=["demo-uk-nbp"],
            hubs=["NBP"],
            max_net_mwh_per_month=1_400_000,
            max_tenor_months=24,
            physical_allowed=True,
            financial_allowed=True,
            min_hedge_ratio_pct=0.0,
            max_hedge_ratio_pct=80.0,
            valid_until=date(today.year + 1, 9, 30),
            updated_by="demo-seed",
            updated_at_utc=now,
        )
    )
    session.add(
        TraderMandateRecord(
            mandate_id="DEMO-NL-1",
            trader="demo.nl.trader",
            display_name="Demo TTF desk trader",
            book_ids=["demo-nl-ttf"],
            hubs=["TTF"],
            max_net_mwh_per_month=600_000,
            max_tenor_months=12,
            physical_allowed=True,
            financial_allowed=True,
            valid_until=date(today.year + 1, 9, 30),
            updated_by="demo-seed",
            updated_at_utc=now,
        )
    )

    for terminal, name, country, hub, regas, entry, fuel, port, sail in (
        ("demo-gate", "Demo Rotterdam terminal", "NL", "TTF", 1.30, 0.45, 0.9, 120_000, 0.0),
        ("demo-zee", "Demo Zeebrugge terminal", "BE", "ZTP", 1.10, 0.40, 1.0, 110_000, 0.5),
        ("demo-grain", "Demo Thames terminal", "GB", "NBP", 1.05, 0.30, 0.7, 95_000, 1.5),
    ):
        session.add(
            LngTerminalTermsRecord(
                terminal_id=terminal,
                name=name,
                country=country,
                hub=hub,
                regas_tariff_per_mwh=regas,
                entry_tariff_per_mwh=entry,
                fuel_retention_pct=fuel,
                port_costs_per_cargo=port,
                other_per_mwh=0.0,
                extra_sailing_days=sail,
                source_note="Demo figures, not published tariffs.",
                updated_by="demo-seed",
                updated_at_utc=now,
            )
        )
    # Risk's approved hedge band for Haldor: 60-80 %. The front month is half covered by the
    # linked NBP hedge and later months not at all, so the demo desk shows a hedge gap
    # (opportunity type G, must-act lane) computed from the book alone.
    session.add(
        HedgeApprovalRecord(
            contract_id="demo-haldor-24",
            min_hedge_ratio_pct=60.0,
            max_hedge_ratio_pct=80.0,
            approval_ref="Demo risk committee RC-07",
            valid_until=date(today.year + 1, 9, 30),
            notes="Demo approval (fictional).",
            updated_by="demo-risk",
            updated_at_utc=now,
        )
    )
    # Two fictional outages for the ticker and the map: a large unplanned one and a derate.
    session.add_all(_demo_outages(now))
    # A local-sale route for the TTF contract, so the scenario can allocate. The NBP contracts
    # land at terminals; a route from there needs TSO entry tariffs, which the demo does not
    # invent, so their volume stays unallocated and the scenario says so.
    session.add(
        RouteCandidateRecord(
            route_id="demo-route-ttf-local",
            route_name="Sell locally at TTF (demo)",
            start_point_name="TTF",
            target_point_name="TTF",
            business_model="VIRTUAL_HUB_SALE",
            route_legs=[],
            required_entry_point_name=None,
            required_exit_point_name=None,
            required_tso_access=[],
            source_systems=["demo_route_template"],
            active=True,
            created_at_utc=now,
        )
    )
    _seed_cross_border_position(session, now, today)
    _seed_simulated_vessels(session, now)
    seed_market_around_the_book(session, now, rng, history_days=history_days)
    return sizing


def _seed_cross_border_position(session, now: datetime, today: date) -> None:
    """A TTF contract whose only sale is NBP through BBL, its route, and simulated tariffs."""

    label = _gas_year_label("current", today)
    session.add(
        UpstreamResourceContractRecord(
            contract_id=CROSS_BORDER_CONTRACT,
            contract_name="Kestrel UK leg (TTF, sold at NBP)",
            resource_type="PIPELINE_IMPORT",
            delivery_point_name="TTF",
            gas_year=label,
            delivery_quantity_mwh_per_day=6_000.0,
            contract_price_gbp_mwh=34.10,
            contract_price_currency="EUR",
            settlement_frequency="monthly",
            upstream_payment_lag_days=20,
            screen_sale_cash_lag_days=1,
            delivery_tolerance_pct=5.0,
            nomination_tolerance_pct=2.0,
            tolerance_risk_allowance_gbp_mwh=None,
            annual_financing_rate_pct=5.0,
            owned_entry_capacity_mwh_per_day=6_600.0,
            owned_exit_capacity_mwh_per_day=6_600.0,
            allowed_exit_points=["NBP"],
            # Bought to be sold at NBP: no local sale at TTF, so the optimiser routes it.
            eligible_sale_modes=["TARGET_MARKET_SALE"],
            notes="Demo contract (fictional): sold at NBP through BBL.",
            # The UK book sells it at NBP; inside its mandate (the NL book is near its own).
            book_id="demo-uk-nbp",
            created_at_utc=now,
            updated_at_utc=now,
        )
    )
    # The route names its crossing (Bacton BBL); the legs come from the market-area graph.
    session.add(
        RouteCandidateRecord(
            route_id=CROSS_BORDER_ROUTE,
            route_name="TTF -> BBL -> NBP (demo)",
            start_point_name="TTF",
            target_point_name="NBP",
            business_model="CROSS_BORDER_TRANSFER",
            route_legs=[
                {
                    "leg_id": "demo-bbl-capacity",
                    "country": "GB",
                    "tso": "BBL company",
                    "point_name": "Bacton (BBL)",
                    "direction": "EXIT",
                    "point_key": "ITP-00207",
                    "available_capacity_mwh_per_day": 6_600.0,
                    "capacity_product": "ANNUAL",
                    "firmness": "FIRM",
                }
            ],
            required_entry_point_name=None,
            required_exit_point_name=None,
            required_tso_access=[],
            source_systems=["demo_route_template"],
            active=True,
            created_at_utc=now,
        )
    )
    start = date(today.year if today.month >= 10 else today.year - 1, 10, 1)
    for country, tso, point, name, direction, value in SIMULATED_TARIFFS:
        session.add(
            TsoTariffRecord(
                tariff_id=f"demo-sim-{tso}-{point}-{direction}".lower().replace(" ", "-"),
                document_id=SIMULATED_TARIFF_DOCUMENT,
                country=country,
                tso=tso,
                market_area="DEMO",
                gas_year=label,
                point_id=point,
                source_point_name=name,
                direction=direction,
                capacity_product="ANNUAL",
                firmness="FIRM",
                tariff_value=value,
                currency="EUR",
                unit="EUR/MWh",
                effective_from=datetime.combine(start, datetime.min.time(), tzinfo=UTC),
                effective_to=None,
                tariff_status="SIMULATOR_ONLY",
                source_table="Simulated demo tariff: not a published tariff",
                source_page=None,
                source_refs=[f"{SOURCE}:simulated-tariff"],
                manual_review_required=True,
                created_at_utc=now,
            )
        )


def retire_simulated_tariffs(session) -> int:
    """Delete simulated demo tariffs whose leg a published row now names; idempotent."""

    published = {
        (row.tso.strip().lower(), row.point_id, row.direction.upper())
        for row in session.query(TsoTariffRecord).filter(
            TsoTariffRecord.document_id != SIMULATED_TARIFF_DOCUMENT
        )
    }
    retired = 0
    for row in session.query(TsoTariffRecord).filter(
        TsoTariffRecord.document_id == SIMULATED_TARIFF_DOCUMENT
    ):
        if (row.tso.strip().lower(), row.point_id, row.direction.upper()) in published:
            session.delete(row)
            retired += 1
    return retired


# ---------------------------------------------------------------------------
# The market around the book: reference network, flows, storage, LNG, power
# ---------------------------------------------------------------------------


def _shape(by_month: list[float | None], day: date) -> float:
    """A monthly-mean shape read on one day: linear between mid-months, wrapping the year."""

    values = [v or 0.0 for v in by_month]
    position = (day.month - 1) + (day.day - 15) / 30.0
    lower = math.floor(position)
    weight = position - lower
    return values[lower % 12] * (1 - weight) + values[(lower + 1) % 12] * weight


class _Wobble:
    """Multiplicative AR(1) noise: day-to-day persistence, as a real series has."""

    def __init__(self, rng: random.Random, sigma: float, persistence: float = 0.8) -> None:
        self.rng, self.sigma, self.persistence, self.state = rng, sigma, persistence, 0.0

    def __call__(self) -> float:
        self.state = self.persistence * self.state + self.rng.gauss(0, self.sigma)
        return max(0.0, 1.0 + self.state)


def _closed_gas_days(now: datetime, count: int) -> list[tuple[date, datetime, datetime]]:
    """The ``count`` newest closed gas days, oldest first: (day, start UTC, end UTC)."""

    open_start = gas_day_start_utc(now)
    open_day = (open_start + timedelta(hours=7)).date()
    days = []
    for back in range(count, 0, -1):
        day = open_day - timedelta(days=back)
        noon = datetime.combine(day, datetime.min.time(), tzinfo=UTC).replace(hour=12)
        start = gas_day_start_utc(noon)
        end = gas_day_start_utc(start + timedelta(hours=30))
        days.append((day, start, end))
    return days


def _received(end: datetime, now: datetime) -> datetime:
    """A closed day's figure arrives a few hours after the day ends, never after ``now``."""

    return min(end + timedelta(hours=3), now)


def _flow_row(point_id, name, operator, direction, gwh, day, start, end, now):
    kwh = round(gwh * 1_000_000, 1)
    return FlowObservationRecord(
        observation_id=f"demo-flow-{point_id}-{operator}-{direction}-{day:%Y%m%d}"[:64],
        point_id=point_id,
        point_name=name,
        direction=direction,
        kind="actual",
        flow_mcm_d=None,
        original_value=kwh,
        original_unit="kWh/d",
        period_start_utc=start,
        period_end_utc=end,
        observed_at_utc=_received(end, now),
        source_system=SOURCE,
        source_reference="demo:flows",
        source_record_id=f"{point_id}-{operator}-{direction}-{day.isoformat()}",
        freshness="daily",
        research_only=True,
        metadata_json={
            "pointKey": point_id,
            "operatorKey": operator,
            "directionKey": direction,
            "unit": "kWh/d",
            "simulated": True,
        },
        normalizer_version="entsog-native-units-v1",
        native_rate_json={
            "unit_text": "kWh/d",
            "normalized_unit": "kWh/day",
            "quantity_kind": "energy",
            "rate_basis": "day",
            "energy_kwh_per_day": str(kwh),
            "volume_mcm_per_day": None,
            "normalizer_version": "entsog-native-units-v1",
        },
    )


def seed_market_around_the_book(
    session,
    now: datetime,
    rng: random.Random,
    *,
    history_days: int = HISTORY_DAYS,
    map_days: int = MAP_FLOW_DAYS,
    power_days: int = POWER_DAYS,
    load_reference: bool = True,
    skip_existing: bool = False,
) -> dict[str, int]:
    """Reference network plus simulated physical history; returns row counts by table.

    The windows end at ``now``. ``skip_existing`` (the roll-forward) writes only rows whose
    key is not stored yet, so a stored day is never rewritten.
    """

    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    if load_reference:
        reference = seed_reference_bundle(session, now=now)
        counts["reference_points"] = (reference.get("nodes") or {}).get("upserted", 0)
    days = _closed_gas_days(now, history_days) if history_days > 0 else []
    rows: list = []

    # Pipeline landings: every registry point every day, so the coverage rule sees full days.
    for point in LANDING_POINTS:
        shape = profiles["landing_points"][point.point_id]["gwh_d_by_month"]
        wobble = _Wobble(rng, 0.025)
        for day, start, end in days:
            gwh = _shape(shape, day) * wobble()
            rows.append(
                _flow_row(point.point_id, point.label, point.operator, "entry", gwh, day, start,
                          end, now)
            )
    counts["landing_flows"] = len(rows)

    # Map points: a week of flows at located points (landing points already have theirs).
    landing_ids = {point.point_id for point in LANDING_POINTS}
    before = len(rows)
    for item in profiles["map_flows"]:
        if item["point_id"] in landing_ids:
            continue
        wobble = _Wobble(rng, 0.04)
        for day, start, end in days[-map_days:] if map_days > 0 else []:
            rows.append(
                _flow_row(item["point_id"], item["name"], item["operator"], item["direction"],
                          item["gwh_d"] * wobble(), day, start, end, now)
            )
    counts["map_flows"] = len(rows) - before

    # Storage (AGSI-shaped, per country and the EU total) and GB storage (National Gas-shaped).
    before = len(rows)
    for code, profile in profiles["storage"].items():
        capacity = profile["working_capacity_twh"]
        fill_noise, flow_noise = _Wobble(rng, 0.004, 0.97), _Wobble(rng, 0.06)
        for day, start, end in days:
            fill = min(100.0, _shape(profile["fill_pct_by_month"], day) * fill_noise())
            rows.append(
                StorageObservationRecord(
                    observation_id=f"demo-agsi-{code}-{day:%Y%m%d}",
                    source_dataset="AGSI",
                    facility_id=code,
                    facility_name=f"{STORAGE_NAMES[code]} (demo)",
                    country=code,
                    inventory_twh=round(capacity * fill / 100, 4),
                    working_capacity_twh=capacity,
                    fill_pct=round(fill, 2),
                    injection_twh_d=round(
                        _shape(profile["injection_twh_d_by_month"], day) * flow_noise(), 5
                    ),
                    withdrawal_twh_d=round(
                        _shape(profile["withdrawal_twh_d_by_month"], day) * flow_noise(), 5
                    ),
                    period_start_utc=start,
                    period_end_utc=end,
                    observed_at_utc=_received(end, now),
                    source_system=SOURCE,
                    source_reference="demo:storage",
                    source_record_id=f"{code}-{day.isoformat()}",
                    freshness="daily",
                    research_only=True,
                    metadata_json={"code": code, "gasDayStart": day.isoformat(), "simulated": True},
                )
            )
    gb = profiles["gb"]
    gb_noise = _Wobble(rng, 0.08)
    for day, start, end in days:
        rows.append(
            StorageObservationRecord(
                observation_id=f"demo-ng-storage-GB-{day:%Y%m%d}",
                source_dataset="NG-SUPPLY",
                facility_id="GB-NTS-STORAGE",
                facility_name="Great Britain storage (demo)",
                country="GB",
                inventory_twh=None,
                working_capacity_twh=None,
                fill_pct=None,
                injection_twh_d=round(
                        _shape(gb["storage_injection_twh_d_by_month"], day) * gb_noise(), 5
                    ),
                withdrawal_twh_d=round(
                        _shape(gb["storage_withdrawal_twh_d_by_month"], day) * gb_noise(), 5
                    ),
                period_start_utc=start,
                period_end_utc=end,
                observed_at_utc=_received(end, now),
                source_system=SOURCE,
                source_reference="demo:storage",
                source_record_id=f"GB-{day.isoformat()}",
                freshness="daily",
                research_only=True,
                metadata_json={"gas_day": day.isoformat(), "simulated": True},
            )
        )
    counts["storage"] = len(rows) - before

    # LNG send-out (ALSI-shaped per country and the EU total; GB National Gas-shaped).
    before = len(rows)
    lng_series = [
        (code, f"{STORAGE_NAMES[code]} LNG (demo)", "ALSI", profile)
        for code, profile in profiles["lng"].items()
    ]
    lng_series.append(("GB", "Great Britain LNG (demo)", "NG-SUPPLY", None))
    for code, name, dataset, profile in lng_series:
        noise = _Wobble(rng, 0.07)
        for day, start, end in days:
            if profile is None:
                send_out = _shape(gb["lng_send_out_twh_d_by_month"], day) * noise()
                stock = dtmi = None
            else:
                send_out = _shape(profile["send_out_twh_d_by_month"], day) * noise()
                stock = round(_shape(profile["inventory_twh_by_month"], day) * noise(), 4)
                dtmi = _shape(profile["dtmi_twh_by_month"], day)
            terminal = "GB-NTS-LNG" if profile is None else code
            rows.append(
                LngObservationRecord(
                    observation_id=f"demo-lng-{terminal}-{day:%Y%m%d}",
                    source_dataset=dataset,
                    terminal_id=terminal,
                    terminal_name=name,
                    country=code,
                    inventory_twh=stock,
                    send_out_twh_d=round(send_out, 5),
                    dtmi_twh=None if dtmi is None else round(dtmi, 4),
                    period_start_utc=start,
                    period_end_utc=end,
                    observed_at_utc=_received(end, now),
                    source_system=SOURCE,
                    source_reference="demo:lng",
                    source_record_id=f"{terminal}-{day.isoformat()}",
                    freshness="daily",
                    research_only=True,
                    metadata_json={"code": code, "gasDayStart": day.isoformat(), "simulated": True},
                )
            )
    counts["lng"] = len(rows) - before

    # Power-system fundamentals by hour: load and generation only. No power price is written:
    # a simulated power price could be read as a market price (AGENTS.md rule 17).
    before = len(rows)
    # Whole UTC days up to last midnight: a half-filled today would read as a drop in burn.
    first_hour = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=power_days)
    for zone, metrics in profiles["power_hourly_mw"].items():
        for metric, by_hour in metrics.items():
            daily = _Wobble(rng, 0.08 if "wind" in metric else 0.03, 0.6)
            level = 1.0
            for hour in range(max(0, power_days) * 24):
                start = first_hour + timedelta(hours=hour)
                if start.hour == 0 or hour == 0:
                    level = daily()
                value = by_hour[start.hour] * level * (1 + rng.gauss(0, 0.01))
                rows.append(
                    PowerObservationRecord(
                        observation_id=f"demo-pw-{zone}-{metric}-{start:%Y%m%d%H}",
                        zone=zone,
                        metric=metric,
                        process_type="A16",
                        period_start_utc=start,
                        period_end_utc=start + timedelta(hours=1),
                        value=round(max(0.0, value), 1),
                        unit="MW",
                        source_system=SOURCE,
                        source_reference="demo:power",
                        published_at_utc=start + timedelta(hours=1),
                        ingested_at_utc=now,
                    )
                )
    counts["power"] = len(rows) - before
    if skip_existing:
        rows = _new_rows_only(session, rows)
        counts["written"] = len(rows)
    session.add_all(rows)
    session.flush()
    return counts


def _new_rows_only(session, rows: list) -> list:
    """Drop the rows whose primary key is already stored (one query per table and chunk)."""

    from sqlalchemy import inspect as sa_inspect

    by_model: dict[type, list] = {}
    for row in rows:
        by_model.setdefault(type(row), []).append(row)
    kept: list = []
    for model, items in by_model.items():
        key = sa_inspect(model).primary_key[0]
        existing: set = set()
        ids = [getattr(item, key.key) for item in items]
        for offset in range(0, len(ids), 500):
            chunk = ids[offset : offset + 500]
            existing.update(value for (value,) in session.query(key).filter(key.in_(chunk)))
        kept.extend(item for item in items if getattr(item, key.key) not in existing)
    return kept


# ---------------------------------------------------------------------------
# Real public data replaces the simulated fundamentals it covers
# ---------------------------------------------------------------------------

#: The simulated physical series, and the column that scopes each against the real rows of
#: the same table: once a real provider has stored a series for a scope (a country's storage,
#: a zone's power, a currency pair), the simulated one of that scope is removed, so no reader
#: mixes the two in one series or sums them twice. ``None``: the whole table is one scope
#: (ENTSOG flows: the simulated landing and map flows stand in for the whole network, and the
#: balance sums landing points across sources).
SIMULATED_SERIES = (
    ("flows", FlowObservationRecord, SOURCE, None),
    ("storage", StorageObservationRecord, SOURCE, "country"),
    ("lng", LngObservationRecord, SOURCE, "country"),
    ("power", PowerObservationRecord, SOURCE, "zone"),
    ("fx", FxObservationRecord, SOURCE, "pair"),
    ("rates", InterestRateObservationRecord, SOURCE, "benchmark_id"),
    # The two fictional outages feed the balance forecast; next to real UMMs they would be
    # counted as if they were market events.
    ("outages", RemitUmmRecord, "DEMO", None),
    # Simulated market vessels step aside once any real cargo row (a vessel feed) arrives.
    ("vessels", LngCargoRecord, SIMULATED_VESSEL_SOURCE, None),
)


def _scope(value) -> str:
    return str(value or "").strip().upper()


def retire_simulated_series(session) -> dict[str, int]:
    """Remove the simulated fundamentals that real provider rows now cover; idempotent.

    Only demo rows are deleted (``DEMO_Sim``, the demo outages); real rows are never read
    for anything but their scope. Demo prices, the demo book, its deliveries and its curve
    stay simulated and labelled so: no public source replaces them. Returns rows removed by
    series (a series with nothing to remove is left out).
    """

    removed: dict[str, int] = {}
    for name, model, demo_source, column_name in SIMULATED_SERIES:
        real = session.query(model).filter(model.source_system != demo_source)
        if column_name is None:
            if real.first() is None:
                continue
            count = session.query(model).filter(model.source_system == demo_source).delete(
                synchronize_session=False
            )
        else:
            column = getattr(model, column_name)
            covered = {_scope(value) for (value,) in real.with_entities(column).distinct()}
            if not covered:
                continue
            demo_scopes = [
                value
                for (value,) in session.query(column)
                .filter(model.source_system == demo_source)
                .distinct()
                if _scope(value) in covered
            ]
            count = 0
            if demo_scopes:
                count = (
                    session.query(model)
                    .filter(model.source_system == demo_source, column.in_(demo_scopes))
                    .delete(synchronize_session=False)
                )
        if count:
            removed[name] = count
    tariffs = retire_simulated_tariffs(session)
    if tariffs:
        removed["tariffs"] = tariffs
    session.flush()
    return removed


# ---------------------------------------------------------------------------
# Roll-forward: keep the demo desk current after the server was paused
# ---------------------------------------------------------------------------


def _gas_day_of(start: datetime) -> date:
    """The gas day a stored period start belongs to (05:00/04:00 UTC start)."""

    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    return (start + timedelta(hours=7)).date()


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def roll_forward(session, now: datetime) -> dict[str, int]:
    """Extend the simulated demo series so they end at ``now`` again; idempotent.

    After the server was paused for days or weeks the demo history ends in the past, the
    curve ages out of the quote lookback and Today looks stale. This appends what is missing
    and nothing else:

    * physical series (flows, storage, LNG, power): the missing gas days and hours, keyed by
      date, so a stored day is never rewritten (``skip_existing``);
    * month-ahead history: the missing days, continuing the random walk from the last price;
    * the forward curve: a new end-of-day snapshot of the same invented seasonal curve when
      the newest is older than a day (the newest snapshot wins, as with a real settlement);
    * demo FX: a new daily fixing row when the newest is older than a day;
    * deliveries of the demo contracts that still exist: the missing gas days, and the
      allocation of a day that was still pending;
    * the two fictional outages: published again from ``now`` once both have ended.

    Contracts, trades, credit lines, mandates, books and terminal terms - what testers edit -
    are not touched, and nothing outside the demo sources is read or written. A store that
    was never seeded is left alone (``{"seeded": 0}``).
    """

    from sqlalchemy import func

    counts: dict[str, int] = {}
    today = now.date()
    if session.get(TradingBookRecord, "demo-uk-nbp") is None:
        return {"seeded": 0}
    # The newest simulated gas day of the daily series that are still simulated (real data
    # may have replaced some, see retire_simulated_series); none left: nothing to extend.
    last_flow = max(
        (
            _aware(value)
            for value in (
                session.query(func.max(model.period_start_utc))
                .filter(model.source_system == SOURCE)
                .scalar()
                for model in (FlowObservationRecord, StorageObservationRecord,
                              LngObservationRecord)
            )
            if value is not None
        ),
        default=None,
    )
    rng = random.Random(today.toordinal())
    newest_closed = _closed_gas_days(now, 1)[0][0]
    gap = 0 if last_flow is None else (newest_closed - _gas_day_of(last_flow)).days
    last_power = (
        session.query(func.max(PowerObservationRecord.period_start_utc))
        .filter(PowerObservationRecord.source_system == SOURCE)
        .scalar()
    )
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    power_gap = (
        0  # replaced by real power everywhere (or never seeded): nothing to extend
        if last_power is None
        else max(0, (midnight - (_aware(last_power) + timedelta(hours=1))).days + 1)
    )
    if gap > 0 or power_gap > 0:
        written = seed_market_around_the_book(
            session,
            now,
            rng,
            history_days=min(max(gap, 0), HISTORY_DAYS),
            map_days=min(max(gap, 0), MAP_FLOW_DAYS),
            power_days=min(power_gap, POWER_DAYS),
            load_reference=False,
            skip_existing=True,
        )
        counts["physical_rows"] = written.get("written", 0)

    counts["curve_rows"] = _roll_curve(session, now)
    counts["month_ahead_rows"] = _roll_month_ahead(session, now, rng)
    counts["fx_rows"] = _roll_fx(session, now)
    rate_rows = _new_rows_only(session, _demo_rate_rows(now, 14))
    session.add_all(rate_rows)
    counts["rate_rows"] = len(rate_rows)
    counts["delivery_rows"] = _roll_deliveries(session, now, rng)
    counts["outage_rows"] = _roll_outages(session, now)
    counts["vessel_rows"] = _roll_vessels(session, now)
    session.flush()
    # What a real source covers stays real: the rows just appended for such a scope go again.
    for name, rows in retire_simulated_series(session).items():
        counts[f"replaced_by_real_{name}"] = rows
    return counts


def _newest(session, column, *filters):
    from sqlalchemy import func

    value = session.query(func.max(column)).filter(*filters).scalar()
    return None if value is None else _aware(value)


def _roll_curve(session, now: datetime) -> int:
    newest = _newest(
        session,
        MarketObservationRecord.observed_at_utc,
        MarketObservationRecord.source_system == SOURCE,
        MarketObservationRecord.source_reference == "demo:curve",
    )
    if newest is not None and now - newest < timedelta(hours=20):
        return 0
    today = now.date()
    rows = []
    for hub, currency in (("TTF", "EUR"), ("NBP", "GBP")):
        for offset in range(HORIZON_MONTHS):
            first = _month_start(today, offset)
            price = _curve_price(hub, first)
            rows.append(
                MarketObservationRecord(
                    observation_id=f"demo-{hub}-{first:%Y-%m}-c{today:%Y%m%d}",
                    market_venue="Demo",
                    product=f"{hub} {first:%b-%y}",
                    price=price,
                    unit=f"{currency}/MWh",
                    currency=currency,
                    period_start_utc=datetime(first.year, first.month, 1, tzinfo=UTC),
                    period_end_utc=datetime.combine(
                        _month_start(first, 1), datetime.min.time(), tzinfo=UTC
                    ),
                    observed_at_utc=now - timedelta(hours=1),
                    source_system=SOURCE,
                    source_reference="demo:curve",
                    freshness="end_of_day",
                    quality_score=0.0,
                    research_only=True,
                    metadata_json={"hub": hub, "tenor": f"{first:%Y-%m}", "simulated": True,
                                   **_native(hub, price)},
                )
            )
    rows = _new_rows_only(session, rows)
    session.add_all(rows)
    return len(rows)


def _roll_month_ahead(session, now: datetime, rng: random.Random) -> int:
    today = now.date()
    rows = []
    for hub, currency in (("TTF", "EUR"), ("NBP", "GBP")):
        last = (
            session.query(MarketObservationRecord)
            .filter(MarketObservationRecord.source_system == SOURCE)
            .filter(MarketObservationRecord.source_reference == "demo:history")
            .filter(MarketObservationRecord.product == f"{hub} month-ahead")
            .order_by(MarketObservationRecord.observed_at_utc.desc())
            .first()
        )
        if last is None:
            continue
        last_day = _aware(last.observed_at_utc).date()
        last_front = _month_start(last_day, 1)
        drift = float(last.price) - _curve_price(hub, last_front)
        for back in range((today - last_day).days - 1, 0, -1):
            day = today - timedelta(days=back)
            front = _month_start(day, 1)
            drift = 0.97 * drift + rng.gauss(0, 0.35)
            price = round(_curve_price(hub, front) + drift, 3)
            rows.append(
                MarketObservationRecord(
                    observation_id=f"demo-{hub}-ma-{day:%Y%m%d}",
                    market_venue="Demo",
                    product=f"{hub} month-ahead",
                    price=price,
                    unit=f"{currency}/MWh",
                    currency=currency,
                    period_start_utc=datetime(front.year, front.month, 1, tzinfo=UTC),
                    period_end_utc=datetime.combine(
                        _month_start(front, 1), datetime.min.time(), tzinfo=UTC
                    ),
                    observed_at_utc=now - timedelta(days=back),
                    source_system=SOURCE,
                    source_reference="demo:history",
                    freshness="end_of_day",
                    quality_score=0.0,
                    research_only=True,
                    metadata_json={"hub": hub, "tenor": "month-ahead", "simulated": True,
                                   **_native(hub, price)},
                )
            )
    rows = _new_rows_only(session, rows)
    session.add_all(rows)
    return len(rows)


def _roll_fx(session, now: datetime) -> int:
    newest = _newest(
        session,
        FxObservationRecord.observed_at_utc,
        FxObservationRecord.source_system == SOURCE,
    )
    if newest is not None and now - newest < timedelta(hours=20):
        return 0
    today = now.date()
    rows = [
        FxObservationRecord(
            observation_id=f"demo-fx-{quote}-{today:%Y%m%d}",
            pair=f"EUR{quote}",
            base_currency="EUR",
            quote_currency=quote,
            rate=rate,
            rate_type="reference",
            value_date=(today - timedelta(days=1)).isoformat(),
            observed_at_utc=now,
            source_system=SOURCE,
            source_reference="demo:fx",
            freshness="daily",
            research_only=True,
        )
        for quote, rate in (("GBP", 0.853), ("USD", 1.087))
    ]
    rows = _new_rows_only(session, rows)
    session.add_all(rows)
    return len(rows)


#: Demo EUR reference rates and overnight benchmark fixings (simulated, flat): the same
#: figures the single demo FX row has always used, and benchmark levels of the right order.
DEMO_EUR_RATES = (("GBP", 0.853), ("USD", 1.087))
DEMO_BENCHMARKS = (("SONIA", "GBP", 3.75, "ACT/365F"), ("ESTR", "EUR", 1.90, "ACT/360"),
                   ("SOFR", "USD", 4.30, "ACT/360"))


def _demo_rate_rows(now: datetime, days: int) -> list:
    """Business-day demo FX reference rates and benchmark fixings for the last ``days`` days.

    Keyed by date, so a re-run adds only what is missing (``_new_rows_only``). Real ECB, BoE,
    ECB €STR or NY Fed rows retire them by pair or benchmark (``retire_simulated_series``).
    """

    rows: list = []
    today = now.date()
    for back in range(days, 0, -1):
        day = today - timedelta(days=back)
        if day.weekday() >= 5:
            continue
        stamp = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=15)
        for quote, rate in DEMO_EUR_RATES:
            rows.append(
                FxObservationRecord(
                    observation_id=f"demo-fx-h-{quote}-{day:%Y%m%d}",
                    pair=f"EUR{quote}",
                    base_currency="EUR",
                    quote_currency=quote,
                    rate=rate,
                    rate_type="reference",
                    value_date=day.isoformat(),
                    observed_at_utc=stamp,
                    source_system=SOURCE,
                    source_reference="demo:fx-history",
                    freshness="daily",
                    research_only=True,
                )
            )
        for benchmark, currency, rate_pct, day_count in DEMO_BENCHMARKS:
            rows.append(
                InterestRateObservationRecord(
                    observation_id=f"demo-{benchmark.lower()}-{day.isoformat()}",
                    benchmark_id=benchmark,
                    currency=currency,
                    value_date=day,
                    rate_pct=rate_pct,
                    day_count=day_count,
                    source_system=SOURCE,
                    source_reference="demo:rates",
                    ingested_at_utc=stamp,
                )
            )
    return rows


def _demo_outages(now: datetime, suffix: str = "") -> list:
    """The two fictional outages, starting 3 and 30 hours before ``now``, lasting 3 days."""

    rows = []
    for message_id, asset, zone, technical, unavailable, kind, hours_ago, reason in (
        ("demo-umm-1", "Demo Haldor field", "NBP", 70.0, 52.0, "unplanned", 3,
         "Compressor trip (demo)"),
        ("demo-umm-2", "Demo Kestrel export line", "TTF", 40.0, 9.0, "planned", 30,
         "Valve maintenance (demo)"),
    ):
        message_id = f"{message_id}{suffix}"
        start = now - timedelta(hours=hours_ago)
        rows.append(RemitUmmRecord(
            record_id=f"{message_id}:1", message_id=message_id, version=1,
            published_at_utc=start, event_status="active", unavailability_type=kind,
            event_start_utc=start, event_stop_utc=start + timedelta(days=3), asset_name=asset,
            asset_eic=f"DEMO-{message_id}", asset_type="production", balancing_zone=zone,
            direction="entry", unit="mcm/d", technical_capacity=technical,
            available_capacity=technical - unavailable, unavailable_capacity=unavailable,
            unavailable_mcm_d=unavailable, unavailable_gwh_d=round(unavailable * 10.83, 1),
            reason=reason, market_participant="Demo operator", remarks="Fictional demo message.",
            source_system="DEMO", source_reference="demo:umm", ingested_at_utc=now,
        ))
    return rows


def _roll_vessels(session, now: datetime) -> int:
    """Sail the simulated vessels again from ``now`` once any of them has arrived."""

    rows = session.query(LngCargoRecord).filter(
        LngCargoRecord.source_system == SIMULATED_VESSEL_SOURCE
    )
    if not rows.count():
        return 0  # none seeded, or retired by a real feed
    if all((row.eta_utc and _aware(row.eta_utc) > now) for row in rows):
        return 0
    rows.delete(synchronize_session=False)
    _seed_simulated_vessels(session, now)
    return len(SIMULATED_VESSELS)


def _roll_outages(session, now: datetime) -> int:
    """When every demo outage has ended (a paused server), publish the pair again from now."""

    newest_stop = _newest(
        session, RemitUmmRecord.event_stop_utc, RemitUmmRecord.source_system == "DEMO"
    )
    if newest_stop is None or newest_stop > now:
        return 0
    rows = _new_rows_only(session, _demo_outages(now, suffix=f"-{now:%Y%m%d}"))
    session.add_all(rows)
    return len(rows)


def _roll_deliveries(session, now: datetime, rng: random.Random) -> int:
    from sqlalchemy import func

    today = now.date()
    written = 0
    for cid, _name, point, _hub, dcq, *_rest in CONTRACTS:
        if session.get(UpstreamResourceContractRecord, cid) is None:
            continue  # a tester removed it: leave it removed
        last = (
            session.query(func.max(ContractDeliveryRecord.gas_day))
            .filter(ContractDeliveryRecord.contract_id == cid)
            .scalar()
        )
        if last is None:
            continue
        # A day whose allocation was still pending gets it now, as a TSO allocation arrives.
        for row in (
            session.query(ContractDeliveryRecord)
            .filter(ContractDeliveryRecord.contract_id == cid)
            .filter(ContractDeliveryRecord.source_system == "DEMO")
            .filter(ContractDeliveryRecord.allocated_mwh.is_(None))
            .filter(ContractDeliveryRecord.gas_day < today - timedelta(days=1))
        ):
            row.allocated_mwh = round((row.nominated_mwh or dcq) * (1 + rng.gauss(0, 0.01)), 1)
            row.updated_at_utc = now
        for back in range((today - last).days - 1, 0, -1):
            day = today - timedelta(days=back)
            nominated = dcq * (1 + rng.uniform(-0.04, 0.04))
            allocated = nominated * (1 + rng.gauss(0, 0.01))
            if cid == "demo-haldor-24" and back <= 7:
                allocated = nominated * 0.88
            session.add(
                ContractDeliveryRecord(
                    contract_id=cid,
                    gas_day=day,
                    nominated_mwh=round(nominated, 1),
                    allocated_mwh=None if back == 1 else round(allocated, 1),
                    tso="Demo TSO",
                    point=point,
                    source_system="DEMO",
                    source_reference="demo:deliveries",
                    updated_at_utc=now,
                )
            )
            written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    import argparse

    if not simulated_sources_allowed():
        print("refused: simulated sources are not allowed in this environment", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--roll-forward",
        action="store_true",
        help="only extend the simulated series to now (keeps every stored row and edit)",
    )
    parser.add_argument(
        "--retire-simulated",
        action="store_true",
        help="only remove the simulated fundamentals that real public data now covers",
    )
    parser.add_argument("--now", help="clock override, ISO 8601 (tests and rehearsals)")
    args = parser.parse_args(argv)
    if args.retire_simulated:
        with get_session_factory()() as session:
            removed = retire_simulated_series(session)
            session.commit()
        print(json.dumps({"ok": True, "sources": {
            name: {"records": rows} for name, rows in removed.items()
        }, "removed": removed}, sort_keys=True))
        return 0
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    if args.roll_forward:
        with get_session_factory()() as session:
            counts = roll_forward(session, now)
            session.commit()
        print("Demo desk rolled forward: " + json.dumps(counts, sort_keys=True))
        return 0
    with get_session_factory()() as session:
        sizing = seed(session, now)
        removed = retire_simulated_series(session)
        session.commit()
    if removed:
        print("Simulated series replaced by stored real data: " + json.dumps(removed))
    for cpty, row in sizing.items():
        print(
            f"{cpty} {row['name']}: net {row['net']:,} vs limit {row['limit']:,.0f} ({row['why']})"
        )
    print("Demo desk seeded. Set EUROGAS_NEXUS_DEMO_MARKS=true to value it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
