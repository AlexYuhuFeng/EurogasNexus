"""EEX TTF NGP local capture-inspection tests — synthetic bytes only, no network or database.

Every CSV below is hand-built to the operator-verified five-column shape. No downloaded EEX
value is recorded here; all prices, volumes and timestamps are invented placeholders.

The tests pin four properties that make the seam useful rather than merely convenient:

1. the exact bytes are hashed before decoding, so BOM/CRLF/re-encoding are visible;
2. the existing pure parser supplies row validation, while the explicit unproven timezone
   contract keeps every row pending and the canonical mapper is never called;
3. raw decimal strings (including trailing zeros and high precision) survive without a float
   round trip, and missing/zero price/volume distinctions remain visible;
4. source-level blockers stay separate from row-level rejections, and the CLI is bounded,
   local-file-only and traceback-free.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from eurogas_nexus.domain.ingestion.source_timezone import SourceTimezoneContract
from eurogas_nexus.ingestion import eex_ngp
from eurogas_nexus.ingestion.eex_ngp_capture import (
    MAX_CAPTURE_BYTES,
    REPORT_VERSION,
    EexNgpCaptureError,
    inspect_eex_ngp_capture,
    serialize_capture_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURE_MODULE = REPO_ROOT / "src" / "eurogas_nexus" / "ingestion" / "eex_ngp_capture.py"
CAPTURE_CLI = REPO_ROOT / "scripts" / "ops" / "inspect_eex_ngp_capture.py"
HEADER = "Gasday;IndexValue (€/MWh);IndexVolume (MWh);Status;Timestamp Let"
RETRIEVED_AT = datetime(2026, 5, 29, 15, 5, tzinfo=UTC)


def _csv_bytes(
    *rows: str,
    bom: bool = True,
    newline: str = "\n",
) -> bytes:
    text = newline.join([HEADER, *rows]) + newline
    encoded = text.encode("utf-8")
    return (b"\xef\xbb\xbf" + encoded) if bom else encoded


def _forbidden_imports(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source_path = str(REPO_ROOT / "src")
    parts = [part for part in environment.get("PYTHONPATH", "").split(os.pathsep) if part]
    if source_path not in parts:
        parts.insert(0, source_path)
    environment["PYTHONPATH"] = os.pathsep.join(parts)
    return subprocess.run(
        [sys.executable, str(CAPTURE_CLI), *arguments],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _assert_no_traceback(result: subprocess.CompletedProcess[str]) -> None:
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def _error(data: bytes, **kwargs: object) -> EexNgpCaptureError:
    with pytest.raises(EexNgpCaptureError) as raised:
        inspect_eex_ngp_capture(
            data,
            retrieved_at_utc=kwargs.pop("retrieved_at_utc", RETRIEVED_AT),  # type: ignore[arg-type]
            **kwargs,  # type: ignore[arg-type]
        )
    return raised.value


def test_report_preserves_exact_bytes_urls_and_self_describing_provenance() -> None:
    raw = _csv_bytes("29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30")

    report = inspect_eex_ngp_capture(raw, retrieved_at_utc=RETRIEVED_AT)

    assert report["report_version"] == REPORT_VERSION
    assert report["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["raw_byte_length"] == len(raw)
    assert report["encoding"] == "utf-8"
    assert report["bom_present"] is True
    assert report["source_system"] == "EEX"
    assert report["source_dataset"] == "ttf-ngp-15min"
    assert report["source_file_url"] == eex_ngp.SOURCE_FILE_URL
    assert report["source_page_url"] == eex_ngp.SOURCE_PAGE_URL
    assert report["retrieved_at_utc"] == "2026-05-29T15:05:00+00:00"
    assert report["retrieved_at_source"] == "operator_supplied"
    assert report["provenance"]["basis"] == "operator_supplied_local_file"
    assert report["provenance"]["provider_authenticity"] == "not_proven_by_bytes_or_hash"
    assert "do not prove" in report["provenance"]["note"]

    assert report["canonicalization_allowed"] is False
    assert report["executable_quote"] is False
    assert report["canonical_publication"]["allowed"] is False
    assert report["canonical_publication"]["publication_time_utc"] is None
    assert report["canonical_publication"]["period_start_utc"] is None
    assert report["canonical_publication"]["period_end_utc"] is None
    assert report["timezone_contract"]["declared_zone"] is None

    assert report["ok"] is True
    assert report["inspection_status"] == "complete"
    assert report["row_count"] == 1
    row = report["rows"][0]
    assert row["row_number"] == 2
    assert row["gas_day_raw"] == "29/05/2026"
    assert row["timestamp_raw"] == "29/05/2026 14:30"
    assert row["status_raw"] == "Final NGP"
    assert row["status"] == "final"
    assert row["index_value_raw"] == "31.400"
    assert row["index_volume_raw"] == "1200.5"
    assert row["price_available"] is True
    assert row["unavailable_reason"] is None
    assert row["normalization_status"] == "pending_source_timezone"
    assert row["publication_time_utc"] is None
    assert row["period_start_utc"] is None
    assert row["period_end_utc"] is None

    # JSON-safe means a strict round trip, not merely "json.dumps accepted it somewhere".
    assert json.loads(json.dumps(report)) == report


def test_bom_and_line_endings_change_the_hash_and_length_not_the_parsed_rows() -> None:
    row = "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30"
    bom_lf = _csv_bytes(row, bom=True, newline="\n")
    plain_lf = _csv_bytes(row, bom=False, newline="\n")
    plain_crlf = _csv_bytes(row, bom=False, newline="\r\n")

    reports = [
        inspect_eex_ngp_capture(payload, retrieved_at_utc=RETRIEVED_AT)
        for payload in (bom_lf, plain_lf, plain_crlf)
    ]

    assert [report["bom_present"] for report in reports] == [True, False, False]
    assert [report["raw_byte_length"] for report in reports] == [
        len(bom_lf),
        len(plain_lf),
        len(plain_crlf),
    ]
    assert len({report["raw_sha256"] for report in reports}) == 3
    assert reports[2]["raw_byte_length"] == len(plain_lf) + 2  # two physical CRLF endings
    assert all(report["raw_sha256"] == hashlib.sha256(payload).hexdigest()
               for report, payload in zip(reports, (bom_lf, plain_lf, plain_crlf), strict=True))
    assert {report["rows"][0]["index_value_raw"] for report in reports} == {"31.400"}
    assert {report["rows"][0]["gas_day_raw"] for report in reports} == {"29/05/2026"}


def test_hash_covers_trailing_bytes_that_row_parsing_may_ignore() -> None:
    row = "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30"
    base = _csv_bytes(row)
    padded = base + b" \r\n"

    base_report = inspect_eex_ngp_capture(base, retrieved_at_utc=RETRIEVED_AT)
    padded_report = inspect_eex_ngp_capture(padded, retrieved_at_utc=RETRIEVED_AT)

    assert base_report["raw_sha256"] == hashlib.sha256(base).hexdigest()
    assert padded_report["raw_sha256"] == hashlib.sha256(padded).hexdigest()
    assert base_report["raw_sha256"] != padded_report["raw_sha256"]
    assert padded_report["raw_byte_length"] == len(base) + 3
    assert base_report["rows"] == padded_report["rows"]


def test_high_precision_and_trailing_zero_decimals_remain_exact_text() -> None:
    value = "31.4000000000000000000000000001"
    volume = "1200.500000000000000000000000"
    zero_price = "0.000000000000000000000000"
    report = inspect_eex_ngp_capture(
        _csv_bytes(
            f"29/05/2026;{value};{volume};Final NGP;29/05/2026 14:30",
            f"29/05/2026;{zero_price};123.4500;Temporary NGP;29/05/2026 14:45",
        ),
        retrieved_at_utc=RETRIEVED_AT,
    )

    first, second = report["rows"]
    assert first["index_value_raw"] == value
    assert first["index_value_exact"] == value
    assert first["index_volume_raw"] == volume
    assert first["index_volume_exact"] == volume
    assert isinstance(first["index_value_raw"], str)
    assert first["price_available"] is True

    # A zero price with positive traded volume is available; it is not missing/unavailable.
    assert second["index_value_raw"] == zero_price
    assert second["index_volume_raw"] == "123.4500"
    assert second["price_available"] is True
    assert second["unavailable_reason"] is None
    assert "price" not in second  # no float/price reinterpretation is emitted


def test_missing_zero_and_negative_price_volume_states_stay_distinct() -> None:
    report = inspect_eex_ngp_capture(
        _csv_bytes(
            "29/05/2026;;1200.5;Final NGP;29/05/2026 14:30",
            "29/05/2026;0;0;Temporary NGP;29/05/2026 14:45",
            "29/05/2026;31.5;;Final NGP;29/05/2026 15:00",
            "29/05/2026;0.000;1200.5;Final NGP;29/05/2026 15:15",
            "29/05/2026;-4.250;10;Final NGP;29/05/2026 15:30",
        ),
        retrieved_at_utc=RETRIEVED_AT,
    )

    missing_value, zero_volume, missing_volume, zero_price, negative = report["rows"]
    assert missing_value["index_value_raw"] == ""
    assert (missing_value["price_available"], missing_value["unavailable_reason"]) == (
        False,
        "missing_index_value",
    )
    assert zero_volume["index_value_raw"] == "0"
    assert (zero_volume["price_available"], zero_volume["unavailable_reason"]) == (
        False,
        "zero_volume",
    )
    assert missing_volume["index_volume_raw"] == ""
    assert (missing_volume["price_available"], missing_volume["unavailable_reason"]) == (
        False,
        "missing_index_volume",
    )
    assert zero_price["index_value_raw"] == "0.000"
    assert (zero_price["price_available"], zero_price["unavailable_reason"]) == (True, None)
    assert negative["index_value_raw"] == "-4.250"
    assert negative["index_value_exact"] == "-4.250"
    assert (negative["price_available"], negative["unavailable_reason"]) == (True, None)


def test_final_and_temporary_rows_are_both_reported_without_revision_overwrite() -> None:
    report = inspect_eex_ngp_capture(
        _csv_bytes(
            "29/05/2026;31.100;900.0;Temporary NGP;29/05/2026 14:30",
            "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
        ),
        retrieved_at_utc=RETRIEVED_AT,
    )

    temporary, final = report["rows"]
    assert (temporary["status"], temporary["status_raw"], temporary["is_provisional"]) == (
        "temporary",
        "Temporary NGP",
        True,
    )
    assert (final["status"], final["status_raw"], final["is_provisional"]) == (
        "final",
        "Final NGP",
        False,
    )
    assert temporary["index_value_raw"] != final["index_value_raw"]


def test_row_level_rejections_are_reported_and_kept_out_of_source_blockers() -> None:
    report = inspect_eex_ngp_capture(
        _csv_bytes(
            "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
            "29/05/2026;not-a-number;1200.5;Final NGP;29/05/2026 14:45",
            "29/05/2026;31.4;10;Settled NGP;29/05/2026 15:00",
        ),
        retrieved_at_utc=RETRIEVED_AT,
    )

    assert report["ok"] is False
    assert report["inspection_status"] == "complete_with_rejections"
    assert report["row_count"] == 1
    assert report["rejected_row_count"] == 2
    assert [(item["row_number"], item["reason"]) for item in report["rejections"]] == [
        (3, "invalid_index_value"),
        (4, "unknown_status"),
    ]
    assert "not-a-number" in report["rejections"][0]["detail"]
    blocker_codes = {item["code"] for item in report["blockers"]}
    assert blocker_codes.isdisjoint({item["reason"] for item in report["rejections"]})
    assert report["canonicalization_allowed"] is False


def test_duplicate_natural_keys_refuse_the_capture_instead_of_deduplicating() -> None:
    payload = _csv_bytes(
        "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
        "29/05/2026;31.500;1300.0;Final NGP;29/05/2026 14:30",
    )

    error = _error(payload)

    assert error.code == "duplicate_observation_key"
    assert error.parser_code == "duplicate_observation_key"
    assert "2" in error.message and "3" in error.message


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ("not-bytes", "invalid_input_type"),
        (bytearray(b"Gasday"), "invalid_input_type"),
        (memoryview(b"Gasday"), "invalid_input_type"),
        (b"", "empty_payload"),
        (b"\xef\xbb\xbf\r\n\t", "empty_payload"),
        (b"\xff\xfe\x00", "invalid_utf8"),
        (b"<html><body>not csv</body></html>", "html_payload"),
        (b"\xef\xbb\xbf  <!DOCTYPE html><html></html>", "html_payload"),
        (b"Gasday,IndexValue\n29/05/2026,31.4\n", "malformed_csv"),
        (b"\x00\x01\x02", "malformed_csv"),
    ],
)
def test_bad_payloads_are_refused_with_stable_codes(payload: object, code: str) -> None:
    error = _error(payload)  # type: ignore[arg-type]

    assert error.code == code


def test_oversized_bytes_are_refused_before_any_hashing_or_decoding() -> None:
    error = _error(b"x" * (MAX_CAPTURE_BYTES + 1))

    assert error.code == "payload_too_large"
    assert str(MAX_CAPTURE_BYTES) in error.message


def test_malformed_header_maps_to_malformed_csv_but_preserves_the_parser_code() -> None:
    error = _error(
        _csv_bytes("29/05/2026;31.4;10;Final NGP;29/05/2026 14:30").replace(
            b"Gasday;IndexValue", b"Gasday;WrongValue"
        )
    )

    assert error.code == "malformed_csv"
    assert error.parser_code == "unexpected_header"


def test_retrieval_instant_is_required_aware_and_normalized_to_utc() -> None:
    payload = _csv_bytes("29/05/2026;31.4;10;Final NGP;29/05/2026 14:30")

    with pytest.raises(TypeError):
        inspect_eex_ngp_capture(payload)  # type: ignore[call-arg]

    naive = _error(payload, retrieved_at_utc=datetime(2026, 5, 29, 15, 5))
    assert naive.code == "naive_retrieval_timestamp"

    invalid = _error(payload, retrieved_at_utc="2026-05-29T15:05:00+00:00")
    assert invalid.code == "invalid_retrieval_timestamp"

    supplied = datetime(2026, 5, 29, 17, 5, 0, tzinfo=timezone(timedelta(hours=2)))
    report = inspect_eex_ngp_capture(payload, retrieved_at_utc=supplied)
    assert report["retrieved_at_utc"] == "2026-05-29T15:05:00+00:00"
    assert report["retrieved_at_utc_supplied"] == "2026-05-29T17:05:00+02:00"
    # The retrieval clock is not a source timestamp and is never assigned to a row.
    assert report["rows"][0]["publication_time_utc"] is None


def test_explicit_unproven_contract_survives_a_future_proven_repository_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proven_elsewhere = SourceTimezoneContract(
        source_system="EEX",
        datasets=("ttf-ngp-15min",),
        declared_zone=ZoneInfo("UTC"),
        evidence="synthetic future default for this guard test only",
    )
    monkeypatch.setattr(eex_ngp, "contract_for", lambda *_args, **_kwargs: proven_elsewhere)

    report = inspect_eex_ngp_capture(
        _csv_bytes("29/05/2026;31.4;10;Final NGP;29/05/2026 14:30"),
        retrieved_at_utc=RETRIEVED_AT,
    )

    assert report["timezone_contract"]["declared_zone"] is None
    assert report["rows"][0]["normalization_status"] == "pending_source_timezone"
    assert report["rows"][0]["publication_time_utc"] is None
    assert report["canonicalization_allowed"] is False


def test_dst_ambiguous_wall_clock_is_not_resolved_without_a_proven_zone() -> None:
    report = inspect_eex_ngp_capture(
        _csv_bytes("25/10/2026;31.4;10;Final NGP;25/10/2026 02:30"),
        retrieved_at_utc=RETRIEVED_AT,
    )

    assert report["rejections"] == []
    row = report["rows"][0]
    assert row["normalization_status"] == "pending_source_timezone"
    assert row["publication_time_utc"] is None
    assert row["period_start_utc"] is None
    assert row["period_end_utc"] is None
    assert report["canonical_publication"]["publication_time_utc"] is None


def test_source_level_blockers_are_explicit_and_independent_of_row_validity() -> None:
    report = inspect_eex_ngp_capture(
        _csv_bytes("29/05/2026;31.4;10;Final NGP;29/05/2026 14:30"),
        retrieved_at_utc=RETRIEVED_AT,
    )

    assert report["rejections"] == []
    codes = {item["code"] for item in report["blockers"]}
    assert codes == {
        "unproven_publication_timezone",
        "unproven_gas_day_calendar",
        "unproven_delivery_granularity",
        "rights_and_certification_not_assessed",
    }
    assert all(item["distinct_from_row_parse_validity"] is True for item in report["blockers"])
    assert all(item["blocks_canonical_publication"] is True for item in report["blockers"])
    assert report["publication_timezone_proven"] is False
    assert report["gas_day_calendar_proven"] is False
    assert report["delivery_granularity_proven"] is False
    assert report["rights_or_certification_assessed"] is False
    assert "15-minute" in report["canonical_publication"]["note"]


def test_report_serialization_is_bounded_and_requires_json_safe_values() -> None:
    oversized = {"payload": "x" * MAX_CAPTURE_BYTES}
    with pytest.raises(EexNgpCaptureError) as over_limit:
        serialize_capture_report(oversized)
    assert over_limit.value.code == "report_too_large"

    with pytest.raises(EexNgpCaptureError) as unsafe:
        serialize_capture_report({"value": object()})
    assert unsafe.value.code == "report_not_json_safe"


def test_capture_and_cli_are_offline_pure_and_never_call_the_canonical_mapper() -> None:
    forbidden = {
        "httpx",
        "requests",
        "socket",
        "urllib",
        "sqlalchemy",
        "psycopg",
        "psycopg2",
        "alembic",
        "subprocess",
        "os",
        "time",
        "platform",
    }
    assert _forbidden_imports(CAPTURE_MODULE).isdisjoint(forbidden)
    assert _forbidden_imports(CAPTURE_CLI).isdisjoint(forbidden)

    capture_source = CAPTURE_MODULE.read_text(encoding="utf-8")
    cli_source = CAPTURE_CLI.read_text(encoding="utf-8")
    assert "eex_ttf_ngp_market_observations" not in capture_source
    assert "eex_ttf_ngp_market_observations" not in cli_source
    assert "datetime.now" not in capture_source
    assert "datetime.now" not in cli_source

    # The CLI must read boundedly rather than slurping an arbitrary local file.
    for node in ast.walk(ast.parse(cli_source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr != "read_bytes"


def test_cli_success_prints_json_and_still_prohibits_canonical_publication(
    tmp_path: Path,
) -> None:
    raw = _csv_bytes("29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30")
    path = tmp_path / "synthetic_ngp.csv"
    path.write_bytes(raw)

    result = _run_cli(
        "--input",
        str(path),
        "--retrieved-at",
        "2026-05-29T17:05:00+02:00",
    )

    _assert_no_traceback(result)
    assert result.returncode == 0, result.stdout
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["retrieved_at_utc"] == "2026-05-29T15:05:00+00:00"
    assert report["canonicalization_allowed"] is False
    assert report["executable_quote"] is False
    assert report["canonical_publication"]["allowed"] is False
    assert report["rows"][0]["price_available"] is True
    assert report["rows"][0]["publication_time_utc"] is None
    # The input is evidence, not an output target.
    assert path.read_bytes() == raw


def test_cli_rejected_rows_are_nonzero_with_a_usable_report(tmp_path: Path) -> None:
    path = tmp_path / "rejected.csv"
    path.write_bytes(
        _csv_bytes(
            "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30",
            "29/05/2026;31.400;1200.5;Settled NGP;29/05/2026 14:45",
        )
    )

    result = _run_cli(
        "--input", str(path), "--retrieved-at", "2026-05-29T15:05:00+00:00"
    )

    _assert_no_traceback(result)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert report["rejections"][0]["reason"] == "unknown_status"
    assert report["canonicalization_allowed"] is False


def test_cli_refusals_are_nonzero_safe_and_stable(tmp_path: Path) -> None:
    valid = tmp_path / "valid.csv"
    valid.write_bytes(_csv_bytes("29/05/2026;31.4;10;Final NGP;29/05/2026 14:30"))
    invalid_utf8 = tmp_path / "invalid_utf8.csv"
    invalid_utf8.write_bytes(b"\xff\xfe\x00")
    directory = tmp_path / "a_directory"
    directory.mkdir()
    missing = tmp_path / "missing.csv"

    cases = [
        ([], 2, "invalid_arguments"),
        (
            ["--input", str(valid), "--retrieved-at", "not-a-timestamp"],
            2,
            "invalid_retrieved_at",
        ),
        (
            ["--input", str(missing), "--retrieved-at", "2026-05-29T15:05:00+00:00"],
            2,
            "input_not_found",
        ),
        (
            ["--input", str(directory), "--retrieved-at", "2026-05-29T15:05:00+00:00"],
            2,
            "input_read_error",
        ),
        (
            ["--input", str(invalid_utf8), "--retrieved-at", "2026-05-29T15:05:00+00:00"],
            1,
            "invalid_utf8",
        ),
        (
            ["--input", str(valid), "--retrieved-at", "2026-05-29T15:05:00"],
            1,
            "naive_retrieval_timestamp",
        ),
    ]

    for arguments, expected_exit, expected_code in cases:
        result = _run_cli(*arguments)
        _assert_no_traceback(result)
        assert result.returncode == expected_exit, (arguments, result.stdout, result.stderr)
        error = json.loads(result.stdout)["error"]
        assert error["code"] == expected_code
        assert "message" in error


def test_cli_reads_boundedly_and_refuses_an_oversized_file(tmp_path: Path) -> None:
    path = tmp_path / "oversized.csv"
    path.write_bytes(b"x" * (MAX_CAPTURE_BYTES + 1))

    result = _run_cli(
        "--input", str(path), "--retrieved-at", "2026-05-29T15:05:00+00:00"
    )

    _assert_no_traceback(result)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "payload_too_large"


def test_cli_has_no_download_option(tmp_path: Path) -> None:
    result = _run_cli(
        "--input",
        "https://gasandregistry.eex.com/Gas/NGP/TTF_NGP_15_Mins.csv",
        "--retrieved-at",
        "2026-05-29T15:05:00+00:00",
    )

    _assert_no_traceback(result)
    assert result.returncode == 2
    # The URL is treated as a local path, never fetched; this host's OS may report a missing
    # path or an unusable path, both of which are bounded local-file refusals.
    assert json.loads(result.stdout)["error"]["code"] in {
        "input_not_found",
        "input_read_error",
    }

    unsupported = _run_cli("--url", "https://example.invalid/data.csv")
    _assert_no_traceback(unsupported)
    assert unsupported.returncode == 2
    assert json.loads(unsupported.stdout)["error"]["code"] == "invalid_arguments"
