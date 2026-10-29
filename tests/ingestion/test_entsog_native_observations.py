"""RFC0005 stage C native ENTSOG observation integration tests."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from eurogas_nexus.application.physical_native_rates import validate_native_rate_payload
from eurogas_nexus.db.repositories import entsog_observation_persistence as persistence
from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    GieRevisionRequiresHistoryError,
)
from eurogas_nexus.ingestion import entsog_ingestion
from eurogas_nexus.ingestion.entsog_native_observations import (
    EntsogNativeObservationError,
    native_entsog_capacity_observations_from_json,
    native_entsog_flow_observations_from_json,
)
from eurogas_nexus.ingestion.entsog_native_units import NORMALIZER_VERSION
from eurogas_nexus.ingestion.entsog_transport import EntsogFetchResult, EntsogPage
from eurogas_nexus.ingestion.public_sources import (
    entsog_capacity_observations_from_json,
    entsog_flow_observations_from_json,
    gie_storage_observations_from_json,
)

_RECEIPT = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)

_FLOW_RAW = b"""{
  "meta": {"limit": 10, "offset": 0, "count": 5, "total": 5, "sort": "id"},
  "operationaldatas": [
    {
      "id": "flow-long",
      "indicator": "Physical Flow",
      "value": 12345678901234567890.123456789,
      "unit": "MWh/d",
      "periodFrom": "2025-01-01T06:00:00",
      "periodTo": "2025-01-01T07:00:00",
      "pointKey": "P-LONG",
      "pointLabel": "Long decimal point",
      "operatorKey": "O1",
      "directionKey": "Entry",
      "periodType": "hour"
    },
    {
      "id": "flow-scientific",
      "indicator": "Physical Flow",
      "value": 1.25e+6,
      "unit": "m3/day",
      "periodFrom": "2025-01-01T06:00:00",
      "periodTo": "2025-01-02T06:00:00",
      "pointKey": "P-SCI",
      "operatorKey": "O2",
      "directionKey": "Exit",
      "periodType": "day"
    },
    {
      "id": "flow-zero",
      "indicator": "Physical Flow",
      "value": 0,
      "unit": "m3/day",
      "periodFrom": "2025-01-01T06:00:00",
      "periodTo": "2025-01-02T06:00:00",
      "pointKey": "P-ZERO",
      "operatorKey": "O3",
      "directionKey": "Entry",
      "periodType": "day"
    },
    {
      "id": "flow-hour",
      "indicator": "Physical Flow",
      "value": 25,
      "unit": "m3/h",
      "periodFrom": "2025-01-01T06:00:00",
      "periodTo": "2025-01-01T07:00:00",
      "pointKey": "P-HOUR",
      "operatorKey": "O4",
      "directionKey": "Entry",
      "periodType": "hour"
    },
    {
      "id": "flow-na",
      "indicator": "Physical Flow",
      "value": "N/A",
      "unit": "m3/day",
      "periodFrom": "2025-01-01T06:00:00",
      "periodTo": "2025-01-02T06:00:00",
      "pointKey": "P-NA",
      "operatorKey": "O5",
      "directionKey": "Entry",
      "periodType": "day"
    }
  ]
}"""

_CAPACITY_RAW = b"""{
  "meta": {"limit": 10, "offset": 0, "count": 2, "total": 2, "sort": "id"},
  "operationaldatas": [
    {
      "id": "cap-volume",
      "indicator": "Firm Technical Capacity",
      "value": 2.5e+6,
      "unit": "m3/h",
      "periodFrom": "2025-01-01T06:00:00",
      "periodTo": "2025-01-01T07:00:00",
      "pointKey": "P-CAP",
      "operatorKey": "O1",
      "directionKey": "Entry",
      "periodType": "hour"
    },
    {
      "id": "cap-energy",
      "indicator": "Firm Booked Capacity",
      "value": 2.5e+6,
      "unit": "MWh/d",
      "periodFrom": "2025-01-01T06:00:00",
      "periodTo": "2025-01-02T06:00:00",
      "pointKey": "P-CAP-ENERGY",
      "operatorKey": "O2",
      "directionKey": "Exit",
      "periodType": "day"
    }
  ]
}"""


def _page(raw_body: bytes, *, dataset: str = "operationaldatas") -> EntsogPage:
    payload = json.loads(raw_body)
    return EntsogPage(
        dataset=dataset,
        offset=0,
        requested_limit=10,
        record_count=len(payload[dataset]),
        provider_total=len(payload[dataset]),
        request_url=f"https://transparency.entsog.example/{dataset}?offset=0",
        received_at_utc=_RECEIPT,
        raw_body=raw_body,
    )


def _row(payload: dict[str, Any], **overrides: object) -> dict[str, Any]:
    return {**payload, **overrides}


def test_native_flow_adapter_preserves_exact_lexemes_and_counts_zero() -> None:
    page = _page(_FLOW_RAW)
    rows = native_entsog_flow_observations_from_json(
        page.numeric_lexeme_payload,
        observed_at_utc=_RECEIPT,
    )
    assert len(rows) == 4
    by_record = {row["source_record_id"]: row for row in rows}

    long_row = by_record["flow-long"]
    assert long_row["native_rate_json"] == {
        "value_text": "12345678901234567890.123456789",
        "unit_text": "MWh/d",
        "native_value": "12345678901234567890.123456789",
        "normalized_unit": "MWh/day",
        "quantity_kind": "energy",
        "rate_basis": "day",
        "energy_kwh_per_day": "12345678901234567890123.456789000",
        "volume_mcm_per_day": None,
        "normalizer_version": NORMALIZER_VERSION,
    }
    assert long_row["flow_mcm_d"] is None
    assert long_row["original_unit"] == "MWh/d"
    assert long_row["original_value"] == float(Decimal("12345678901234567890.123456789"))
    assert long_row["normalizer_version"] == NORMALIZER_VERSION
    assert long_row["kind"] == "actual"
    assert long_row["observation_id"].startswith("entsog-flow-n1-")
    assert len(long_row["observation_id"]) <= 64
    assert long_row["observation_id"] != "entsog-flow-flow-long"
    assert long_row["metadata_json"]["kind"] == "actual"
    assert (
        long_row["metadata_json"]["native_value_basis"]
        == "source_string_or_numeric_lexeme"
    )
    assert long_row["metadata_json"]["normalized_period_start_utc"] == (
        "2025-01-01T05:00:00+00:00"
    )
    assert long_row["metadata_json"]["normalized_period_end_utc"] == (
        "2025-01-01T06:00:00+00:00"
    )
    assert long_row["metadata_json"]["source_receipt_at_utc"] == _RECEIPT.isoformat()
    assert long_row["metadata_json"]["periodType"] == "hour"
    assert validate_native_rate_payload(
        long_row["native_rate_json"], long_row["normalizer_version"]
    ).quantity_kind == "energy"

    assert by_record["flow-scientific"]["flow_mcm_d"] == 1.25
    assert by_record["flow-zero"]["flow_mcm_d"] == 0.0
    assert by_record["flow-zero"]["original_value"] == 0.0
    assert by_record["flow-hour"]["flow_mcm_d"] == pytest.approx(0.0006)
    assert by_record["flow-hour"]["native_rate_json"]["rate_basis"] == "hour"
    assert "flow-na" not in by_record


def test_native_capacity_adapter_scales_m3_hour_and_never_makes_energy_volume() -> None:
    page = _page(_CAPACITY_RAW)
    rows = native_entsog_capacity_observations_from_json(
        page.numeric_lexeme_payload,
        observed_at_utc=_RECEIPT,
    )
    by_record = {row["source_record_id"]: row for row in rows}
    volume_row = by_record["cap-volume"]
    assert volume_row["capacity_type"] == "firm_technical"
    assert volume_row["metadata_json"]["capacity_type"] == "firm_technical"
    assert volume_row["capacity_mcm_d"] == pytest.approx(60.0)
    assert volume_row["native_rate_json"]["rate_basis"] == "hour"
    assert volume_row["observation_id"].startswith("entsog-capacity-n1-")
    assert len(volume_row["observation_id"]) <= 96

    energy_row = by_record["cap-energy"]
    assert energy_row["capacity_mcm_d"] is None
    assert energy_row["native_rate_json"]["quantity_kind"] == "energy"
    assert energy_row["capacity_type"] == "firm_booked"


def test_native_adapter_requires_explicit_aware_receipt() -> None:
    page = _page(_FLOW_RAW)
    with pytest.raises(EntsogNativeObservationError) as missing:
        native_entsog_flow_observations_from_json(page.numeric_lexeme_payload)
    assert missing.value.code == "entsog_native_receipt_required"

    with pytest.raises(EntsogNativeObservationError) as naive:
        native_entsog_flow_observations_from_json(
            page.numeric_lexeme_payload,
            observed_at_utc=_RECEIPT.replace(tzinfo=None),
        )
    assert naive.value.code == "entsog_native_receipt_naive"


def test_native_adapter_refuses_nonstrings_and_unsupported_units() -> None:
    base = {
        "id": "bad",
        "indicator": "Physical Flow",
        "periodFrom": "2025-01-01T06:00:00Z",
        "periodTo": "2025-01-02T06:00:00Z",
        "unit": "m3/day",
    }
    with pytest.raises(EntsogNativeObservationError) as numeric:
        native_entsog_flow_observations_from_json(
            {"operationaldatas": [_row(base, value=1.25)]},
            observed_at_utc=_RECEIPT,
        )
    assert numeric.value.code == "entsog_native_value_type_invalid"

    with pytest.raises(EntsogNativeObservationError) as boolean:
        native_entsog_flow_observations_from_json(
            {"operationaldatas": [_row(base, value=True)]},
            observed_at_utc=_RECEIPT,
        )
    assert boolean.value.code == "entsog_native_value_type_invalid"

    with pytest.raises(EntsogNativeObservationError) as unit:
        native_entsog_flow_observations_from_json(
            {"operationaldatas": [_row(base, value="1.0", unit="MW")]},
            observed_at_utc=_RECEIPT,
        )
    assert unit.value.code == "unsupported_unit"

    with pytest.raises(EntsogNativeObservationError) as unit_type:
        native_entsog_flow_observations_from_json(
            {"operationaldatas": [_row(base, value="1.0", unit=42)]},
            observed_at_utc=_RECEIPT,
        )
    assert unit_type.value.code == "entsog_native_unit_type_invalid"


def test_native_adapter_refuses_equal_or_reversed_periods() -> None:
    base = {
        "id": "bad-period",
        "indicator": "Physical Flow",
        "periodFrom": "2025-01-01T06:00:00Z",
        "unit": "m3/day",
        "value": "1.0",
    }
    for period_to in ("2025-01-01T06:00:00Z", "2025-01-01T05:00:00Z"):
        with pytest.raises(EntsogNativeObservationError) as invalid:
            native_entsog_flow_observations_from_json(
                {"operationaldatas": [_row(base, periodTo=period_to)]},
                observed_at_utc=_RECEIPT,
            )
        assert invalid.value.code == "entsog_native_period_invalid"


def test_public_wrappers_delegate_and_leave_gie_path_unchanged() -> None:
    page = _page(_FLOW_RAW)
    wrapped = entsog_flow_observations_from_json(
        page.numeric_lexeme_payload,
        observed_at_utc=_RECEIPT,
    )
    direct = native_entsog_flow_observations_from_json(
        page.numeric_lexeme_payload,
        observed_at_utc=_RECEIPT,
    )
    assert wrapped == direct
    capacity = entsog_capacity_observations_from_json(
        _page(_CAPACITY_RAW).numeric_lexeme_payload,
        observed_at_utc=_RECEIPT,
    )
    assert capacity == native_entsog_capacity_observations_from_json(
        _page(_CAPACITY_RAW).numeric_lexeme_payload,
        observed_at_utc=_RECEIPT,
    )

    gie_rows = gie_storage_observations_from_json(
        {
            "data": [
                {
                    "code": "DE",
                    "gasDayStart": "2025-01-01",
                    "updatedAt": "2025-01-02T00:00:00Z",
                    "gasInStorage": 1.5,
                }
            ]
        }
    )
    assert len(gie_rows) == 1
    assert gie_rows[0]["source_system"] == "GIE"


def test_persist_uses_numeric_lexeme_payload_and_stamps_raw_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _page(_FLOW_RAW)
    result = EntsogFetchResult(
        dataset="operationaldatas",
        pages=(page,),
        complete=True,
        stop_reason="provider_offset_exhausted",
        budget_records=10,
        budget_pages=10,
    )

    class FakeFlowModel:
        __table__ = SimpleNamespace(name="flow_observations")

    captured: dict[str, Any] = {}

    def fake_archive(session: object, results: object) -> list[list[tuple[EntsogPage, str]]]:
        assert session is not None
        assert list(results) == [result]  # type: ignore[arg-type]
        return [[(page, "raw-test-id")]]

    def fake_upsert(
        session: object,
        model: object,
        rows: list[dict[str, Any]],
    ) -> dict[str, int]:
        assert session is not None
        assert model is FakeFlowModel
        captured["rows"] = rows
        return {"inserted": len(rows), "verified": 0}

    monkeypatch.setattr(entsog_ingestion, "FlowObservationRecord", FakeFlowModel)
    monkeypatch.setattr(entsog_ingestion, "archive_entsog_pages", fake_archive)
    monkeypatch.setattr(entsog_ingestion, "upsert_entsog_observation_rows", fake_upsert)

    summary = entsog_ingestion.persist_entsog_observations(
        object(),
        results=[result],
        model=FakeFlowModel,
        run_id="run-native-1",
    )

    rows = captured["rows"]
    assert len(rows) == 4
    assert summary == {
        "records": 4,
        "received_records": 5,
        "skipped_records": 1,
        "archived_pages": 1,
        "inserted": 4,
        "verified": 0,
    }
    long_row = next(row for row in rows if row["source_record_id"] == "flow-long")
    assert long_row["native_rate_json"]["value_text"] == "12345678901234567890.123456789"
    assert long_row["flow_mcm_d"] is None
    assert long_row["metadata_json"]["raw_archive_id"] == "raw-test-id"
    assert long_row["metadata_json"]["payload_sha256"] == page.payload_sha256
    assert long_row["metadata_json"]["source_receipt_at_utc"] == _RECEIPT.isoformat()
    assert long_row["metadata_json"]["ingestion_run_id"] == "run-native-1"


class _FakeSession:
    def begin_nested(self) -> object:
        return nullcontext()


class _FakeFlowModel:
    __table__ = SimpleNamespace(name="flow_observations")


def _native_flow_rows() -> list[dict[str, Any]]:
    return native_entsog_flow_observations_from_json(
        _page(_FLOW_RAW).numeric_lexeme_payload,
        observed_at_utc=_RECEIPT,
    )


def test_repository_compares_native_columns_and_accepts_legacy_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_upsert(
        session: object,
        model: object,
        rows: list[dict[str, Any]],
        *,
        semantic_fields: tuple[str, ...],
    ) -> dict[str, int]:
        captured["rows"] = rows
        captured["fields"] = semantic_fields
        return {"inserted": len(rows), "verified": 0}

    monkeypatch.setattr(
        persistence,
        "upsert_revision_safe_observation_rows",
        fake_upsert,
    )
    native_row = _native_flow_rows()[0]
    outcome = persistence.upsert_entsog_observation_rows(
        _FakeSession(),
        _FakeFlowModel,
        [native_row],
    )
    assert outcome == {"inserted": 1, "verified": 0}
    assert "normalizer_version" in captured["fields"]
    assert "native_rate_json" in captured["fields"]
    assert captured["rows"][0]["native_rate_json"] == native_row["native_rate_json"]

    legacy = {
        key: value
        for key, value in native_row.items()
        if key not in {"normalizer_version", "native_rate_json"}
    }
    legacy["observation_id"] = "entsog-flow-flow-long"
    legacy["flow_mcm_d"] = 1.0
    persistence.upsert_entsog_observation_rows(
        _FakeSession(),
        _FakeFlowModel,
        [legacy],
    )
    assert captured["rows"][0]["observation_id"] == "entsog-flow-flow-long"


def test_repository_refuses_energy_volume_and_legacy_id_for_native_content() -> None:
    native_row = _native_flow_rows()[0]
    with pytest.raises(persistence.EntsogInvalidObservationError):
        persistence.upsert_entsog_observation_rows(
            _FakeSession(),
            _FakeFlowModel,
            [_row(native_row, flow_mcm_d=1.0)],
        )

    with pytest.raises(persistence.EntsogInvalidObservationError):
        persistence.upsert_entsog_observation_rows(
            _FakeSession(),
            _FakeFlowModel,
            [_row(native_row, observation_id="entsog-flow-flow-long")],
        )


def test_repository_changed_native_content_is_typed_revision_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_upsert(
        session: object,
        model: object,
        rows: list[dict[str, Any]],
        *,
        semantic_fields: tuple[str, ...],
    ) -> dict[str, int]:
        raise GieRevisionRequiresHistoryError("changed native content")

    monkeypatch.setattr(
        persistence,
        "upsert_revision_safe_observation_rows",
        fake_upsert,
    )
    with pytest.raises(persistence.EntsogRevisionRequiresHistoryError):
        persistence.upsert_entsog_observation_rows(
            _FakeSession(),
            _FakeFlowModel,
            [_native_flow_rows()[0]],
        )


def test_repository_refuses_perturbed_native_volume_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native_row = next(
        row
        for row in _native_flow_rows()
        if row["source_record_id"] == "flow-scientific"
    )
    canonical = native_row["flow_mcm_d"]
    assert isinstance(canonical, float)
    # The old 1e-12 tolerance accepted this drift; the stored projection is exact.
    perturbed = _row(native_row, flow_mcm_d=canonical + 1e-13)
    legacy = {
        key: value
        for key, value in native_row.items()
        if key not in {"normalizer_version", "native_rate_json"}
    }
    legacy["observation_id"] = "entsog-flow-flow-scientific"
    legacy["flow_mcm_d"] = 123.0
    legacy_snapshot = dict(legacy)

    calls: list[list[dict[str, Any]]] = []

    def fake_upsert(
        session: object,
        model: object,
        rows: list[dict[str, Any]],
        *,
        semantic_fields: tuple[str, ...],
    ) -> dict[str, int]:
        calls.append(rows)
        return {"inserted": len(rows), "verified": 0}

    monkeypatch.setattr(
        persistence,
        "upsert_revision_safe_observation_rows",
        fake_upsert,
    )
    with pytest.raises(persistence.EntsogInvalidObservationError):
        persistence.upsert_entsog_observation_rows(
            _FakeSession(),
            _FakeFlowModel,
            [perturbed, legacy],
        )
    assert calls == []
    assert legacy == legacy_snapshot

    outcome = persistence.upsert_entsog_observation_rows(
        _FakeSession(),
        _FakeFlowModel,
        [legacy],
    )
    assert outcome == {"inserted": 1, "verified": 0}
    assert calls[0][0]["flow_mcm_d"] == 123.0
    assert calls[0][0]["normalizer_version"] is None
    assert calls[0][0]["native_rate_json"] is None
    assert legacy == legacy_snapshot
