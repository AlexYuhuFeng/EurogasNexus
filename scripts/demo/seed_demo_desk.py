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
    HedgeApprovalRecord,
    InterestRateObservationRecord,
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
#: Storage keeps six gas years and the current one, so the storage read draws its five-year
#: range from simulated history on the demo desk (CP-04); still marked simulated, and removed
#: per country once real GIE rows cover it (``retire_simulated_series``).
STORAGE_HISTORY_DAYS = 7 * 365
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


#: Every hub the board lists gets a simulated curve and month-ahead history, so the board, the
#: spreads, the answer bar and the reports have a complete demo market. Invented levels: TTF as
#: the reference, the others at plausible (made-up) premiums or discounts to it, NBP in GBP.
#: Marked simulated like every DEMO_Sim row; a provider's closes for a hub always win over these.
#: (hub, currency, base per MWh, winter swing)
DEMO_HUB_CURVES: tuple[tuple[str, str, float, float], ...] = (
    ("TTF", "EUR", 38.0, 2.4),
    ("NBP", "GBP", 33.6, 2.1),
    ("THE", "EUR", 38.7, 2.6),
    ("PEG", "EUR", 38.4, 2.5),
    ("ZTP", "EUR", 37.8, 2.4),
    ("PSV", "EUR", 40.2, 2.2),
    ("CEGH", "EUR", 40.6, 2.7),
    ("PVB", "EUR", 39.5, 1.9),
    ("ETF", "EUR", 38.5, 2.5),
    ("GTF", "EUR", 38.4, 2.5),
)
DEMO_PRICE_HUBS: tuple[tuple[str, str], ...] = tuple((hub, cur) for hub, cur, *_ in DEMO_HUB_CURVES)
_CURVE_SHAPE = {hub: (base, swing) for hub, _, base, swing in DEMO_HUB_CURVES}
ORIGINAL_DEMO_HUBS = frozenset({"TTF", "NBP"})


