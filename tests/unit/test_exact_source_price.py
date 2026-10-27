"""Exact EEX NGP source-decimal consumption through normalization and research.

The fixtures are synthetic, but the valid golden path goes through the real
``eex_ngp.py`` parser/canonical mapper and the real normalized-view/repository
adapters. No downloaded market value is recorded here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, Inexact, Rounded, getcontext, localcontext
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FxObservationRecord, MarketObservationRecord
from eurogas_nexus.db.repositories.market_intelligence import list_normalized_market_view
from eurogas_nexus.domain.ingestion.source_timezone import SourceTimezoneContract
from eurogas_nexus.domain.market.gas_day import EU_CAM_UTC_CALENDAR
from eurogas_nexus.domain.market_intelligence.normalized_view import (
    FxRateInput,
    MarketObservationInput,
    build_normalized_market_view,
    normalize_observation,
)
from eurogas_nexus.domain.market_intelligence.source_price import (
    FLOAT_PROVENANCE_EXACT,
    FLOAT_PROVENANCE_INVALID,
    FLOAT_PROVENANCE_MISSING,
    PROVENANCE_EXACT,
    PROVENANCE_LEGACY,
    STATUS_EXACT,
    STATUS_INVALID,
    STATUS_LEGACY_FLOAT,
    STATUS_MISSING,
    resolve_source_price,
)
from eurogas_nexus.domain.strategy_lab.price_series import (
    exact_source_price_decimal,
    source_price_for_series,
)
from eurogas_nexus.ingestion.eex_ngp import (
    EexNgpGasDayCalendarContract,
    eex_ttf_ngp_market_observations,
    parse_eex_ttf_ngp_csv,
)

RETRIEVED_AT = datetime(2026, 5, 29, 15, 5, tzinfo=UTC)
HEADER = "Gasday;IndexValue (€/MWh);IndexVolume (MWh);Status;Timestamp Let"
EUR_GBP = FxRateInput(
    pair="EURGBP",
    base_currency="EUR",
    quote_currency="GBP",
    rate=0.85,
    observed_at_utc="2026-05-29T15:00:00+00:00",
)
EXACT_PRICE = "31.1234567890123456789012345678901230"
EXACT_VOLUME = "1200.500000000000000001"


def _governed_contract() -> SourceTimezoneContract:
    """A synthetic evidenced contract used only to exercise the canonical path."""

    return SourceTimezoneContract(
        source_system="EEX",
        datasets=("ttf-ngp-15min",),
        declared_zone=ZoneInfo("Europe/Berlin"),
        evidence="synthetic test contract: exercise the governed-zone path only",
    )


def _gas_day_contract() -> EexNgpGasDayCalendarContract:
    """A synthetic delivery calendar used only by these tests."""

    return EexNgpGasDayCalendarContract(
        calendar_id=EU_CAM_UTC_CALENDAR,
        evidence="synthetic test contract: exercise the governed-calendar path only",
    )


def _eex_ngp_row(value: str = "31.400", volume: str = "1200.5") -> dict:
    """Run the real EEX parser and canonical mapper for one synthetic row."""

    payload = "\ufeff" + "\n".join(
        [
            HEADER,
            f"29/05/2026;{value};{volume};Final NGP;29/05/2026 14:30",
        ]
    )
    result = parse_eex_ttf_ngp_csv(
        payload,
        retrieved_at_utc=RETRIEVED_AT,
        timezone_contract=_governed_contract(),
    )
    return eex_ttf_ngp_market_observations(
        result,
        gas_day_calendar_contract=_gas_day_contract(),
    )[0]


def _observation_from_row(row: dict, **overrides) -> MarketObservationInput:
    """Map the parser's canonical row shape into the normalization input."""

    fields = {
        "market_venue": row["market_venue"],
        "product": row["product"],
        "price": row["price"],
        "currency": row["currency"],
        "unit": row["unit"],
        "observed_at_utc": row["observed_at_utc"].isoformat(),
        "period_start_utc": row["period_start_utc"].isoformat(),
        "metadata_json": row["metadata_json"],
        "source_system": row["source_system"],
        "source_reference": row["source_reference"],
        "source_record_id": row["source_record_id"],
    }
    fields.update(overrides)
    return MarketObservationInput(**fields)


