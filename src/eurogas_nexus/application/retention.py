"""Retention by data class (decision record 2026-11-26, amending Decision 24).

Replaces the hard-coded pruning that deleted market quotes after 30 days and market
observations after 90 days: that destroyed the settlement and curve history risk, compliance
and the five-year backfill need, and archived nothing first.

Rules this module enforces rather than documents:

- **Every data class has a floor in code.** An operator may raise a class's hot period
  (``retention_policies``) or switch its action off; a value below the floor is refused, and a
  stored row is never read below it either.
- **Records a regulation requires are kept.** Trading records, decisions, approvals and audit
  (REMIT, MiFID II, EMIR: at least 7 years), settlements, curves, marks and fundamentals have
  the action ``keep``: the job never removes them. Removing any of them needs a code change
  and a decision, not a setting.
- **Archive before remove.** A row leaves the hot store only after the file that holds it has
  been written to object storage, read back and matched by SHA-256 and size, and a manifest and a
  ``retention_archives`` row exist. Without a configured object store, nothing is removed and
  the run says why.
- **A dry run reports, per class, what an enforced run would do**, and changes nothing.
- **Every run is recorded** (``retention_runs``) **and audited** (``audit_events``), scheduled or
  by hand.

Actions:

``keep``                 never removed.
``thin_then_archive``    (live ticks) after the hot period, each UTC day's ticks are archived in
                         full, then the hot store keeps the last quote of each minute per
                         instrument (one-minute snapshot bars).
``offload``              (raw source pages) first each receipt's page is moved into the
                         content store once per digest (receipts written before 0096), then
                         pages not received again within the hot period move to object storage;
                         the receipt and digest stay, and the read path fetches the page.
``archive_then_delete``  (intraday opportunity snapshots) each UTC day is archived in full,
                         then removed from the hot store.

Archived rows are read back with :func:`restore_archive` (into the hot store) or
:func:`read_archive_rows` (without touching it): ``scripts/ops/retention.py``.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import tempfile
import uuid
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Date, DateTime, LargeBinary, func, select, text
from sqlalchemy.orm import Session

KEEP = "keep"
THIN_THEN_ARCHIVE = "thin_then_archive"
OFFLOAD = "offload"
ARCHIVE_THEN_DELETE = "archive_then_delete"

MODE_DRY_RUN = "dry_run"
MODE_ENFORCE = "enforce"
MODE_OFF = "off"

SEVEN_YEARS_DAYS = 2557

ARCHIVE_FORMAT = "jsonl+gzip/1"
RETENTION_LOCK_KEY = "eurogas_nexus.retention"


@dataclass(frozen=True)
class DataClass:
    """One class of data, its action, its floor and why."""

    name: str
    title: str
    action: str
    tables: tuple[str, ...]
    legal_basis: str
    floor_days: int | None = None
    default_hot_days: int | None = None
    time_column: str | None = None


#: The schedule. ``docs/compliance/RETENTION_SCHEDULE.md`` is written for a reader; this is
#: what the code does. ``tests/unit/test_retention_policy.py`` keeps the two from drifting.
DATA_CLASSES: tuple[DataClass, ...] = (
    DataClass(
        name="trading_records",
        title="Trading records: the firm's trades, books, mandates, credit lines, hedges, "
        "capacity and LNG positions",
        action=KEEP,
        tables=(
            "screen_order_observations",
            "trading_books",
            "trader_mandates",
            "credit_lines",
            "hedge_approvals",
            "lng_cargo_hedges",
            "lng_cargoes",
            "regas_slots",
            "capacity_bookings",
            "contract_daily_deliveries",
            "upstream_resource_contracts",
            "upstream_contract_revisions",
            "gas_day_schedule_lines",
            "gas_day_nomination_events",
            "portfolio_pnl_snapshots",
            # Deal capture: every version of the desk's captured deals, the files they came
            # from, the rows that could not be read, the day's close and the packs sent.
            "captured_deals",
            "deal_import_files",
            "deal_import_problems",
            "deal_day_closes",
            "daily_packs",
        ),
        floor_days=SEVEN_YEARS_DAYS,
        legal_basis="REMIT Art. 8 and Implementing Regulation 1348/2014 Art. 9 (records of "
        "transactions and orders, 5 years); MiFID II Art. 16(6)-(7) and Delegated Regulation "
        "2017/565 Art. 72-76 (5, up to 7 years on request); EMIR Art. 9(2) (at least 5 years "
        "after termination). Kept 7 years minimum, the longest horizon.",
    ),
    DataClass(
        name="audit_and_decisions",
        title="Audit trail, decisions, approvals, reviews, change requests and licensed-data use",
        action=KEEP,
        tables=(
            "audit_events",
            "decision_cases",
            "decision_case_records",
            "review_decisions",
            "change_requests",
            "entitlement_decisions",
            "licensed_data_use",
            "lng_disruption_decisions",
            "gas_day_delegations",
        ),
        floor_days=SEVEN_YEARS_DAYS,
        legal_basis="MiFID II Art. 16(6) and MAR Art. 16 (records of decisions and their "
        "evidence); the firm's own control framework. Kept 7 years minimum; the audit trail is "
        "append-only.",
    ),
    DataClass(
        name="settlements_curves_and_marks",
        title="Exchange settlements, price assessments and indices, firm marks, valuations",
        action=KEEP,
        tables=(
            "market_observations",
            "option_settlements",
            "firm_marks",
            "live_market_marks",
            "valuation_snapshots",
            "valuation_snapshot_inputs",
            "market_reports",
        ),
        legal_basis="Needed to recompute any past figure (risk, valuation, close) and for "
        "the five-year history; MiFID II record keeping where a figure supported a decision. "
        "Kept; the earlier 90-day deletion of market observations is withdrawn.",
    ),
    DataClass(
        name="fundamentals",
        title="Fundamentals: flows, capacity, storage, LNG, power, weather, demand, FX, rates, "
        "outages and their revisions",
        action=KEEP,
        tables=(
            "flow_observations",
            "capacity_observations",
            "storage_observations",
            "storage_inventory_observations",
            "lng_observations",
            "power_observations",
            "fx_observations",
            "interest_rate_observations",
            "forecast_observations",
            "observation_revisions",
            "observation_temporal_metadata",
            "national_gas_actual_demand",
            "remit_umm_messages",
            "cost_observations",
            "news_items",
        ),
        legal_basis="The product's master data (it is the golden source for fundamentals); "
        "REMIT inside information (UMMs) as evidence. Kept; a cold tier in Parquet files "
        "follows Decision 24's trigger.",
    ),
    DataClass(
        name="exchange_trade_prints",
        title="Exchange trade prints from the customer's licensed feed",
        action=KEEP,
        tables=("market_trades",),
        legal_basis="Evidence of the market the desk saw; the volume is small next to quotes.",
    ),
    DataClass(
        name="live_ticks",
        title="Live quotes (ticks) from a licensed feed or the demo simulator",
        action=THIN_THEN_ARCHIVE,
        tables=("market_quotes",),
        time_column="observed_at_utc",
        floor_days=90,
        default_hot_days=90,
        legal_basis="No obligation to keep every tick; the full ticks are archived to object "
        "storage before thinning, and the hot store keeps one-minute bars. Raise the hot "
        "period for surveillance needs.",
    ),
    DataClass(
        name="raw_source_pages",
        title="Raw pages exactly as a public or licensed source sent them",
        action=OFFLOAD,
        tables=("raw_payload_contents", "raw_payload_archives"),
        time_column="last_received_at_utc",
        floor_days=7,
        default_hot_days=28,
        legal_basis="Lineage evidence for every stored observation; kept per each source's "
        "terms (docs/legal/DATA_SOURCE_TERMS.md). Stored once per digest; moved to object "
        "storage after the hot period, never deleted by this job.",
    ),
    DataClass(
        name="intraday_opportunity_snapshots",
        title="Intraday opportunity snapshots computed from quotes",
        action=ARCHIVE_THEN_DELETE,
        tables=("intraday_opportunities",),
        time_column="detected_at_utc",
        floor_days=7,
        default_hot_days=90,
        legal_basis="Derived and reproducible from the archived ticks; archived in full "
        "before removal from the hot store.",
    ),
)

CLASSES_BY_NAME = {data_class.name: data_class for data_class in DATA_CLASSES}


class RetentionPolicyError(ValueError):
    """A setting below a floor, an unknown class, or a change to a class that is kept."""


@dataclass(frozen=True)
class EffectivePolicy:
    data_class: DataClass
    hot_days: int | None
    enabled: bool
    configured_by: str | None = None

    def cutoff(self, now: datetime) -> datetime | None:
        """Start of the UTC day ``hot_days`` before ``now``: whole days are archived."""

        if self.hot_days is None:
            return None
        day = (now.astimezone(UTC) - timedelta(days=self.hot_days)).date()
        return datetime.combine(day, time(0), tzinfo=UTC)


def effective_policies(session: Session) -> dict[str, EffectivePolicy]:
    """Code defaults with each operator setting applied, never below a floor."""

    from eurogas_nexus.db.models import RetentionPolicyRecord

    rows = {row.data_class: row for row in session.query(RetentionPolicyRecord).all()}
    result: dict[str, EffectivePolicy] = {}
    for data_class in DATA_CLASSES:
        hot_days = data_class.default_hot_days
        enabled = True
        configured_by = None
        row = rows.get(data_class.name)
        if row is not None:
            enabled = bool(row.enabled)
            configured_by = row.updated_by
            if row.hot_days is not None and data_class.default_hot_days is not None:
                hot_days = row.hot_days
        if hot_days is not None and data_class.floor_days is not None:
            hot_days = max(hot_days, data_class.floor_days)
        result[data_class.name] = EffectivePolicy(
            data_class=data_class, hot_days=hot_days, enabled=enabled, configured_by=configured_by
        )
    return result


def set_policy(
    session: Session,
    *,
    data_class: str,
    principal: str,
    reason: str,
    hot_days: int | None = None,
    enabled: bool = True,
    now_utc: datetime | None = None,
) -> EffectivePolicy:
    """Raise a class's hot period or switch its action off or on; audited.

    Raises:
        RetentionPolicyError: unknown class, a class that is kept, or a period below the floor.
    """

    from eurogas_nexus.db.models import RetentionPolicyRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event

    spec = CLASSES_BY_NAME.get(data_class)
    if spec is None:
        raise RetentionPolicyError(f"unknown data class {data_class!r}")
    if spec.action == KEEP:
        raise RetentionPolicyError(
            f"{data_class} is kept by rule; changing that needs a code change and a decision"
        )
    if hot_days is not None and spec.floor_days is not None and hot_days < spec.floor_days:
        raise RetentionPolicyError(
            f"{data_class}: {hot_days} days is below the floor of {spec.floor_days} days"
        )
    if not reason.strip():
        raise RetentionPolicyError("a reason is required")
    now = _utc(now_utc or datetime.now(UTC))
    row = session.get(RetentionPolicyRecord, data_class)
    before = None if row is None else {"hot_days": row.hot_days, "enabled": row.enabled}
    if row is None:
        row = RetentionPolicyRecord(data_class=data_class)
        session.add(row)
    row.hot_days = hot_days
    row.enabled = enabled
    row.reason = reason.strip()
    row.updated_by = principal
    row.updated_at_utc = now
    record_audit_event(
        session,
        event_type="retention.policy",
        principal=principal,
        action="retention.policy.set",
        resource=f"retention_policy:{data_class}",
        outcome="recorded",
        detail=reason.strip()[:500],
        now_utc=now,
        before_summary=before,
        after_summary={"hot_days": hot_days, "enabled": enabled},
    )
    session.flush()
    return effective_policies(session)[data_class]


# --- run ---------------------------------------------------------------------------------


@dataclass
class RunLimits:
    """Bounds on one pass so a scheduled run never holds the scheduler for long."""

    dedupe_batches: int = 40
    dedupe_batch_size: int = 500
    offload_batches: int = 20
    offload_batch_size: int = 200
    days_per_class: int = 7
    export_chunk_rows: int = 5000


@dataclass
class RunReport:
    run_id: str
    mode: str
    principal: str
    started_at_utc: str
    status: str = "running"
    object_store: str | None = None
    classes: dict[str, dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_retention(
    session_factory: Callable[[], Session],
    *,
    mode: str = MODE_DRY_RUN,
    principal: str = "scheduler",
    now_utc: datetime | None = None,
    object_store=None,
    limits: RunLimits | None = None,
) -> dict[str, Any]:
    """One retention pass over every class; dry run unless ``mode`` is ``enforce``.

    Each class's work is committed in its own bounded transactions, so a failure in one class
    is reported and never undoes another's verified work.

    Runs in the explicit system book scope (``security/portfolio_scope.py``), whether the
    scheduler or an operator's command starts it: retention acts on a data class across every
    book by age, never on one person's books, and under default-deny book isolation a scope
    left over from elsewhere would make it skip rows silently. It writes no row a person reads
    unfiltered (its runs and archives are operator records).
    """

    from eurogas_nexus.security.portfolio_scope import system_scope

    with system_scope():
        return _run_retention(
            session_factory,
            mode=mode,
            principal=principal,
            now_utc=now_utc,
            object_store=object_store,
            limits=limits,
        )


def _run_retention(
    session_factory: Callable[[], Session],
    *,
    mode: str,
    principal: str,
    now_utc: datetime | None,
    object_store,
    limits: RunLimits | None,
) -> dict[str, Any]:
    from eurogas_nexus.db.models import RetentionRunRecord
    from eurogas_nexus.runtime_store.object_store import (
        ObjectStoreNotConfigured,
        object_store_from_environment,
    )

    if mode not in {MODE_DRY_RUN, MODE_ENFORCE}:
        raise ValueError("mode must be 'dry_run' or 'enforce'")
    limits = limits or RunLimits()
    now = _utc(now_utc or datetime.now(UTC))
    report = RunReport(
        run_id=f"ret-{uuid.uuid4().hex[:20]}",
        mode=mode,
        principal=principal,
        started_at_utc=now.isoformat(),
    )
    store_error = None
    if object_store is None:
        try:
            object_store = object_store_from_environment()
        except (ObjectStoreNotConfigured, ValueError) as exc:
            store_error = str(exc)
    report.object_store = object_store.describe() if object_store is not None else None

    with _run_lock(session_factory) as acquired:
        if not acquired:
            report.status = "skipped_locked"
            return report.as_dict()
        with session_factory() as session:
            session.add(
                RetentionRunRecord(
                    run_id=report.run_id,
                    mode=mode,
                    status="running",
                    principal=principal,
                    started_at_utc=now,
                )
            )
            session.commit()
            policies = effective_policies(session)

        context = _RunContext(
            session_factory=session_factory,
            report=report,
            now=now,
            store=object_store,
            store_error=store_error,
            limits=limits,
            dry_run=mode == MODE_DRY_RUN,
        )
        failed = False
        for data_class in DATA_CLASSES:
            policy = policies[data_class.name]
            entry: dict[str, Any] = {
                "action": data_class.action,
                "hot_days": policy.hot_days,
                "floor_days": data_class.floor_days,
                "enabled": policy.enabled,
            }
            report.classes[data_class.name] = entry
            if data_class.action == KEEP:
                entry["result"] = "kept"
                continue
            if not policy.enabled:
                entry["result"] = "switched_off"
                continue
            handler = _HANDLERS[data_class.action]
            try:
                entry.update(handler(context, policy))
            except Exception as exc:  # noqa: BLE001 - one class never stops the others
                failed = True
                entry["result"] = "failed"
                entry["error_type"] = exc.__class__.__name__
                entry["error"] = str(exc)[:300]

        report.status = "failed" if failed else "ok"
        _finish_run(session_factory, report, now=_utc(datetime.now(UTC)))
    return report.as_dict()


@dataclass
class _RunContext:
    session_factory: Callable[[], Session]
    report: RunReport
    now: datetime
    store: Any
    store_error: str | None
    limits: RunLimits
    dry_run: bool


class _run_lock:
    """At most one retention pass at a time (PostgreSQL advisory lock; a no-op elsewhere)."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self.session: Session | None = None

    def __enter__(self) -> bool:
        session = self.session_factory()
        if session.get_bind().dialect.name != "postgresql":
            session.close()
            return True
        self.session = session
        acquired = session.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:key))"), {"key": RETENTION_LOCK_KEY}
        ).scalar()
        if not acquired:
            session.close()
            self.session = None
        return bool(acquired)

    def __exit__(self, *exc_info) -> None:
        if self.session is not None:
            try:
                self.session.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:key))"),
                    {"key": RETENTION_LOCK_KEY},
                )
            finally:
                self.session.close()


