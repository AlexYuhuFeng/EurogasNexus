"""Persistence of assumption sets, firm marks and valuation snapshots.

Every write records an audit event. The audit detail names what changed (set, version,
keys, hubs and periods, counts) and a SHA-256 of the values, never the values themselves:
the audit trail is read by platform administrators, who hold no commercial permission, and
a charter hire or a firm's mark is commercial data.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.commercial_assumptions import (
    AssumptionSetRecord,
    AssumptionSetVersionRecord,
    AssumptionValueRecord,
    FirmMarkRecord,
    ValuationSnapshotInputRecord,
    ValuationSnapshotRecord,
)
from eurogas_nexus.db.repositories.audit import record_governed_audit
from eurogas_nexus.domain.valuation.assumptions import (
    AssumptionError,
    AssumptionSetVersion,
    AssumptionValue,
    ReviewState,
    changed_keys,
    validate_set_name,
    values_digest,
)
from eurogas_nexus.domain.valuation.firm_marks import FirmMark, FirmMarkEntry
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.snapshot import SnapshotInput, SnapshotManifest

_PLACES = Decimal("1E-10")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _dec(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(_PLACES).normalize()


def _num(value: Decimal | None) -> str | None:
    """A decimal for a JSON payload, as text so no digit is lost on the way."""

    return None if value is None else format(value.normalize(), "f")


# ------------------------------------------------------------------- assumption sets


def _version_domain(
    record: AssumptionSetVersionRecord, set_row: AssumptionSetRecord, values
) -> AssumptionSetVersion:
    return AssumptionSetVersion(
        set_id=set_row.set_id,
        name=set_row.name,
        version=record.version,
        book_id=set_row.book_id,
        effective_from=record.effective_from,
        effective_to=record.effective_to,
        review_state=ReviewState(record.review_state),
        created_by=record.created_by,
        created_at_utc=_aware(record.created_at_utc),
        approved_by=record.approved_by,
        approved_at_utc=_aware(record.approved_at_utc),
        values=tuple(
            AssumptionValue(
                key=row.key,
                value=_dec(row.value),
                unit=row.unit,
                currency=row.currency,
                range_low=_dec(row.range_low),
                range_high=_dec(row.range_high),
                note=row.note or "",
            )
            for row in sorted(values, key=lambda item: item.key)
        ),
    )


def _version_payload(version: AssumptionSetVersion, version_id: str) -> dict:
    return {
        "version_id": version_id,
        "version": version.version,
        "effective_from": version.effective_from.isoformat(),
        "effective_to": version.effective_to.isoformat() if version.effective_to else None,
        "review_state": version.review_state.value,
        "created_by": version.created_by,
        "created_at_utc": version.created_at_utc.isoformat(),
        "approved_by": version.approved_by,
        "approved_at_utc": (
            version.approved_at_utc.isoformat() if version.approved_at_utc else None
        ),
        "values": [
            {
                "key": item.key,
                "value": _num(item.value),
                "unit": item.unit,
                "currency": item.currency,
                "range_low": _num(item.range_low),
                "range_high": _num(item.range_high),
                "note": item.note,
                "set_by": version.created_by,
                "set_at_utc": version.created_at_utc.isoformat(),
            }
            for item in version.values
        ],
    }


def _set_payload(session: Session, row: AssumptionSetRecord, *, with_values: bool) -> dict:
    versions = (
        session.query(AssumptionSetVersionRecord)
        .filter(AssumptionSetVersionRecord.set_id == row.set_id)
        .order_by(AssumptionSetVersionRecord.version.desc())
        .all()
    )
    payload_versions = []
    for record in versions:
        values = (
            session.query(AssumptionValueRecord)
            .filter(AssumptionValueRecord.version_id == record.version_id)
            .all()
            if with_values
            else []
        )
        domain = _version_domain(record, row, values)
        entry = _version_payload(domain, record.version_id)
        if not with_values:
            entry.pop("values")
        payload_versions.append(entry)
    approved = next((item for item in payload_versions if item["review_state"] == "approved"), None)
    return {
        "set_id": row.set_id,
        "name": row.name,
        "scope": "book" if row.book_id else "organisation",
        "book_id": row.book_id,
        "description": row.description,
        "created_by": row.created_by,
        "created_at_utc": _aware(row.created_at_utc).isoformat(),
        "approved_version": approved["version"] if approved else None,
        "latest_version": payload_versions[0]["version"] if payload_versions else None,
        "versions": payload_versions,
    }


def create_assumption_set(
    session: Session,
    *,
    name: str,
    book_id: str | None,
    description: str,
    actor: str,
    now_utc: datetime | None = None,
) -> dict:
    """Create an empty set (values arrive with its first version).

    Raises:
        AssumptionError: ``name_invalid`` or ``set_exists``.
    """

    now = now_utc or datetime.now(UTC)
    clean = validate_set_name(name)
    exists = (
        session.query(AssumptionSetRecord)
        .filter(AssumptionSetRecord.name == clean)
        .filter(
            AssumptionSetRecord.book_id.is_(None)
            if book_id is None
            else AssumptionSetRecord.book_id == book_id
        )
        .first()
    )
    if exists is not None:
        raise AssumptionError("set_exists", f"a set named {clean!r} already exists here")
    row = AssumptionSetRecord(
        set_id=f"aset-{uuid4().hex[:20]}",
        name=clean,
        book_id=book_id,
        description=(description or "").strip()[:400],
        created_by=actor,
        created_at_utc=now,
    )
    session.add(row)
    record_governed_audit(
        session,
        event_type="desk.reference",
        principal=actor,
        action="assumption_set.create",
        resource=f"assumption_set:{row.set_id}",
        outcome="created",
        detail=f"name={clean} scope={'book:' + book_id if book_id else 'organisation'}",
        source_system="assumptions-api",
        now_utc=now,
    )
    session.flush()
    return _set_payload(session, row, with_values=True)


def list_assumption_sets(session: Session, visible_books: set[str] | None) -> list[dict]:
    """Every set the caller may read: organisation sets, and sets of visible books."""

    rows = session.query(AssumptionSetRecord).order_by(AssumptionSetRecord.name).all()
    return [
        _set_payload(session, row, with_values=False)
        for row in rows
        if row.book_id is None or visible_books is None or row.book_id in visible_books
    ]


def get_assumption_set(session: Session, set_id: str) -> dict | None:
    """One set with every version and its values, or ``None``."""

    row = session.get(AssumptionSetRecord, set_id)
    return None if row is None else _set_payload(session, row, with_values=True)


def assumption_set_book(session: Session, set_id: str) -> tuple[bool, str | None]:
    """``(exists, book_id)`` of a set, for the route's scope check."""

    row = session.get(AssumptionSetRecord, set_id)
    return (row is not None, None if row is None else row.book_id)


