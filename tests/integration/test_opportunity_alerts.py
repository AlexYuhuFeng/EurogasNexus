"""M7 (b): new-engine opportunities raise alerts, are withdrawn when no longer viable, are routed
to their owner and notify once.

See docs/engineering/Commercial-Intelligence-V3/15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md.
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.alert_routing import route_for
from eurogas_nexus.application.alert_scope import alert_visibility
from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.application.notifications import (
    Message,
    channel_matches,
    dispatch,
    mirror_monitoring_alerts,
    queue_notification,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    MonitoringAlertRecord,
    NotificationOutboxRecord,
    OpportunityRecord,
    TradingBookRecord,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal
from eurogas_nexus.security.portfolio_scope import BookScope

NOW = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)


@pytest.fixture()
def engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _record(
    opportunity_id: str = "opp-1",
    *,
    state: str = "actionable",
    surfaced: bool = True,
    lane: str = "must_act",
    books: tuple[str, ...] = ("B1",),
    families: tuple[str, ...] = (),
    expires: datetime | None = None,
) -> OpportunityRecord:
    return OpportunityRecord(
        opportunity_id=opportunity_id,
        opp_key=f"key-{opportunity_id}",
        type="hedge_gap",
        lane=lane,
        state=state,
        assessed_state=state,
        version=1,
        version_basis=Decimal("42000"),
        claim_key="hedge_gap.unhedged",
        claim_fields={"contract": "Haldor supply"},
        claim_text="Haldor supply is under-hedged",
        headline_value=Decimal("12000"),
        headline_unit="MWh",
        value_amount=Decimal("42000.50"),
        value_currency="EUR",
        period_label="Jan-27",
        period_start=date(2027, 1, 1),
        period_end=date(2027, 1, 31),
        quality_class="sourced",
        simulated=False,
        book_ids=list(books),
        source_families=list(families),
        reasons=[],
        first_seen_utc=NOW,
        last_evaluated_utc=NOW,
        last_changed_utc=NOW,
        consecutive_seen=2,
        consecutive_missed=0,
        surfaced=surfaced,
        expires_at_utc=expires or NOW + timedelta(days=3),
        snapshot_id="snap-1",
        evaluation_id="oeval-1",
        evaluator="hedge_gap",
        evaluator_version="1",
    )


def _scan(session, at: datetime) -> None:
    scan_monitoring_conditions(session, now_utc=at, enrich_with_llm=False)


def _opportunity_alerts(session) -> list[MonitoringAlertRecord]:
    return (
        session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.category == "opportunity")
        .order_by(MonitoringAlertRecord.fingerprint)
        .all()
    )


def test_a_listed_opportunity_raises_one_alert_and_notifies_once(engine) -> None:
    with Session(engine) as session:
        session.add(_record())
        session.commit()
        _scan(session, NOW)
        _scan(session, NOW + timedelta(seconds=10))
        (alert,) = _opportunity_alerts(session)
        assert alert.severity == "warning" and alert.status == "open"
        assert alert.entity_type == "opportunity" and alert.entity_id == "opp-1"
        assert alert.title_en == "Opportunity open: Haldor supply"
        assert "42000.5 EUR" in alert.message_en and "nothing is traded" in alert.message_en
        assert alert.evidence_snapshot["book_ids"] == ["B1"]
        assert mirror_monitoring_alerts(session, now=NOW) == 1
        assert mirror_monitoring_alerts(session, now=NOW + timedelta(seconds=10)) == 0
        (row,) = session.query(NotificationOutboxRecord).all()
        assert row.category == "opportunity"
        assert row.body.endswith("For: Trader. If not acted on: Management.")


def test_an_opportunity_that_stops_being_viable_is_withdrawn(engine) -> None:
    with Session(engine) as session:
        session.add(_record("opp-1"))
        session.add(_record("opp-2", expires=NOW + timedelta(minutes=5)))
        session.add(_record("opp-3", state="indicative"))
        session.commit()
        _scan(session, NOW)
        alerts = {row.entity_id: row for row in _opportunity_alerts(session)}
        assert alerts["opp-3"].severity == "info"
        assert {row.status for row in alerts.values()} == {"open"}
        # The engine expires opp-1; opp-2 passes its validity before the engine runs again.
        session.get(OpportunityRecord, "opp-1").state = "expired"
        session.commit()
        _scan(session, NOW + timedelta(minutes=6))
        alerts = {row.entity_id: row for row in _opportunity_alerts(session)}
        assert alerts["opp-1"].status == "resolved"
        assert alerts["opp-2"].status == "resolved"
        assert alerts["opp-3"].status == "open"


@pytest.mark.parametrize(
    ("state", "surfaced"),
    [("new", False), ("actionable", False), ("watch", True), ("blocked", True)],
)
def test_only_listed_opportunities_alert(engine, state, surfaced) -> None:
    with Session(engine) as session:
        session.add(_record(state=state, surfaced=surfaced))
        session.commit()
        _scan(session, NOW)
        assert _opportunity_alerts(session) == []


def _principal(*scopes: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="p", name="p", principal_type="USER", role="ANALYST", status="ACTIVE",
        data_scopes=scopes, roles=("ANALYST",),
    )


def test_an_opportunity_alert_is_shown_by_the_opportunitys_own_rule(engine) -> None:
    with Session(engine) as session:
        for book in ("B1", "B2"):
            session.add(
                TradingBookRecord(
                    book_id=book, name=book, legal_entity="E", region="NWE", business="gas",
                    base_currency="EUR", active=True, updated_by="t", updated_at_utc=NOW,
                )
            )
        session.add(_record("opp-own", books=("B1",)))
        session.add(_record("opp-other", books=("B2",)))
        session.add(_record("opp-market", lane="market", books=()))
        session.add(_record("opp-licensed", lane="market", books=(), families=("EEX",)))
        session.commit()
        _scan(session, NOW)
        alerts = {row.entity_id: row for row in _opportunity_alerts(session)}
        visible = alert_visibility(
            session, principal=_principal("DEMO"), scope=BookScope(books=frozenset({"B1"}))
        )
        assert {key for key, row in alerts.items() if visible(row)} == {"opp-own", "opp-market"}
        everyone = alert_visibility(session, principal=_principal("*"), scope=None)
        assert {key for key, row in alerts.items() if everyone(row)} == set(alerts)


def test_alerts_are_routed_to_their_owner_and_an_alert_subscription_keeps_them() -> None:
    assert route_for("opportunity").notification_category == "opportunity"
    assert route_for("limits").owner == "RISK_MANAGER"
    assert route_for("delivery").notification_category == "nomination"
    assert route_for("data_source").owner == "DATA_OPERATOR"
    assert route_for("something new").notification_category == "alert"

    def channel(*categories: str):
        return SimpleNamespace(enabled=True, categories=list(categories), min_severity="info")

    opportunity = Message("opportunity", "warning", "t", "b")
    nomination = Message("nomination", "warning", "t", "b")
    limits = Message("limits", "critical", "t", "b")
    assert channel_matches(channel("alert"), opportunity)
    assert channel_matches(channel("alert"), nomination)
    assert not channel_matches(channel("alert"), limits)
    assert channel_matches(channel("opportunity"), opportunity)
    assert not channel_matches(channel("opportunity"), nomination)
    assert channel_matches(channel(), limits)


POSTGRES = os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql")


@pytest.mark.skipif(not POSTGRES, reason="needs PostgreSQL (scripts/ci/run_postgres_ci.sh)")
def test_two_workers_queue_and_send_a_notification_once_on_postgres() -> None:
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    key = f"m7-{uuid4().hex}"
    try:
        # Queue: both pass the existence check; the second insert waits for the first commit
        # and then writes nothing.
        first, second = Session(engine), Session(engine)
        assert queue_notification(
            first, category="alert", severity="warning", title="t", body="b",
            dedupe_key=key, now=NOW,
        )
        outcome: list[bool] = []
        racer = threading.Thread(
            target=lambda: outcome.append(
                queue_notification(
                    second, category="alert", severity="warning", title="t", body="b",
                    dedupe_key=key, now=NOW,
                )
            )
        )
        racer.start()
        racer.join(0.5)
        first.commit()
        racer.join(10)
        second.commit()
        assert outcome == [False]
        first.close()
        second.close()

        # Send: the first worker holds the row; the second finds nothing to send.
        sent: list[str] = []
        a, b = Session(engine), Session(engine)
        channel = SimpleNamespace(
            channel_id="c", kind="email", enabled=True, categories=None, min_severity="info"
        )

        def sender(_channel, message):
            sent.append(message.title)

        a.query(NotificationOutboxRecord).filter(
            NotificationOutboxRecord.dedupe_key != key,
            NotificationOutboxRecord.dispatched_at_utc.is_(None),
        ).update({"dispatched_at_utc": NOW}, synchronize_session=False)
        a.commit()
        from eurogas_nexus.db.models import NotificationChannelRecord

        a.query(NotificationChannelRecord).delete()
        a.add(
            NotificationChannelRecord(
                channel_id=channel.channel_id, name="c", kind="email", recipients="x@example.com",
                categories=None, min_severity="info", enabled=True, updated_by="t",
                updated_at_utc=NOW,
            )
        )
        a.commit()
        assert dispatch(a, now=NOW, senders={"email": sender})["sent"] == 1
        assert dispatch(b, now=NOW, senders={"email": sender})["sent"] == 0
        a.commit()
        b.commit()
        assert sent == ["t"]
        a.close()
        b.close()
    finally:
        from eurogas_nexus.db.models import NotificationChannelRecord

        with Session(engine) as session:
            session.query(NotificationOutboxRecord).filter(
                NotificationOutboxRecord.dedupe_key == key
            ).delete()
            # The channel takes every category: left behind, a later PostgreSQL test that
            # dispatches would also send to it.
            session.query(NotificationChannelRecord).filter(
                NotificationChannelRecord.channel_id == "c"
            ).delete()
            session.commit()
        engine.dispose()