def _curve_price(hub: str, month: date) -> float:
    """A smooth winter-premium curve; invented, never a market price."""

    base, swing = _CURVE_SHAPE[hub]
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
    from eurogas_nexus.db.models import MarketQuoteRecord

    session.query(MarketQuoteRecord).filter(
        MarketQuoteRecord.source_system == SOURCE
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
    ttf_drift: dict[int, float] = {}
    for hub, currency in DEMO_PRICE_HUBS:
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
        # The hubs added later walk on their own generator, so the original two (and every
        # series drawn after them) are exactly as before.
        # The others follow TTF's walk with a small basis of their own: hubs move together.
        walk = rng if hub in ORIGINAL_DEMO_HUBS else random.Random(f"demo-walk-{hub}")
        drift = basis = 0.0
        for back in range(history_days, 0, -1):
            front = _month_start(today - timedelta(days=back), 1)
            if hub in ORIGINAL_DEMO_HUBS:
                drift = 0.97 * drift + walk.gauss(0, 0.35)
                if hub == "TTF":
                    ttf_drift[back] = drift
            else:
                basis = 0.9 * basis + walk.gauss(0, 0.05)
                drift = ttf_drift.get(back, 0.0) + basis
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
    seed_demo_review_case(session, now)
    session.flush()
    seed_demo_market(session, now, history_days)
    return sizing


#: The one decision case the demo opens for review (fixed id, so a re-seed replaces it).
DEMO_REVIEW_CASE_ID = "case-demo-review-haldor"


def seed_demo_review_case(session, now: datetime) -> int:
    """One case awaiting review, so the reviewer, risk and compliance desks have something
    to open: opened by the demo trader (a reviewer never reviews their own case), about the
    demo book's open Haldor volume. Replaced on a re-seed; never touches other cases.
    Returns rows written."""

    from eurogas_nexus.db.models.decision import DecisionCaseRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event
    from eurogas_nexus.domain.ontology.vocabulary import DecisionCaseStatus

    existing = session.get(DecisionCaseRecord, DEMO_REVIEW_CASE_ID)
    if existing is not None:
        session.delete(existing)
        session.flush()
    gas_day = now.date().isoformat()
    session.add(
        DecisionCaseRecord(
            case_id=DEMO_REVIEW_CASE_ID,
            objective=(
                "Demo: the Haldor supply (Easington) volume is open on the NBP book; cover "
                "tomorrow on NBP day-ahead or from storage?"
            ),
            status=DecisionCaseStatus.UNDER_REVIEW.value,
            created_by="demo.trader",
            created_at_utc=now,
            updated_at_utc=now,
            gas_day=gas_day,
            delivery_product="DA",
            hub_id="NBP",
            portfolio_ref="demo-uk-nbp",
            snapshot_id="",
            decision_due_at_utc=now + timedelta(days=1),
            assumptions_json=[
                {"key": "haldor_dcq_mwh_d", "value": "24000", "source": "MANUAL",
                 "note": "Daily contract quantity of the demo Haldor contract"},
            ],
            alternatives_json=[
                {"alternative_id": "buy-nbp-da", "label": "Buy NBP day-ahead",
                 "description": "Priced at the demo mark (simulated).", "economics_ref": "",
                 "warnings": ["simulated price"]},
                {"alternative_id": "draw-storage", "label": "Draw demo storage",
                 "description": "Within the demo book's storage terms.", "economics_ref": "",
                 "warnings": []},
            ],
            evidence_json=[],
            ai_findings_json=[],
            warnings_json=["Demo case: every figure behind it is simulated."],
        )
    )
    record_audit_event(
        session,
        event_type="decision.case",
        principal="demo-seed",
        action="decision_case_create",
        resource=f"decision_case:{DEMO_REVIEW_CASE_ID}",
        outcome="created",
        severity="info",
        detail=f"demo seed; gas_day={gas_day}; status=UNDER_REVIEW",
        source_system="decision",
        now_utc=now,
    )
    session.flush()
    return 1


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
    storage_history_days: int | None = None,
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

    # The long series (storage, LNG, pipeline landings) reach back seven gas years, so the
    # fundamentals reads draw their five-year ranges from simulated history on the demo desk.
    if storage_history_days is None:
        storage_history_days = (
            STORAGE_HISTORY_DAYS if history_days == HISTORY_DAYS else history_days
        )
    storage_days = (
        _closed_gas_days(now, storage_history_days) if storage_history_days > 0 else []
    )
    recent = {day for day, _, _ in days}

    # Pipeline landings: every registry point every day, so the coverage rule sees full days.
    # The days shared with the other series draw from the shared generator exactly as before;
    # older years from their own, with a slow level drift that eases in beyond that window.
    for point in LANDING_POINTS:
        shape = profiles["landing_points"][point.point_id]["gwh_d_by_month"]
        wobble = _Wobble(rng, 0.025)
        older = _Wobble(random.Random(f"demo-landing-history-{point.point_id}"), 0.025)
        phase = sum(ord(letter) for letter in point.point_id)
        newest = storage_days[-1][0] if storage_days else None
        for day, start, end in storage_days:
            is_recent = day in recent
            age = (newest - day).days if newest else 0
            ramp = 0.0 if is_recent else min(1.0, max(0.0, (age - len(recent)) / 60))
            drift = 1 + ramp * (
                0.08 * math.sin(2 * math.pi * day.toordinal() / (3.1 * 365) + phase)
                + 0.04 * math.sin(2 * math.pi * day.toordinal() / (1.7 * 365) + phase / 3)
            )
            gwh = _shape(shape, day) * (wobble() if is_recent else older()) * drift
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
    # Storage reaches back further than the other series (``STORAGE_HISTORY_DAYS``), and each
    # country's level drifts slowly from year to year, so the five-year range has a width.
    before = len(rows)
    for code, profile in profiles["storage"].items():
        capacity = profile["working_capacity_twh"]
        # The days of the other series draw from the shared generator exactly as before, so
        # nothing else on the demo desk changes; the older years have their own generator.
        fill_noise, flow_noise = _Wobble(rng, 0.004, 0.97), _Wobble(rng, 0.06)
        phase = sum(ord(letter) for letter in code)
        older = random.Random(f"demo-storage-history-{code}")
        old_fill, old_flow = _Wobble(older, 0.004, 0.97), _Wobble(older, 0.06)
        newest = storage_days[-1][0] if storage_days else None
        for day, start, end in storage_days:
            is_recent = day in recent
            fill_draw, flow_draw = (fill_noise, flow_noise) if is_recent else (old_fill, old_flow)
            # Older years drift a few points from year to year (the range gets a width); the
            # drift eases in over 60 days beyond the shared window and is 1 inside it.
            age = (newest - day).days if newest else 0
            ramp = 0.0 if is_recent else min(1.0, max(0.0, (age - len(recent)) / 60))
            drift = 1 + ramp * (
                0.07 * math.sin(2 * math.pi * day.toordinal() / (3.3 * 365) + phase)
                + 0.04 * math.sin(2 * math.pi * day.toordinal() / (1.9 * 365) + phase / 3)
            )
            fill = min(100.0, max(1.0, _shape(profile["fill_pct_by_month"], day) * fill_draw()
                                  * drift))
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
                        _shape(profile["injection_twh_d_by_month"], day) * flow_draw(), 5
                    ),
                    withdrawal_twh_d=round(
                        _shape(profile["withdrawal_twh_d_by_month"], day) * flow_draw(), 5
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
    # ALSI-shaped series reach back as far as storage (the LNG read's five-year range); the
    # days shared with the other series draw from the shared generator exactly as before, older
    # years from their own, with a slow level drift that eases in beyond the shared window.
    for code, name, dataset, profile in lng_series:
        noise = _Wobble(rng, 0.07)
        older = _Wobble(random.Random(f"demo-lng-history-{code}"), 0.07)
        phase = sum(ord(letter) for letter in code)
        series_days = days if profile is None else storage_days
        newest = series_days[-1][0] if series_days else None
        for day, start, end in series_days:
            is_recent = day in recent
            draw = noise if is_recent else older
            age = (newest - day).days if newest else 0
            ramp = 0.0 if is_recent else min(1.0, max(0.0, (age - len(recent)) / 60))
            drift = 1 + ramp * (
                0.12 * math.sin(2 * math.pi * day.toordinal() / (2.7 * 365) + phase)
                + 0.06 * math.sin(2 * math.pi * day.toordinal() / (1.6 * 365) + phase / 3)
            )
            if profile is None:
                send_out = _shape(gb["lng_send_out_twh_d_by_month"], day) * draw()
                stock = dtmi = None
            else:
                send_out = _shape(profile["send_out_twh_d_by_month"], day) * draw() * drift
                stock = round(_shape(profile["inventory_twh_by_month"], day) * draw(), 4)
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
    return _without_stored_fixings(session, kept)


def _without_stored_fixings(session, rows: list) -> list:
    """Drop demo benchmark fixings for a (benchmark, day) any source has already stored.

    ``interest_rate_observations`` is unique on (benchmark_id, value_date) whatever the source,
    so a real BoE SONIA fixing stored by the catch-up made the demo's own row for that day
    fail the whole roll-forward on PostgreSQL, and the demo did not start (2026-11-18).
    """

    fixings = [row for row in rows if isinstance(row, InterestRateObservationRecord)]
    if not fixings:
        return rows
    days = {row.value_date for row in fixings}
    stored = {
        (benchmark, day)
        for benchmark, day in session.query(
            InterestRateObservationRecord.benchmark_id, InterestRateObservationRecord.value_date
        ).filter(InterestRateObservationRecord.value_date.in_(days))
    }
    # A benchmark a real source publishes is retired from the demo series by
    # ``retire_simulated_series``: writing its demo days again only to remove them churns
    # every start, so they are not written.
    real = {
        benchmark
        for (benchmark,) in session.query(InterestRateObservationRecord.benchmark_id)
        .filter(InterestRateObservationRecord.source_system != SOURCE)
        .distinct()
    }
    return [
        row for row in rows
        if not isinstance(row, InterestRateObservationRecord)
        or (
            (row.benchmark_id, row.value_date) not in stored
            and row.benchmark_id not in real
        )
    ]


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
    counts.update(ensure_demo_fixtures(session, now))
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
            storage_history_days=min(max(gap, 0), STORAGE_HISTORY_DAYS),
            map_days=min(max(gap, 0), MAP_FLOW_DAYS),
            power_days=min(power_gap, POWER_DAYS),
            load_reference=False,
            skip_existing=True,
        )
        counts["physical_rows"] = written.get("written", 0)

    counts["curve_rows"] = _roll_curve(session, now)
    counts["month_ahead_rows"] = _roll_month_ahead(session, now, rng)
    session.flush()
    counts.update(seed_demo_market(session, now, _demo_market_gap(session, now)))
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
    real = _real_price_hubs(session)
    for hub, currency in DEMO_PRICE_HUBS:
        if hub in real:
            continue
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


