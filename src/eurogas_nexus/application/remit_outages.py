"""Current REMIT outages from stored UMMs, shared by the outage list and the live map."""

from __future__ import annotations

from datetime import UTC, datetime


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def load_outage_rows(
    session, *, now: datetime, horizon_days: int, asset_type: str | None = None
) -> list[dict[str, object]]:
    """Live and upcoming outages (latest version of each message), soonest first."""

    from eurogas_nexus.db.models import RemitUmmRecord
    from eurogas_nexus.domain.observations.remit_umm import UmmMessage, outage_view

    naive = session.get_bind().dialect.name == "sqlite"
    cutoff = now.replace(tzinfo=None) if naive else now
    # Messages with any version still open; then every version of them, so the latest
    # version decides (a revision may have ended or dismissed the event).
    open_ids = session.query(RemitUmmRecord.message_id).filter(
        (RemitUmmRecord.event_stop_utc.is_(None)) | (RemitUmmRecord.event_stop_utc > cutoff)
    )
    if asset_type:
        open_ids = open_ids.filter(RemitUmmRecord.asset_type == asset_type.casefold())
    records = (
        session.query(RemitUmmRecord)
        .filter(RemitUmmRecord.message_id.in_(open_ids.distinct().limit(5_000)))
        .all()
    )
    fields = UmmMessage.__dataclass_fields__
    messages = [
        UmmMessage(
            **{
                name: _aware(getattr(record, name))
                if name.endswith("_utc")
                else getattr(record, name)
                for name in fields
            }
        )
        for record in records
    ]
    return outage_view(messages, now=now, horizon_days=horizon_days)