def _finish_run(session_factory, report: RunReport, *, now: datetime) -> None:
    from eurogas_nexus.db.models import RetentionRunRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event

    with session_factory() as session:
        run = session.get(RetentionRunRecord, report.run_id)
        run.status = report.status
        run.finished_at_utc = now
        run.summary_json = report.as_dict()
        totals = {
            name: {
                key: entry.get(key)
                for key in ("result", "rows_removed", "rows_archived", "pages_offloaded")
                if key in entry
            }
            for name, entry in report.classes.items()
            if entry.get("action") != KEEP
        }
        record_audit_event(
            session,
            event_type="retention.run",
            principal=report.principal,
            action=f"retention.{report.mode}",
            resource=f"retention_run:{report.run_id}",
            outcome=report.status,
            severity="info" if report.status == "ok" else "warning",
            detail=json.dumps(totals, sort_keys=True)[:4000],
            now_utc=now,
            after_summary=totals,
        )
        session.commit()


# --- raw source pages: deduplicate, then offload -----------------------------------------


def _raw_pages(context: _RunContext, policy: EffectivePolicy) -> dict[str, Any]:
    from eurogas_nexus.db.models import RawPayloadArchiveRecord, RawPayloadContentRecord
    from eurogas_nexus.db.repositories.raw_archive import (
        STORED_IN_DATABASE,
        move_inline_payloads_to_contents,
    )

    limits = context.limits
    result: dict[str, Any] = {}
    # 1. Receipts written before 0096 still carry their page: move each page in once.
    with context.session_factory() as session:
        inline = (
            session.query(func.count())
            .select_from(RawPayloadArchiveRecord)
            .filter(
                (RawPayloadArchiveRecord.payload_text.is_not(None))
                | (RawPayloadArchiveRecord.payload_json.is_not(None))
            )
            .scalar()
        )
    result["receipts_with_inline_page"] = int(inline)
    moved = added = 0
    if not context.dry_run:
        for _ in range(limits.dedupe_batches):
            with context.session_factory() as session:
                batch = move_inline_payloads_to_contents(
                    session, limit=limits.dedupe_batch_size
                )
                session.commit()
            moved += batch["receipts_moved"]
            added += batch["distinct_pages_added"]
            if batch["receipts_moved"] == 0:
                break
    result["receipts_deduplicated"] = moved
    result["distinct_pages_added"] = added

    # 2. Pages not received again within the hot period go to object storage.
    cutoff = policy.cutoff(context.now)
    result["cutoff_utc"] = cutoff.isoformat()
    with context.session_factory() as session:
        due = session.query(
            func.count(), func.coalesce(func.sum(RawPayloadContentRecord.byte_size), 0)
        ).filter(
            RawPayloadContentRecord.stored_in == STORED_IN_DATABASE,
            RawPayloadContentRecord.last_received_at_utc < cutoff,
        ).one()
    result["pages_due_for_offload"] = int(due[0])
    result["bytes_due_for_offload"] = int(due[1])
    if context.dry_run:
        result["result"] = "dry_run"
        return result
    if context.store is None:
        result["result"] = "blocked_no_object_store"
        result["reason"] = context.store_error
        return result
    offloaded = 0
    for batch_number in range(limits.offload_batches):
        count = _offload_page_batch(context, cutoff, batch_number)
        offloaded += count
        if count == 0:
            break
    result["pages_offloaded"] = offloaded
    result["result"] = "done"
    return result