def create_assumption_version(
    session: Session,
    *,
    set_id: str,
    values: Iterable[AssumptionValue],
    effective_from: date,
    effective_to: date | None,
    note: str,
    actor: str,
    now_utc: datetime | None = None,
) -> dict:
    """Append a draft version holding the full list of values.

    Raises:
        AssumptionError: ``unknown_set``, ``duplicate_key``, ``effective_range_inverted``.
    """

    now = now_utc or datetime.now(UTC)
    set_row = session.get(AssumptionSetRecord, set_id)
    if set_row is None:
        raise AssumptionError("unknown_set", f"no assumption set {set_id!r}")
    items = list(values)
    keys = [item.key for item in items]
    if len(set(keys)) != len(keys):
        raise AssumptionError("duplicate_key", "each key appears once in a version")
    if effective_to is not None and effective_to <= effective_from:
        raise AssumptionError("effective_range_inverted", "effective_to must follow from")
    previous = (
        session.query(AssumptionSetVersionRecord)
        .filter(AssumptionSetVersionRecord.set_id == set_id)
        .order_by(AssumptionSetVersionRecord.version.desc())
        .first()
    )
    before: list[AssumptionValue] = []
    if previous is not None:
        before = list(
            _version_domain(
                previous,
                set_row,
                session.query(AssumptionValueRecord)
                .filter(AssumptionValueRecord.version_id == previous.version_id)
                .all(),
            ).values
        )
    number = 1 if previous is None else previous.version + 1
    digest = values_digest(items)
    record = AssumptionSetVersionRecord(
        version_id=f"asv-{uuid4().hex[:20]}",
        set_id=set_id,
        version=number,
        effective_from=effective_from,
        effective_to=effective_to,
        review_state=ReviewState.DRAFT.value,
        note=(note or "").strip()[:400],
        values_sha256=digest,
        created_by=actor,
        created_at_utc=now,
    )
    session.add(record)
    session.flush()
    for item in items:
        session.add(
            AssumptionValueRecord(
                version_id=record.version_id,
                key=item.key,
                value=item.value,
                unit=item.unit,
                currency=item.currency,
                range_low=item.range_low,
                range_high=item.range_high,
                note=item.note,
            )
        )
    record_governed_audit(
        session,
        event_type="desk.reference",
        principal=actor,
        action="assumption_set.version.create",
        resource=f"assumption_set:{set_id}:v{number}",
        outcome="created",
        detail=json.dumps(
            {
                "keys_changed": changed_keys(before, items),
                "value_count": len(items),
                "values_sha256": digest,
                "effective_from": effective_from.isoformat(),
            },
            sort_keys=True,
        ),
        source_system="assumptions-api",
        now_utc=now,
    )
    session.flush()
    return _set_payload(session, set_row, with_values=True)


