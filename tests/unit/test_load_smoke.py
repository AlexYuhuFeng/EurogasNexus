"""Load-smoke helper tests (Gate 4 load baseline)."""

import importlib.util
from pathlib import Path

_load_smoke_path = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "load_smoke.py"
)
_spec = importlib.util.spec_from_file_location("load_smoke", _load_smoke_path)
load_smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(load_smoke)

percentile = load_smoke.percentile
run_requests = load_smoke.run_requests


def test_percentile_on_empty_values() -> None:
    assert percentile([], 0.95) == 0.0


def test_percentile_basic() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert percentile(values, 0.5) == 6.0
    assert percentile(values, 0.95) == 10.0


def test_run_requests_in_process_returns_latencies_and_no_errors() -> None:
    latencies, errors = run_requests(20, 4, ("/api/health",))
    assert len(latencies) == 20
    assert errors == []
    assert all(latency > 0 for latency in latencies)


def test_run_requests_with_base_url_uses_real_http() -> None:
    # Port 9 (discard) refuses connections. The in-process transport answers
    # these paths successfully, so connection errors prove the request left the
    # process instead of being served by the ASGI app.
    latencies, errors = run_requests(2, 1, ("/api/health",), base_url="http://127.0.0.1:9")
    assert latencies == []
    assert len(errors) == 2
    assert all(error.startswith("/api/health:") for error in errors)