def raw_page_object_key(payload_sha256: str) -> str:
    return f"raw-pages/{payload_sha256[:2]}/{payload_sha256}.gz"


def _offload_page_batch(context: _RunContext, cutoff: datetime, batch_number: int) -> int:
    from eurogas_nexus.db.models import RawPayloadContentRecord, RetentionArchiveRecord
    from eurogas_nexus.db.repositories.raw_archive import (
        STORED_IN_DATABASE,
        STORED_IN_OBJECT_STORE,
    )

    store = context.store
    with context.session_factory() as session:
        pages = (
            session.query(RawPayloadContentRecord)
            .filter(
                RawPayloadContentRecord.stored_in == STORED_IN_DATABASE,
                RawPayloadContentRecord.last_received_at_utc < cutoff,
                RawPayloadContentRecord.payload_compressed.is_not(None),
            )
            .order_by(
                RawPayloadContentRecord.last_received_at_utc,
                RawPayloadContentRecord.payload_sha256,
            )
            .limit(context.limits.offload_batch_size)
            .all()
        )
        if not pages:
            return 0
        items = []
        for page in pages:
            blob = page.payload_compressed
            if hashlib.sha256(gzip.decompress(blob)).hexdigest() != page.payload_sha256:
                raise RuntimeError(f"hot page {page.payload_sha256[:12]} failed its digest check")
            key = raw_page_object_key(page.payload_sha256)
            stored = store.put_bytes(key, blob, content_type="application/gzip")
            if not store.verify(key, sha256=hashlib.sha256(blob).hexdigest(), size=len(blob)):
                raise RuntimeError(f"offloaded page {key} did not read back identically")
            items.append(
                {
                    "payload_sha256": page.payload_sha256,
                    "object_key": key,
                    "byte_size": page.byte_size,
                    "stored_size": stored.size,
                    "stored_sha256": stored.sha256,
                    "last_received_at_utc": _utc(page.last_received_at_utc).isoformat(),
                }
            )
        first = _utc(pages[0].last_received_at_utc)
        last = _utc(pages[-1].last_received_at_utc)
        manifest_key = (
            f"manifests/raw-pages/{context.report.run_id}-{batch_number:04d}.json"
        )
        manifest = _manifest(
            context,
            data_class="raw_source_pages",
            table="raw_payload_contents",
            action=OFFLOAD,
            range_start=first,
            range_end=last,
            extra={"objects": items, "compression": "gzip of the exact page bytes"},
        )
        manifest_obj = _put_verified_json(store, manifest_key, manifest)
        verified_at = _utc(datetime.now(UTC))
        session.add(
            RetentionArchiveRecord(
                archive_id=f"arc-{uuid.uuid4().hex[:20]}",
                run_id=context.report.run_id,
                data_class="raw_source_pages",
                table_name="raw_payload_contents",
                action=OFFLOAD,
                range_start_utc=first,
                range_end_utc=last,
                object_store=store.describe()[:256],
                object_key=manifest_key,
                manifest_key=manifest_key,
                row_count=len(items),
                rows_removed=0,
                byte_size=sum(item["stored_size"] for item in items),
                sha256=manifest_obj.sha256,
                status="verified",
                created_at_utc=verified_at,
                verified_at_utc=verified_at,
            )
        )
        for page, item in zip(pages, items, strict=True):
            page.payload_compressed = None
            page.stored_in = STORED_IN_OBJECT_STORE
            page.object_key = item["object_key"]
            page.offloaded_at_utc = verified_at
        session.commit()
        return len(items)


