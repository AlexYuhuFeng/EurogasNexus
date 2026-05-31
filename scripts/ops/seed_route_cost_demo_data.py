"""Seed public/demo route-cost and glossary data into the configured runtime DB.

This script is for local demonstrations only. It does not call external APIs,
does not run migrations, and does not print database secrets.
"""

from __future__ import annotations

from datetime import UTC, datetime

from eurogas_nexus.db.models import (
    GlossaryTermRecord,
    LiveMarketMarkRecord,
    RouteCandidateRecord,
    TsoTariffRecord,
)
from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url
from eurogas_nexus.domain.glossary import baseline_glossary_terms
from eurogas_nexus.domain.route_cost.uk_demo_data import demo_uk_capacity_tariffs


def main() -> int:
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2

    print(f"Runtime DB: {redact_database_url(database_url)}")
    now = datetime.now(UTC)
    session_factory = get_session_factory(database_url=database_url)
    with session_factory() as session:
        for tariff in demo_uk_capacity_tariffs():
            session.merge(
                TsoTariffRecord(
                    tariff_id=tariff.tariff_id,
                    document_id=tariff.document_id,
                    country=tariff.country,
                    tso=tariff.tso,
                    market_area=tariff.market_area,
                    gas_year=tariff.gas_year,
                    point_id=tariff.point_id,
                    source_point_name=tariff.source_point_name,
                    direction=tariff.direction.value,
                    capacity_product=tariff.capacity_product.value,
                    firmness=tariff.firmness.value,
                    tariff_value=tariff.tariff_value,
                    currency=tariff.currency,
                    unit=tariff.unit,
                    effective_from=datetime.combine(
                        tariff.effective_from,
                        datetime.min.time(),
                        UTC,
                    ),
                    effective_to=(
                        datetime.combine(tariff.effective_to, datetime.min.time(), UTC)
                        if tariff.effective_to
                        else None
                    ),
                    tariff_status=tariff.tariff_status.value,
                    source_table=tariff.source_table,
                    source_page=tariff.source_page,
                    source_refs=tariff.source_refs,
                    manual_review_required=tariff.manual_review_required,
                    created_at_utc=now,
                )
            )
        for record in _route_candidates(now):
            session.merge(record)
        session.merge(
            LiveMarketMarkRecord(
                mark_id="demo-ice-ocm-nbp-within-day",
                venue="ICE OCM",
                hub="NBP",
                product="Within-day",
                bid_gbp_mwh=28.2,
                ask_gbp_mwh=28.4,
                last_gbp_mwh=28.3,
                mark_time_utc=now,
                source_system="demo-operator-mark",
                source_reference="operator-entered demo mark",
                created_at_utc=now,
            )
        )
        for term in baseline_glossary_terms():
            session.merge(
                GlossaryTermRecord(
                    term_id=term.term_id,
                    term=term.term,
                    category=term.category,
                    definition_en=term.definition_en,
                    definition_zh_cn=term.definition_zh_cn,
                    aliases=term.aliases,
                    related_terms=term.related_terms,
                    source_refs=term.source_refs,
                    active=True,
                    created_at_utc=now,
                    updated_at_utc=now,
                )
            )
        session.commit()

    print("Seeded demo route-cost tariffs, route candidates, live mark, and glossary terms.")
    return 0


def _route_candidates(now: datetime) -> list[RouteCandidateRecord]:
    return [
        RouteCandidateRecord(
            route_id="uk-easington-nbp",
            route_name="Easington beach delivery -> NBP virtual sale",
            start_point_name="Easington Beach Terminal",
            target_point_name="NBP",
            business_model="VIRTUAL_HUB_SALE",
            route_legs=[
                {"step": "entry_capacity", "point": "Easington Beach Terminal"},
                {"step": "virtual_hub_sale", "point": "NBP"},
            ],
            required_entry_point_name="Easington Beach Terminal",
            required_exit_point_name=None,
            required_tso_access=["National Gas NTS"],
            source_systems=["National Gas NTS", "ICE OCM", "EEX"],
            active=True,
            created_at_utc=now,
        ),
        RouteCandidateRecord(
            route_id="uk-easington-bacton-physical",
            route_name="Easington beach delivery -> Bacton physical exit",
            start_point_name="Easington Beach Terminal",
            target_point_name="Bacton GDN (EA)",
            business_model="PHYSICAL_DELIVERY",
            route_legs=[
                {"step": "entry_capacity", "point": "Easington Beach Terminal"},
                {"step": "exit_capacity", "point": "Bacton GDN (EA)"},
                {"step": "physical_delivery", "point": "Bacton GDN (EA)"},
            ],
            required_entry_point_name="Easington Beach Terminal",
            required_exit_point_name="Bacton GDN (EA)",
            required_tso_access=["National Gas NTS"],
            source_systems=["National Gas NTS", "ENTSOG"],
            active=True,
            created_at_utc=now,
        ),
    ]


if __name__ == "__main__":
    raise SystemExit(main())
