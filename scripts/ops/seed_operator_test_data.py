"""Seed operator-owned test prices/contracts and public tariff references.

This script is for the local PostgreSQL test server only. Public tariff rows are
manually transcribed source references. Price marks and contracts are
operator-owned test records because exchange/vendor prices require entitlement.
The script does not call external APIs, run migrations, or print database
secrets.
"""

from __future__ import annotations

from datetime import UTC, datetime

from eurogas_nexus.db.models import (
    GlossaryTermRecord,
    LiveMarketMarkRecord,
    TsoTariffRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.session import (
    get_session_factory,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.domain.glossary import baseline_glossary_terms
from eurogas_nexus.domain.route_cost.uk_public_tariffs import (
    DOCUMENT_ID as UK_NTS_DOCUMENT_ID,
)
from eurogas_nexus.domain.route_cost.uk_public_tariffs import (
    published_uk_capacity_tariffs,
)


def main() -> int:
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2

    print(f"Runtime DB: {redact_database_url(database_url)}")
    now = datetime.now(UTC)
    session_factory = get_session_factory(database_url=database_url)
    with session_factory() as session:
        session.query(TsoTariffRecord).filter(
            TsoTariffRecord.document_id == UK_NTS_DOCUMENT_ID
        ).delete(synchronize_session=False)
        session.flush()
        for tariff in published_uk_capacity_tariffs():
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
        session.merge(
            LiveMarketMarkRecord(
                mark_id="operator-test-ice-ocm-nbp-within-day",
                venue="ICE OCM",
                hub="NBP",
                product="Within-day",
                bid_gbp_mwh=28.2,
                ask_gbp_mwh=28.4,
                last_gbp_mwh=28.3,
                mark_time_utc=now,
                source_system="operator-entered-test-price",
                source_reference="local-test-price-mark",
                created_at_utc=now,
            )
        )
        session.merge(
            UpstreamResourceContractRecord(
                contract_id="operator-test-easington-contract",
                contract_name="Operator test Easington annual supply",
                resource_type="BEACH_DELIVERY",
                delivery_point_name="Easington Beach Terminal",
                gas_year="2025/26",
                delivery_quantity_mwh_per_day=10000.0,
                contract_price_gbp_mwh=25.0,
                settlement_frequency="monthly",
                upstream_payment_lag_days=20,
                screen_sale_cash_lag_days=1,
                annual_financing_rate_pct=6.0,
                delivery_tolerance_pct=2.0,
                nomination_tolerance_pct=1.0,
                allowed_exit_points=["Bacton GDN (EA)"],
                eligible_sale_modes=["VIRTUAL_HUB_SALE", "PHYSICAL_DELIVERY"],
                notes="operator-entered-test-contract: local-test-contract",
                created_at_utc=now,
                updated_at_utc=now,
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

    print(
        "Seeded public tariff rows, operator test price mark, "
        "operator test contract, and glossary terms."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
