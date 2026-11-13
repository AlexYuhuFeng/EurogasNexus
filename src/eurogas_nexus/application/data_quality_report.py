"""Data-quality report: what each source actually delivered, measured in the store.

"Implemented" and "healthy" say a connector ran. This says what arrived: how many rows,
for which entities and periods, whether closed periods are complete against the source's
own usual coverage, whether a natural key repeats, how much is blank, and how old the
latest period is against the freshness the source promises. One declarative spec per
dataset, the same checks for all, no judgement in the model.

A finding is a fact with a severity (``ok``, ``warning``, ``critical``); a dataset with no
rows is ``empty``, never ``ok``. The report is the evidence for a source certification and
the input to source alerts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

#: A closed period is short when it holds less than this share of the usual entity count.
COVERAGE_FLOOR = 0.9
#: Provider revisions are counted over this many days (``observation_revisions``).
REVISION_WINDOW_DAYS = 7
#: Tables whose superseded values are kept in ``observation_revisions``.
REVISED_TABLES = frozenset(
    {"flow_observations", "capacity_observations", "storage_observations", "lng_observations"}
)


@dataclass(frozen=True)
class DatasetSpec:
    """What one dataset is and how to measure it."""

    dataset: str
    source: str
    table: str
    #: Column that places a row in time (period start, value date, publication).
    period: str
    #: Columns that identify the measured thing; with the period they form the natural key.
    entity: tuple[str, ...]
    #: Columns of which at least one must carry a value for the row to be useful.
    values: tuple[str, ...]
    #: Expected spacing of periods per entity, in minutes (1440 = daily).
    interval_minutes: int
    #: The latest period may be this old before the dataset is stale.
    max_age_hours: float
    #: SQL condition selecting the dataset's rows in a shared table.
    where: str = "TRUE"
    #: When the row was received, for lateness (optional).
    received: str | None = None
    #: Period ends this many hours after its start are still open (not judged for coverage).
    open_hours: float = 30.0
    #: False for series whose publication days differ by calendar or that log revisions.
    check_coverage: bool = True


#: The reporting operator, kept in the row's provider metadata.
OPERATOR = "metadata_json->>'operatorKey'"

SPECS: tuple[DatasetSpec, ...] = (
    DatasetSpec("ENTSOG flows", "ENTSOG", "flow_observations", "period_start_utc",
                # Both operators at an interconnection report it, so the operator is part
                # of the key; a consumer summing by point must pick one side.
                ("point_id", "direction", OPERATOR), ("original_value",), 1440, 54,
                where="source_system = 'ENTSOG'", received="observed_at_utc"),
    DatasetSpec("ENTSOG capacity", "ENTSOG", "capacity_observations", "period_start_utc",
                ("point_id", "direction", "capacity_type", OPERATOR), ("original_value",),
                1440, 54,
                where="source_system = 'ENTSOG'", received="observed_at_utc"),
    DatasetSpec("GIE storage (AGSI)", "GIE", "storage_observations", "period_start_utc",
                ("facility_id",), ("inventory_twh", "fill_pct"), 1440, 72,
                where="source_system = 'GIE'", received="observed_at_utc"),
    DatasetSpec("GIE LNG (ALSI)", "GIE", "lng_observations", "period_start_utc",
                ("terminal_id",), ("inventory_twh", "send_out_twh_d", "dtmi_twh"), 1440, 72,
                where="source_system = 'GIE'", received="observed_at_utc"),
    # GB storage and LNG: nominations D+1, stock D+1 afternoon, allocations D+2.
    DatasetSpec("GB storage (National Gas)", "NATIONAL_GAS", "storage_observations",
                "period_start_utc", ("facility_id",),
                ("inventory_twh", "withdrawal_twh_d", "injection_twh_d"), 1440, 72,
                where="source_system = 'NATIONAL_GAS'", received="observed_at_utc"),
    DatasetSpec("GB LNG (National Gas)", "NATIONAL_GAS", "lng_observations",
                "period_start_utc", ("terminal_id",), ("inventory_twh", "send_out_twh_d"),
                1440, 72, where="source_system = 'NATIONAL_GAS'", received="observed_at_utc"),
    DatasetSpec("ECB FX reference", "ECB", "fx_observations", "value_date",
                ("pair",), ("rate",), 1440, 96, where="source_system = 'ECB'",
                received="observed_at_utc"),
    DatasetSpec("Overnight rates", "BOE/ECB/NYFED", "interest_rate_observations", "value_date",
                # Fixings follow three different holiday calendars: judged for age, not days.
                ("benchmark_id",), ("rate_pct",), 1440, 120, check_coverage=False),
    DatasetSpec("Henry Hub (EIA)", "EIA", "market_observations", "period_start_utc",
                ("product",), ("price",), 1440, 264, where="source_system = 'EIA'",
                received="observed_at_utc"),
    DatasetSpec("Power (ENTSO-E)", "ENTSOE", "power_observations", "period_start_utc",
                ("zone", "metric"), ("value",), 15, 30, where="source_system = 'ENTSOE'",
                received="ingested_at_utc", open_hours=3.0),
    DatasetSpec("GB power (Elexon)", "ELEXON", "power_observations", "period_start_utc",
                ("zone", "metric"), ("value",), 30, 6, where="source_system = 'ELEXON'",
                received="ingested_at_utc", open_hours=3.0),
    DatasetSpec("GB demand (National Gas)", "NationalGas", "national_gas_actual_demand",
                # An append-only revision log: each publication of a gas day is its own row.
                "gas_day", ("provider_item_id", "series_key", "applicable_at_raw"),
                ("value_text",), 1440, 72, check_coverage=False),
    DatasetSpec("Outages (REMIT UMM)", "REMIT", "remit_umm_messages", "published_at_utc",
                ("message_id", "version"), ("unavailable_capacity",), 0, 24 * 14),
)


@dataclass
class DatasetQuality:
    dataset: str
    source: str
    status: str = "ok"
    rows: int = 0
    entities: int = 0
    first_period: str | None = None
    last_period: str | None = None
    age_hours: float | None = None
    max_age_hours: float = 0.0
    duplicate_keys: int = 0
    blank_rows: int = 0
    closed_periods: int = 0
    short_periods: list[str] = field(default_factory=list)
    usual_entities_per_period: int = 0
    median_lateness_hours: float | None = None
    #: Rows whose value the provider revised in the last REVISION_WINDOW_DAYS (None: the
    #: dataset keeps no revision history), and open-day snapshots replaced at day close.
    revised_rows: int | None = None
    closed_snapshots: int | None = None
    findings: list[dict[str, str]] = field(default_factory=list)

    def add(self, severity: str, message: str) -> None:
        self.findings.append({"severity": severity, "message": message})
        order = {"ok": 0, "empty": 1, "warning": 2, "critical": 3}
        if order[severity] > order[self.status]:
            self.status = severity

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def build_report(session, *, now: datetime | None = None) -> dict[str, Any]:
    """Measure every dataset in :data:`SPECS` that exists in this store."""

    now = now or datetime.now(UTC)
    datasets = [measure(session, spec, now) for spec in SPECS]
    counts: dict[str, int] = {}
    for item in datasets:
        counts[item.status] = counts.get(item.status, 0) + 1
    return {
        "generated_at_utc": now.isoformat(),
        "summary": counts,
        "datasets": [item.as_dict() for item in datasets],
    }


def measure(session, spec: DatasetSpec, now: datetime) -> DatasetQuality:
    result = DatasetQuality(spec.dataset, spec.source, max_age_hours=spec.max_age_hours)
    columns = _columns(session, spec.table)
    if not columns:
        result.add("empty", "The table does not exist in this store.")
        return result
    missing = [
        c
        for c in (spec.period, *spec.entity, *spec.values)
        if c.split("->>")[0] not in columns
    ]
    if missing:
        result.add("critical", f"Spec names columns the table lacks: {', '.join(missing)}.")
        return result

    entity = " || '|' || ".join(f"COALESCE(CAST({c} AS TEXT), '')" for c in spec.entity)
    blank = " AND ".join(f"{c} IS NULL" for c in spec.values)
    base = f"FROM {spec.table} WHERE {spec.where}"
    row = session.execute(text(
        f"SELECT COUNT(*), COUNT(DISTINCT {entity}), MIN({spec.period}), MAX({spec.period}), "
        f"SUM(CASE WHEN {blank} THEN 1 ELSE 0 END) {base}"
    )).one()
    result.rows, result.entities = int(row[0] or 0), int(row[1] or 0)
    if not result.rows:
        result.add("empty", "No rows: the source has not delivered to this store.")
        return result
    first, last = _instant(row[2]), _instant(row[3])
    result.first_period, result.last_period = first.isoformat(), last.isoformat()
    result.blank_rows = int(row[4] or 0)
    result.age_hours = round((now - last).total_seconds() / 3600, 1)

    result.duplicate_keys = int(session.execute(text(
        f"SELECT COUNT(*) FROM (SELECT 1 {base} GROUP BY {entity}, {spec.period} "
        "HAVING COUNT(*) > 1) AS repeated"
    )).scalar() or 0)

    if spec.interval_minutes and spec.check_coverage:
        _coverage(session, spec, result, entity, base, now)
    if spec.received and spec.received in columns:
        result.median_lateness_hours = _median_lateness(session, spec, base)
    if spec.table in REVISED_TABLES:
        _revisions(session, spec, result, now)

    if result.age_hours > spec.max_age_hours:
        result.add(
            "warning" if result.age_hours < 3 * spec.max_age_hours else "critical",
            f"Latest period is {result.age_hours:.0f} h old; expected within "
            f"{spec.max_age_hours:.0f} h.",
        )
    if result.duplicate_keys:
        result.add("critical", f"{result.duplicate_keys} natural keys occur more than once.")
    if result.blank_rows:
        share = result.blank_rows / result.rows
        result.add(
            "warning" if share < 0.2 else "critical",
            f"{result.blank_rows} rows ({share:.0%}) carry no value.",
        )
    if result.short_periods:
        result.add(
            "warning",
            f"{len(result.short_periods)} of {result.closed_periods} closed days hold under "
            f"{COVERAGE_FLOOR:.0%} of the usual {result.usual_entities_per_period} series.",
        )
    if not result.findings:
        result.add("ok", "Complete, current and unique.")
    return result


def _coverage(session, spec, result: DatasetQuality, entity: str, base: str, now) -> None:
    """Closed days against the dataset's own usual series count (its median day)."""

    rows = session.execute(text(
        # The day as text: the one form PostgreSQL and SQLite both give for a timestamp.
        f"SELECT SUBSTR(CAST({spec.period} AS TEXT), 1, 10) AS day, COUNT(DISTINCT {entity}) "
        f"{base} GROUP BY 1 ORDER BY 1"
    )).all()
    closed = [
        (str(day), int(count))
        for day, count in rows
        if (now - _instant(day)).total_seconds() / 3600 > spec.open_hours + 24
    ]
    if not closed:
        return
    counts = sorted(count for _, count in closed)
    usual = counts[len(counts) // 2]
    result.closed_periods = len(closed)
    result.usual_entities_per_period = usual
    result.short_periods = [day for day, count in closed if count < COVERAGE_FLOOR * usual]


def _revisions(session, spec, result: DatasetQuality, now: datetime) -> None:
    """Revision records of this dataset's rows written in the last REVISION_WINDOW_DAYS."""

    if not _columns(session, "observation_revisions"):
        return
    since = now - timedelta(days=REVISION_WINDOW_DAYS)
    counts = dict(session.execute(
        text(
            "SELECT reason, COUNT(DISTINCT observation_id) FROM observation_revisions "
            "WHERE observation_table = :table AND recorded_at_utc >= :since "
            f"AND observation_id IN (SELECT observation_id FROM {spec.table} "
            f"WHERE {spec.where}) GROUP BY reason"
        ),
        {"table": spec.table, "since": since},
    ).all())
    result.revised_rows = int(counts.get("value_changed", 0))
    result.closed_snapshots = int(counts.get("period_closed", 0))


def _median_lateness(session, spec, base: str) -> float | None:
    """Median hours between a period's start and its receipt, over the latest 2,000 rows."""

    rows = session.execute(text(
        f"SELECT {spec.period}, {spec.received} {base} ORDER BY {spec.period} DESC LIMIT 2000"
    )).all()
    hours = sorted(
        (_instant(received) - _instant(period)).total_seconds() / 3600
        for period, received in rows
        if period is not None and received is not None
    )
    return round(hours[len(hours) // 2], 1) if hours else None


def _columns(session, table: str) -> set[str]:
    from sqlalchemy import inspect

    inspector = inspect(session.connection())  # the session's own connection and transaction
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _instant(value: Any) -> datetime:
    """A date, a datetime or their text form, as an aware UTC instant."""

    if isinstance(value, datetime):
        moment = value
    else:
        moment = datetime.fromisoformat(str(value)[:19])
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def as_text(report: dict[str, Any]) -> str:
    """The report as a fixed-width table for a terminal or a ticket."""

    lines = [
        f"Data quality, {report['generated_at_utc'][:16]} UTC",
        f"{'dataset':26} {'status':9} {'rows':>8} {'series':>6} {'last period':16} "
        f"{'age h':>6} {'dup':>4} {'blank':>6} {'short days':>10} "
        f"{f'rev {REVISION_WINDOW_DAYS}d':>6}",
    ]
    for item in report["datasets"]:
        lines.append(
            f"{item['dataset'][:26]:26} {item['status']:9} {item['rows']:>8} "
            f"{item['entities']:>6} {(item['last_period'] or '-')[:16]:16} "
            f"{item['age_hours'] if item['age_hours'] is not None else '-':>6} "
            f"{item['duplicate_keys']:>4} {item['blank_rows']:>6} "
            f"{len(item['short_periods']):>4}/{item['closed_periods']:<5} "
            f"{item.get('revised_rows') if item.get('revised_rows') is not None else '-':>6}"
        )
        for finding in item["findings"]:
            if finding["severity"] != "ok":
                lines.append(f"    {finding['severity']}: {finding['message']}")
    return "\n".join(lines) + "\n"