def approve_assumption_version(
    session: Session, *, set_id: str, version: int, actor: str, now_utc: datetime | None = None
) -> dict:
    """Approve a draft (four eyes); an earlier approved version of the set is retired.

    Raises:
        AssumptionError: ``unknown_version``, ``not_a_draft``, ``four_eyes_required``.
    """

    now = now_utc or datetime.now(UTC)
    record = (
        session.query(AssumptionSetVersionRecord)
        .filter(AssumptionSetVersionRecord.set_id == set_id)
        .filter(AssumptionSetVersionRecord.version == version)
        .first()
    )
    if record is None:
        raise AssumptionError("unknown_version", f"no version {version} of {set_id!r}")
    if record.review_state != ReviewState.DRAFT.value:
        raise AssumptionError("not_a_draft", "only a draft version can be approved")
    if record.created_by.casefold() == actor.casefold():
        raise AssumptionError(
            "four_eyes_required", "the person who set the values cannot approve them"
        )
    for older in (
        session.query(AssumptionSetVersionRecord)
        .filter(AssumptionSetVersionRecord.set_id == set_id)
        .filter(AssumptionSetVersionRecord.review_state == ReviewState.APPROVED.value)
        .all()
    ):
        older.review_state = ReviewState.RETIRED.value
    record.review_state = ReviewState.APPROVED.value
    record.approved_by = actor
    record.approved_at_utc = now
    record_governed_audit(
        session,
        event_type="desk.reference",
        principal=actor,
        action="assumption_set.version.approve",
        resource=f"assumption_set:{set_id}:v{version}",
        outcome="approved",
        detail=json.dumps(
            {"values_sha256": record.values_sha256, "set_by": record.created_by},
            sort_keys=True,
        ),
        source_system="assumptions-api",
        now_utc=now,
    )
    session.flush()
    set_row = session.get(AssumptionSetRecord, set_id)
    return _set_payload(session, set_row, with_values=True)


def resolve_assumption_version(
    session: Session,
    *,
    day: date,
    set_id: str | None = None,
    book_id: str | None = None,
) -> tuple[str, AssumptionSetVersion] | None:
    """The approved version a valuation on ``day`` reads.

    Order: the named set; else the book's own set; else the organisation set approved most
    recently. ``None`` when no approved version is in force (every assumption then reads
    as missing).
    """

    query = (
        session.query(AssumptionSetVersionRecord, AssumptionSetRecord)
        .join(AssumptionSetRecord, AssumptionSetRecord.set_id == AssumptionSetVersionRecord.set_id)
        .filter(AssumptionSetVersionRecord.review_state == ReviewState.APPROVED.value)
    )
    if set_id is not None:
        candidates = query.filter(AssumptionSetRecord.set_id == set_id).all()
    else:
        candidates = []
        if book_id is not None:
            candidates = query.filter(AssumptionSetRecord.book_id == book_id).all()
        if not candidates:
            candidates = query.filter(AssumptionSetRecord.book_id.is_(None)).all()
    resolved = []
    for record, set_row in candidates:
        values = (
            session.query(AssumptionValueRecord)
            .filter(AssumptionValueRecord.version_id == record.version_id)
            .all()
        )
        domain = _version_domain(record, set_row, values)
        if domain.in_force(day):
            resolved.append((record.version_id, domain))
    if not resolved:
        return None
    earliest = datetime.min.replace(tzinfo=UTC)
    return max(resolved, key=lambda pair: pair[1].approved_at_utc or earliest)


