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

Usage (local PostgreSQL or SQLite runtime store, migrations already applied):

    RUNTIME_STORE_DATABASE_URL=... python scripts/demo/seed_demo_desk.py

Re-running replaces the demo rows (ids start with ``demo-`` or belong to the demo
counterparties); it touches nothing else.
"""

from __future__ import annotations

import math
import random
import sys
from datetime import UTC, date, datetime, timedelta

from eurogas_nexus.api.positions import gas_year_window
from eurogas_nexus.core.config import simulated_sources_allowed
from eurogas_nexus.db.models import (
    ContractDeliveryRecord,
    CreditLineRecord,
    FxObservationRecord,
    LngTerminalTermsRecord,
    MarketObservationRecord,
    RemitUmmRecord,
    ScreenOrderObservationRecord,
    TraderMandateRecord,
    TradingBookRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.session import get_session_factory
from eurogas_nexus.domain.risk.limits import CounterpartyLeg, CreditLine, credit_exposure

SOURCE = "DEMO_Sim"
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

    # Prices: a full monthly curve for the risk horizon and 45 days of month-ahead history.
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
                    metadata_json={"hub": hub, "tenor": f"{first:%Y-%m}", "simulated": True},
                )
            )
        front = _month_start(today, 1)
        for back in range(45, 0, -1):
            price = round(_curve_price(hub, front) + rng.gauss(0, 0.5) - back * 0.03, 3)
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
                    metadata_json={"hub": hub, "tenor": "month-ahead", "simulated": True},
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
    return sizing


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
