"""The tariff book: versions of every public tariff, capacity notices, freshness (TAR-1).

What it records
---------------
Route pricing and valuations keep reading the registers they read today: ``tso_tariffs``
(ENTSOG reserve prices, administrators' reviewed entries, documents loaded by an
administrator) and ``lng_terminal_tariff`` (terminal documents, when the firm has recorded the
operator's permission). Those registers hold the figure in force and are overwritten when a
publisher republishes. This module keeps their history: :func:`record_versions` compares each
register row with the current version of its tariff (``domain/tariffs/model.decide_version``)
and, when the content hash differs, writes version ``n + 1`` to ``tariff_versions``, stamps the
old one ``superseded_at_utc`` and publishes one ``tariff.changed`` market event in the same
transaction. A row that left a register is recorded as ``withdrawn``.

When it runs
------------
* inside the ENTSOG tariff read (``ingestion/entsog_tariffs.persist_entsog_tariffs``), for the
  point just read, in that point's transaction: the event commits with the figure;
* in every scheduler cycle through ``market_event_capture.capture`` (kind ``tariffs``), over the
  whole register: it catches an administrator's entry or review, a terminal document, and
  withdrawals; content already held writes nothing;
* ``scripts/ops/tariff_book.py sync`` by hand.

The event carries the snapshot keys an opportunity stores for a tariff
(``tariff:<point>:<DIR>:<PRODUCT>:<gas year>[:<operator>]``, ``domain/valuation/snapshot``), and
the stored dependency keys that begin with the same point, direction and product, so the outbox
re-runs only the evaluators that read the changed tariff; the input class ``tariffs`` is also
marked pending, so the debounced full sweep discovers what the change makes newly possible.

Capacity notices
----------------
``capacity_notices`` holds upcoming windows: the CAM standard auctions, derived from the
regulation and labelled so (:func:`refresh_standard_auctions`), and notices imported from a
publisher's own list (:func:`import_capacity_notices`: LNG slot offers, secondary-capacity
windows, a moved auction date). A changed notice updates its row and counts a revision.

Freshness
---------
:func:`publisher_status` says, per publisher, when it was last read, what is held, and whether
an expected update was missed: an automated publisher not read within its stale threshold, or
an operator on ENTSOG that has not published reserve prices for its next tariff period by the
NC TAR deadline (30 days before the July yearly auction). :func:`monitoring_candidates` turns
those, and windows opening within three days, into monitoring alerts (M6, routed by M7).

TAR-1：公开费率版本簿、容量通知与发布方新鲜度。
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.tariffs.model import (
    BASIS_AWAITING_REVIEW,
    BASIS_FIGURES_DISAGREE,
    BASIS_OPERATOR_STATED,
    BASIS_REVIEWED,
    FINAL,
    INDICATIVE,
    ChangeKind,
    HeldVersion,
    TariffError,
    TariffSpec,
    decide_version,
    status_as_of,
    status_change_label,
)
from eurogas_nexus.domain.tariffs.publishers import (
    PUBLISHERS,
    lng_publisher_for,
    publisher,
)
from eurogas_nexus.domain.tariffs.tariff_year import (
    BASIS_AUCTION_HELD,
    BASIS_BEFORE_AUCTION,
    PER_ROW,
    RULE_TEXT,
    parse_tariff_year,
    tariff_year_for,
)

ENTSOG_API = "https://transparency.entsog.eu/api/v1/tariffsfulls"
#: Register publishers whose rows are enumerated in full by :func:`register_specs`, so a key
#: no longer present was withdrawn.
REGISTER_PUBLISHERS = ("entsog-tp", "tso-entries", "register-documents")
#: Windows opening within this many days raise a capacity alert.
NOTICE_ALERT_DAYS = 3
#: How far ahead the standard auction calendar is kept.
AUCTION_HORIZON_DAYS = 400
#: Most dependency keys one tariff event carries.
MAX_DEPENDENCY_KEYS = 40

NOTICE_KINDS = ("auction", "lng_slot", "secondary_capacity")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    return value.isoformat()


def _day(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def source_family(publisher_id: str) -> str:
    """The source family a publisher's figures are entitled and metered under."""

    item = publisher(publisher_id)
    return item.source_family if item is not None else "operator-input"


# ------------------------------------------------------------------- register -> specs


_URL = re.compile(r"https://[^\s,;)]+")
_PUBLISHED_ON = re.compile(r"published on (\d{4}-\d{2}-\d{2})")


def _refs(row: Any) -> list[str]:
    return [str(ref) for ref in (getattr(row, "source_refs", None) or [])]


def _entsog_basis(row: Any) -> str:
    refs = _refs(row)
    if any(ref.startswith("check:") for ref in refs):
        return BASIS_FIGURES_DISAGREE
    remarks = " ".join(ref for ref in refs if ref.startswith("remarks:")).lower()
    if any(word in remarks for word in ("indicative", "provisional", "preliminary", "final")):
        return BASIS_OPERATOR_STATED
    # No marker on the row: the ingestion applied NC TAR Art. 29's rule as of the read
    # (``tariff_year.nc_tar_status``); the basis names it, and reads re-evaluate it as of T.
    return BASIS_AUCTION_HELD if row.tariff_status == FINAL else BASIS_BEFORE_AUCTION


def register_tariff_year(row: Any, publisher_id: str) -> str:
    """The tariff year of a ``tso_tariffs`` row: ENTSOG's own tariff period (the gas-year
    column), else the publisher's convention for the row's first day."""

    if publisher_id == "entsog-tp":
        parsed = parse_tariff_year(str(row.gas_year or ""))
        if parsed is not None:
            return parsed.label
    start = _day(row.effective_from)
    item = publisher(publisher_id)
    convention = item.tariff_year if item is not None else PER_ROW
    return tariff_year_for(start, _day(row.effective_to), convention).label if start else ""


def register_publisher(tariff_id: str) -> str:
    """Which publisher a ``tso_tariffs`` row comes from, by its id."""

    if tariff_id.startswith("entsog-"):
        return "entsog-tp"
    if tariff_id.startswith("entry-"):
        return "tso-entries"
    return "register-documents"


def spec_from_register_row(row: Any) -> TariffSpec | str:
    """A ``tso_tariffs`` row as a tariff spec, or why it is not versioned.

    Demo rows (``SIMULATOR_ONLY``) are not publications and are never versioned.
    """

    stored = str(row.tariff_status or "").upper()
    if stored == "SIMULATOR_ONLY":
        return "simulated"
    tariff_id = str(row.tariff_id)
    publisher_id = register_publisher(tariff_id)
    refs = _refs(row)
    published_at = None
    if publisher_id == "entsog-tp":
        url = f"{ENTSOG_API}?pointKey={row.point_id}"
        basis = _entsog_basis(row)
    else:
        found = next((m.group(0) for ref in refs for m in [_URL.search(ref)] if m), None)
        if found is None:
            return "no_source_url"
        url = found.rstrip(".")
        if publisher_id == "tso-entries":
            basis = BASIS_AWAITING_REVIEW if row.manual_review_required else BASIS_REVIEWED
            when = next(
                (m.group(1) for ref in refs for m in [_PUBLISHED_ON.search(ref)] if m), None
            )
            if when:
                published_at = datetime.combine(
                    date.fromisoformat(when), datetime.min.time(), tzinfo=UTC
                )
        else:
            basis = BASIS_OPERATOR_STATED
    status = FINAL if stored == FINAL else INDICATIVE
    if stored not in {FINAL, INDICATIVE}:
        # PROVISIONAL and DRAFT price as indicative; the version says so.
        basis = BASIS_OPERATOR_STATED
    start = _day(row.effective_from)
    try:
        return TariffSpec(
            tariff_key=f"{publisher_id}:{tariff_id}",
            publisher_id=publisher_id,
            facility_kind="point",
            facility_id=str(row.point_id),
            facility_name=str(row.source_point_name or row.point_id),
            operator=str(row.tso or ""),
            country=row.country or None,
            market_area=row.market_area or None,
            direction=str(row.direction or "").upper() or None,
            product=str(row.capacity_product or "").upper(),
            firmness=str(row.firmness or "").upper() or None,
            value=float(row.tariff_value),
            unit=str(row.unit),
            currency=str(row.currency or "").upper()[:3],
            period_from=start,
            period_to=_day(row.effective_to),
            status=status,
            status_basis=basis,
            published_at_utc=published_at,
            retrieved_at_utc=_aware(row.created_at_utc),
            source_url=url[:500],
            source_ref=f"{row.document_id}:{tariff_id}"[:256],
            tariff_year=register_tariff_year(row, publisher_id),
        )
    except (TariffError, TypeError, ValueError):
        return "not_a_tariff"


