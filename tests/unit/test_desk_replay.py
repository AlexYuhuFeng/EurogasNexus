"""Independent acceptance cases for the desk replay proposal."""

import json
from decimal import Decimal

import pytest

from eurogas_nexus.domain.portfolio.desk_replay import DeskReplay, replay
from scripts.ops.replay_desk_evidence import main


def evidence(record_id, **fields):
    return {
        "record_id": record_id,
        "revision": 1,
        "available_at": "2026-03-27T07:00:00Z",
        "source_ref": f"test:{record_id}",
        "resource_id": "pipe",
        **fields,
    }


def sample():
    return {
        "book_id": "desk",
        "hub_id": "TTF",
        "gas_day": "2026-03-28",
        "as_of": "2026-03-27T09:00:00Z",
        "currency": "EUR",
        "positions": [
            evidence("contract", kind="AVAILABLE", mwh="100"),
            evidence("nomination", kind="COMMITMENT", mwh="40"),
        ],
    }


def outage(**fields):
    return evidence(
        "outage",
        **{
            "starts_at": "2026-03-28T00:00:00Z",
            "ends_at": "2026-03-29T06:00:00Z",
            "unavailable_mw": "3",
            **fields,
        },
    )


def buy(**fields):
    return evidence(
        "quote",
        **{
            "kind": "BUY_GAS",
            "quantity_mwh": "20",
            "cost_per_mwh": "27.5",
            "price_basis": "EXECUTABLE",
            "deadline": "2026-03-27T13:00:00Z",
            "price_valid_until": "2026-03-27T10:00:00Z",
            "right_confirmed": True,
            "credit_per_mwh": "5",
            **fields,
        },
    )


def run(data):
    return replay(DeskReplay.model_validate(data))


def test_reconciles_known_commitments_and_preserves_unknown():
    data = sample()
    assert run(data)["resources"][0]["remaining_mwh"] == 60
    data["positions"].pop()
    assert run(data)["resources"][0]["remaining_mwh"] is None


def test_replays_dst_day_against_independent_quantity_and_cost():
    data = sample()
    data["outages"] = [
        outage(),
        outage(),
        outage(revision=2, available_at="2026-03-27T12:00:00Z", unavailable_mw="4"),
    ]
    data["alternatives"] = [buy()]
    result = run(data)
    # On this 23-hour gas day: lose 69 from 100, deliver 31 against 40,
    # buy the 9 MWh gap at EUR 27.50/MWh and use EUR 45 of credit.
    row = result["resources"][0]
    assert row["prior_gap_mwh"] == 0
    assert row["outage_loss_mwh"] == 69
    assert row["keep_plan_gap_mwh"] == 9
    assert row["alternatives"][0]["remaining_gap_mwh"] == 0
    assert row["alternatives"][0]["incremental_cost"] == Decimal("247.50")
    assert row["alternatives"][0]["incremental_credit"] == 45
    assert run(result["frozen_inputs"]) == result
    data["as_of"] = "2026-03-27T12:30:00Z"
    later = run(data)
    assert later["resources"][0]["keep_plan_gap_mwh"] == 32
    assert later["resources"][0]["alternatives"][0]["blocked"] == ["WINDOW_CLOSED"]


def test_rejects_conflicts_and_unverified_responses():
    data = sample()
    data["outages"] = [outage()]
    data["alternatives"] = [buy(right_confirmed=False, price_basis="INDICATIVE")]
    assert run(data)["resources"][0]["alternatives"][0]["blocked"] == [
        "RIGHT_UNCONFIRMED",
        "PRICE_NOT_ACTIONABLE",
    ]
    data["outages"].append(outage(unavailable_mw="4"))
    with pytest.raises(ValueError, match="Conflicting evidence"):
        run(data)


def test_cli_outputs_replay(tmp_path, capsys):
    path = tmp_path / "desk.json"
    path.write_text(json.dumps(sample()), encoding="utf-8")
    assert main(["--input", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["resources"][0]["remaining_mwh"] == "60"
