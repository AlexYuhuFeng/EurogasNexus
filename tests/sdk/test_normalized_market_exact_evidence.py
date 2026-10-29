"""Exact source-price evidence must survive the actual backend-to-SDK projection.

The producer under test is the real EEX receipt mapper feeding the real ORM row and
``list_normalized_market_view``. The SDK is projected from that actual repository
payload, so a renamed or invented field cannot pass this test.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from eurogas_nexus_sdk.market import NormalizedMarketObservation
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import FxObservationRecord, MarketObservationRecord
from eurogas_nexus.db.repositories.market_intelligence import list_normalized_market_view
from eurogas_nexus.domain.market.gas_day import EU_CAM_UTC_CALENDAR
from eurogas_nexus.ingestion.eex_ngp import (
    EexNgpGasDayCalendarContract,
    eex_ttf_ngp_receipt_observations,
    parse_eex_ttf_ngp_csv,
)

RECEIPT = datetime(2026, 10, 29, 14, 54, 5, 623743, tzinfo=UTC)
EEX_CSV = (
    "\ufeffGasday;IndexValue (€/MWh);IndexVolume (MWh);Status;Timestamp Let\r\n"
    "29/10/2026;+123.4500000000000000001;+42.500000000000000000;"
    "Final NGP;29/10/2026 12:00\r\n"
)

#: The exact 15 names emitted by
#: ``normalized_view._source_price_fields``. No aliases are introduced.
SOURCE_PRICE_FIELDS = (
    "source_price_status",
    "source_price_exact",
    "source_price_raw",
    "source_price_volume_mwh_exact",
    "source_price_volume_raw",
    "source_price_volume_status",
    "source_price_provenance",
    "source_price_issue",
    "source_price_issue_detail",
    "source_price_source_system",
    "source_price_source_reference",
    "source_price_source_dataset",
    "price_float_provenance",
    "price_semantics",
    "executable_quote",
)

#: Exact/raw decimal evidence is text. A JSON number or boolean is not evidence
#: and must be refused rather than stringified by the SDK.
STRICT_DECIMAL_TEXT_FIELDS = (
    "price_gbp_mwh_exact",
    "source_price_exact",
    "source_price_raw",
    "source_price_volume_mwh_exact",
    "source_price_volume_raw",
)


def _fx_row() -> FxObservationRecord:
    return FxObservationRecord(
        observation_id="fx-eurgbp-20261029",
        pair="EURGBP",
        base_currency="EUR",
        quote_currency="GBP",
        rate=0.85,
        rate_type="reference",
        value_date="2026-10-29",
        observed_at_utc=RECEIPT,
        source_system="ECB",
        source_reference="ecb-eurofxref",
        source_record_id=None,
        freshness="unknown",
        research_only=True,
        metadata_json=None,
    )


def _actual_produced_row(
    session: Session,
    *,
    metadata_override: dict | None = None,
) -> dict:
    """Map authentic EEX receipt evidence through the actual backend projector."""

    parsed = parse_eex_ttf_ngp_csv(EEX_CSV, retrieved_at_utc=RECEIPT)
    observations = eex_ttf_ngp_receipt_observations(
        parsed,
        received_at_utc=RECEIPT,
        gas_day_calendar_contract=EexNgpGasDayCalendarContract(
            calendar_id=EU_CAM_UTC_CALENDAR,
            evidence="test-owned receipt/calendar evidence for the projection boundary",
        ),
    )
    observation = observations[0]
    if metadata_override:
        observation["metadata_json"] = {
            **observation["metadata_json"],
            **metadata_override,
        }
    session.add(MarketObservationRecord(**observation))
    session.add(_fx_row())
    session.flush()
    view = list_normalized_market_view(session, limit=10)
    assert len(view["rows"]) == 1
    return view["rows"][0]


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    MarketObservationRecord.__table__.create(engine)
    FxObservationRecord.__table__.create(engine)
    with Session(engine) as active:
        yield active


def test_actual_producer_evidence_projects_into_sdk(session: Session) -> None:
    produced = _actual_produced_row(session)
    sdk = NormalizedMarketObservation.model_validate(produced)

    for name in SOURCE_PRICE_FIELDS:
        assert getattr(sdk, name) == produced[name]
    assert len(SOURCE_PRICE_FIELDS) == 15

    assert sdk.source_price_status == "exact"
    assert sdk.source_price_exact == "123.4500000000000000001"
    assert sdk.source_price_raw == "+123.4500000000000000001"
    assert sdk.source_price_volume_mwh_exact == "42.500000000000000000"
    assert sdk.source_price_volume_raw == "+42.500000000000000000"
    assert sdk.source_price_source_system == "EEX"
    assert sdk.source_price_source_reference == "eex-ttf-ngp-15-mins"
    assert sdk.source_price_source_dataset == "ttf-ngp-15min"
    assert sdk.executable_quote is False
    assert sdk.price_name == produced["price_name"] == "EEX_TTF_NGP"

    # GBP conversion used a float FX rate. The SDK may carry the approximate
    # number and its provenance, but it must not invent an exact FX claim.
    assert sdk.price_gbp_mwh == produced["price_gbp_mwh"]
    assert sdk.price_gbp_mwh_exact is None
    assert sdk.price_gbp_mwh_provenance == (
        "exact_source_decimal_times_float_fx_approximation"
    )


def test_metadata_publication_null_and_receipt_availability_are_unmodified(
    session: Session,
) -> None:
    produced = _actual_produced_row(session)
    sdk = NormalizedMarketObservation.model_validate(produced)

    assert sdk.metadata_json == produced["metadata_json"]
    assert sdk.metadata_json["publication_time_utc"] is None
    assert sdk.metadata_json["publication_time_basis"] == "unknown"
    assert sdk.metadata_json["availability_basis"] == "response_receipt"
    assert sdk.metadata_json["available_at_utc"] == RECEIPT.isoformat()
    assert sdk.metadata_json["retrieved_at_utc"] == RECEIPT.isoformat()


def test_invalid_backend_exact_claim_cannot_become_exact_sdk_value(
    session: Session,
) -> None:
    produced = _actual_produced_row(
        session,
        metadata_override={"index_value_exact": "not-a-decimal"},
    )
    sdk = NormalizedMarketObservation.model_validate(produced)

    assert produced["source_price_status"] == "invalid"
    assert sdk.source_price_status == "invalid"
    assert sdk.source_price_exact is None
    assert sdk.source_price_raw is None
    assert sdk.price_gbp_mwh is None
    assert sdk.price_gbp_mwh_exact is None
    assert sdk.source_price_issue


def test_legacy_response_without_new_fields_still_parses(session: Session) -> None:
    produced = _actual_produced_row(session)
    new_fields = {
        *SOURCE_PRICE_FIELDS,
        "price_gbp_mwh_exact",
        "price_gbp_mwh_provenance",
        "price_name",
    }
    legacy = {key: value for key, value in produced.items() if key not in new_fields}

    sdk = NormalizedMarketObservation.model_validate(legacy)

    for name in new_fields:
        assert getattr(sdk, name) is None
    assert sdk.metadata_json == legacy["metadata_json"]


def test_exact_decimal_text_rejects_numbers_and_booleans(session: Session) -> None:
    produced = _actual_produced_row(session)
    for name in STRICT_DECIMAL_TEXT_FIELDS:
        for forged in (123.45, 42, True):
            payload = {**produced, name: forged}
            with pytest.raises(ValidationError):
                NormalizedMarketObservation.model_validate(payload)

    with pytest.raises(ValidationError):
        NormalizedMarketObservation.model_validate(
            {**produced, "executable_quote": 1}
        )

    accepted = NormalizedMarketObservation.model_validate(
        {**produced, "executable_quote": False}
    )
    assert accepted.executable_quote is False


def test_installed_smoke_summary_requires_market_contract_counts(
    monkeypatch, tmp_path
) -> None:
    from scripts.ci import check_installed_sdk as acceptance

    installed_origin = (
        tmp_path / "venv" / "site-packages" / "eurogas_nexus_sdk" / "__init__.py"
    )
    installed_origin.parent.mkdir(parents=True)
    installed_origin.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        acceptance,
        "_assert_installed_origin",
        lambda *args, **kwargs: installed_origin,
    )
    venv_prefix = tmp_path / "venv"
    checkout_root = tmp_path / "checkout"
    checkout_root.mkdir()
    summary = {
        "status": "passed",
        "sdk_origin": "site-packages/eurogas_nexus_sdk/__init__.py",
        "module_count": 3,
        "python_version": "3.11.9",
        "typed_validation_case_count": 2,
        "typed_error_fields": ["billing_start", "valuation_date"],
        "sdk_version": "0.5.0",
        "market_evidence_field_count": 18,
        "market_contract_case_count": 6,
    }
    acceptance._validate_smoke_summary(
        summary,
        venv_prefix=venv_prefix,
        checkout_root=checkout_root,
        installed_origin=installed_origin,
    )
    for key, code in (
        ("market_evidence_field_count", "market_evidence_field_count_changed"),
        ("market_contract_case_count", "market_contract_case_count_changed"),
    ):
        broken = dict(summary)
        del broken[key]
        with pytest.raises(acceptance.AcceptanceFailure) as excinfo:
            acceptance._validate_smoke_summary(
                broken,
                venv_prefix=venv_prefix,
                checkout_root=checkout_root,
                installed_origin=installed_origin,
            )
        assert excinfo.value.code == code
