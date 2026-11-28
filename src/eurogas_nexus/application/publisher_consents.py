"""Which publishers' written consents are in force, and an administrator's withdrawal of one.

The records ship as data (``domain/publications/consents``). An administrator can withdraw one
in the product (Admin -> Data sources -> Watched publications): the withdrawal is audited, the
watch stops fetching that publisher's publications at once (``publication_watch``), and the
data already held stays, marked "consent withdrawn on <date>" wherever it is shown. Restoring
a withdrawn record (a mistaken click, or the publisher confirming again) is audited the same way.

发布方书面同意的状态：管理员可撤回（记入审计，立即停止获取，已存数据标注撤回日期）或恢复。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.domain.publications.consents import (
    PublisherConsent,
    consent_for_family,
    publisher_consent,
    publisher_consents,
)

EVENT_SOURCE = "src-publications"


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _states(session) -> dict[str, Any]:
    from eurogas_nexus.db.models import PublisherConsentStateRecord

    return {row.publisher_id: row for row in session.query(PublisherConsentStateRecord).all()}


def withdrawn_on(session, publisher_id: str | None) -> datetime | None:
    """When an administrator withdrew this publisher's consent, or ``None`` when in force."""

    from eurogas_nexus.db.models import PublisherConsentStateRecord

    if not publisher_id:
        return None
    row = session.get(PublisherConsentStateRecord, publisher_id)
    if row is None or row.state != "withdrawn":
        return None
    return _aware(row.withdrawn_at_utc)


def consent_in_force(session, publisher_id: str | None) -> PublisherConsent | None:
    """The publisher's consent record when it exists and has not been withdrawn."""

    consent = publisher_consent(publisher_id)
    if consent is None or withdrawn_on(session, publisher_id) is not None:
        return None
    return consent


def consent_row(consent: PublisherConsent, state_row) -> dict[str, Any]:
    withdrawn = state_row is not None and state_row.state == "withdrawn"
    at = _aware(state_row.withdrawn_at_utc) if withdrawn else None
    return consent.to_json() | {
        "state": "withdrawn" if withdrawn else "in_force",
        "withdrawn_at_utc": at.isoformat() if at else None,
        "withdrawn_by": state_row.withdrawn_by if withdrawn else None,
        "withdrawn_reason": (state_row.reason or "") if withdrawn else "",
        "restored_at_utc": (_aware(state_row.restored_at_utc).isoformat()
                            if state_row is not None and state_row.restored_at_utc else None),
        "line": (f"consent withdrawn on {at:%Y-%m-%d}" if withdrawn else consent.line()),
    }


def consent_status(session) -> list[dict[str, Any]]:
    """Every shipped consent record with its state (for the administrators' list)."""

    states = _states(session)
    return [consent_row(c, states.get(c.publisher_id)) for c in publisher_consents()]


def family_consent_marks(session) -> dict[str, dict[str, Any]]:
    """For each consented source family: the consent line its data is shown with."""

    states = _states(session)
    out: dict[str, dict[str, Any]] = {}
    for consent in publisher_consents():
        row = consent_row(consent, states.get(consent.publisher_id))
        for family in consent.families:
            out[family] = {"publisher_id": consent.publisher_id, "state": row["state"],
                           "line": row["line"], "withdrawn_at_utc": row["withdrawn_at_utc"],
                           "scope": consent.scope}
    return out


def consent_mark_for(session, source_system: str | None) -> dict[str, Any] | None:
    consent = consent_for_family(source_system)
    if consent is None:
        return None
    return family_consent_marks(session).get(str(source_system))


def _set_state(session, publisher_id: str, *, withdraw: bool, principal: str, now: datetime,
               reason: str) -> dict[str, Any]:
    from eurogas_nexus.db.models import PublisherConsentStateRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event

    consent = publisher_consent(publisher_id)
    if consent is None:
        raise KeyError(publisher_id)
    now = _aware(now)
    row = session.get(PublisherConsentStateRecord, publisher_id)
    if withdraw and row is not None and row.state == "withdrawn":
        raise ValueError("the consent is already withdrawn")
    if not withdraw and (row is None or row.state != "withdrawn"):
        raise ValueError("the consent is in force: nothing to restore")
    if row is None:
        row = PublisherConsentStateRecord(publisher_id=publisher_id, state="in_force",
                                          reason="", updated_at_utc=now)
        session.add(row)
    if withdraw:
        row.state = "withdrawn"
        row.withdrawn_at_utc = now
        row.withdrawn_by = principal[:128]
        row.reason = (reason or "").strip()[:500]
    else:
        row.state = "in_force"
        row.restored_at_utc = now
        row.restored_by = principal[:128]
    row.updated_at_utc = now
    record_audit_event(
        session, event_type="governance.data", principal=principal[:128],
        action="publisher_consent.withdraw" if withdraw else "publisher_consent.restore",
        resource=f"publisher_consent:{publisher_id}", outcome="success", severity="medium",
        detail=((f"Withdrew the written consent of {consent.name}" if withdraw
                 else f"Restored the written consent of {consent.name}")
                + (f": {reason.strip()}" if reason and reason.strip() else ""))[:500],
        source_system=EVENT_SOURCE, now_utc=now,
    )
    if withdraw:
        _stop_fetching(session, publisher_id, now=now)
    session.flush()
    return consent_row(consent, row)


def _stop_fetching(session, publisher_id: str, *, now: datetime) -> None:
    """Mark every publication fetched under this consent: no further fetch, data kept."""

    from eurogas_nexus.application.publication_watch import _row
    from eurogas_nexus.domain.publications.registry import WATCHED_PUBLICATIONS

    for item in WATCHED_PUBLICATIONS:
        if item.consent_publisher != publisher_id:
            continue
        row = _row(session, item)
        row.state = "consent_withdrawn"
        row.detail = (f"Consent withdrawn on {now:%Y-%m-%d}: not fetched; the data held stays, "
                      "marked")[:500]


def withdraw_consent(session, publisher_id: str, *, principal: str, now: datetime,
                     reason: str = "") -> dict[str, Any]:
    """Withdraw a publisher's consent (audited): fetching stops at once, the data stays."""

    return _set_state(session, publisher_id, withdraw=True, principal=principal, now=now,
                      reason=reason)


def restore_consent(session, publisher_id: str, *, principal: str, now: datetime
                    ) -> dict[str, Any]:
    """Put a withdrawn consent back in force (audited); the next check fetches again."""

    out = _set_state(session, publisher_id, withdraw=False, principal=principal, now=now,
                     reason="")
    from eurogas_nexus.db.models import WatchedPublicationRecord
    from eurogas_nexus.domain.publications.registry import WATCHED_PUBLICATIONS

    for item in WATCHED_PUBLICATIONS:
        if item.consent_publisher != publisher_id:
            continue
        row = session.get(WatchedPublicationRecord, item.publication_id)
        if row is not None and row.state == "consent_withdrawn":
            row.state = "current" if row.record else "never_fetched"
            row.detail = f"Consent restored on {_aware(now):%Y-%m-%d}."
            row.last_checked_at_utc = None
    session.flush()
    return out


__all__ = [
    "consent_in_force",
    "consent_mark_for",
    "consent_row",
    "consent_status",
    "family_consent_marks",
    "restore_consent",
    "withdraw_consent",
    "withdrawn_on",
]
