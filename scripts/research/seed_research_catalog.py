#!/usr/bin/env python
"""Seed the CR-14 research catalog into a configured runtime database.

Definitions are semantic and deterministic. The script writes no market values
except two synthetic weather forecast vintages, which are clearly marked as
simulated test data.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from eurogas_nexus.db.models import (  # noqa: E402
    SeriesDefinitionRecord,
)
from eurogas_nexus.db.repositories.research import (  # noqa: E402
    upsert_canonical_entity,
    upsert_feature_definition,
    upsert_forecast_observation,
    upsert_resampling_policy,
    upsert_series_definition,
    upsert_source_entity_mapping,
    upsert_target_definition,
)
from eurogas_nexus.db.session import (  # noqa: E402
    get_session_factory,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.domain.research.features import FeatureDefinition  # noqa: E402
from eurogas_nexus.domain.research.ontology import canonical_entity_id  # noqa: E402
from eurogas_nexus.domain.research.resampling import (  # noqa: E402
    MissingDataPolicy,
    ResamplingPolicy,
)
from eurogas_nexus.domain.research.targets import TargetDefinition, TargetKind  # noqa: E402


def _feature(feature_id: str, name: str, deps: list[str], unit: str) -> FeatureDefinition:
    return FeatureDefinition(
        feature_id=feature_id,
        name=name,
        description=f"{name} for point-in-time research datasets.",
        category="market" if "MARGIN" not in feature_id else "commercial",
        input_dependencies=deps,
        output_unit=unit,
        frequency="1h",
        availability_class="DERIVED_AS_OF",
        transformation=f"builtin:{feature_id}",
        transformation_version="v1",
        lookback="none",
        missing_data_policy="mask",
    )


def _target(target_id: str, name: str, entity: str, unit: str) -> TargetDefinition:
    return TargetDefinition(
        target_id=target_id,
        name=name,
        description=f"{name} evaluation target.",
        target_type=TargetKind.PRICE if "PRICE" in target_id else TargetKind.SPREAD,
        entity_type="market_hub",
        entity_id=entity,
        metric=target_id.lower().replace("-", "."),
        horizon="D1",
        target_window="1d",
        unit=unit,
        aggregation="first",
        label_calculation="first_observation_at_or_after_origin_plus_horizon",
        availability_delay="0h",
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
        for code, name in (
            ("TTF", "Title Transfer Facility"),
            ("NBP", "National Balancing Point"),
            ("THE", "Trading Hub Europe"),
            ("PEG", "Point d'Echange de Gaz"),
            ("ZTP", "Zeebrugge Trading Point"),
            ("PSV", "Punto di Scambio Virtuale"),
        ):
            upsert_canonical_entity(
                session,
                canonical_entity_id=canonical_entity_id("market_hub", code),
                entity_type="market_hub",
                canonical_code=code,
                display_name=name,
                description=f"{code} gas trading hub",
            )
        for source_id, _venue in (
            ("EEX_Sim", "EEX"),
            ("ICE_OCM_Sim", "ICE OCM"),
            ("ICIS_Sim", "ICIS Heren"),
        ):
            for hub in ("TTF", "NBP", "THE", "PEG", "ZTP", "PSV"):
                upsert_source_entity_mapping(
                    session,
                    mapping_id=f"map:{source_id}:{hub}",
                    canonical_entity_id=canonical_entity_id("market_hub", hub),
                    source_id=source_id,
                    source_entity_type="market_hub",
                    source_identifier=hub,
                    valid_from_utc=now - timedelta(days=365),
                    evidence="CR-14 canonical hub mapping; code identity, not display name.",
                )
        for source_id, name in (
            ("BBL Company", "BBL Interconnector"),
            ("Interconnector UK", "IUK Interconnector"),
        ):
            code = "BBL" if "BBL" in source_id else "IUK"
            canonical = canonical_entity_id("interconnector", code)
            upsert_canonical_entity(
                session,
                canonical_entity_id=canonical,
                entity_type="interconnector",
                canonical_code=code,
                display_name=name,
            )
            upsert_source_entity_mapping(
                session,
                mapping_id=f"map:{source_id}",
                canonical_entity_id=canonical,
                source_id=source_id,
                source_entity_type="interconnector",
                source_identifier=source_id,
                valid_from_utc=now - timedelta(days=365),
                evidence="CR-14 interconnector mapping.",
            )

        for series in (
            SeriesDefinitionRecord(
                series_id="market.fx.EUR.GBP",
                name="EUR/GBP reference FX",
                metric_type="fx",
                entity_type="market_area",
                entity_id="ent:market_area:EUROZONE",
                product_id=None,
                source_class="ECB",
                native_frequency="event",
                native_unit="GBP/EUR",
                currency="GBP",
                temporal_type="OBSERVED",
                availability_semantics="available_at_required",
                schema_version="series/v1",
                created_at_utc=now,
            ),
            SeriesDefinitionRecord(
                series_id="market.price.NBP.DAY_AHEAD",
                name="NBP day-ahead price",
                metric_type="price",
                entity_type="market_hub",
                entity_id="ent:market_hub:NBP",
                product_id="day-ahead",
                source_class="EEX_Sim",
                native_frequency="event",
                native_unit="EUR/MWh",
                currency="EUR",
                temporal_type="OBSERVED",
                availability_semantics="available_at_required",
                schema_version="series/v1",
                created_at_utc=now,
            ),
            SeriesDefinitionRecord(
                series_id="market.price.TTF.DAY_AHEAD",
                name="TTF day-ahead price",
                metric_type="price",
                entity_type="market_hub",
                entity_id="ent:market_hub:TTF",
                product_id="day-ahead",
                source_class="EEX_Sim",
                native_frequency="event",
                native_unit="EUR/MWh",
                currency="EUR",
                temporal_type="OBSERVED",
                availability_semantics="available_at_required",
                schema_version="series/v1",
                created_at_utc=now,
            ),
        ):
            upsert_series_definition(session, series)

        for feature in (
            _feature(
                "NBP_TTF_DA_SPREAD",
                "NBP/TTF day-ahead spread",
                ["market.price.NBP.DAY_AHEAD", "market.price.TTF.DAY_AHEAD"],
                "EUR/MWh",
            ),
            _feature(
                "ROUTE_MARGIN",
                "Transport-adjusted route margin",
                ["market.price.NBP.DAY_AHEAD"],
                "GBP/MWh",
            ),
        ):
            upsert_feature_definition(
                session,
                feature_id=feature.feature_id,
                definition_json=feature.model_dump(mode="json"),
                content_hash=feature.content_hash(),
            )
        for target in (
            _target("NBP_DA_PRICE_D1", "NBP day-ahead price D1", "NBP", "EUR/MWh"),
            _target("TTF_DA_PRICE_D1", "TTF day-ahead price D1", "TTF", "EUR/MWh"),
            _target("NBP_TTF_SPREAD_D1", "NBP/TTF spread D1", "NBP", "EUR/MWh"),
        ):
            upsert_target_definition(
                session,
                target_id=target.target_id,
                definition_json=target.model_dump(mode="json"),
                content_hash=target.content_hash(),
            )
        policy = ResamplingPolicy(
            policy_id="resampling/v1",
            semantic_type="market_price",
            carry_forward_policy=MissingDataPolicy.DROP,
            maximum_carry_seconds=3600,
        )
        upsert_resampling_policy(
            session,
            policy_id=policy.policy_id,
            definition_json=policy.model_dump(mode="json"),
            content_hash=policy.content_hash(),
        )

        # Two synthetic weather forecast vintages prove forecast storage does
        # not overwrite earlier vintages.
        for issued_hours_ago, value in ((2, 12.5), (14, 13.2)):
            issued = now - timedelta(hours=issued_hours_ago)
            valid_start = now + timedelta(hours=12)
            valid_end = now + timedelta(hours=36)
            upsert_forecast_observation(
                session,
                forecast_observation_id=f"uat-weather-london-{issued:%Y%m%d%H%M%S}",
                series_id="weather.LONDON.TEMPERATURE_FORECAST",
                entity_id="ent:market_area:GB",
                forecast_issued_at=issued,
                forecast_valid_start=valid_start,
                forecast_valid_end=valid_end,
                horizon="12h",
                value=value,
                unit="degC",
                source_system="WEATHER_UAT_Sim",
                available_at_utc=issued + timedelta(minutes=2),
                provenance={"simulated": True, "fixture": "CR-14"},
            )
        session.commit()
    print(
        "Seeded CR-14 research catalog: entities, mappings, series, features, "
        "targets, policy, forecast vintages."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