def _last_history(session, hub: str):
    return (
        session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.source_system == SOURCE)
        .filter(MarketObservationRecord.source_reference == "demo:history")
        .filter(MarketObservationRecord.product == f"{hub} month-ahead")
        .order_by(MarketObservationRecord.observed_at_utc.desc())
        .first()
    )


def _ttf_drift_on(session, day: date) -> float:
    """TTF's stored month-ahead drift on ``day`` (0 when none), for a hub that follows it."""

    row = session.get(MarketObservationRecord, f"demo-TTF-ma-{day:%Y%m%d}")
    if row is None:
        return 0.0
    return float(row.price) - _curve_price("TTF", _month_start(day, 1))


def _real_price_hubs(session) -> set[str]:
    """Hubs a provider (anything but the demo) has stored gas prices for."""

    hubs: set[str] = set()
    # DISTINCT over the hub text, not the JSON document: PostgreSQL has no equality operator
    # for ``json``, and the demo would not start on its own store (2026-11-18).
    stated_hub = MarketObservationRecord.metadata_json["hub"].as_string()
    for hub, product in (
        session.query(stated_hub, MarketObservationRecord.product)
        .filter(MarketObservationRecord.source_system != SOURCE)
        .filter(~MarketObservationRecord.source_system.like("%\\_Sim", escape="\\"))
        .distinct()
    ):
        stated = hub or str(product or "").split(" ")[0]
        hubs.add(str(stated).upper())
    return hubs & set(_CURVE_SHAPE)


