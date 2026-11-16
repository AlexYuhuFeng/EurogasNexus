"""ENTSOG Transparency Platform urgent market messages (transmission UMMs).

ENTSOG publishes the REMIT urgent market messages that transmission system operators send
it at ``https://transparency.entsog.eu/api/v1/urgentmarketmessages``: the same public API
and paging as its other datasets (``ingestion/entsog_transport.py``; probed live on
2026-11-16: ``sort=id`` is echoed, ``meta.total`` is the rows left from the offset capped at
the limit, and a request past the last row answers 404). The whole dataset is small (93
message versions from 19 TSOs on 2026-11-16, the oldest published 2021), so every run reads
all of it and selects locally; nothing is filtered by the provider.

Two message types: ``Gas`` (ACER "unavailabilities of gas facilities": transmission system,
compressor station and other unavailability, with unit and capacities) and ``Other`` (other
market information, no capacity). Only ``Gas`` is an outage. ``messageId`` is
``<threadId>_<versionNumber>``: the thread is the message and the number its version, as on
GIE's IIP. Times carry their offset (CET/CEST). The publisher is a TSO (``marketParticipantKey``
is ENTSOG's operator key, e.g. ``DE-TSO-0009``) and the asset EIC is the ENTSOG point's EIC.

Terms: ENTSOG TP Terms of Use (Rev. 3) Art. 5: download, store and use, citing
"ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/" with the download date
(``docs/legal/DATA_SOURCE_TERMS.md``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

DATASET = "urgentmarketmessages"
#: ENTSOG's message type for an unavailability of gas facilities (ACER UMM type 1).
UNAVAILABILITY_TYPE = "gas"
#: Read bounds: the whole dataset fits in one page of 100 today; ten pages is ten times that.
PAGE_SIZE = 100
MAX_PAGES = 10


def citation(downloaded: datetime) -> str:
    """The citation ENTSOG's terms (Art. 5.2) require, with the download date."""

    return f"ENTSOG TP [{downloaded:%d-%m-%Y}] https://transparency.entsog.eu/"


def _zone(key: object) -> str:
    # ENTSOG pads balancing-zone keys with dashes to 12 characters ("DE-THE-----").
    return str(key or "").rstrip("-")


def _participant(record: Mapping[str, Any]) -> str:
    name = str(record.get("marketParticipantName") or "").strip()
    key = str(record.get("marketParticipantKey") or "").strip()
    if name and key:
        return f"{name} ({key})"
    return name or key


def _asset_type(record: Mapping[str, Any]) -> str:
    # The publisher is the system operator; an ENTSOG UMM is a transmission-side event,
    # including those at storage connection points (OGE's "Speicher ... Entry").
    key = str(record.get("marketParticipantKey") or "")
    return "transmission" if "-TSO-" in key else "other"


def _direction(record: Mapping[str, Any]) -> str:
    # OGE leaves ``direction`` empty and names the point with it ("Speicher Bierwang Entry").
    stated = str(record.get("direction") or "").strip()
    if stated:
        return stated
    last = str(record.get("affectedAssetName") or "").strip().rsplit(" ", 1)[-1].casefold()
    return last if last in {"entry", "exit"} else ""


def acer_fields(record: Mapping[str, Any]) -> dict[str, Any] | None:
    """One ENTSOG UMM as the ACER field names the importer reads; None if not an outage."""

    if str(record.get("messageType") or "").strip().casefold() != UNAVAILABILITY_TYPE:
        return None
    thread = str(record.get("threadId") or "").strip()
    version_text = str(record.get("versionNumber") or "").strip()
    if not thread:
        base, _, suffix = str(record.get("messageId") or "").rpartition("_")
        thread, version_text = base.strip(), suffix
    if not thread:
        return None
    reason = " - ".join(
        text
        for text in (
            str(record.get("eventType") or "").strip(),
            str(record.get("unavailabilityReason") or "").strip(),
        )
        if text
    )
    return {
        "messageId": thread,
        "version": int(version_text) if version_text.isdigit() else 1,
        "publicationDateTime": record.get("publicationDateTime"),
        "eventStatus": record.get("eventStatus"),
        "unavailabilityType": record.get("unavailabilityType"),
        "eventStart": record.get("eventStart"),
        "eventStop": record.get("eventStop"),
        "affectedAssetName": record.get("affectedAssetName"),
        "affectedAssetEic": record.get("affectedAssetEic"),
        "affectedAssetType": _asset_type(record),
        "balancingZone": _zone(record.get("balancingZoneKey")),
        "direction": _direction(record),
        "unitMeasure": record.get("unitMeasure"),
        "technicalCapacity": record.get("technicalCapacity"),
        "availableCapacity": record.get("availableCapacity"),
        "unavailableCapacity": record.get("unavailableCapacity"),
        "unavailabilityReason": reason,
        "marketParticipant": _participant(record),
        "remarks": record.get("remarks"),
    }


def _instant(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def in_window(record: Mapping[str, Any], *, since: datetime) -> bool:
    """A version published since ``since``, or one whose event had not ended by then.

    The second clause keeps outages that are still live or upcoming although they were
    announced earlier (live: OGE's France-Germany reduction, published 2024, runs to 2029).
    """

    published = _instant(record.get("publicationDateTime"))
    if published is not None and published >= since:
        return True
    stop = record.get("eventStop")
    if stop in (None, ""):
        return True
    ended = _instant(stop)
    return ended is None or ended > since


def acer_messages(
    records: Iterable[Mapping[str, Any]], *, since: datetime
) -> list[dict[str, Any]]:
    """Every unavailability version in the window, once per message and version."""

    found: dict[tuple[str, int], dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping) or not in_window(record, since=since):
            continue
        fields = acer_fields(record)
        if fields is not None:
            found.setdefault((fields["messageId"], fields["version"]), fields)
    return list(found.values())


def threads_without_latest(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Messages whose newest published version ENTSOG itself flags as not the latest.

    ENTSOG marks each version ``isLatestVersion`` Yes/No. Live on 2026-11-16 two
    unavailability messages had no version marked Yes (GRTgaz Deutschland's VIP
    France-Germany ``...P013`` version 1, NaTran's ``...S001`` versions 4-5): their latest
    version is not in the feed. Readers take the newest held version as the event's state,
    so such a message would be served as current although the provider says it is not;
    it is held back instead. Returns thread -> newest version held.
    """

    newest: dict[str, tuple[int, bool]] = {}
    for record in records:
        fields = acer_fields(record)
        if fields is None:
            continue
        flagged = str(record.get("isLatestVersion") or "").strip().casefold() == "yes"
        held = newest.get(fields["messageId"])
        if held is None or fields["version"] > held[0]:
            newest[fields["messageId"]] = (fields["version"], flagged)
        elif fields["version"] == held[0]:
            newest[fields["messageId"]] = (held[0], held[1] or flagged)
    return {thread: version for thread, (version, flagged) in newest.items() if not flagged}


def records_of(result) -> list[dict[str, Any]]:
    """The UMM records of a complete ``fetch_entsog_dataset`` read."""

    rows: list[dict[str, Any]] = []
    for page in result.pages:
        rows.extend(
            row for row in page.payload.get(DATASET) or [] if isinstance(row, Mapping)
        )
    return rows