def _metadata(**overrides) -> dict:
    """A canonical EEX NGP metadata fixture with individually overridable fields."""

    metadata = {
        "source_system": "EEX",
        "source_reference": "eex-ttf-ngp-15-mins",
        "source_dataset": "ttf-ngp-15min",
        "index": "NGP",
        "index_type": "volume_weighted_reference_index",
        "contract_type": "index",
        "price_type": "index",
        "price_semantics": "reference_index_never_an_executable_bid_or_ask",
        "executable_quote": False,
        "simulated": False,
        "index_value_raw": "31.400",
        "index_value_exact": "31.400",
        "index_volume_raw": "1200.5",
        "index_volume_mwh_exact": "1200.5",
    }
    metadata.update(overrides)
    return metadata


def _resolve(
    metadata: dict,
    *,
    numeric_price: object = 31.4,
    source_system: str | None = "EEX",
    source_reference: str | None = "eex-ttf-ngp-15-mins",
    unit: str | None = "EUR/MWh",
    currency: str | None = "EUR",
):
    """Resolve one synthetic metadata claim through the shared authority."""

    return resolve_source_price(
        source_system=source_system,
        source_reference=source_reference,
        numeric_price=numeric_price,
        metadata=metadata,
        unit=unit,
        currency=currency,
    )


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _record_from_row(row: dict) -> MarketObservationRecord:
    return MarketObservationRecord(
        observation_id=row["observation_id"],
        market_venue=row["market_venue"],
        product=row["product"],
        price=row["price"],
        unit=row["unit"],
        currency=row["currency"],
        period_start_utc=row["period_start_utc"],
        period_end_utc=row["period_end_utc"],
        observed_at_utc=row["observed_at_utc"],
        source_system=row["source_system"],
        source_reference=row["source_reference"],
        source_record_id=row["source_record_id"],
        freshness=row["freshness"],
        quality_score=row["quality_score"],
        research_only=row["research_only"],
        metadata_json=row["metadata_json"],
    )


def _expected_gbp(value: str) -> float:
    """The exact-source value times the exact binary 0.85 rate, then to float."""

    with localcontext() as context:
        context.prec = 500
        return float(Decimal(value) * Decimal.from_float(0.85))


def _fx_record() -> FxObservationRecord:
    return FxObservationRecord(
        observation_id="fx-eurgbp-20260529",
        pair="EURGBP",
        base_currency="EUR",
        quote_currency="GBP",
        rate=0.85,
        rate_type="reference",
        value_date="2026-05-29",
        observed_at_utc=datetime(2026, 5, 29, 15, 0, tzinfo=UTC),
        source_system="ECB",
        source_reference="ecb-eurofxref",
        source_record_id=None,
        freshness="unknown",
        research_only=True,
        metadata_json={},
    )


def test_actual_parser_metadata_reaches_the_consumer_without_float_loss() -> None:
    """A high-precision parser row keeps its exact digits through normalization."""

    row = _eex_ngp_row(EXACT_PRICE, EXACT_VOLUME)

    assert row["metadata_json"]["index_value_exact"] == EXACT_PRICE
    assert row["metadata_json"]["index_volume_mwh_exact"] == EXACT_VOLUME
    # The persisted Float contract has already lost digits by this point.
    assert row["price"] == float(Decimal(EXACT_PRICE))
    assert Decimal(str(row["price"])) != Decimal(EXACT_PRICE)

    source_price = resolve_source_price(
        source_system=row["source_system"],
        source_reference=row["source_reference"],
        numeric_price=row["price"],
        metadata=row["metadata_json"],
        unit=row["unit"],
        currency=row["currency"],
    )
    assert source_price.status == STATUS_EXACT
    assert source_price.exact_decimal == Decimal(EXACT_PRICE)
    assert source_price.exact_text == EXACT_PRICE
    assert source_price.raw_text == EXACT_PRICE
    assert source_price.volume_decimal == Decimal(EXACT_VOLUME)
    assert source_price.volume_exact_text == EXACT_VOLUME
    assert source_price.executable_quote is False

    normalized = normalize_observation(_observation_from_row(row), [EUR_GBP])

    assert normalized["price"] == row["price"]
    assert normalized["source_price_status"] == STATUS_EXACT
    assert normalized["source_price_exact"] == EXACT_PRICE
    assert normalized["source_price_raw"] == EXACT_PRICE
    assert normalized["source_price_provenance"] == PROVENANCE_EXACT
    assert normalized["price_float_provenance"] == FLOAT_PROVENANCE_EXACT
    assert normalized["source_price_volume_mwh_exact"] == EXACT_VOLUME
    assert normalized["source_price_volume_status"] == "valid"
    assert normalized["price_gbp_mwh"] is not None
    assert normalized["price_gbp_mwh_exact"] is None
    assert (
        normalized["price_gbp_mwh_provenance"]
        == "exact_source_decimal_times_float_fx_approximation"
    )
    assert normalized["price_gbp_mwh"] == _expected_gbp(EXACT_PRICE)
    # A reference index is never promoted to a bid/ask or executable quote.
    assert normalized["executable_quote"] is False
    assert "reference_index" in normalized["price_semantics"]
    assert "bid_price" not in normalized
    assert "ask_price" not in normalized
    assert exact_source_price_decimal(normalized) == Decimal(EXACT_PRICE)