# --- whole-day archives: thin ticks, archive and delete snapshots ------------------------


def _day_archives(context: _RunContext, policy: EffectivePolicy) -> dict[str, Any]:
    from eurogas_nexus.db.models import RetentionArchiveRecord

    data_class = policy.data_class
    table_name = data_class.tables[0]
    table, column = _table_and_column(table_name, data_class.time_column)
    cutoff = policy.cutoff(context.now)
    result: dict[str, Any] = {"cutoff_utc": cutoff.isoformat()}
    with context.session_factory() as session:
        oldest = session.execute(
            select(func.min(column)).where(column < cutoff)
        ).scalar()
        done = {
            _utc(start).date()
            for (start,) in session.query(RetentionArchiveRecord.range_start_utc).filter(
                RetentionArchiveRecord.data_class == data_class.name,
                RetentionArchiveRecord.table_name == table_name,
            )
        }
    if oldest is None:
        result.update(result="nothing_due", days_due=0)
        return result
    days = []
    day = _utc(oldest).date()
    while day < cutoff.date():
        if day not in done:
            days.append(day)
        day += timedelta(days=1)
    result["days_due"] = len(days)
    planned = days[: context.limits.days_per_class]
    result["days_this_run"] = [d.isoformat() for d in planned]
    if context.dry_run or context.store is None:
        rows = removable = 0
        with context.session_factory() as session:
            for day in planned:
                day_rows, day_removable = _count_day(session, data_class, table, column, day)
                rows += day_rows
                removable += day_removable
        result["rows_to_archive"] = rows
        result["rows_to_remove"] = removable
        if context.dry_run:
            result["result"] = "dry_run"
        else:
            result["result"] = "blocked_no_object_store"
            result["reason"] = context.store_error
        return result
    archived = removed = 0
    for day in planned:
        day_archived, day_removed = _archive_day(context, data_class, table, column, day)
        archived += day_archived
        removed += day_removed
    result.update(
        rows_archived=archived,
        rows_removed=removed,
        days_pending_after_run=len(days) - len(planned),
        result="done",
    )
    return result


