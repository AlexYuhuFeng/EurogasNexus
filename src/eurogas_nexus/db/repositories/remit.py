"""Storage of REMIT UMM versions (``remit_umm_messages``), shared by file import and API.

Each message version is stored once under ``message_id:version``. A version already stored
with the same content is left as it is (its first ingestion time stays); a stored version
whose content the platform republished differently is replaced and counted as updated.
Readers take the latest version per message (``application/remit_outages``).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import RemitUmmRecord
from eurogas_nexus.domain.observations.remit_umm import UmmMessage


def _same(left: object, right: object) -> bool:
    if isinstance(left, datetime) and isinstance(right, datetime):
        def aware(moment: datetime) -> datetime:
            return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment

        return aware(left) == aware(right)
    return left == right


def store_umm_messages(
    session: Session,
    messages: Iterable[UmmMessage],
    *,
    now: datetime,
    source_system: str = "REMIT",
) -> dict[str, int]:
    """Insert new versions, keep identical ones; returns inserted/updated/unchanged."""

    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    for message in messages:
        values = message.as_record()
        stored = session.get(RemitUmmRecord, values["record_id"])
        if stored is None:
            session.add(RemitUmmRecord(**values, source_system=source_system, ingested_at_utc=now))
            session.flush()  # a repeated version later in the batch finds this one
            counts["inserted"] += 1
            continue
        compared = {key: value for key, value in values.items() if key != "source_reference"}
        if all(_same(getattr(stored, key), value) for key, value in compared.items()):
            counts["unchanged"] += 1
            continue
        for key, value in values.items():
            setattr(stored, key, value)
        stored.ingested_at_utc = now
        counts["updated"] += 1
    return counts