def _roll_month_ahead(session, now: datetime, rng: random.Random) -> int:
    today = now.date()
    rows = []
    real = _real_price_hubs(session)
    ttf_drift: dict[int, float] = {}
    last_ttf = _last_history(session, "TTF")
    if last_ttf is not None:
        # TTF's level at its last stored day, against which a following hub's basis is kept.
        ttf_drift[-1] = float(last_ttf.price) - _curve_price(
            "TTF", _month_start(_aware(last_ttf.observed_at_utc).date(), 1)
        )
    for hub, currency in DEMO_PRICE_HUBS:
        if hub in real:
            continue  # a provider prices this hub: no simulated series beside it
        last = _last_history(session, hub)
        if last is None:
            # A hub added to the demo market after this store was seeded: its history from
            # the same window a fresh seed writes.
            last_day = today - timedelta(days=HISTORY_DAYS + 1)
            drift = 0.0
        else:
            last_day = _aware(last.observed_at_utc).date()
            drift = float(last.price) - _curve_price(hub, _month_start(last_day, 1))
        walk = rng if hub in ORIGINAL_DEMO_HUBS else random.Random(f"demo-walk-{hub}-{today}")
        basis = 0.0 if last is None else drift - ttf_drift.get(-1, drift)
        for back in range((today - last_day).days - 1, 0, -1):
            day = today - timedelta(days=back)
            front = _month_start(day, 1)
            if hub in ORIGINAL_DEMO_HUBS:
                drift = 0.97 * drift + walk.gauss(0, 0.35)
                if hub == "TTF":
                    ttf_drift[back] = drift
            else:
                basis = 0.9 * basis + walk.gauss(0, 0.05)
                drift = ttf_drift.get(back, _ttf_drift_on(session, day)) + basis
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
    """The two fictional outages: the Norwegian-shelf field out since 75 hours before ``now``
    for six days (so the landings over its days are held), the export line since 30 hours
    before ``now`` for three days."""

    rows = []
    for message_id, asset, zone, technical, unavailable, kind, hours_ago, reason, days in (
        # A Norwegian-shelf field landing in Britain: an asked report about Norwegian outages
        # attributes it (``reports.sections.norwegian_basis``), as it would a real one.
        ("demo-umm-1", "Demo Haldor field, Norwegian shelf", "NBP", 70.0, 52.0, "unplanned", 75,
         "Compressor trip (demo)", 6),
        ("demo-umm-2", "Demo Kestrel export line", "TTF", 40.0, 9.0, "planned", 30,
         "Valve maintenance (demo)", 3),
    ):
        message_id = f"{message_id}{suffix}"
        start = now - timedelta(hours=hours_ago)
        # The unplanned outage runs for days, but its message is news: the operator's
        # latest word on it is three hours old, so the strip shows it and the roll-forward
        # revises it after DEMO_OUTAGE_REVISION.
        published = start if kind == "planned" else now - timedelta(hours=min(hours_ago, 3))
        rows.append(RemitUmmRecord(
            record_id=f"{message_id}:1", message_id=message_id, version=1,
            published_at_utc=published, event_status="active", unavailability_type=kind,
            event_start_utc=start, event_stop_utc=start + timedelta(days=days), asset_name=asset,
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


#: A demo outage is news for six hours after it is published (the situational strip's urgent
#: window, BREAKING_WINDOW_MS in the web client). The demo revises its unplanned outage a little
#: sooner, so a demo opened at any hour shows one live urgent item, marked as demo data.
DEMO_OUTAGE_REVISION = timedelta(hours=5)


def _roll_outages(session, now: datetime) -> int:
    """Keep the fictional outages current.

    When every demo outage has ended (a paused server), the pair is published again from now.
    While the unplanned one runs, a new version of its message is published whenever the
    newest is older than :data:`DEMO_OUTAGE_REVISION`: the same event, its size nudged by one
    mcm/d either way, as an operator's revision would. Only ``DEMO`` messages are touched.
    """

    newest_stop = _newest(
        session, RemitUmmRecord.event_stop_utc, RemitUmmRecord.source_system == "DEMO"
    )
    if newest_stop is None:
        return 0
    if newest_stop <= now:
        rows = _new_rows_only(session, _demo_outages(now, suffix=f"-{now:%Y%m%d}"))
        session.add_all(rows)
        return len(rows)
    latest = (
        session.query(RemitUmmRecord)
        .filter(RemitUmmRecord.source_system == "DEMO")
        .filter(RemitUmmRecord.unavailability_type == "unplanned")
        .order_by(RemitUmmRecord.published_at_utc.desc(), RemitUmmRecord.version.desc())
        .first()
    )
    if latest is None or _aware(latest.event_stop_utc) <= now:
        return 0
    if now - _aware(latest.published_at_utc) < DEMO_OUTAGE_REVISION:
        return 0
    from sqlalchemy import func

    version = (
        session.query(func.max(RemitUmmRecord.version))
        .filter(RemitUmmRecord.message_id == latest.message_id)
        .scalar()
    ) + 1
    unavailable = latest.unavailable_capacity + (1.0 if version % 2 else -1.0)
    session.add(RemitUmmRecord(
        record_id=f"{latest.message_id}:{version}", message_id=latest.message_id,
        version=version, published_at_utc=now, event_status="active",
        unavailability_type=latest.unavailability_type, event_start_utc=latest.event_start_utc,
        event_stop_utc=latest.event_stop_utc, asset_name=latest.asset_name,
        asset_eic=latest.asset_eic, asset_type=latest.asset_type,
        balancing_zone=latest.balancing_zone, direction=latest.direction, unit=latest.unit,
        technical_capacity=latest.technical_capacity,
        available_capacity=latest.technical_capacity - unavailable,
        unavailable_capacity=unavailable, unavailable_mcm_d=unavailable,
        unavailable_gwh_d=round(unavailable * 10.83, 1), reason=latest.reason,
        market_participant=latest.market_participant,
        remarks="Fictional demo message, revised.", source_system="DEMO",
        source_reference="demo:umm", ingested_at_utc=now,
    ))
    return 1


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




# ---------------------------------------------------------------------------
# The demo market: every product of every demo hub (scripts/demo/demo_market.py)
# ---------------------------------------------------------------------------

#: Fixed (dated) quarters, seasons and years are kept as closes for this many recent days; the
#: rolling Q+1/S+1/Cal+1 series carry the long history backtests and z-scores need.
FIXED_PRODUCT_HISTORY_DAYS = 30
#: Board quotes older than this are removed by the roll-forward (only the demo's own).
DEMO_QUOTE_KEEP_DAYS = 3
_BOARD_PROMPT = (("WD", "within_day"), ("DA", "day_ahead"), ("WE", "weekend"),
                 ("BOM", "balance_of_month"))
_BOARD_CURVE = (
    *(f"M+{n}" for n in range(1, 13)),
    *(f"Q+{n}" for n in range(1, 5)),
    "S+1", "S+2", "Cal+1", "Cal+2",
)
_PROMPT_TENOR = {"WD": "within-day", "DA": "day-ahead", "WE": "weekend", "BOM": "bom"}
_BOARD_PRODUCT = {**_PROMPT_TENOR, "M+1": "month-ahead"}


def _load_demo_market():
    import importlib.util

    path = Path(__file__).with_name("demo_market.py")
    spec = importlib.util.spec_from_file_location("demo_market", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("demo_market", module)
    spec.loader.exec_module(module)
    return module


def _native_price(hub: str, price_per_mwh: float) -> float:
    native = _native(hub, price_per_mwh).get("native")
    return float(native["price"]) if native else price_per_mwh


_DELIVERY_CACHE: dict[tuple[str, date], object] = {}


def _delivery(code: str, day: date):
    key = (code, day)
    if key not in _DELIVERY_CACHE:
        _DELIVERY_CACHE[key] = _resolve_delivery(code, day)
    return _DELIVERY_CACHE[key]


def _resolve_delivery(code: str, day: date):
    """The product's delivery on ``day``; ``None`` where it has none (BOM on a month's last day)."""

    from eurogas_nexus.domain.market.products import ProductCodeError, resolve_product

    try:
        period = resolve_product(code, day)
    except ProductCodeError:
        return None
    start = datetime.combine(period.first_gas_day, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(period.last_gas_day + timedelta(days=1), datetime.min.time(),
                           tzinfo=UTC)
    return period, start, end


def _outage_days(session) -> list[tuple[date, date]]:
    """Days covered by the demo's unplanned outages in the NBP zone (the O1 case)."""

    rows = (
        session.query(RemitUmmRecord.event_start_utc, RemitUmmRecord.event_stop_utc)
        .filter(RemitUmmRecord.source_system == "DEMO",
                RemitUmmRecord.unavailability_type == "unplanned",
                RemitUmmRecord.balancing_zone == "NBP")
        .all()
    )
    return [(_aware(start).date(), _aware(stop).date()) for start, stop in rows]


def _month_ahead_history(session, hub: str, since: date) -> dict[date, tuple[float, datetime]]:
    rows = (
        session.query(MarketObservationRecord.price, MarketObservationRecord.observed_at_utc)
        .filter(MarketObservationRecord.source_system == SOURCE,
                MarketObservationRecord.source_reference == "demo:history",
                MarketObservationRecord.product == f"{hub} month-ahead",
                MarketObservationRecord.observed_at_utc
                >= datetime.combine(since, datetime.min.time(), tzinfo=UTC))
        .all()
    )
    return {_aware(observed).date(): (float(price), _aware(observed)) for price, observed in rows}


def _close_row(hub, currency, tenor_key, label, kind, price, observed, start, end, day, case):
    metadata = {"hub": hub, "tenor": tenor_key, "simulated": True, "product_label": label,
                "product_kind": kind, "demo_market": "v1", **_native(hub, price)}
    if case:
        metadata["demo_planted_case"] = case
    return dict(
        observation_id=f"demo-mkt-{hub}-{tenor_key}-{day:%Y%m%d}"[:128],
        market_venue="Demo",
        product=f"{hub} {label}",
        price=round(price, 4),
        unit=f"{currency}/MWh",
        currency=currency,
        period_start_utc=start,
        period_end_utc=end,
        observed_at_utc=observed,
        source_system=SOURCE,
        source_reference="demo:market",
        source_record_id=None,
        freshness="end_of_day",
        quality_score=0.0,
        research_only=True,
        metadata_json=metadata,
    )


def demo_market_rows(session, now: datetime, days: int) -> tuple[list, list]:
    """Closes (history) and board quotes of every demo hub's products for the last ``days``.

    Derived from the stored month-ahead history (``demo:history``); a hub a provider prices
    is skipped, as its month-ahead is. Returns (observation rows, quote rows); quotes only for
    the newest day.
    """

    market_module = _load_demo_market()
    market = market_module.DemoMarket(_curve_price, eur_per_mwh_to_native=_native_price)
    today = now.date()
    since = today - timedelta(days=days + 1)
    real = _real_price_hubs(session)
    outages = _outage_days(session)
    closes: list = []
    quotes: list = []
    ttf_da: dict[date, float] = {}
    ordered = sorted(DEMO_PRICE_HUBS, key=lambda item: item[0] != "TTF")
    for hub, currency in ordered:
        if hub in real:
            continue
        history = _month_ahead_history(session, hub, since)
        if not history:
            continue
        newest = max(history)
        for day, (month_ahead, observed) in sorted(history.items()):
            outage = any(first <= day <= last for first, last in outages)
            prompt = market.prompt(hub, day, month_ahead, ttf_day_ahead=ttf_da.get(day),
                                   outage=outage)
            if hub == "TTF":
                ttf_da[day] = prompt["day-ahead"]
            planted = {
                "day-ahead": "L1-nbp-over-ttf-da" if hub == "NBP"
                and market_module.l1_planted(day) else None,
                "within-day": "W1-ttf-wd-over-da" if hub == "TTF"
                and market_module.w1_planted(day) else None,
            }
            for code, tenor_key in _PROMPT_TENOR.items():
                delivery = _delivery(code, day)
                if delivery is None:
                    continue
                period, start, end = delivery
                closes.append(_close_row(hub, currency, tenor_key, code, period.kind,
                                         prompt[tenor_key], observed, start, end, day,
                                         planted.get(tenor_key)))
            for code, tenor_key in (("Q+1", "q+1"), ("S+1", "s+1"), ("Cal+1", "cal+1")):
                delivery = _delivery(code, day)
                if delivery is None:
                    continue
                period, start, end = delivery
                price = market.strip(hub, day, month_ahead, period.first_gas_day,
                                     period.last_gas_day)
                closes.append(_close_row(hub, currency, tenor_key, code, period.kind, price,
                                         observed, start, end, day, None))
            if (newest - day).days < FIXED_PRODUCT_HISTORY_DAYS:
                for code in ("Q+1", "Q+2", "Q+3", "Q+4", "S+1", "S+2", "Cal+1", "Cal+2"):
                    delivery = _delivery(code, day)
                    if delivery is None:
                        continue
                    period, start, end = delivery
                    price = market.strip(hub, day, month_ahead, period.first_gas_day,
                                         period.last_gas_day)
                    closes.append(_close_row(hub, currency, period.label.lower(), period.label,
                                             period.kind, price, observed, start, end, day,
                                             "T1-cegh-winter-over-summer"
                                             if hub == "CEGH" and period.kind == "season"
                                             else None))
            if day != newest:
                continue
            for code, kind in _BOARD_PROMPT:
                delivery = _delivery(code, day)
                if delivery is None:
                    continue
                period, start, end = delivery
                # Prompt products keep their desk code (the dated window is in the delivery).
                quotes.append(_quote_row(market, hub, currency, code, code, kind,
                                         prompt[_PROMPT_TENOR[code]], start, end, now, day))
            for code in _BOARD_CURVE:
                delivery = _delivery(code, day)
                if delivery is None:
                    continue
                period, start, end = delivery
                price = market.strip(hub, day, month_ahead, period.first_gas_day,
                                     period.last_gas_day)
                quotes.append(_quote_row(market, hub, currency, code, period.label, period.kind,
                                         price, start, end, now, day))
    return closes, quotes


def _quote_row(market, hub, currency, code, label, kind, mid, start, end, now, day):
    from eurogas_nexus.domain.market.units import HUB_NATIVE_PRICE_UNIT

    bid, native_mid, ask = market.quote(hub, mid, kind)
    native_unit = HUB_NATIVE_PRICE_UNIT.get(hub) or f"{currency}/MWh"
    per_mwh = (lambda value: value) if native_unit.endswith("/MWh") else (
        lambda value: value * mid / _native_price(hub, mid)
    )
    observed = now - timedelta(minutes=5)
    return dict(
        quote_id=f"demo-q-{hub}-{label}-{day:%Y%m%d}".replace(" ", "")[:128],
        source_system=SOURCE,
        source_record_id=None,
        venue="Demo",
        instrument_id=f"{hub}:{label}",
        hub=hub,
        # The board and the market context match quotes by tenor key (``day-ahead``,
        # ``month-ahead``); the desk label (DA, Jan-27) travels in the metadata and the
        # instrument id (``TTF:DA``).
        product=_BOARD_PRODUCT.get(code, label),
        delivery_start_utc=start,
        delivery_end_utc=end,
        bid_price=round(per_mwh(bid), 4),
        ask_price=round(per_mwh(ask), 4),
        last_price=round(per_mwh(native_mid), 4),
        bid_quantity_mwh=None,
        ask_quantity_mwh=None,
        currency=currency,
        unit="MWh",
        observed_at_utc=observed,
        received_at_utc=observed,
        source_reference="demo:market",
        freshness="simulated",
        quality_score=0.0,
        simulated=True,
        metadata_json={
            "simulated": True, "demo_market": "v1", "product_label": label,
            "product_kind": kind, "rolling_code": code, "native_unit": native_unit,
            "native_bid": bid, "native_ask": ask, "native_mid": native_mid,
            "tick": market_tick(hub),
        },
    )


def market_tick(hub: str) -> float:
    return _load_demo_market().tick_of(hub)


def _insert_new(session, model, key: str, rows: list[dict]) -> list[dict]:
    from sqlalchemy import insert

    column = getattr(model, key)
    ids = [row[key] for row in rows]
    stored: set = set()
    for offset in range(0, len(ids), 500):
        chunk = ids[offset : offset + 500]
        stored.update(value for (value,) in session.query(column).filter(column.in_(chunk)))
    fresh = [row for row in rows if row[key] not in stored]
    for offset in range(0, len(fresh), 2000):
        session.execute(insert(model), fresh[offset : offset + 2000])
    return fresh


def _demo_market_gap(session, now: datetime) -> int:
    """Days the demo market's closes lag ``now`` (the whole history when it has none)."""

    newest = _newest(session, MarketObservationRecord.observed_at_utc,
                     MarketObservationRecord.source_system == SOURCE,
                     MarketObservationRecord.source_reference == "demo:market")
    if newest is None:
        return HISTORY_DAYS
    return min(HISTORY_DAYS, max(1, (now.date() - newest.date()).days + 1))


def seed_demo_market(session, now: datetime, days: int = HISTORY_DAYS) -> dict[str, int]:
    """Write the demo market (closes and the board) for the last ``days``; keyed, idempotent."""

    from eurogas_nexus.db.models import MarketQuoteRecord

    closes, quotes = demo_market_rows(session, now, days)
    # Some 30 000 rows on a fresh seed: core inserts of the rows not yet stored, not ORM
    # objects (which took longer than generating them).
    closes = _insert_new(session, MarketObservationRecord, "observation_id", closes)
    quotes = _insert_new(session, MarketQuoteRecord, "quote_id", quotes)
    cutoff = now - timedelta(days=DEMO_QUOTE_KEEP_DAYS)
    removed = (
        session.query(MarketQuoteRecord)
        .filter(MarketQuoteRecord.source_system == SOURCE,
                MarketQuoteRecord.source_reference == "demo:market",
                MarketQuoteRecord.observed_at_utc < cutoff)
        .delete(synchronize_session=False)
    )
    return {"market_close_rows": len(closes), "market_quote_rows": len(quotes),
            "market_quotes_removed": removed}


# ---------------------------------------------------------------------------
# Top up the demo fixtures a newer build adds, on a volume an older build seeded
# ---------------------------------------------------------------------------


def _fixture_scopes():
    """The demo reference rows a fresh seed writes and an older volume may lack.

    Each is (model, filter on the demo rows): only rows matching the filter are copied, and
    only when their primary key is absent, so nothing a tester changed or a real source
    stored is touched. Contracts, trades and books are not topped up: a tester may have
    removed them on purpose.
    """

    from eurogas_nexus.db.models.decision import DecisionCaseRecord

    return (
        ("tariffs", TsoTariffRecord,
         lambda model: model.document_id == SIMULATED_TARIFF_DOCUMENT),
        ("review_case", DecisionCaseRecord,
         lambda model: model.case_id == DEMO_REVIEW_CASE_ID),
        ("credit_lines", CreditLineRecord,
         lambda model: model.counterparty_id.in_([row[0] for row in COUNTERPARTIES])),
        ("mandates", TraderMandateRecord,
         lambda model: model.mandate_id.like("DEMO-%")),
        ("routes", RouteCandidateRecord,
         lambda model: model.route_id.like("demo-%")),
    )


def ensure_demo_fixtures(session, now: datetime) -> dict[str, int]:
    """Add the demo reference rows a fresh seed would write and this store lacks; idempotent.

    A volume seeded by an older build kept its rows ("testers' changes kept") but never got
    what a newer seed adds: the simulated BBL tariffs (so "TTF -> NBP net of transport"
    showed its inputs as missing), the case awaiting review, a new credit line. The fresh
    seed is written to a throwaway in-memory store with the same ``now`` and its demo rows
    of those tables are copied where the primary key is absent. Simulated tariffs a published
    row has replaced are retired again straight after. The all-tenor demo market is written
    by the roll-forward itself (``seed_demo_market`` from the start of the history).
    """

    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import Session as OrmSession

    from eurogas_nexus.db.base import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    counts: dict[str, int] = {}
    with OrmSession(engine) as fresh:
        # No history: only the reference rows are wanted from it.
        seed(fresh, now, history_days=0)
        fresh.flush()
        for name, model, demo_rows in _fixture_scopes():
            key = inspect(model).primary_key[0]
            candidates = fresh.query(model).filter(demo_rows(model)).all()
            if not candidates:
                continue
            ids = [getattr(row, key.key) for row in candidates]
            stored = {value for (value,) in session.query(key).filter(key.in_(ids))}
            added = 0
            columns = [column.key for column in inspect(model).column_attrs]
            for row in candidates:
                if getattr(row, key.key) in stored:
                    continue
                session.add(model(**{column: getattr(row, column) for column in columns}))
                added += 1
            if added:
                counts[f"fixture_{name}"] = added
    engine.dispose()
    session.flush()
    if counts.get("fixture_tariffs"):
        retire_simulated_tariffs(session)
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