def _table_and_column(table_name: str, column_name: str | None):
    from eurogas_nexus.db.registry import get_metadata

    table = get_metadata().tables[table_name]
    return table, table.c[column_name]


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0), tzinfo=UTC)
    return start, start + timedelta(days=1)


def _minute_bucket(session: Session, column):
    if session.get_bind().dialect.name == "postgresql":
        return func.date_trunc("minute", column)
    return func.strftime("%Y-%m-%d %H:%M", column)


#: Columns that identify one instrument's quote stream (one bar per minute each).
TICK_STREAM_KEY = (
    "source_system",
    "venue",
    "instrument_id",
    "hub",
    "product",
    "delivery_start_utc",
)


def _kept_bars_subquery(session: Session, table, column, start, end):
    """``(key, rn)`` with rn = 1 for the last quote of each minute of each stream."""

    stream = [table.c[name] for name in TICK_STREAM_KEY]
    primary = list(table.primary_key.columns)[0]
    rank = (
        func.row_number()
        .over(
            partition_by=[*stream, _minute_bucket(session, column)],
            order_by=[column.desc(), primary.desc()],
        )
        .label("rn")
    )
    return (
        select(primary.label("key"), rank)
        .where(column >= start, column < end)
        .subquery("ranked")
    )


def _count_day(session, data_class: DataClass, table, column, day: date) -> tuple[int, int]:
    start, end = _day_bounds(day)
    rows = session.execute(
        select(func.count()).select_from(table).where(column >= start, column < end)
    ).scalar()
    if data_class.action == ARCHIVE_THEN_DELETE:
        return int(rows), int(rows)
    ranked = _kept_bars_subquery(session, table, column, start, end)
    removable = session.execute(
        select(func.count()).select_from(ranked).where(ranked.c.rn > 1)
    ).scalar()
    return int(rows), int(removable)


