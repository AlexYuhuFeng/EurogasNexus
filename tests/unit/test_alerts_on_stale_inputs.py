"""Small-desk plan 3.7: an alert raised on stale inputs says so in its own words."""

from __future__ import annotations

from datetime import UTC, datetime

from eurogas_nexus.application.monitoring_service import _credit_candidate

NOW = datetime(2026, 11, 27, 9, tzinfo=UTC)


def _row(state: str) -> dict:
    return {
        "counterparty_id": "cp-1", "counterparty": "Desk Counterparty", "currency": "EUR",
        "status": "breach", "net_exposure": 12_000_000.0, "limit": 10_000_000.0,
        "utilisation_pct": 120.0, "headroom": -2_000_000.0, "collateral": 0.0,
        "valid_until": None, "unvalued_legs": 0, "legs": 1, "replacement_exposure": 9_000_000.0,
        "receivable_exposure": 3_000_000.0,
        "marks_as_of": "2026-11-20", "state": state,
    }


def test_a_breach_on_stale_marks_says_the_marks_are_stale():
    candidate = _credit_candidate(_row("stale"), ("book-a",), NOW)
    assert candidate.severity == "critical"
    assert "(marks from 2026-11-20, stale)" in candidate.title_en
    assert "2026-11-20" in candidate.title_zh_cn
    assert "older than one business day" in candidate.message_en


def test_a_breach_on_current_marks_reads_as_before():
    candidate = _credit_candidate(_row("current"), ("book-a",), NOW)
    assert "marks from" not in candidate.title_en
