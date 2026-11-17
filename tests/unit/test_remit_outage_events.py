"""One row per outage event (remit_umm.outage_events): the grouping rule, table-driven."""

import pytest

from eurogas_nexus.domain.observations.remit_umm import outage_events

START = "2026-10-01T04:00:00+00:00"
STOP = "2029-10-01T04:00:00+00:00"


def _row(event_id, **fields):
    row = {
        "event_id": event_id,
        "version": 1,
        "facility_id": "",
        "facility_name": "VIP France - Germany",
        "start_utc": START,
        "end_utc": STOP,
        "published_at_utc": "2026-09-01T10:00:00+00:00",
        "unavailable_gwh_d": 81.0,
        "unavailable_capacity": 3375000.0,
        "unit": "kWh/h",
        "market_participant": "GRTgaz Deutschland",
        "direction": "entry",
        "status": "active",
    }
    row.update(fields)
    return row


CASES = [
    (
        "four GRTgaz Deutschland messages on VIP France-Germany, 81 GWh/d, 2026-2029",
        [
            _row("P012"),
            _row("P014", published_at_utc="2026-09-02T10:00:00+00:00"),
            _row("P015", published_at_utc="2026-09-03T10:00:00+00:00"),
            _row("P016", published_at_utc="2026-09-04T10:00:00+00:00"),
        ],
        [("P016", ["P012", "P014", "P015", "P016"], ["GRTgaz Deutschland"])],
    ),
    (
        "the two operators' sides of one interconnection point, names spelt differently",
        [
            _row(
                "FR-1",
                facility_name="VIP France-Germany",
                market_participant="GRTgaz",
                direction="exit",
            ),
            _row("DE-1", market_participant="GRTgaz Deutschland"),
        ],
        [("FR-1", ["DE-1", "FR-1"], ["GRTgaz", "GRTgaz Deutschland"])],
    ),
    (
        "the same EIC under two names is one asset",
        [
            _row("A", facility_id="21Z000000000001X", facility_name="Medelsheim"),
            _row("B", facility_id="21Z000000000001X", facility_name="Obergailbach"),
        ],
        [("B", ["A", "B"], ["GRTgaz Deutschland"])],
    ),
    (
        "a different size is a different event",
        [_row("A"), _row("B", unavailable_gwh_d=60.0)],
        [("A", ["A"], ["GRTgaz Deutschland"]), ("B", ["B"], ["GRTgaz Deutschland"])],
    ),
    (
        "a different period is a different event",
        [_row("A"), _row("B", end_utc="2027-10-01T04:00:00+00:00")],
        [("A", ["A"], ["GRTgaz Deutschland"]), ("B", ["B"], ["GRTgaz Deutschland"])],
    ),
    (
        "without a daily figure the published capacity and unit decide",
        [
            _row("A", unavailable_gwh_d=None, unavailable_capacity=500.0, unit="GWh"),
            _row("B", unavailable_gwh_d=None, unavailable_capacity=500.0, unit="GWh"),
            _row("C", unavailable_gwh_d=None, unavailable_capacity=400.0, unit="GWh"),
        ],
        [("B", ["A", "B"], ["GRTgaz Deutschland"]), ("C", ["C"], ["GRTgaz Deutschland"])],
    ),
    (
        "equal publication time: the higher version, then the larger id leads",
        [_row("A", version=2), _row("B", version=1)],
        [("A", ["A", "B"], ["GRTgaz Deutschland"])],
    ),
]


@pytest.mark.parametrize(("case", "rows", "expected"), CASES, ids=[case[0] for case in CASES])
def test_outage_events(case, rows, expected):
    events = outage_events(rows)
    assert [(e["event_id"], e["messages"], e["operators"]) for e in events] == expected
    assert [e["message_count"] for e in events] == [len(item[1]) for item in expected]


def test_grouping_does_not_depend_on_input_order():
    rows = CASES[0][1]
    forward = outage_events(rows)
    backward = outage_events(list(reversed(rows)))
    assert forward[0]["event_id"] == backward[0]["event_id"] == "P016"
    assert forward[0]["messages"] == backward[0]["messages"]
