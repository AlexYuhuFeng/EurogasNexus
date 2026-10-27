"""ALSI source units are not assumed to be energy.

The reviewed GIE API documentation v007 (4 October 2022) documents ``inventory`` and
``dtmi`` as LNG volume in 10**3 m3, and ``sendOut`` as GWh/d. Repository synthetic
fixtures also use ``{"lng": ..., "gwh": ...}`` objects for inventory/DTMI. Only an
explicit ``gwh`` member is energy. Later GIE document versions were not retrieved for
this task, so these tests pin the reviewed contract and the fail-closed seam only.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eurogas_nexus.ingestion.public_sources import (
    gie_lng_observations_from_json,
    gie_storage_observations_from_json,
)


def _payload(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "code": "EU",
        "name": "EU LNG",
        "gasDayStart": "2026-05-29",
        "gasDayEnd": "2026-05-30",
        "updatedAt": "2026-05-29T14:00:00+02:00",
    }
    record.update(overrides)
    return {"data": [record]}


def _row(**overrides: object) -> dict:
    return gie_lng_observations_from_json(_payload(**overrides))[0]


def test_scalar_inventory_and_dtmi_are_refused_as_energy() -> None:
    row = _row(inventory="9.5", sendOut="3.4", dtmi="14.4")

    assert row["inventory_twh"] is None
    assert row["dtmi_twh"] is None
    assert row["send_out_twh_d"] == pytest.approx(0.0034)

    provenance = row["metadata_json"]["measurement_provenance"]
    assert provenance["inventory"] == {
        "raw": "9.5",
        "shape": "scalar",
        "energy_basis": "scalar_volume_not_energy",
    }
    assert provenance["dtmi"] == {
        "raw": "14.4",
        "shape": "scalar",
        "energy_basis": "scalar_volume_not_energy",
    }
    assert provenance["send_out"]["energy_basis"] == "scalar_gwh_per_day"
    assert row["metadata_json"]["unit_warnings"] == [
        "inventory_scalar_volume_not_converted",
        "dtmi_scalar_volume_not_converted",
    ]


def test_lng_only_objects_are_volume_not_energy() -> None:
    row = _row(inventory={"lng": "9.5"}, dtmi={"lng": "14.4"})

    assert row["inventory_twh"] is None
    assert row["dtmi_twh"] is None

    provenance = row["metadata_json"]["measurement_provenance"]
    assert provenance["inventory"] == {
        "raw": {"lng": "9.5"},
        "shape": "nested",
        "energy_basis": "literal_lng_volume",
    }
    assert provenance["dtmi"] == {
        "raw": {"lng": "14.4"},
        "shape": "nested",
        "energy_basis": "literal_lng_volume",
    }
    assert row["metadata_json"]["unit_warnings"] == [
        "inventory_lng_volume_without_explicit_gwh",
        "dtmi_lng_volume_without_explicit_gwh",
    ]


def test_explicit_gwh_including_zero_is_converted() -> None:
    row = _row(inventory={"gwh": 0}, dtmi={"gwh": "0.0"}, sendOut=0)

    assert row["inventory_twh"] == 0.0
    assert row["inventory_twh"] is not None
    assert row["dtmi_twh"] == 0.0
    assert row["dtmi_twh"] is not None
    assert row["send_out_twh_d"] == 0.0
    assert row["send_out_twh_d"] is not None
    assert row["metadata_json"]["unit_warnings"] == []


def test_mixed_nested_gwh_and_lng_preserve_both_raw_members() -> None:
    row = _row(
        inventory={"lng": "9.5", "gwh": "42.5"},
        dtmi={"lng": "14.4", "gwh": "65.0"},
    )

    assert row["inventory_twh"] == pytest.approx(0.0425)
    assert row["dtmi_twh"] == pytest.approx(0.065)

    provenance = row["metadata_json"]["measurement_provenance"]
    assert provenance["inventory"]["raw"] == {"lng": "9.5", "gwh": "42.5"}
    assert provenance["dtmi"]["raw"] == {"lng": "14.4", "gwh": "65.0"}
    assert provenance["inventory"]["energy_basis"] == "explicit_gwh"
    assert provenance["dtmi"]["energy_basis"] == "explicit_gwh"
    assert row["metadata_json"]["unit_warnings"] == []


def test_send_out_scalar_is_gwh_per_day() -> None:
    row = _row(sendOut="3.4")

    assert row["send_out_twh_d"] == pytest.approx(0.0034)
    assert row["metadata_json"]["measurement_provenance"]["send_out"] == {
        "raw": "3.4",
        "shape": "scalar",
        "energy_basis": "scalar_gwh_per_day",
    }
    assert row["metadata_json"]["unit_warnings"] == []


def test_send_out_lng_only_is_not_energy() -> None:
    row = _row(sendOut={"lng": "3.4"})

    assert row["send_out_twh_d"] is None
    assert row["metadata_json"]["measurement_provenance"]["send_out"] == {
        "raw": {"lng": "3.4"},
        "shape": "nested",
        "energy_basis": "literal_lng_volume",
    }
    assert row["metadata_json"]["unit_warnings"] == [
        "send_out_lng_volume_without_explicit_gwh"
    ]


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        float("nan"),
        float("inf"),
        float("-inf"),
        "nan",
        "NaN",
        "inf",
        "-Infinity",
    ],
)
def test_boolean_and_nonfinite_explicit_energy_fail_closed(value: object) -> None:
    row = _row(inventory={"gwh": value}, dtmi={"gwh": value}, sendOut=value)

    assert row["inventory_twh"] is None
    assert row["dtmi_twh"] is None
    assert row["send_out_twh_d"] is None

    warnings = row["metadata_json"]["unit_warnings"]
    assert "inventory_explicit_gwh_invalid" in warnings
    assert "dtmi_explicit_gwh_invalid" in warnings
    assert "send_out_scalar_gwh_invalid" in warnings


@pytest.mark.parametrize("value", ["", "not-a-number", [], {"value": "1"}])
def test_malformed_explicit_gwh_fails_closed(value: object) -> None:
    row = _row(inventory={"gwh": value}, dtmi={"gwh": value})

    assert row["inventory_twh"] is None
    assert row["dtmi_twh"] is None

    warnings = row["metadata_json"]["unit_warnings"]
    assert "inventory_explicit_gwh_invalid" in warnings
    assert "dtmi_explicit_gwh_invalid" in warnings


def test_alsi_calendar_and_provenance_are_unchanged() -> None:
    row = _row(
        inventory={"gwh": "42.5"},
        sendOut="3.4",
        dtmi={"gwh": "65.0"},
    )

    assert row["observation_id"] == "gie-alsi-EU-2026-05-29"
    assert row["period_start_utc"] == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)
    assert row["period_end_utc"] == datetime(2026, 5, 30, 4, 0, tzinfo=UTC)
    assert row["observed_at_utc"] == datetime(2026, 5, 29, 12, 0, tzinfo=UTC)

    metadata = row["metadata_json"]
    assert metadata["calendar_version"] == "EU-CAM-UTC-2025"
    assert metadata["availability_basis"] == "provider_updated_at"
    assert metadata["provider_updated_at_zone"] == "provider_offset"
    assert metadata["updatedAt"] == "2026-05-29T14:00:00+02:00"
    assert "v007" in metadata["unit_contract"]
    assert "2022-10-04" in metadata["unit_contract"]
    assert "later versions unverified" in metadata["unit_contract"]


def test_alsi_bare_updated_at_receipt_provenance_is_unchanged() -> None:
    receipt = datetime(2026, 10, 9, 22, 45, tzinfo=UTC)

    rows = gie_lng_observations_from_json(
        _payload(updatedAt="2026-05-29 12:00:00", inventory={"gwh": "42.5"}),
        observed_at_utc=receipt,
    )

    assert rows[0]["observed_at_utc"] == receipt
    assert rows[0]["metadata_json"]["availability_basis"] == "response_receipt"
    assert rows[0]["metadata_json"]["provider_updated_at_zone"] == "unproven"
    assert rows[0]["period_start_utc"] == datetime(2026, 5, 29, 4, 0, tzinfo=UTC)
    assert rows[0]["period_end_utc"] == datetime(2026, 5, 30, 4, 0, tzinfo=UTC)


def test_agsi_scalar_energy_conversion_is_not_rewritten() -> None:
    payload = {
        "data": [
            {
                "code": "EU",
                "name": "EU",
                "gasDayStart": "2026-05-29",
                "gasDayEnd": "2026-05-30",
                "gasInStorage": "650.25",
                "workingGasVolume": "1100.50",
                "full": "59.1",
                "injection": "2.5",
                "withdrawal": "1.2",
                "updatedAt": "2026-05-29T14:00:00+02:00",
            }
        ]
    }

    rows = gie_storage_observations_from_json(payload)

    assert rows[0]["inventory_twh"] == 650.25
    assert rows[0]["injection_twh_d"] == 0.0025
    assert rows[0]["withdrawal_twh_d"] == 0.0012