def _archive_day(context: _RunContext, data_class: DataClass, table, column, day: date):
    from eurogas_nexus.db.models import RetentionArchiveRecord

    start, end = _day_bounds(day)
    store = context.store
    base_key = f"{data_class.name}/{table.name}/{day:%Y/%m/%d}"
    data_key = f"{base_key}.jsonl.gz"
    manifest_key = f"{base_key}.manifest.json"
    primary = list(table.primary_key.columns)[0]
    with context.session_factory() as session, tempfile.TemporaryDirectory(
        prefix="nexus-retention-"
    ) as tmp:
        path = Path(tmp) / "day.jsonl.gz"
        row_count = _export_rows(
            session,
            table,
            select(table).where(column >= start, column < end).order_by(column, primary),
            path,
            chunk_rows=context.limits.export_chunk_rows,
        )
        if row_count == 0:
            return 0, 0
        stored = store.put_file(data_key, path, content_type="application/gzip")
        if not store.verify(data_key, sha256=stored.sha256, size=stored.size):
            raise RuntimeError(f"archive {data_key} did not read back identically")
        if data_class.action == THIN_THEN_ARCHIVE:
            ranked = _kept_bars_subquery(session, table, column, start, end)
            doomed = select(ranked.c.key).where(ranked.c.rn > 1)
            rule = (
                "after archiving, the hot store keeps the last quote of each UTC minute per "
                + ", ".join(TICK_STREAM_KEY)
            )
        else:
            doomed = select(primary).where(column >= start, column < end)
            rule = "after archiving, every row of the day is removed from the hot store"
        manifest = _manifest(
            context,
            data_class=data_class.name,
            table=table.name,
            action=data_class.action,
            range_start=start,
            range_end=end,
            extra={
                "data_object_key": data_key,
                "data_sha256": stored.sha256,
                "data_size": stored.size,
                "row_count": row_count,
                "columns": [col.name for col in table.columns],
                "rule": rule,
            },
        )
        _put_verified_json(store, manifest_key, manifest)
        removed = session.execute(
            table.delete().where(primary.in_(doomed)).execution_options(
                synchronize_session=False
            )
        ).rowcount
        verified_at = _utc(datetime.now(UTC))
        session.add(
            RetentionArchiveRecord(
                archive_id=f"arc-{uuid.uuid4().hex[:20]}",
                run_id=context.report.run_id,
                data_class=data_class.name,
                table_name=table.name,
                action=data_class.action,
                range_start_utc=start,
                range_end_utc=end,
                object_store=store.describe()[:256],
                object_key=data_key,
                manifest_key=manifest_key,
                row_count=row_count,
                rows_removed=int(removed or 0),
                byte_size=stored.size,
                sha256=stored.sha256,
                status="verified",
                created_at_utc=verified_at,
                verified_at_utc=verified_at,
            )
        )
        session.commit()
        return row_count, int(removed or 0)