def lng_identity(row: Any, publisher_id: str) -> str:
    start = row.valid_from.isoformat() if row.valid_from else (row.period_label or "open")
    return ":".join(
        (publisher_id, row.terminal_id, row.service, row.product, row.charge_basis, start)
    )[:200]


def spec_from_lng_row(row: Any) -> TariffSpec | str:
    """An ``lng_terminal_tariff`` row (one figure of one terminal document) as a spec.

    A reviewed row is FINAL (a second person checked it against the published, regulated
    tariff); a candidate is INDICATIVE until reviewed, as it prices.
    """

    publisher_id = lng_publisher_for(str(row.terminal_id))
    if publisher_id is None:
        return "terminal_not_in_registry"
    reviewed = row.review_status == "REVIEWED"
    start = row.valid_from or _day(row.retrieved_at_utc)
    item = publisher(publisher_id)
    convention = item.tariff_year if item is not None else PER_ROW
    try:
        return TariffSpec(
            tariff_key=lng_identity(row, publisher_id),
            publisher_id=publisher_id,
            facility_kind="terminal",
            facility_id=str(row.terminal_id),
            facility_name=str(row.terminal_name),
            operator=str(row.operator),
            country=row.country,
            market_area=row.hub,
            product=f"{row.service}/{row.product}"[:32],
            value=None if row.amount is None else float(row.amount),
            by_class={str(k): float(v) for k, v in (row.by_cargo_class or {}).items()},
            unit=str(row.unit),
            currency=str(row.currency),
            period_from=start,
            period_to=row.valid_to,
            tariff_year=tariff_year_for(start, row.valid_to, convention).label,
            status=FINAL if reviewed else INDICATIVE,
            status_basis=BASIS_REVIEWED if reviewed else BASIS_AWAITING_REVIEW,
            retrieved_at_utc=_aware(row.retrieved_at_utc),
            source_url=str(row.source_url),
            source_ref=f"sha256:{row.source_sha256}"[:256],
        )
    except (TariffError, TypeError, ValueError):
        return "not_a_tariff"


def register_specs(session) -> tuple[list[TariffSpec], dict[str, int]]:
    """Every register row as a spec (newest document per terminal tariff), and skips by reason."""

    from eurogas_nexus.db.models import LngTerminalTariffRecord, TsoTariffRecord

    specs: list[TariffSpec] = []
    skipped: dict[str, int] = {}
    for row in session.query(TsoTariffRecord).all():
        spec = spec_from_register_row(row)
        if isinstance(spec, str):
            skipped[spec] = skipped.get(spec, 0) + 1
        else:
            specs.append(spec)
    newest: dict[str, TariffSpec] = {}
    for row in session.query(LngTerminalTariffRecord).all():
        spec = spec_from_lng_row(row)
        if isinstance(spec, str):
            skipped[spec] = skipped.get(spec, 0) + 1
            continue
        held = newest.get(spec.tariff_key)
        if held is None or spec.retrieved_at_utc >= held.retrieved_at_utc:
            newest[spec.tariff_key] = spec
    specs.extend(newest.values())
    return specs, skipped


# ------------------------------------------------------------------------- versions


def version_id(tariff_key: str, version: int) -> str:
    digest = hashlib.sha256(tariff_key.encode("utf-8")).hexdigest()[:32]
    return f"tv-{digest}-{version}"


def _current(session, keys: Iterable[str] | None = None) -> dict[str, Any]:
    from eurogas_nexus.db.models import TariffVersionRecord

    query = session.query(TariffVersionRecord).filter(
        TariffVersionRecord.superseded_at_utc.is_(None)
    )
    if keys is None:
        return {row.tariff_key: row for row in query.all()}
    wanted = sorted(set(keys))
    out: dict[str, Any] = {}
    for start in range(0, len(wanted), 500):
        chunk = wanted[start : start + 500]
        for row in query.filter(TariffVersionRecord.tariff_key.in_(chunk)).all():
            out[row.tariff_key] = row
    return out


def _gas_years(start: date, end: date | None) -> list[str]:
    last = end or start
    first_year = start.year if start.month >= 10 else start.year - 1
    last_year = last.year if last.month >= 10 else last.year - 1
    years = range(first_year, min(last_year, first_year + 5) + 1)
    return [f"{year}/{(year + 1) % 100:02d}" for year in years]


def _operator_slug(operator: str) -> str:
    return "-".join(operator.lower().replace("/", " ").split())


class _StoredKeys:
    """The tariff dependency keys opportunities hold, by their point/direction/product prefix."""

    def __init__(self, session) -> None:
        from eurogas_nexus.db.models import OpportunityDependencyRecord

        self.by_prefix: dict[str, set[str]] = {}
        rows = (
            session.query(OpportunityDependencyRecord.input_key)
            .filter(OpportunityDependencyRecord.input_key.like("tariff:%"))
            .distinct()
            .all()
        )
        for (key,) in rows:
            parts = str(key).split(":")
            if len(parts) >= 5:
                prefix = ":".join(parts[:5]).split("#", 1)[0]
                self.by_prefix.setdefault(prefix, set()).add(str(key))


def dependency_keys(spec_like: Any, stored: _StoredKeys | None = None) -> list[str]:
    """The valuation snapshot keys a tariff version touches (design J.2 key format)."""

    if spec_like.facility_kind != "point" or not spec_like.direction:
        return []
    keys: set[str] = set()
    for gas_year in _gas_years(spec_like.period_from, spec_like.period_to):
        base = (
            f"tariff:{spec_like.facility_id}:{spec_like.direction.upper()}:"
            f"{spec_like.product.upper()}:{gas_year}"
        )
        keys.add(base)
        if spec_like.operator:
            keys.add(f"{base}:{_operator_slug(spec_like.operator)}")
        if stored is not None:
            keys |= stored.by_prefix.get(base, set())
    return sorted(key for key in keys if len(key) <= 160)[:MAX_DEPENDENCY_KEYS]


def _payload(record: Any, previous_status: str | None) -> dict[str, Any]:
    return {
        "tariff_key": record.tariff_key,
        "version": record.version,
        "change_kind": record.change_kind,
        "status": record.status,
        "status_basis": record.status_basis,
        "previous_status": previous_status,
        "status_change": record.status_change,
        "publisher_id": record.publisher_id,
        "facility_id": record.facility_id,
        "operator": record.operator,
        "direction": record.direction,
        "product": record.product,
        "firmness": record.firmness,
        "value": record.value,
        "unit": record.unit,
        "currency": record.currency,
        "period_from": _iso(record.period_from),
        "period_to": _iso(record.period_to),
        "source_url": record.source_url,
        "content_hash": record.content_hash,
        "tariff_year": year_of_record(record).label,
        "published_at_utc": _iso(record.published_at_utc),
        "recorded_at_utc": _iso(record.recorded_at_utc),
        # TAR-2: a newly final tariff year is what a desk waits for; it is flagged so.
        "new_final": record.status == FINAL
        and record.change_kind in {ChangeKind.FIRST.value, ChangeKind.STATUS_CHANGE.value},
    }