# ------------------------------------------------------------------------- firm marks


def _mark_domain(row: FirmMarkRecord) -> FirmMark:
    return FirmMark(
        mark_id=row.mark_id,
        hub=row.hub,
        period=DeliveryPeriod(row.period_start, row.period_end, row.period_label),
        value=_dec(row.value),
        unit=row.unit,
        currency=row.currency,
        entered_by=row.entered_by,
        entered_at_utc=_aware(row.entered_at_utc),
        note=row.note or "",
    )


def mark_payload(mark: FirmMark) -> dict:
    """A firm mark as the API returns it; the class is stated on every row."""

    return {
        "mark_id": mark.mark_id,
        "hub": mark.hub,
        "period": mark.period.label,
        "value": _num(mark.value),
        "unit": mark.unit,
        "currency": mark.currency,
        "input_class": mark.input_class.value,
        "class_label": "firm's mark",
        "entered_by": mark.entered_by,
        "entered_at_utc": mark.entered_at_utc.isoformat(),
        "note": mark.note,
    }


def current_firm_marks(
    session: Session, *, as_of_utc: datetime | None = None, hub: str | None = None
) -> list[FirmMark]:
    """The marks in force at an instant (default now): entered before it, not superseded."""

    moment = as_of_utc or datetime.now(UTC)
    naive = session.get_bind().dialect.name == "sqlite"
    bound = moment.replace(tzinfo=None) if naive else moment
    query = (
        session.query(FirmMarkRecord)
        .filter(FirmMarkRecord.entered_at_utc <= bound)
        .filter(
            or_(
                FirmMarkRecord.superseded_at_utc.is_(None),
                FirmMarkRecord.superseded_at_utc > bound,
            )
        )
    )
    if hub:
        query = query.filter(FirmMarkRecord.hub == hub.upper())
    rows = query.order_by(FirmMarkRecord.hub, FirmMarkRecord.period_start).all()
    return [_mark_domain(row) for row in rows]


def mark_change_ids(session: Session, mark_ids: Iterable[str]) -> dict[str, str | None]:
    """``mark_id -> change_id``: the approved proposal that set each mark (P-17), if any."""

    ids = list(mark_ids)
    if not ids:
        return {}
    return dict(
        session.query(FirmMarkRecord.mark_id, FirmMarkRecord.change_id)
        .filter(FirmMarkRecord.mark_id.in_(ids))
        .all()
    )


def put_firm_marks(
    session: Session,
    entries: Iterable[FirmMarkEntry],
    *,
    actor: str,
    now_utc: datetime | None = None,
    approved_by: str | None = None,
    change_id: str | None = None,
) -> list[FirmMark]:
    """Store a grid of marks; each supersedes the current mark for its hub and period.

    ``actor`` entered the marks. When a second person approved them (P-17), ``approved_by``
    and ``change_id`` say so: each row keeps the change id and the audit row names both.
    """

    now = now_utc or datetime.now(UTC)
    stored: list[FirmMark] = []
    items = list(entries)
    for entry in items:
        for current in (
            session.query(FirmMarkRecord)
            .filter(FirmMarkRecord.hub == entry.hub)
            .filter(FirmMarkRecord.period_label == entry.period.label)
            .filter(FirmMarkRecord.superseded_at_utc.is_(None))
            .all()
        ):
            current.superseded_at_utc = now
        row = FirmMarkRecord(
            mark_id=f"fmark-{uuid4().hex[:20]}",
            hub=entry.hub,
            period_label=entry.period.label,
            period_start=entry.period.start,
            period_end=entry.period.end,
            value=entry.value,
            unit=entry.unit,
            currency=entry.currency,
            note=entry.note,
            entered_by=actor,
            entered_at_utc=now,
            change_id=change_id,
        )
        session.add(row)
        session.flush()
        stored.append(_mark_domain(row))
    digest = hashlib.sha256(
        json.dumps(sorted((e.hub, e.period.label, str(e.value), e.unit) for e in items)).encode(
            "utf-8"
        )
    ).hexdigest()
    summary: dict = {
        "count": len(items),
        "cells": sorted(f"{e.hub}:{e.period.label}" for e in items),
        "values_sha256": digest,
    }
    if approved_by:
        # P-17: the principal is the approver; the proposal (who entered the marks, why) is
        # the correlated change request. Still no values on the audit row.
        summary["second_approval"] = True
    record_governed_audit(
        session,
        event_type="desk.reference",
        principal=approved_by or actor,
        action="market.firm_marks.update",
        resource="firm_marks:" + ",".join(sorted({entry.hub for entry in items})),
        outcome="recorded",
        detail=json.dumps(summary, sort_keys=True)[:2000],
        source_system="assumptions-api",
        now_utc=now,
        correlation_id=change_id,
    )
    session.flush()
    return stored