def test_repository_adapts_source_identity_and_strategy_research_gets_decimal() -> None:
    """The DB composition passes source identity and the research adapter reads it."""

    row = _eex_ngp_row(EXACT_PRICE, EXACT_VOLUME)
    with _session() as session:
        session.add(_record_from_row(row))
        session.add(_fx_record())
        session.commit()
        view = list_normalized_market_view(session, limit=10)

    assert len(view["rows"]) == 1
    repository_row = view["rows"][0]
    assert repository_row["source_system"] == "EEX"
    assert repository_row["source_reference"] == "eex-ttf-ngp-15-mins"
    assert repository_row["source_price_exact"] == EXACT_PRICE
    assert repository_row["source_price_raw"] == EXACT_PRICE
    assert repository_row["source_price_volume_mwh_exact"] == EXACT_VOLUME
    assert repository_row["price_float_provenance"] == FLOAT_PROVENANCE_EXACT
    assert exact_source_price_decimal(repository_row) == Decimal(EXACT_PRICE)
    assert source_price_for_series(repository_row).exact_decimal == Decimal(EXACT_PRICE)


def test_negative_source_price_stays_signed_through_normalization() -> None:
    row = _eex_ngp_row("-5.25", "1200.5")
    normalized = normalize_observation(_observation_from_row(row), [EUR_GBP])

    assert row["price"] == -5.25
    assert normalized["source_price_exact"] == "-5.25"
    assert normalized["source_price_provenance"] == PROVENANCE_EXACT
    assert normalized["price_gbp_mwh"] == _expected_gbp("-5.25")
    assert normalized["price_gbp_mwh"] < 0


def test_hostile_ambient_decimal_context_does_not_change_the_exact_result() -> None:
    row = _eex_ngp_row(EXACT_PRICE, EXACT_VOLUME)
    observation = _observation_from_row(row)
    expected_decimal = Decimal(EXACT_PRICE)

    prior_precision = getcontext().prec
    with localcontext() as context:
        context.prec = 2
        context.Emax = 9
        context.Emin = -9
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        source_price = resolve_source_price(
            source_system=observation.source_system,
            source_reference=observation.source_reference,
            numeric_price=observation.price,
            metadata=observation.metadata_json,
            unit=observation.unit,
            currency=observation.currency,
        )
        normalized = normalize_observation(observation, [EUR_GBP])

        assert getcontext().prec == 2
        assert source_price.exact_decimal == expected_decimal
        assert normalized["source_price_exact"] == EXACT_PRICE
        assert normalized["price_gbp_mwh"] is not None
    assert getcontext().prec == prior_precision


def test_ordinary_non_eex_source_keeps_legacy_float_provenance_and_value() -> None:
    observation = MarketObservationInput(
        market_venue="ICIS",
        product="TTF Day-Ahead",
        price=31.25,
        currency="EUR",
        unit="EUR/MWh",
        observed_at_utc="2026-05-29T15:30:00+00:00",
        metadata_json={"hub": "TTF"},
    )

    view = build_normalized_market_view([observation], [EUR_GBP])
    row = view["rows"][0]

    assert row["price_gbp_mwh"] == 31.25 * 0.85
    assert row["source_price_status"] == STATUS_LEGACY_FLOAT
    assert row["source_price_exact"] is None
    assert row["source_price_provenance"] == PROVENANCE_LEGACY
    assert row["price_float_provenance"] == "legacy_float_approximation"
    assert row["price_gbp_mwh_provenance"] == "legacy_float_approximation"
    assert row["source_price_issue"] is None
    assert view["warnings"] == []