def tariff_event(record: Any, previous_status: str | None, keys: Sequence[str]):
    """The ``tariff.changed`` event one version publishes."""

    from eurogas_nexus.domain.market_events import MarketEvent

    subject = ":".join(
        (
            "tariff",
            record.facility_id,
            record.direction or record.facility_kind,
            record.product,
            record.period_from.isoformat(),
        )
    )[:160]
    return MarketEvent(
        source_id=source_family(record.publisher_id),
        event_type="tariff.changed",
        subject_key=subject,
        identity=f"tariff-version:{record.tariff_key}",
        ingested_at_utc=_aware(record.recorded_at_utc),
        market_time_utc=datetime.combine(record.period_from, datetime.min.time(), tzinfo=UTC),
        published_at_utc=_aware(record.published_at_utc),
        payload=_payload(record, previous_status),
        dependency_keys=tuple(keys) or (f"tariff-version:{record.tariff_key}"[:160],),
        # A newly final tariff year is what a desk waits for: ahead of other tariff revisions.
        priority=1
        if record.status_change == "INDICATIVE->FINAL"
        or (record.status == FINAL and record.change_kind == ChangeKind.FIRST.value)
        else None,
        correlation_id=record.version_id,
    )


@dataclass
class RecordResult:
    """What one :func:`record_versions` call did."""

    examined: int = 0
    written: dict[str, int] = field(default_factory=dict)
    unchanged: int = 0
    out_of_order: int = 0
    events: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    version_ids: list[str] = field(default_factory=list)

    def count(self, kind: str) -> None:
        self.written[kind] = self.written.get(kind, 0) + 1

    def to_json(self) -> dict[str, Any]:
        return {
            "examined": self.examined,
            "written": dict(sorted(self.written.items())),
            "unchanged": self.unchanged,
            "out_of_order": self.out_of_order,
            "events": self.events,
            "skipped": dict(sorted(self.skipped.items())),
        }


def _new_record(spec: TariffSpec, *, version: int, kind: ChangeKind, previous: str | None, now):
    from eurogas_nexus.db.models import TariffVersionRecord

    return TariffVersionRecord(
        version_id=version_id(spec.tariff_key, version),
        tariff_key=spec.tariff_key,
        version=version,
        change_kind=kind.value,
        status_change=status_change_label(previous, spec.status),
        publisher_id=spec.publisher_id,
        facility_kind=spec.facility_kind,
        facility_id=spec.facility_id[:128],
        facility_name=spec.facility_name[:256],
        operator=spec.operator[:128],
        country=(spec.country or None) and spec.country[:8],
        market_area=(spec.market_area or None) and spec.market_area[:64],
        direction=spec.direction,
        product=spec.product[:32],
        duration=spec.duration,
        firmness=spec.firmness,
        value=spec.value,
        by_class=dict(spec.by_class) or None,
        unit=spec.unit[:32],
        currency=spec.currency[:3],
        period_from=spec.period_from,
        period_to=spec.period_to,
        status=spec.status,
        status_basis=spec.status_basis,
        published_at_utc=spec.published_at_utc,
        retrieved_at_utc=spec.retrieved_at_utc,
        source_url=spec.source_url[:500],
        source_ref=spec.source_ref[:256] or spec.tariff_key[:256],
        content_hash=spec.content_hash,
        recorded_at_utc=now,
        superseded_at_utc=None,
        tariff_year=spec.tariff_year or None,
    )


def _withdrawal(held: Any, now: datetime):
    from eurogas_nexus.db.models import TariffVersionRecord

    version = held.version + 1
    columns = {
        column: getattr(held, column)
        for column in TariffVersionRecord.__table__.columns.keys()
        if column
        not in {
            "version_id",
            "version",
            "change_kind",
            "status_change",
            "recorded_at_utc",
            "superseded_at_utc",
            "event_id",
            "content_hash",
        }
    }
    return TariffVersionRecord(
        **columns,
        version_id=version_id(held.tariff_key, version),
        version=version,
        change_kind=ChangeKind.WITHDRAWN.value,
        status_change=None,
        content_hash=hashlib.sha256(f"withdrawn:{held.content_hash}".encode()).hexdigest(),
        recorded_at_utc=now,
        superseded_at_utc=None,
    )


def record_versions(
    session,
    specs: Iterable[TariffSpec],
    *,
    now_utc: datetime | None = None,
    withdraw_missing_for: Sequence[str] = (),
    publish: bool = True,
) -> RecordResult:
    """Record a new version for each spec whose content changed; commit is the caller's.

    Args:
        specs: Tariffs as their publishers state them now (later duplicates of a key win).
        withdraw_missing_for: Publishers whose specs are complete here: a current version of
            theirs with no spec is recorded as ``withdrawn``.
        publish: Publish one ``tariff.changed`` event per version written (default).
    """

    from eurogas_nexus.application import market_events as outbox

    now = _aware(now_utc) or datetime.now(UTC)
    result = RecordResult()
    by_key: dict[str, TariffSpec] = {}
    for spec in specs:
        by_key[spec.tariff_key] = spec
    result.examined = len(by_key)
    withdraw = set(withdraw_missing_for)
    held_all = _current(session, None if withdraw else by_key)
    written: list[tuple[Any, str | None]] = []
    for key in sorted(by_key):
        spec = by_key[key]
        current = held_all.get(key)
        held = None
        if current is not None:
            held = HeldVersion(
                current.version,
                current.content_hash,
                current.status,
                _aware(current.retrieved_at_utc),
                withdrawn=current.change_kind == ChangeKind.WITHDRAWN.value,
            )
        decision = decide_version(spec, held)
        if not decision.writes:
            if decision.reason == "out_of_order":
                result.out_of_order += 1
            else:
                result.unchanged += 1
            continue
        if current is not None:
            current.superseded_at_utc = now
            session.flush()
        record = _new_record(
            spec,
            version=decision.version,
            kind=decision.kind,
            previous=decision.previous_status,
            now=now,
        )
        session.add(record)
        written.append((record, decision.previous_status))
        result.count(decision.kind.value)
    for key, current in sorted(held_all.items()):
        if (
            current.publisher_id in withdraw
            and key not in by_key
            and current.change_kind != ChangeKind.WITHDRAWN.value
        ):
            current.superseded_at_utc = now
            session.flush()
            record = _withdrawal(current, now)
            session.add(record)
            written.append((record, current.status))
            result.count(ChangeKind.WITHDRAWN.value)
    session.flush()
    if written and publish:
        stored = _StoredKeys(session)
        for record, previous in written:
            published = outbox.publish(
                session, tariff_event(record, previous, dependency_keys(record, stored))
            )
            if published.kind.value in {"new", "revision"}:
                record.event_id = published.event_id
                result.events += 1
        from eurogas_nexus.application.opportunities.schedule import note_input_changed

        note_input_changed(
            session, "tariffs", reason=f"{len(written)} tariff version(s) recorded", at_utc=now
        )
        session.flush()
    result.version_ids = [record.version_id for record, _ in written]
    return result


def record_register_rows(session, rows: Iterable[Any], *, now_utc: datetime | None = None):
    """Version ``tso_tariffs`` rows a writer has just stored (the ENTSOG read, an entry)."""

    specs: list[TariffSpec] = []
    skipped: dict[str, int] = {}
    for row in rows:
        spec = spec_from_register_row(row)
        if isinstance(spec, str):
            skipped[spec] = skipped.get(spec, 0) + 1
        else:
            specs.append(spec)
    result = record_versions(session, specs, now_utc=now_utc)
    result.skipped = skipped
    return result


#: A scheduled capture skips a register that has not changed, but makes a full pass at least
#: this often (it also refreshes the rule-derived auction calendar).
FULL_PASS_EVERY = timedelta(hours=1)
_LAST_PASS: dict[str, tuple[tuple, datetime]] = {}


