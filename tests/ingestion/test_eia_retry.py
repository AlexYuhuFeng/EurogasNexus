"""The EIA reader waits out a gateway outage and refuses what retrying cannot fix."""

from __future__ import annotations

import importlib.util
import io
import urllib.error
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "ingest_eia.py"


def _script():
    spec = importlib.util.spec_from_file_location("ingest_eia_retry_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _opener(outcomes):
    calls = []

    def open_url(url, timeout):
        calls.append(url)
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return io.BytesIO(outcome)

    return open_url, calls


def _http(code):
    return urllib.error.HTTPError("https://api.eia.gov/v2/x", code, "gateway", {}, None)


def test_a_gateway_outage_is_retried_then_read():
    module = _script()
    waits = []
    opener, calls = _opener([_http(502), TimeoutError(), b'{"response": {}}'])
    assert module._read_with_retry("u", sleep=waits.append, opener=opener) == b'{"response": {}}'
    assert waits == [30.0, 90.0] and len(calls) == 3


def test_an_outage_that_does_not_clear_and_a_refused_key_are_raised():
    module = _script()
    opener, calls = _opener([_http(504)] * 3)
    with pytest.raises(urllib.error.HTTPError):
        module._read_with_retry("u", sleep=lambda _s: None, opener=opener)
    assert len(calls) == 3
    opener, calls = _opener([_http(403)])
    with pytest.raises(urllib.error.HTTPError):
        module._read_with_retry("u", sleep=lambda _s: None, opener=opener)
    assert len(calls) == 1
