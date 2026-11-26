"""Current REMIT outages from stored UMMs, shared by the outage list and the live map."""

from __future__ import annotations

from datetime import UTC, datetime

#: Open messages one outage read considers; past it the read refuses rather than drop some.
MAX_OPEN_MESSAGES = 5_000


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def load_outage_rows(
    session,
    *,
    now: datetime,
    horizon_days: int,
    asset_type: str | None = None,
    ended_since: datetime | None = None,
) -> list[dict[str, object]]:
    """Live and upcoming outages (latest version of each message), soonest first.

    ``ended_since`` also returns outages that ended between it and ``now`` (status
    ``ended``), for a report over a past period; the live views leave it unset.
    """

    from eurogas_nexus.db.models import RemitUmmRecord
    from eurogas_nexus.domain.observations.remit_umm import UmmMessage, outage_view

    naive = session.get_bind().dialect.name == "sqlite"
    since = ended_since or now
    cutoff = since.replace(tzinfo=None) if naive else since
    # Messages with any version still open; then every version of them, so the latest
    # version decides (a revision may have ended or dismissed the event).
    open_ids = session.query(RemitUmmRecord.message_id).filter(
        (RemitUmmRecord.event_stop_utc.is_(None)) | (RemitUmmRecord.event_stop_utc > cutoff)
    )
    if asset_type:
        open_ids = open_ids.filter(RemitUmmRecord.asset_type == asset_type.casefold())
    # The bound used to be applied to an unordered DISTINCT, so past 5,000 open messages an
    # arbitrary part of the outages was left out of the list and the map without a word.
    from eurogas_nexus.application.bounded_reads import read_bounded

    bounded_ids = [row[0] for row in read_bounded(
        open_ids.distinct(), MAX_OPEN_MESSAGES, what="open REMIT message"
    )]
    records = (
        session.query(RemitUmmRecord).filter(RemitUmmRecord.message_id.in_(bounded_ids)).all()
        if bounded_ids
        else []
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
    return outage_view(messages, now=now, horizon_days=horizon_days, ended_since=ended_since)