def register_signature(session) -> tuple:
    """A cheap digest of the registers: rows, newest receipt, rows under review, rows final.

    An ENTSOG read, an administrator's entry or review, a retired entry and a terminal
    document or review each change it; an in-place edit that changes none of these waits for
    the hourly full pass.
    """

    from sqlalchemy import case, func

    from eurogas_nexus.db.models import LngTerminalTariffRecord as L
    from eurogas_nexus.db.models import TsoTariffRecord as R

    tso = session.query(
        func.count(),
        func.max(R.created_at_utc),
        func.sum(case((R.manual_review_required.is_(True), 1), else_=0)),
        func.sum(case((R.tariff_status == FINAL, 1), else_=0)),
    ).one()
    lng = session.query(
        func.count(),
        func.max(L.created_at_utc),
        func.sum(case((L.review_status == "REVIEWED", 1), else_=0)),
    ).one()
    return tuple(str(item) for item in (*tso, *lng))


def capture_tariffs(
    session, *, now_utc: datetime | None = None, only_if_changed: bool = False
) -> dict[str, Any]:
    """Version the whole register and refresh the standard auction calendar; commit is the
    caller's. Content already held writes nothing, so it is safe every scheduler cycle.

    ``only_if_changed`` (the scheduler's capture): skip when :func:`register_signature` is the
    one this process saw at its last pass and that pass is under :data:`FULL_PASS_EVERY` old.
    A full pass over 12,670 ENTSOG rows with nothing new takes about 2 s on PostgreSQL; the
    signature is two aggregate queries.
    """

    now = _aware(now_utc) or datetime.now(UTC)
    bind = str(getattr(session.get_bind(), "url", "default"))
    signature = register_signature(session)
    held = _LAST_PASS.get(bind)
    if only_if_changed and held and held[0] == signature and now - held[1] < FULL_PASS_EVERY:
        return {"skipped": "registers unchanged since the last pass"}
    specs, skipped = register_specs(session)
    lng = tuple(item.publisher_id for item in PUBLISHERS if item.kind == "lng_terminal")
    result = record_versions(
        session, specs, now_utc=now, withdraw_missing_for=REGISTER_PUBLISHERS + lng
    )
    result.skipped = skipped
    notices = refresh_standard_auctions(session, now_utc=now)
    _LAST_PASS[bind] = (signature, now)
    return {"tariffs": result.to_json(), "notices": notices}


# ---------------------------------------------------------------------------- reads


def version_row(record: Any) -> dict[str, Any]:
    """One version as the API returns it."""

    item = publisher(record.publisher_id)
    return {
        "tariff_key": record.tariff_key,
        "version": record.version,
        "version_id": record.version_id,
        "change_kind": record.change_kind,
        "status": record.status,
        "status_basis": record.status_basis,
        "status_change": record.status_change,
        "data_class": "sourced" if record.status == FINAL else "indicative",
        "publisher_id": record.publisher_id,
        "publisher_name": item.name if item else record.publisher_id,
        "facility_kind": record.facility_kind,
        "facility_id": record.facility_id,
        "facility_name": record.facility_name,
        "operator": record.operator,
        "country": record.country,
        "market_area": record.market_area,
        "direction": record.direction,
        "product": record.product,
        "duration": record.duration,
        "firmness": record.firmness,
        "value": record.value,
        "by_class": record.by_class,
        "unit": record.unit,
        "currency": record.currency,
        "period_from": _iso(record.period_from),
        "period_to": _iso(record.period_to),
        "published_at_utc": _iso(record.published_at_utc),
        "retrieved_at_utc": _iso(record.retrieved_at_utc),
        "recorded_at_utc": _iso(record.recorded_at_utc),
        "superseded_at_utc": _iso(record.superseded_at_utc),
        "source_url": record.source_url,
        "source_ref": record.source_ref,
        "content_hash": record.content_hash,
        "event_id": record.event_id,
        "withdrawn": record.change_kind == ChangeKind.WITHDRAWN.value,
        "tariff_year": year_of_record(record).label,
        "status_rule": RULE_TEXT.get(record.status_basis),
        "new": _is_new(record),
        "published_at_stated": record.published_at_utc is not None,
    }


def _is_new(record: Any, now: datetime | None = None) -> bool:
    """Recorded within :data:`NEW_FOR` and a first, revised or newly final figure."""

    recorded = _aware(record.recorded_at_utc)
    moment = _aware(now) or datetime.now(UTC)
    return (
        recorded is not None
        and moment - recorded <= NEW_FOR
        and record.change_kind != ChangeKind.WITHDRAWN.value
    )


def version_at(session, tariff_key: str, at: datetime | None = None):
    """The version of one tariff in force at ``at`` (now when ``None``), or ``None``."""

    from sqlalchemy import or_

    from eurogas_nexus.db.models import TariffVersionRecord as V

    query = session.query(V).filter(V.tariff_key == tariff_key)
    moment = _aware(at)
    if moment is None:
        query = query.filter(V.superseded_at_utc.is_(None))
    else:
        query = query.filter(V.recorded_at_utc <= moment).filter(
            or_(V.superseded_at_utc.is_(None), V.superseded_at_utc > moment)
        )
    row = query.order_by(V.version.desc()).first()
    if row is None or row.change_kind == ChangeKind.WITHDRAWN.value:
        return None
    return row


# ------------------------------------------------------------- point in time (TAR-2)

#: A version recorded within this long is flagged ``new`` in reads (the desk's "just published").
NEW_FOR = timedelta(days=7)


def year_of_record(record: Any) -> Any:
    """The tariff year of a version: its stored label, else worked out from its period with
    its publisher's convention (versions recorded before TAR-2)."""

    parsed = parse_tariff_year(getattr(record, "tariff_year", None) or "")
    if parsed is not None:
        return parsed
    item = publisher(record.publisher_id)
    convention = item.tariff_year if item is not None else PER_ROW
    return tariff_year_for(_day(record.period_from), _day(record.period_to), convention)


def effective_status(record: Any, as_of: datetime | None = None) -> tuple[str, str]:
    """A version's ``(status, basis)`` as of ``as_of`` (now when ``None``): NC TAR's rule
    re-evaluated for a row that carries no marker, else what was stated."""

    moment = _aware(as_of) or datetime.now(UTC)
    year = year_of_record(record)
    return status_as_of(record.status, record.status_basis, year.first, moment.date())


def _version_fields(record: Any, as_of: datetime | None) -> dict[str, Any]:
    status, basis = effective_status(record, as_of)
    return {
        "version_id": record.version_id,
        "version": record.version,
        "tariff_year": year_of_record(record).label,
        "status_basis": basis,
        "published_at_utc": _aware(record.published_at_utc),
        "recorded_at_utc": _aware(record.recorded_at_utc),
        "tariff_status": status,
    }