def _manifest(context, *, data_class, table, action, range_start, range_end, extra) -> dict:
    return {
        "format": ARCHIVE_FORMAT,
        "product": "eurogas-nexus",
        "run_id": context.report.run_id,
        "data_class": data_class,
        "table": table,
        "action": action,
        "range_start_utc": range_start.isoformat(),
        "range_end_utc": range_end.isoformat(),
        "written_at_utc": _utc(datetime.now(UTC)).isoformat(),
        "restore": "python scripts/ops/retention.py restore --archive-id <id>",
        **extra,
    }


def _put_verified_json(store, key: str, document: dict):
    data = json.dumps(document, sort_keys=True, indent=1).encode("utf-8")
    stored = store.put_bytes(key, data, content_type="application/json")
    if not store.verify(key, sha256=hashlib.sha256(data).hexdigest(), size=len(data)):
        raise RuntimeError(f"manifest {key} did not read back identically")
    return stored


# --- serialisation -----------------------------------------------------------------------


def _encode_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes | bytearray | memoryview):
        return {"$base64": base64.b64encode(bytes(value)).decode("ascii")}
    return value


def _decode_row(table, row: dict[str, Any]) -> dict[str, Any]:
    decoded = {}
    for name, value in row.items():
        column = table.c[name]
        if value is None:
            decoded[name] = None
        elif isinstance(column.type, DateTime):
            decoded[name] = datetime.fromisoformat(value)
        elif isinstance(column.type, Date):
            decoded[name] = date.fromisoformat(value)
        elif isinstance(column.type, LargeBinary):
            decoded[name] = base64.b64decode(value["$base64"])
        else:
            decoded[name] = value
    return decoded


def _export_rows(session, table, statement, path: Path, *, chunk_rows: int) -> int:
    count = 0
    names = [column.name for column in table.columns]
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as handle:
        result = session.execute(statement.execution_options(yield_per=chunk_rows))
        for row in result:
            mapping = row._mapping
            record = {name: _encode_value(mapping[table.c[name]]) for name in names}
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
            handle.write("\n")
            count += 1
    return count


# --- read path -----------------------------------------------------------------------------


def read_archive_rows(session: Session, archive_id: str, *, object_store=None) -> Iterator[dict]:
    """Rows of one archive file, verified against its recorded digest; the hot store is
    not touched. Raw-page manifests yield their object entries."""

    from eurogas_nexus.db.models import RetentionArchiveRecord
    from eurogas_nexus.runtime_store.object_store import object_store_from_environment

    record = session.get(RetentionArchiveRecord, archive_id)
    if record is None:
        raise LookupError(f"no archive {archive_id}")
    store = object_store or object_store_from_environment()
    with tempfile.TemporaryDirectory(prefix="nexus-restore-") as tmp:
        path = Path(tmp) / "archive"
        stored = store.get_to_file(record.object_key, path)
        if stored.sha256 != record.sha256:
            raise RuntimeError(f"archive {archive_id} does not match its recorded digest")
        if record.action == OFFLOAD:
            yield from json.loads(path.read_bytes())["objects"]
            return
        from eurogas_nexus.db.registry import get_metadata

        table = get_metadata().tables[record.table_name]
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                yield _decode_row(table, json.loads(line))


def restore_archive(
    session: Session,
    archive_id: str,
    *,
    principal: str,
    object_store=None,
    batch_rows: int = 2000,
) -> dict[str, Any]:
    """Load an archived range back into the hot store (rows already there are left as they
    are). Raw pages return to the database copy. Audited; the caller commits."""

    from eurogas_nexus.db.models import RawPayloadContentRecord, RetentionArchiveRecord
    from eurogas_nexus.db.registry import get_metadata
    from eurogas_nexus.db.repositories.audit import record_audit_event
    from eurogas_nexus.db.repositories.raw_archive import STORED_IN_DATABASE
    from eurogas_nexus.runtime_store.object_store import object_store_from_environment

    record = session.get(RetentionArchiveRecord, archive_id)
    if record is None:
        raise LookupError(f"no archive {archive_id}")
    store = object_store or object_store_from_environment()
    restored = 0
    if record.action == OFFLOAD:
        for item in read_archive_rows(session, archive_id, object_store=store):
            page = session.get(RawPayloadContentRecord, item["payload_sha256"])
            if page is None or page.payload_compressed is not None:
                continue
            blob = store.get_bytes(item["object_key"])
            if hashlib.sha256(gzip.decompress(blob)).hexdigest() != item["payload_sha256"]:
                raise RuntimeError(f"page {item['object_key']} failed its digest check")
            page.payload_compressed = blob
            page.stored_in = STORED_IN_DATABASE
            restored += 1
    else:
        table = get_metadata().tables[record.table_name]
        insert = _insert_ignoring_conflicts(session, table)
        batch: list[dict] = []
        for row in read_archive_rows(session, archive_id, object_store=store):
            batch.append(row)
            if len(batch) >= batch_rows:
                restored += session.execute(insert, batch).rowcount or 0
                batch = []
        if batch:
            restored += session.execute(insert, batch).rowcount or 0
    now = _utc(datetime.now(UTC))
    record.status = "restored"
    record.restored_at_utc = now
    record_audit_event(
        session,
        event_type="retention.restore",
        principal=principal,
        action="retention.restore",
        resource=f"retention_archive:{archive_id}",
        outcome="restored",
        detail=f"{record.table_name} {record.range_start_utc} - {record.range_end_utc}",
        now_utc=now,
        after_summary={"rows_or_pages_restored": restored},
    )
    session.flush()
    return {
        "archive_id": archive_id,
        "table": record.table_name,
        "range_start_utc": _utc(record.range_start_utc).isoformat(),
        "range_end_utc": _utc(record.range_end_utc).isoformat(),
        "restored": restored,
    }


