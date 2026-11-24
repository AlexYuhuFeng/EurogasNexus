"""The cargo-plan SDK against the real application: plan, what-if and recorded hedges."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from eurogas_nexus_sdk import _http
from eurogas_nexus_sdk.lng_cargo_plan import (
    fetch_cargo_plan,
    fetch_cargo_plans,
    record_cargo_hedges,
    try_cargo_eta,
)
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from tests.api.test_lng_cargo_plan_api import PUBLIC_TOKEN, _setup

BASE = "http://testserver/"  # the trailing slash is deliberate: the SDK must cope with it


@pytest.fixture
def sdk(tmp_path, monkeypatch):
    _engine, who, now = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    state = {"bearer": who["analyst"]["X-Eurogas-Identity"]}
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", PUBLIC_TOKEN)

    def _send(method):
        def call(url, *, timeout=None, headers=None, params=None, json=None, **_kw):
            merged = {**(headers or {}), "X-Eurogas-Api-Key": PUBLIC_TOKEN}
            merged["X-Eurogas-Identity"] = state["bearer"]
            return client.request(
                method, url.replace("http://testserver", ""), headers=merged, params=params,
                json=json,
            )

        return call

    for method in ("get", "post", "put"):
        monkeypatch.setattr(httpx, method, _send(method.upper()))
    assert _http.resolve_api_token() == PUBLIC_TOKEN
    return state, who, now


def test_sdk_reads_the_plan_and_tries_a_later_eta(sdk):
    _state, _who, now = sdk

    plan = fetch_cargo_plan(BASE, "own-1", demurrage_per_day=80_000)
    assert plan.cargo_id == "own-1"
    assert plan.slot_status == "on_time"
    assert sum(month.physical_mwh for month in plan.months) == pytest.approx(
        plan.delivered_mwh, abs=1
    )
    assert any(row["input"] == "ETA" for row in plan.inputs)

    change = try_cargo_eta(BASE, "own-1", eta_utc=now + timedelta(days=16))
    assert change["headline"] == "The new ETA misses the slot window."

    board = fetch_cargo_plans(BASE)
    assert [line["cargo_id"] for line in board] == ["own-1"]


def test_sdk_records_hedges_and_surfaces_refusals(sdk):
    state, who, _now = sdk
    legs = [{"hub": "TTF", "month": "2027-01", "mwh": -100_000, "reference": "EEX 1"}]

    result = record_cargo_hedges(BASE, "own-1", legs)
    assert result["events"]["published"] == {"cargo.changed": 1}
    assert fetch_cargo_plan(BASE, "own-1").months  # the plan still reads after the change

    state["bearer"] = who["viewer"]["X-Eurogas-Identity"]
    with pytest.raises(httpx.HTTPStatusError) as refused:
        record_cargo_hedges(BASE, "own-1", legs)
    assert refused.value.response.status_code == 403
    with pytest.raises(httpx.HTTPStatusError) as missing:
        fetch_cargo_plan(BASE, "feed-1")
    assert missing.value.response.json()["detail"]["code"] == "cargo_not_found"