def annotate_register_rows(session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Register rows (route pricing's input) with their current version and, for a status a
    rule decides, the status as of now. Simulated rows are not versioned and stay as they are.
    """

    keys = {
        f"{register_publisher(str(row['tariff_id']))}:{row['tariff_id']}": row
        for row in rows
        if str(row.get("tariff_status") or "").upper() != "SIMULATOR_ONLY"
    }
    if not keys:
        return rows
    for key, record in _current(session, keys).items():
        if record.change_kind == ChangeKind.WITHDRAWN.value:
            continue
        keys[key].update(_version_fields(record, None))
    return rows


def tariff_versions_as_rows(
    session, *, product: str, firmness: str, as_of: datetime
) -> list[dict[str, Any]]:
    """The point tariffs the book held at ``as_of``, shaped as register rows, so route pricing
    prices a past instant with what was known then (never a version recorded later)."""

    from sqlalchemy import or_

    from eurogas_nexus.db.models import TariffVersionRecord as V

    moment = _aware(as_of)
    query = (
        session.query(V)
        .filter(V.publisher_id.in_(REGISTER_PUBLISHERS))
        .filter(V.facility_kind == "point")
        .filter(V.product == product.upper())
        .filter(or_(V.firmness.is_(None), V.firmness == firmness.upper()))
        .filter(V.recorded_at_utc <= moment)
        .filter(or_(V.superseded_at_utc.is_(None), V.superseded_at_utc > moment))
        .filter(V.change_kind != ChangeKind.WITHDRAWN.value)
    )
    out = []
    for record in query.all():
        fields_ = _version_fields(record, moment)
        out.append(
            {
                "tariff_id": record.tariff_key.split(":", 1)[1],
                "tso": record.operator,
                "point_id": record.facility_id,
                "direction": record.direction,
                "gas_year": fields_["tariff_year"],
                "tariff_value": record.value,
                "currency": record.currency,
                "unit": record.unit,
                "effective_from": datetime.combine(record.period_from, datetime.min.time(),
                                                   tzinfo=UTC),
                "effective_to": None
                if record.period_to is None
                else datetime.combine(record.period_to, datetime.min.time(), tzinfo=UTC),
                "source_table": f"tariff book v{record.version} ({record.publisher_id})",
                "capacity_product": record.product,
                "firmness": record.firmness,
                **fields_,
            }
        )
    return out


def tariff_years(
    session,
    *,
    facility_id: str,
    direction: str | None = None,
    product: str | None = None,
    operator: str | None = None,
    as_of: datetime | None = None,
    allowed_publishers: Iterable[str] | None = None,
) -> dict[str, Any]:
    """The tariff book of one facility by tariff year: per year and product, the indicative
    and the final version side by side (each with its value, publication date, record time
    and source), and which one a decision as of ``as_of`` uses (final once one is held, else
    indicative). Versions recorded after ``as_of`` are left out."""

    from eurogas_nexus.db.models import TariffVersionRecord as V

    moment = _aware(as_of)
    query = session.query(V).filter(V.facility_id == facility_id)
    if direction:
        query = query.filter(V.direction == direction.upper())
    if product:
        query = query.filter(V.product == product.upper())
    if operator:
        query = query.filter(V.operator == operator)
    if allowed_publishers is not None:
        query = query.filter(V.publisher_id.in_(sorted(set(allowed_publishers))))
    if moment is not None:
        query = query.filter(V.recorded_at_utc <= moment)
    groups: dict[tuple, dict[str, Any]] = {}
    for record in query.order_by(V.recorded_at_utc, V.version).all():
        if record.change_kind == ChangeKind.WITHDRAWN.value:
            continue
        year = year_of_record(record)
        status, basis = effective_status(record, moment)
        group_key = (
            year.label, record.direction or "", record.product, record.firmness or "",
            record.operator, record.period_from.isoformat(),
        )
        group = groups.setdefault(
            group_key,
            {
                "tariff_year": year.as_dict(),
                "direction": record.direction,
                "product": record.product,
                "firmness": record.firmness,
                "operator": record.operator,
                "period_from": _iso(record.period_from),
                "period_to": _iso(record.period_to),
                INDICATIVE: None,
                FINAL: None,
                "versions": 0,
            },
        )
        group["versions"] += 1
        row = version_row(record) | {"status": status, "status_basis": basis}
        # The newest version of each status held by the instant asked for.
        group[status] = row
    rows = []
    for key in sorted(groups):
        group = groups[key]
        used = group[FINAL] or group[INDICATIVE]
        group["used"] = None if used is None else used["status"]
        group["used_version_id"] = None if used is None else used["version_id"]
        rows.append(group)
    return {"facility_id": facility_id, "as_of": _iso(moment), "years": rows}


@dataclass(frozen=True)
class TariffFilter:
    publisher_id: str | None = None
    facility_id: str | None = None
    operator: str | None = None
    direction: str | None = None
    product: str | None = None
    status: str | None = None
    on: date | None = None
    tariff_key: str | None = None


def list_tariffs(
    session,
    *,
    filters: TariffFilter | None = None,
    as_of: datetime | None = None,
    history: bool = False,
    allowed_publishers: Iterable[str] | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    """Tariffs as known now or at ``as_of``: the version in force per key, or every version.

    ``history`` (needs ``tariff_key`` or ``facility_id``) returns every version recorded up to
    ``as_of`` (or now), oldest first per key, so a reader sees indicative become final.
    Withdrawn tariffs are left out of the current list and kept in the history.
    """

    from sqlalchemy import or_

    from eurogas_nexus.db.models import TariffVersionRecord as V

    filters = filters or TariffFilter()
    query = session.query(V)
    if filters.publisher_id:
        query = query.filter(V.publisher_id == filters.publisher_id)
    if filters.facility_id:
        query = query.filter(V.facility_id == filters.facility_id)
    if filters.tariff_key:
        query = query.filter(V.tariff_key == filters.tariff_key)
    if filters.direction:
        query = query.filter(V.direction == filters.direction.upper())
    if filters.product:
        query = query.filter(V.product == filters.product.upper())
    if filters.operator:
        query = query.filter(V.operator == filters.operator)
    if allowed_publishers is not None:
        query = query.filter(V.publisher_id.in_(sorted(set(allowed_publishers))))
    moment = _aware(as_of)
    if moment is not None:
        query = query.filter(V.recorded_at_utc <= moment)
    if not history:
        if moment is None:
            query = query.filter(V.superseded_at_utc.is_(None))
        else:
            query = query.filter(or_(V.superseded_at_utc.is_(None), V.superseded_at_utc > moment))
        query = query.filter(V.change_kind != ChangeKind.WITHDRAWN.value)
        if filters.status:
            query = query.filter(V.status == filters.status.upper())
        if filters.on:
            query = query.filter(V.period_from <= filters.on).filter(
                or_(V.period_to.is_(None), V.period_to >= filters.on)
            )
    total = query.count()
    order = (V.facility_name, V.direction, V.product, V.period_from, V.tariff_key, V.version)
    rows = query.order_by(*order).offset(offset).limit(limit).all()
    return {
        "rows": [version_row(row) for row in rows],
        "total": total,
        "as_of": _iso(moment),
        "history": history,
    }


def _last_read(session, publisher_id: str):
    """When the platform last read a publisher successfully (its own rows' receipt)."""

    from sqlalchemy import func

    from eurogas_nexus.db.models import CapacityNoticeRecord, TsoTariffRecord

    if publisher_id == "entsog-tp":
        return _aware(
            session.query(func.max(TsoTariffRecord.created_at_utc))
            .filter(TsoTariffRecord.tariff_id.like("entsog-%"))
            .scalar()
        )
    if publisher_id == "cam-nc-calendar":
        return _aware(
            session.query(func.max(CapacityNoticeRecord.retrieved_at_utc))
            .filter(CapacityNoticeRecord.publisher_id == publisher_id)
            .scalar()
        )
    return None


def final_deadline_for(period_start: date) -> date:
    """NC TAR: reserve prices for a tariff period are due 30 days before the yearly auction
    held in the July before the period starts."""

    from eurogas_nexus.domain.route_cost.tariff_calendar import annual_yearly_auction

    year = period_start.year if period_start.month > 7 else period_start.year - 1
    return annual_yearly_auction(year) - timedelta(days=30)


def missed_publications(session, *, today: date, publisher_id: str = "entsog-tp") -> list[dict]:
    """Operators whose next tariff period has no yearly price by the NC TAR deadline.

    Per operator, the last day of the latest yearly price held starts the next period; when
    its deadline has passed and no yearly price for that period is held, it is missed.
    Operators whose prices ended more than a year ago are not followed.
    """

    from eurogas_nexus.db.models import TariffVersionRecord as V

    latest: dict[str, date] = {}
    for operator, period_to in (
        session.query(V.operator, V.period_to)
        .filter(V.publisher_id == publisher_id)
        .filter(V.superseded_at_utc.is_(None))
        .filter(V.change_kind != ChangeKind.WITHDRAWN.value)
        .filter(V.product == "ANNUAL")
        .filter(V.period_to.is_not(None))
        .all()
    ):
        if operator not in latest or period_to > latest[operator]:
            latest[operator] = period_to
    missed = []
    for operator, period_to in sorted(latest.items()):
        next_start = period_to + timedelta(days=1)
        deadline = final_deadline_for(next_start)
        if deadline <= today and next_start >= today - timedelta(days=365):
            missed.append(
                {
                    "operator": operator,
                    "next_period_from": next_start.isoformat(),
                    "deadline": deadline.isoformat(),
                }
            )
    return missed


def _firm_permission(session, item) -> bool | None:
    """For a terminal operator whose terms need the firm's permission: whether it is recorded
    (``lng_terminal_tariff_register``); ``None`` where the platform records none."""

    if item.kind != "lng_terminal" or not item.facilities:
        return None
    from eurogas_nexus.application.lng_terminal_tariff_register import (
        operator_for_terminal,
        operator_permitted,
    )

    operator = operator_for_terminal(item.facilities[0])
    return None if operator is None else operator_permitted(session, operator)


def publisher_status(session, *, now_utc: datetime | None = None) -> list[dict[str, Any]]:
    """Every registry publisher with what is held, when it was last read, and its state.

    ``state``: ``current`` (read within its threshold), ``stale`` (an expected update was
    missed), ``never_read`` (automated, nothing held yet), ``manual`` (entered or imported by
    a person; no poll), ``excluded`` (terms forbid reuse without the firm's permission).
    """

    from sqlalchemy import func

    from eurogas_nexus.db.models import CapacityNoticeRecord
    from eurogas_nexus.db.models import TariffVersionRecord as V

    now = _aware(now_utc) or datetime.now(UTC)
    counts = {
        (publisher_id, status): count
        for publisher_id, status, count in session.query(V.publisher_id, V.status, func.count())
        .filter(V.superseded_at_utc.is_(None))
        .filter(V.change_kind != ChangeKind.WITHDRAWN.value)
        .group_by(V.publisher_id, V.status)
        .all()
    }
    changed = dict(
        session.query(V.publisher_id, func.max(V.recorded_at_utc)).group_by(V.publisher_id).all()
    )
    notices = dict(
        session.query(CapacityNoticeRecord.publisher_id, func.count())
        .group_by(CapacityNoticeRecord.publisher_id)
        .all()
    )
    out = []
    for item in PUBLISHERS:
        last = _last_read(session, item.publisher_id)
        stale_after = item.poll.stale_after_minutes if item.poll else None
        permitted = _firm_permission(session, item)
        if item.reuse == "needs_firm_terms" and not permitted:
            state = "excluded"
        elif not item.automated:
            state = "manual"
        elif last is None:
            state = "never_read"
        elif stale_after is not None and now - last > timedelta(minutes=stale_after):
            state = "stale"
        else:
            state = "current"
        missed = (
            missed_publications(session, today=now.date())
            if item.publisher_id == "entsog-tp"
            else []
        )
        out.append(
            item.to_json()
            | {
                "state": state,
                "last_read_at_utc": _iso(last),
                "last_changed_at_utc": _iso(_aware(changed.get(item.publisher_id))),
                "next_poll_minutes": (
                    item.poll.interval_minutes(now) if item.poll and item.automated else None
                ),
                "tariffs_final": counts.get((item.publisher_id, FINAL), 0),
                "tariffs_indicative": counts.get((item.publisher_id, INDICATIVE), 0),
                "notices": notices.get(item.publisher_id, 0),
                "missed_publications": missed,
                "firm_permission": permitted,
            }
        )
    return out


# --------------------------------------------------------------------------- notices


@dataclass(frozen=True)
class NoticeSpec:
    notice_key: str
    publisher_id: str
    kind: str
    basis: str
    product: str
    title: str
    opens_at_utc: datetime
    source_url: str
    retrieved_at_utc: datetime
    closes_at_utc: datetime | None = None
    offers_from: date | None = None
    offers_to: date | None = None
    facility_kind: str | None = None
    facility_id: str | None = None
    facility_name: str | None = None
    quantity: float | None = None
    quantity_unit: str | None = None
    state: str = "open"
    published_at_utc: datetime | None = None

    def content_hash(self) -> str:
        content = [
            self.kind,
            self.basis,
            self.product,
            self.title,
            _iso(self.opens_at_utc),
            _iso(self.closes_at_utc),
            _iso(self.offers_from),
            _iso(self.offers_to),
            self.facility_id,
            self.quantity,
            self.quantity_unit,
            self.state,
            self.source_url,
        ]
        return hashlib.sha256(repr(content).encode("utf-8")).hexdigest()


def record_notices(session, specs: Iterable[NoticeSpec], *, now_utc: datetime) -> dict[str, int]:
    """Insert new notices and update changed ones (revision + 1); commit is the caller's."""

    from eurogas_nexus.db.models import CapacityNoticeRecord

    now = _aware(now_utc)
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for spec in specs:
        digest = spec.content_hash()
        row = session.get(CapacityNoticeRecord, spec.notice_key)
        fields = {
            "publisher_id": spec.publisher_id,
            "kind": spec.kind,
            "basis": spec.basis,
            "facility_kind": spec.facility_kind,
            "facility_id": spec.facility_id,
            "facility_name": spec.facility_name,
            "product": spec.product,
            "title": spec.title[:256],
            "opens_at_utc": _aware(spec.opens_at_utc),
            "closes_at_utc": _aware(spec.closes_at_utc),
            "offers_from": spec.offers_from,
            "offers_to": spec.offers_to,
            "quantity": spec.quantity,
            "quantity_unit": spec.quantity_unit,
            "state": spec.state,
            "source_url": spec.source_url[:500],
            "published_at_utc": _aware(spec.published_at_utc),
            "retrieved_at_utc": _aware(spec.retrieved_at_utc),
            "content_hash": digest,
        }
        if row is None:
            session.add(
                CapacityNoticeRecord(
                    notice_key=spec.notice_key,
                    **fields,
                    first_recorded_at_utc=now,
                    changed_at_utc=now,
                    revision=1,
                )
            )
            counts["created"] += 1
            continue
        if row.content_hash == digest:
            row.retrieved_at_utc = _aware(spec.retrieved_at_utc)
            counts["unchanged"] += 1
            continue
        for name, value in fields.items():
            setattr(row, name, value)
        row.changed_at_utc = now
        row.revision += 1
        counts["updated"] += 1
    session.flush()
    return counts


def refresh_standard_auctions(
    session, *, now_utc: datetime | None = None, horizon_days: int = AUCTION_HORIZON_DAYS
) -> dict[str, int]:
    """Keep the CAM standard auctions opening from a week ago to ``horizon_days`` ahead."""

    from eurogas_nexus.domain.tariffs.auction_calendar import REGULATION_URL, standard_auctions

    now = _aware(now_utc) or datetime.now(UTC)
    windows = standard_auctions(
        now.date() - timedelta(days=7), now.date() + timedelta(days=horizon_days)
    )
    specs = [
        NoticeSpec(
            notice_key=window.notice_key,
            publisher_id="cam-nc-calendar",
            kind="auction",
            basis="rule_derived",
            product=window.product,
            title=f"{window.label} (rule-derived, CAM NC {window.article})",
            opens_at_utc=window.opens_at_utc,
            offers_from=window.offers_from,
            offers_to=window.offers_to,
            facility_kind="point",
            facility_id="all-interconnection-points",
            facility_name="Every EU interconnection point offering bundled capacity",
            source_url=REGULATION_URL,
            retrieved_at_utc=now,
        )
        for window in windows
    ]
    return record_notices(session, specs, now_utc=now)


class NoticeImportError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


#: Columns an imported notice file has (CSV header or JSON keys).
NOTICE_COLUMNS = (
    "notice_id",
    "kind",
    "product",
    "title",
    "opens_at_utc",
    "closes_at_utc",
    "offers_from",
    "offers_to",
    "facility_kind",
    "facility_id",
    "facility_name",
    "quantity",
    "quantity_unit",
    "state",
    "source_url",
    "published_at_utc",
)
_REQUIRED = ("notice_id", "kind", "product", "title", "opens_at_utc", "source_url")


def _parse_instant(text: str) -> datetime:
    value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("an instant needs a UTC offset")
    return value.astimezone(UTC)


def _row_text(row: Mapping[str, Any]):
    def read(name: str) -> str | None:
        return str(row.get(name) or "").strip() or None

    return read


def _row_day(row: Mapping[str, Any]):
    text = _row_text(row)

    def read(name: str) -> date | None:
        value = text(name)
        return date.fromisoformat(value) if value else None

    return read


def import_capacity_notices(
    session,
    rows: Sequence[Mapping[str, Any]],
    *,
    publisher_id: str,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Validate and record notices read from a publisher's own list (one row per notice).

    Each row is checked on its own; one refused row refuses the whole file (nothing stored)
    so a desk fixes the file rather than half-loading it. The publisher must be in the
    registry and publish that kind of notice, and must not be one whose terms exclude reuse.
    Every row needs an https ``source_url``: the publisher's own page for that notice.
    """

    item = publisher(publisher_id)
    if item is None:
        raise NoticeImportError("publisher_unknown", f"{publisher_id} is not in the registry")
    if item.reuse == "needs_firm_terms":
        raise NoticeImportError(
            "publisher_terms_exclude",
            f"{item.name}: its terms forbid reuse without the firm's written permission",
        )
    now = _aware(now_utc) or datetime.now(UTC)
    kinds_published = {
        "auction": "capacity_auctions",
        "lng_slot": "lng_slots",
        "secondary_capacity": "secondary_capacity",
    }
    specs: list[NoticeSpec] = []
    refused: list[dict[str, Any]] = []
    for line, row in enumerate(rows, start=1):
        try:
            missing = [name for name in _REQUIRED if not str(row.get(name) or "").strip()]
            if missing:
                raise ValueError(f"missing {', '.join(missing)}")
            kind = str(row["kind"]).strip()
            if kind not in NOTICE_KINDS:
                raise ValueError(f"kind must be one of {', '.join(NOTICE_KINDS)}")
            if kinds_published[kind] not in item.publishes:
                raise ValueError(f"{item.publisher_id} does not publish {kind} notices")
            url = str(row["source_url"]).strip()
            if not url.startswith("https://"):
                raise ValueError("source_url must be an https address")
            opens = _parse_instant(str(row["opens_at_utc"]))
            closes = (
                _parse_instant(str(row["closes_at_utc"]))
                if str(row.get("closes_at_utc") or "").strip()
                else None
            )
            if closes is not None and closes < opens:
                raise ValueError("closes_at_utc is before opens_at_utc")
            text = _row_text(row)
            day = _row_day(row)
            quantity = text("quantity")
            state = text("state") or "open"
            if state not in {"open", "cancelled"}:
                raise ValueError("state must be open or cancelled")
            specs.append(
                NoticeSpec(
                    notice_key=f"{publisher_id}:{str(row['notice_id']).strip()}"[:160],
                    publisher_id=publisher_id,
                    kind=kind,
                    basis="published",
                    product=str(row["product"]).strip()[:32],
                    title=str(row["title"]).strip(),
                    opens_at_utc=opens,
                    closes_at_utc=closes,
                    offers_from=day("offers_from"),
                    offers_to=day("offers_to"),
                    facility_kind=text("facility_kind"),
                    facility_id=text("facility_id"),
                    facility_name=text("facility_name"),
                    quantity=None if quantity is None else float(quantity),
                    quantity_unit=text("quantity_unit"),
                    state=state,
                    source_url=url,
                    published_at_utc=(
                        _parse_instant(text("published_at_utc"))
                        if text("published_at_utc")
                        else None
                    ),
                    retrieved_at_utc=now,
                )
            )
        except (ValueError, TypeError) as exc:
            refused.append({"line": line, "notice_id": row.get("notice_id"), "reason": str(exc)})
    if refused:
        return {"stored": False, "rows": len(rows), "refused": refused}
    counts = record_notices(session, specs, now_utc=now)
    return {"stored": True, "rows": len(rows), "refused": [], **counts}


def notice_row(record: Any, now: datetime) -> dict[str, Any]:
    opens = _aware(record.opens_at_utc)
    return {
        "notice_key": record.notice_key,
        "publisher_id": record.publisher_id,
        "publisher_name": getattr(publisher(record.publisher_id), "name", record.publisher_id),
        "kind": record.kind,
        "basis": record.basis,
        "product": record.product,
        "title": record.title,
        "facility_kind": record.facility_kind,
        "facility_id": record.facility_id,
        "facility_name": record.facility_name,
        "opens_at_utc": _iso(opens),
        "closes_at_utc": _iso(record.closes_at_utc),
        "offers_from": _iso(record.offers_from),
        "offers_to": _iso(record.offers_to),
        "quantity": record.quantity,
        "quantity_unit": record.quantity_unit,
        "state": record.state,
        "source_url": record.source_url,
        "published_at_utc": _iso(record.published_at_utc),
        "retrieved_at_utc": _iso(record.retrieved_at_utc),
        "changed_at_utc": _iso(record.changed_at_utc),
        "revision": record.revision,
        "opens_in_days": (opens.date() - now.date()).days,
    }


def list_notices(
    session,
    *,
    now_utc: datetime | None = None,
    days: int = 120,
    kind: str | None = None,
    product: str | None = None,
    facility_id: str | None = None,
    publisher_id: str | None = None,
    include_past_days: int = 0,
    allowed_publishers: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Notices opening from ``include_past_days`` ago to ``days`` ahead, soonest first."""

    from eurogas_nexus.db.models import CapacityNoticeRecord as N

    now = _aware(now_utc) or datetime.now(UTC)
    query = (
        session.query(N)
        .filter(N.opens_at_utc >= now - timedelta(days=include_past_days))
        .filter(N.opens_at_utc <= now + timedelta(days=days))
    )
    if kind:
        query = query.filter(N.kind == kind)
    if product:
        query = query.filter(N.product == product.upper())
    if facility_id:
        query = query.filter(N.facility_id == facility_id)
    if publisher_id:
        query = query.filter(N.publisher_id == publisher_id)
    if allowed_publishers is not None:
        query = query.filter(N.publisher_id.in_(sorted(set(allowed_publishers))))
    return [notice_row(row, now) for row in query.order_by(N.opens_at_utc, N.notice_key).all()]


# ------------------------------------------------------------------------- monitoring


#: A final recorded within this long raises the "new final tariff" alert (TAR-2).
NEW_FINAL_ALERT_FOR = timedelta(days=3)


def new_final_candidates(session, now: datetime) -> list:
    """TAR-2: one prominent alert per facility and tariff year whose FINAL version was
    recorded lately (a first final, or indicative turned final); its valuations are marked
    for re-evaluation through the ``tariff.changed`` event's dependency keys."""

    from sqlalchemy import or_

    from eurogas_nexus.db.models import TariffVersionRecord as V
    from eurogas_nexus.domain.monitoring import MonitoringCandidate

    now = _aware(now)
    rows = (
        session.query(V)
        .filter(V.recorded_at_utc >= now - NEW_FINAL_ALERT_FOR)
        .filter(V.recorded_at_utc <= now)
        .filter(V.status == FINAL)
        .filter(
            or_(
                V.status_change == "INDICATIVE->FINAL",
                V.change_kind == ChangeKind.FIRST.value,
            )
        )
        .order_by(V.recorded_at_utc)
        .all()
    )
    groups: dict[tuple[str, str, str], list[Any]] = {}
    for record in rows:
        year = year_of_record(record).label
        groups.setdefault((record.publisher_id, record.facility_id, year), []).append(record)
    out = []
    for (publisher_id, facility_id, year), records in sorted(groups.items()):
        first = records[0]
        published = _iso(first.published_at_utc) or "not stated"
        out.append(
            MonitoringCandidate(
                fingerprint=f"tariff_final_published:{publisher_id}:{facility_id}:{year}"[:200],
                category="data_source",
                alert_type="tariff_final_published",
                severity="warning",
                title_en=f"Final tariff published: {first.facility_name} {year}",
                title_zh_cn=f"最终费率已发布：{first.facility_name} {year}",
                message_en=(
                    f"{len(records)} FINAL tariff(s) for {first.facility_name} ({first.operator}), "
                    f"tariff year {year}, recorded {_iso(first.recorded_at_utc)} (published "
                    f"{published}). Valuations that used the indicative version are marked for "
                    "re-evaluation."
                ),
                message_zh_cn=(
                    f"{first.facility_name}（{first.operator}）费率年度 {year} 的 {len(records)} 项"
                    f"最终费率已于 {_iso(first.recorded_at_utc)} 记录（发布于 {published}）。"
                    "使用指示性版本的估值已标记为需重新评估。"
                ),
                entity_type="tariff_facility",
                entity_id=facility_id[:128],
                event_time_utc=_aware(first.recorded_at_utc),
                evidence_snapshot={
                    "publisher_id": publisher_id,
                    "facility_id": facility_id,
                    "tariff_year": year,
                    "version_ids": [item.version_id for item in records][:20],
                    "published_at_utc": published,
                },
                source_refs=[f"tariff_version:{item.version_id}" for item in records][:20],
            )
        )
    return out


def monitoring_candidates(session, now: datetime) -> list:
    """Stale publishers, missed NC TAR publications and windows opening soon (M6, M7)."""

    from eurogas_nexus.domain.monitoring import MonitoringCandidate

    now = _aware(now)
    out = []
    for row in publisher_status(session, now_utc=now):
        if row["state"] == "stale":
            minutes = row["stale_after_minutes"]
            out.append(
                MonitoringCandidate(
                    fingerprint=f"tariff_publisher_stale:{row['publisher_id']}",
                    category="data_source",
                    alert_type="tariff_publisher_stale",
                    severity="warning",
                    title_en=f"{row['name']}: tariffs not read on schedule",
                    title_zh_cn=f"{row['name']}：费率未按计划读取",
                    message_en=(
                        f"{row['name']} should be read at least every {minutes // 60} hours; it "
                        f"was last read {row['last_read_at_utc']}. A tariff it changed since may "
                        "not be in the tariff book or in valuations."
                    ),
                    message_zh_cn=(
                        f"{row['name']} 应至少每 {minutes // 60} 小时读取一次；最近读取于 "
                        f"{row['last_read_at_utc']}。此后的费率变更可能尚未进入费率簿与估值。"
                    ),
                    entity_type="tariff_publisher",
                    entity_id=row["publisher_id"],
                    event_time_utc=datetime.fromisoformat(row["last_read_at_utc"]),
                    evidence_snapshot={
                        "publisher_id": row["publisher_id"],
                        "last_read_at_utc": row["last_read_at_utc"],
                        "stale_after_minutes": minutes,
                    },
                    source_refs=[f"tariff_publisher:{row['publisher_id']}"],
                )
            )
        missed = row["missed_publications"]
        if missed:
            names = ", ".join(item["operator"] for item in missed[:6])
            more = f" and {len(missed) - 6} more" if len(missed) > 6 else ""
            out.append(
                MonitoringCandidate(
                    fingerprint=f"tariff_publication_missed:{row['publisher_id']}",
                    category="data_source",
                    alert_type="tariff_publication_missed",
                    severity="warning",
                    title_en=f"{len(missed)} operator(s) without next-period reserve prices",
                    title_zh_cn=f"{len(missed)} 家运营商未发布下一费率期的保留价格",
                    message_en=(
                        f"No yearly reserve price for the next tariff period is held from {names}"
                        f"{more}, past the NC TAR deadline (30 days before the July yearly "
                        "auction). Routes through their points will price as tariff not held "
                        "when the period starts; check the operator's own publication."
                    ),
                    message_zh_cn=(
                        f"{names}{more} 已过 NC TAR 截止日（7 月年度拍卖前 30 天），仍未持有其下一"
                        "费率期的年度保留价格。费率期开始后，经其点位的路径将显示费率未持有；请核对运营商发布。"
                    ),
                    entity_type="tariff_publisher",
                    entity_id=row["publisher_id"],
                    event_time_utc=now,
                    evidence_snapshot={"publisher_id": row["publisher_id"], "missed": missed},
                    source_refs=[f"tariff_publisher:{row['publisher_id']}"],
                )
            )
    out.extend(new_final_candidates(session, now))
    from eurogas_nexus.db.models import CapacityNoticeRecord as N

    soon = (
        session.query(N)
        .filter(N.opens_at_utc >= now)
        .filter(N.opens_at_utc <= now + timedelta(days=NOTICE_ALERT_DAYS))
        .filter(N.state == "open")
        .all()
    )
    for notice in soon:
        if notice.kind == "auction" and notice.product == "MONTHLY":
            continue  # every month; the calendar shows it, an alert would be noise
        opens = _aware(notice.opens_at_utc)
        out.append(
            MonitoringCandidate(
                fingerprint=f"capacity_window:{notice.notice_key}"[:255],
                category="capacity",
                alert_type="capacity_window_opening",
                severity="info",
                title_en=f"Opens {opens:%a %d %b %H:%M} UTC: {notice.title}"[:255],
                title_zh_cn=f"{opens:%Y-%m-%d %H:%M} UTC 开放：{notice.title}"[:255],
                message_en=(
                    f"{notice.title}. Opens {opens.isoformat()}"
                    + (
                        " (rule-derived from the CAM network code; the platform's calendar is "
                        "authoritative)."
                        if notice.basis == "rule_derived"
                        else "."
                    )
                    + f" Source: {notice.source_url}"
                ),
                message_zh_cn=(
                    f"{notice.title}。开放时间 {opens.isoformat()}"
                    + (
                        "（按 CAM 网络规范推导，以平台日历为准）。"
                        if notice.basis == "rule_derived"
                        else "。"
                    )
                    + f" 来源：{notice.source_url}"
                ),
                entity_type="capacity_notice",
                entity_id=notice.notice_key[:128],
                event_time_utc=opens,
                evidence_snapshot={
                    "notice_key": notice.notice_key,
                    "kind": notice.kind,
                    "product": notice.product,
                    "basis": notice.basis,
                    "opens_at_utc": opens.isoformat(),
                    "publisher_id": notice.publisher_id,
                },
                source_refs=[f"capacity_notice:{notice.notice_key}"[:255]],
            )
        )
    return out


__all__ = [
    "ENTSOG_API",
    "NOTICE_COLUMNS",
    "NoticeImportError",
    "NoticeSpec",
    "RecordResult",
    "TariffFilter",
    "capture_tariffs",
    "dependency_keys",
    "final_deadline_for",
    "import_capacity_notices",
    "list_notices",
    "list_tariffs",
    "missed_publications",
    "monitoring_candidates",
    "publisher_status",
    "record_notices",
    "record_register_rows",
    "record_versions",
    "refresh_standard_auctions",
    "register_specs",
    "spec_from_lng_row",
    "spec_from_register_row",
    "tariff_event",
    "version_at",
    "version_row",
    "annotate_register_rows",
    "effective_status",
    "tariff_versions_as_rows",
    "tariff_years",
    "year_of_record",
]
