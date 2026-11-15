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
    LngTerminalTermsRecord,
    MarketObservationRecord,
    RemitUmmRecord,
    RouteCandidateRecord,
    ScreenOrderObservationRecord,
    TraderMandateRecord,
    TradingBookRecord,
    UpstreamResourceContractRecord,
)
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


def _clear(session) -> None:
    ids = [row[0] for row in CONTRACTS]
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

def seed(session, now: datetime) -> dict[str, dict]:
    """Write the demo desk and return each credit line's sizing, for the caller to print."""

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
        for back in range(HISTORY_DAYS, 0, -1):
            front = _month_start(today - timedelta(days=back), 1)
            drift = 0.97 * drift + rng.gauss(0, 0.35)
            price = round(_curve_price(hub, front) + drift - back * 0.003, 3)
            session.add(
                MarketObservationRecord(
                    observation_id=f"demo-{hub}-ma-{back}",
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

    def trade(oid, provider, account, side, hub, currency, price, mwh, start, days, book):
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
                linked_resource_id=None,
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
    # Two fictional outages for the ticker and the map: a large unplanned one and a derate.
    for message_id, asset, zone, technical, unavailable, kind, hours_ago, reason in (
        ("demo-umm-1", "Demo Haldor field", "NBP", 70.0, 52.0, "unplanned", 3,
         "Compressor trip (demo)"),
        ("demo-umm-2", "Demo Kestrel export line", "TTF", 40.0, 9.0, "planned", 30,
         "Valve maintenance (demo)"),
    ):
        start = now - timedelta(hours=hours_ago)
        session.add(RemitUmmRecord(
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
    seed_market_around_the_book(session, now, rng)
    return sizing


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


def seed_market_around_the_book(session, now: datetime, rng: random.Random) -> dict[str, int]:
    """Reference network plus simulated physical history; returns row counts by table."""

    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    reference = seed_reference_bundle(session, now=now)
    counts["reference_points"] = (reference.get("nodes") or {}).get("upserted", 0)
    days = _closed_gas_days(now, HISTORY_DAYS)
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
        for day, start, end in days[-MAP_FLOW_DAYS:]:
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
    first_hour = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=POWER_DAYS)
    for zone, metrics in profiles["power_hourly_mw"].items():
        for metric, by_hour in metrics.items():
            daily = _Wobble(rng, 0.08 if "wind" in metric else 0.03, 0.6)
            level = 1.0
            for hour in range(POWER_DAYS * 24):
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
    session.add_all(rows)
    session.flush()
    return counts


def main() -> int:
    if not simulated_sources_allowed():
        print("refused: simulated sources are not allowed in this environment", file=sys.stderr)
        return 2
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        sizing = seed(session, now)
        session.commit()
    for cpty, row in sizing.items():
        print(
            f"{cpty} {row['name']}: net {row['net']:,} vs limit {row['limit']:,.0f} ({row['why']})"
        )
    print("Demo desk seeded. Set EUROGAS_NEXUS_DEMO_MARKS=true to value it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