# ---------------------------------------------------------------------- snapshots


def save_snapshot(
    session: Session,
    manifest: SnapshotManifest,
    *,
    purpose: str,
    created_by: str,
    now_utc: datetime | None = None,
) -> str:
    """Persist what an evaluation read; returns the snapshot id."""

    summary = manifest.summary()

    def moment(text: str | None) -> datetime | None:
        return None if text is None else datetime.fromisoformat(text)

    session.add(
        ValuationSnapshotRecord(
            snapshot_id=manifest.snapshot_id,
            as_of_utc=manifest.as_of_utc,
            purpose=purpose,
            created_by=created_by,
            created_at_utc=now_utc or datetime.now(UTC),
            demo_desk=manifest.demo_desk,
            simulated=manifest.simulated,
            quality_class=manifest.quality.value,
            fx_method=manifest.fx_method,
            assumption_version_id=manifest.assumption_version,
            curve_as_of_utc=moment(summary["curve_as_of_utc"]),
            fx_as_of_utc=moment(summary["fx_as_of_utc"]),
            rates_as_of_utc=moment(summary["rates_as_of_utc"]),
            book_as_of_utc=moment(summary["book_as_of_utc"]),
            tariff_documents=summary["tariff_documents"],
            input_count=len(manifest.inputs),
            inputs_sha256=manifest.digest(),
        )
    )
    session.flush()
    for seq, item in enumerate(manifest.inputs):
        data = item.to_json()
        session.add(
            ValuationSnapshotInputRecord(
                snapshot_id=manifest.snapshot_id,
                input_key=item.key,
                seq=seq,
                kind=data["kind"],
                input_class=data["input_class"],
                value_text=data["value"],
                unit=data["unit"],
                currency=data["currency"],
                as_of_utc=item.as_of_utc,
                source_family=data["source_family"],
                source_ref=data["source_ref"][:200],
                label=data["label"],
                detail_json=data["detail"],
            )
        )
    session.flush()
    return manifest.snapshot_id


def load_snapshot(session: Session, snapshot_id: str) -> tuple[dict, SnapshotManifest] | None:
    """The stored header and the manifest a replay serves, or ``None``."""

    header = session.get(ValuationSnapshotRecord, snapshot_id)
    if header is None:
        return None
    rows = (
        session.query(ValuationSnapshotInputRecord)
        .filter(ValuationSnapshotInputRecord.snapshot_id == snapshot_id)
        .order_by(ValuationSnapshotInputRecord.seq)
        .all()
    )
    inputs = tuple(
        SnapshotInput.from_json(
            {
                "key": row.input_key,
                "kind": row.kind,
                "input_class": row.input_class,
                "value": row.value_text,
                "unit": row.unit,
                "currency": row.currency,
                "as_of_utc": (None if row.as_of_utc is None else _aware(row.as_of_utc).isoformat()),
                "source_family": row.source_family,
                "source_ref": row.source_ref,
                "label": row.label,
                "detail": row.detail_json,
            }
        )
        for row in rows
    )
    manifest = SnapshotManifest(
        snapshot_id=header.snapshot_id,
        as_of_utc=_aware(header.as_of_utc),
        demo_desk=header.demo_desk,
        fx_method=header.fx_method,
        assumption_version=header.assumption_version_id,
        inputs=inputs,
    )
    meta = {
        "snapshot_id": header.snapshot_id,
        "as_of_utc": _aware(header.as_of_utc).isoformat(),
        "purpose": header.purpose,
        "created_by": header.created_by,
        "created_at_utc": _aware(header.created_at_utc).isoformat(),
        "demo_desk": header.demo_desk,
        "simulated": header.simulated,
        "quality_class": header.quality_class,
        "fx_method": header.fx_method,
        "assumption_version_id": header.assumption_version_id,
        "input_count": header.input_count,
        "inputs_sha256": header.inputs_sha256,
        "summary": manifest.summary(),
    }
    return meta, manifest
