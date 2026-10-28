"""Tests for the bounded ECMWF single-point capture probe."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import types
from datetime import date
from pathlib import Path

import pytest


def _load_probe() -> types.ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "ops"
        / "probe_ecmwf_degree_days.py"
    )
    spec = importlib.util.spec_from_file_location("probe_ecmwf_degree_days", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = _load_probe()


@dataclasses.dataclass
class _Field:
    source: str
    run_date: date
    cycle_hour: int
    step_hours: int
    grib_bytes: bytes


@dataclasses.dataclass
class _Decoded:
    step_hours: int


class _UpstreamFailure(RuntimeError):
    code = "UPSTREAM_FAILED"


class _FakeClient:
    def __init__(self, fields: dict[int, _Field], error_at: int | None = None) -> None:
        self.fields = fields
        self.error_at = error_at
        self.requests: list[object] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def retrieve(self, request: object) -> _Field:
        self.requests.append(request)
        step_hours = request.step_hours
        if step_hours == self.error_at:
            raise _UpstreamFailure(
                "token=secret-token-123 https://provider.invalid/private"
            )
        return self.fields[step_hours]


def _field(step: int, payload: bytes) -> _Field:
    return _Field(
        source="ecmwf",
        run_date=date(2026, 1, 1),
        cycle_hour=0,
        step_hours=step,
        grib_bytes=payload,
    )


def _install(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> None:
    monkeypatch.setattr(probe, "EcmwfOpenDataClient", lambda source: client)
    monkeypatch.setattr(
        probe,
        "decode_field",
        lambda field: _Decoded(step_hours=field.step_hours),
    )


def _args(out: Path, **overrides: str) -> list[str]:
    values = {
        "run_date": "2026-01-01",
        "cycle_hour": "0",
        "steps": "3,6",
        "latitude": "51.5",
        "longitude": "-0.1",
        "output_dir": str(out),
    }
    values.update(overrides)
    argv: list[str] = []
    for name, value in values.items():
        argv.extend((f"--{name.replace('_', '-')}", value))
    return argv


def _keys(value: object) -> list[str]:
    if isinstance(value, dict):
        keys: list[str] = []
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_keys(nested))
        return keys
    if isinstance(value, list):
        keys = []
        for nested in value:
            keys.extend(_keys(nested))
        return keys
    return []


def test_existing_output_is_refused_and_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "capture"
    out.mkdir()
    (out / "keep.txt").write_bytes(b"untouched")
    before = {path.name: path.read_bytes() for path in out.iterdir()}
    client = _FakeClient(fields={})
    _install(monkeypatch, client)

    assert probe.main(_args(out)) == 1

    after = {path.name: path.read_bytes() for path in out.iterdir()}
    assert after == before == {"keep.txt": b"untouched"}
    assert client.requests == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"steps": "4"},
        {"latitude": "91"},
        {"longitude": "181"},
    ],
)
def test_invalid_bounds_do_not_fetch_or_create_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, str],
) -> None:
    out = tmp_path / "capture"
    client = _FakeClient(fields={})
    _install(monkeypatch, client)

    assert probe.main(_args(out, **overrides)) == 1

    assert client.requests == []
    assert not out.exists()


def test_partial_fetch_failure_reports_incomplete_without_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "capture"
    client = _FakeClient({3: _field(3, b"first")}, error_at=6)
    _install(monkeypatch, client)

    assert probe.main(_args(out, steps="3,6")) == 1

    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["complete"] is False
    assert report["artifacts"] == [
        {"step": 3, "grib": "step_003.grib2", "json": "step_003.json"}
    ]
    assert report["error"] == {
        "type": "_UpstreamFailure",
        "code": "UPSTREAM_FAILED",
    }
    assert (out / "step_003.grib2").read_bytes() == b"first"
    assert not (out / "step_006.grib2").exists()
    captured = capsys.readouterr()
    visible = json.dumps(report) + captured.out + captured.err
    assert "secret-token-123" not in visible
    assert "provider.invalid" not in visible


def test_successful_two_fields_save_exact_bytes_and_metadata_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "capture"
    fields = {3: _field(3, b"grib-three"), 6: _field(6, b"grib-six")}
    client = _FakeClient(fields)
    _install(monkeypatch, client)

    assert probe.main(_args(out, steps="6,3")) == 0

    assert [request.step_hours for request in client.requests] == [3, 6]
    assert (out / "step_003.grib2").read_bytes() == b"grib-three"
    assert (out / "step_006.grib2").read_bytes() == b"grib-six"
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["complete"] is True
    assert report["label"] == probe.LABEL
    assert report["run_date"] == "2026-01-01"
    assert report["cycle_hour"] == 0
    assert report["steps"] == [3, 6]
    assert (report["latitude"], report["longitude"]) == (51.5, -0.1)
    assert report["artifacts"] == [
        {"step": 3, "grib": "step_003.grib2", "json": "step_003.json"},
        {"step": 6, "grib": "step_006.grib2", "json": "step_006.json"},
    ]
    expected_field = {
        "source": "ecmwf",
        "run_date": "2026-01-01",
        "cycle_hour": 0,
    }
    for step in (3, 6):
        document = json.loads(
            (out / f"step_{step:03d}.json").read_text(encoding="utf-8")
        )
        assert document["grib_file"] == f"step_{step:03d}.grib2"
        assert document["decoded"] == {"step_hours": step}
        assert document["field"] == {**expected_field, "step_hours": step}
    assert not [
        key for key in _keys(report) if key.endswith("_at") or "timestamp" in key
    ]