def _insert_ignoring_conflicts(session: Session, table):
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(table).on_conflict_do_nothing()


# --- scheduling ----------------------------------------------------------------------------


def configured_mode(environ=None) -> str:
    """``EUROGAS_NEXUS_RETENTION_MODE``: ``enforce`` (default), ``dry_run`` or ``off``."""

    env = os.environ if environ is None else environ
    value = (env.get("EUROGAS_NEXUS_RETENTION_MODE") or MODE_ENFORCE).strip().lower()
    return value if value in {MODE_ENFORCE, MODE_DRY_RUN, MODE_OFF} else MODE_DRY_RUN


def configured_hour(environ=None) -> int:
    """``EUROGAS_NEXUS_RETENTION_HOUR_UTC``: the hour after which the daily pass runs (2)."""

    env = os.environ if environ is None else environ
    try:
        hour = int((env.get("EUROGAS_NEXUS_RETENTION_HOUR_UTC") or "2").strip())
    except ValueError:
        return 2
    return hour if 0 <= hour <= 23 else 2


def retention_due(session: Session, *, now_utc: datetime, hour_utc: int) -> bool:
    """Due once a day, after ``hour_utc``, when no pass has started since that time."""

    from eurogas_nexus.db.models import RetentionRunRecord

    now = _utc(now_utc)
    slot = datetime.combine(now.date(), time(hour_utc), tzinfo=UTC)
    if now < slot:
        return False
    last = session.query(func.max(RetentionRunRecord.started_at_utc)).scalar()
    return last is None or _utc(last) < slot


def run_retention_if_due(session_factory, *, now_utc: datetime, environ=None) -> dict:
    """The scheduler's daily hook. Never raises: a failure is reported in the summary."""

    mode = configured_mode(environ)
    if mode == MODE_OFF:
        return {"status": "off"}
    try:
        with session_factory() as session:
            if not retention_due(session, now_utc=now_utc, hour_utc=configured_hour(environ)):
                return {"status": "not_due"}
        report = run_retention(session_factory, mode=mode, principal="scheduler", now_utc=now_utc)
    except Exception as exc:  # noqa: BLE001 - retention never stops ingestion
        return {"status": "failed", "error_type": exc.__class__.__name__}
    return {
        "status": report["status"],
        "run_id": report["run_id"],
        "mode": report["mode"],
        "results": {name: entry.get("result") for name, entry in report["classes"].items()},
    }


def schedule_rows(session: Session | None = None) -> list[dict[str, Any]]:
    """The schedule as rows (for the CLI and the schedule document's consistency test)."""

    policies = effective_policies(session) if session is not None else None
    rows = []
    for data_class in DATA_CLASSES:
        policy = policies[data_class.name] if policies else EffectivePolicy(
            data_class, data_class.default_hot_days, True
        )
        rows.append(
            {
                "data_class": data_class.name,
                "title": data_class.title,
                "action": data_class.action,
                "floor_days": data_class.floor_days,
                "hot_days": policy.hot_days,
                "enabled": policy.enabled,
                "tables": list(data_class.tables),
                "legal_basis": data_class.legal_basis,
            }
        )
    return rows


_HANDLERS: dict[str, Callable[[_RunContext, EffectivePolicy], dict[str, Any]]] = {
    OFFLOAD: _raw_pages,
    THIN_THEN_ARCHIVE: _day_archives,
    ARCHIVE_THEN_DELETE: _day_archives,
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "ARCHIVE_THEN_DELETE",
    "CLASSES_BY_NAME",
    "DATA_CLASSES",
    "KEEP",
    "MODE_DRY_RUN",
    "MODE_ENFORCE",
    "OFFLOAD",
    "THIN_THEN_ARCHIVE",
    "DataClass",
    "EffectivePolicy",
    "RetentionPolicyError",
    "RunLimits",
    "configured_mode",
    "effective_policies",
    "read_archive_rows",
    "restore_archive",
    "run_retention",
    "run_retention_if_due",
    "schedule_rows",
    "set_policy",
]