def test_exact_price_without_volume_keys_marks_volume_missing_not_invalid() -> None:
    metadata = _metadata()
    metadata.pop("index_volume_raw")
    metadata.pop("index_volume_mwh_exact")

    source_price = _resolve(metadata)

    assert source_price.status == STATUS_EXACT
    assert source_price.exact_decimal == Decimal("31.400")
    assert source_price.volume_decimal is None
    assert source_price.volume_status == "missing"


def test_missing_eex_exact_claim_is_explicit_not_a_float_fallback() -> None:
    metadata = _metadata()
    for key in (
        "index_value_exact",
        "index_value_raw",
        "index_volume_mwh_exact",
        "index_volume_raw",
    ):
        metadata.pop(key)
    source_price = _resolve(metadata)
    assert source_price.status == STATUS_MISSING
    assert source_price.exact_decimal is None
    assert source_price.issue_code == "exact_source_price_missing"
    assert source_price.price_float_provenance == FLOAT_PROVENANCE_MISSING

    observation = _observation_from_row(_eex_ngp_row(), metadata_json=metadata)
    view = build_normalized_market_view([observation], [EUR_GBP])
    row = view["rows"][0]

    assert row["price"] == 31.4
    assert row["price_gbp_mwh"] is None
    assert row["source_price_status"] == STATUS_MISSING
    assert row["source_price_issue"] == "exact_source_price_missing"
    assert "exact_source_price_missing" in view["warnings"][0]


@pytest.mark.parametrize(
    ("metadata", "numeric_price", "expected_code"),
    [
        (_metadata(index_value_exact=31.4), 31.4, "exact_decimal_not_string"),
        (_metadata(index_value_exact="NaN"), 31.4, "exact_decimal_not_plain"),
        (_metadata(index_value_exact="1e3"), 31.4, "exact_decimal_not_plain"),
        (_metadata(index_value_raw="31.401"), 31.4, "exact_raw_mismatch"),
        (_metadata(), 99.9, "exact_numeric_price_mismatch"),
        (_metadata(index_volume_mwh_exact="NaN"), 31.4, "exact_volume_not_plain"),
        (_metadata(index_volume_mwh_exact="1200.6"), 31.4, "exact_volume_mismatch"),
        (
            _metadata(
                index_volume_raw="-1200.5",
                index_volume_mwh_exact="-1200.5",
            ),
            31.4,
            "exact_volume_not_positive",
        ),
        (
            _metadata(index_value_exact="1" + "0" * 512),
            1e300,
            "exact_decimal_too_long",
        ),
    ],
)
def test_malformed_or_contradictory_exact_payload_fails_closed(
    metadata: dict,
    numeric_price: object,
    expected_code: str,
) -> None:
    source_price = _resolve(metadata, numeric_price=numeric_price)

    assert source_price.status == STATUS_INVALID
    assert source_price.exact_decimal is None
    assert source_price.exact_text is None
    assert source_price.issue_code == expected_code


def test_forged_source_identity_is_refused_before_any_numeric_use() -> None:
    source_price = _resolve(_metadata(), source_system="ICIS")
    assert source_price.status == STATUS_INVALID
    assert source_price.issue_code == "exact_source_identity_mismatch"

    metadata_mismatch = _resolve(_metadata(source_system="ICIS"))
    assert metadata_mismatch.status == STATUS_INVALID
    assert metadata_mismatch.issue_code == "exact_metadata_source_mismatch"

    unit_mismatch = _resolve(_metadata(), unit="p/therm")
    assert unit_mismatch.status == STATUS_INVALID
    assert unit_mismatch.issue_code == "exact_unit_mismatch"


def test_malformed_exact_claim_does_not_fall_back_to_float_gbp() -> None:
    metadata = _metadata(index_value_exact="NaN")
    observation = _observation_from_row(_eex_ngp_row(), metadata_json=metadata)
    view = build_normalized_market_view([observation], [EUR_GBP])
    row = view["rows"][0]

    assert row["price"] == 31.4
    assert row["price_gbp_mwh"] is None
    assert row["source_price_status"] == STATUS_INVALID
    assert row["source_price_issue"] == "exact_decimal_not_plain"
    assert row["price_float_provenance"] == FLOAT_PROVENANCE_INVALID
    assert "exact_decimal_not_plain" in view["warnings"][0]
