"""Identical daily-close reads inside one composed read (Today) are answered once."""

from __future__ import annotations

from datetime import date

from eurogas_nexus.application.projections import daily_closes
from eurogas_nexus.security.identity import AuthenticatedPrincipal


def _principal(pid: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=pid, name=pid, principal_type="USER", role="ANALYST", status="ACTIVE",
        data_scopes=("*",), roles=("ANALYST",),
    )


def test_identical_reads_are_shared_only_inside_the_block(monkeypatch):
    from eurogas_nexus.application.caller import Caller

    calls = []

    def fake(who, date_from=None, date_to=None):
        calls.append((date_from, date_to))
        return [{"hub": "NBP", "day": date_to}]

    monkeypatch.setattr(daily_closes, "_daily_rows", fake)
    trader = Caller(_principal("trader"))
    window = (date(2025, 10, 1), date(2026, 11, 18))
    with daily_closes.shared_daily_rows():
        first = daily_closes.daily_rows(trader, *window)
        second = daily_closes.daily_rows(trader, *window)
        daily_closes.daily_rows(trader, date(2026, 11, 8), date(2026, 11, 18))
        daily_closes.daily_rows(Caller(_principal("risk")), *window)
    assert first == second and first is not second
    assert len(calls) == 3  # one per distinct (caller, window)
    daily_closes.daily_rows(trader, *window)
    assert len(calls) == 4  # outside the block nothing is kept
