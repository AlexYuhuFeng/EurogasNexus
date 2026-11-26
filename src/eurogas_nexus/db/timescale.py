"""Optional TimescaleDB Community Edition for the high-volume time-series tables (ADR 39).

PostgreSQL stays the runtime store. TimescaleDB is an extension an operator may install on a
self-hosted server; when it is installed, enabled and the Community Edition (licence
``timescale``, the Timescale License) is loaded, three append-only tables become hypertables
with columnstore compression. Without it every table stays a plain PostgreSQL table and the
platform behaves exactly as before, so development, CI and the demo need nothing.

The setting ``EUROGAS_NEXUS_TIMESCALE`` chooses:

``off`` (the default)
    Nothing is converted, even on a server where the extension is installed. A conversion
    changes three primary keys and is not reversed by a downgrade, so it happens only when
    an operator asks for it. Managed PostgreSQL services often list ``timescaledb`` as
    available, usually the Apache-2 edition without compression; a default of ``auto``
    would convert such a server without anyone choosing it.
``auto``
    Convert when the server can (PostgreSQL, the extension available and preloaded, version
    :data:`MIN_VERSION` or later, the Community Edition loaded); otherwise log why not and
    leave the schema unchanged.
``require``
    As ``auto``, but stop with :class:`TimescaleRequiredError` when the server cannot, so a
    production server that should have it does not silently run without it.

Migration ``0093_timescale_optional`` calls :func:`apply` once. The same call is idempotent,
so an operator who installs the extension later runs ``scripts/ops/timescale.py apply``
instead of re-running a migration that is already recorded.

What is converted and what is not is data in this module (:data:`HYPERTABLE_PLANS`,
:data:`SKIPPED_TABLES`), each with its reason. A hypertable needs its time column in every
unique index. The three tables converted are written append-only under an id that is random
or a digest that includes the time, and no write path names their primary key as an
``ON CONFLICT`` target, so their primary key is widened from ``(id)`` to ``(id, time)``
without changing what any writer does. The observation tables are not converted: the
ingestion upsert and the revision lookup are keyed on ``observation_id`` alone, which a
hypertable cannot keep unique (see :data:`SKIPPED_TABLES`).

No continuous aggregate is created. The readers that aggregate these series by day
(``api/routes/public/fundamentals.py:_daily_sum``) answer as of an instant, take revisions
from ``observation_revisions`` and resolve identities at read time; a continuous aggregate
holds current values only and would leak a later revision into an earlier read.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import text

logger = logging.getLogger(__name__)

ENV_VAR = "EUROGAS_NEXUS_TIMESCALE"
Mode = Literal["off", "auto", "require"]
MODES: tuple[Mode, ...] = ("off", "auto", "require")
DEFAULT_MODE: Mode = "off"
EXTENSION = "timescaledb"
#: Oldest release accepted: UPDATE and DELETE on compressed chunks (the retention job deletes
#: quotes) arrived in 2.11; 2.13 is the floor chosen for this platform (no older release has
#: been tried).
MIN_VERSION = (2, 13)
#: ``timescaledb.license`` when the Community Edition's features are loaded. ``apache`` means
#: the Apache-2 edition, which has hypertables but no compression or continuous aggregates.
COMMUNITY_LICENSE = "timescale"

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_INTERVAL = re.compile(r"^[0-9]+ (day|days|hour|hours)$")


class TimescaleRequiredError(RuntimeError):
    """``EUROGAS_NEXUS_TIMESCALE=require`` and the server cannot provide it."""


@dataclass(frozen=True)
class HypertablePlan:
    """How one table becomes a hypertable with compression."""

    table: str
    time_column: str
    key_column: str
    chunk_interval: str
    segment_by: tuple[str, ...]
    order_by: str
    compress_after: str
    #: Create Timescale's default index on the time column (only where none exists).
    default_indexes: bool
    why: str

    def __post_init__(self) -> None:
        for name in (self.table, self.time_column, self.key_column, *self.segment_by):
            if not _IDENTIFIER.match(name):
                raise ValueError(f"not a plain identifier: {name!r}")
        for interval in (self.chunk_interval, self.compress_after):
            if not _INTERVAL.match(interval):
                raise ValueError(f"not a plain interval: {interval!r}")
        if self.order_by != f"{self.time_column} DESC":
            raise ValueError(f"order_by must be the time column descending: {self.order_by!r}")


#: Chunk and compression intervals are estimates sized from doc 19's rates (section 2.2):
#: a chunk of a few days to a week keeps each chunk's indexes well inside memory, and
#: compression starts after the window in which rows are still written or revised.
HYPERTABLE_PLANS: tuple[HypertablePlan, ...] = (
    HypertablePlan(
        table="raw_payload_archives",
        time_column="received_at_utc",
        key_column="archive_id",
        chunk_interval="7 days",
        segment_by=("source_system", "dataset"),
        order_by="received_at_utc DESC",
        compress_after="28 days",
        default_indexes=True,
        why=(
            "About 91 % of today's growth (doc 19 section 1.4). Append-only "
            "(archive_raw_payload); archive_id is raw-<random uuid>, so (archive_id, "
            "received_at_utc) is as unique as archive_id."
        ),
    ),
    HypertablePlan(
        table="market_quotes",
        time_column="observed_at_utc",
        key_column="quote_id",
        chunk_interval="1 day",
        segment_by=("source_system", "hub", "product"),
        order_by="observed_at_utc DESC",
        compress_after="7 days",
        default_indexes=False,
        why=(
            "Ticks: the largest stream once ticks are licensed (scenario C). Written by "
            "ingest_ticks (check, then insert) or by ORM merge; the tick and file ids are "
            "digests that include observed_at_utc."
        ),
    ),
    HypertablePlan(
        table="market_trades",
        time_column="traded_at_utc",
        key_column="trade_id",
        chunk_interval="7 days",
        segment_by=("source_system", "hub", "product"),
        order_by="traded_at_utc DESC",
        compress_after="7 days",
        default_indexes=False,
        why=(
            "Trade prints: append-only (ingest_ticks checks the id, then inserts); "
            "trade_id is the venue's own trade id, printed once at one time."
        ),
    ),
)

_UPSERT_KEYED = (
    "written by keyed upserts on its id alone (ON CONFLICT (observation_id) in "
    "db/repositories/public_ingestion_upsert.py, the per-row revision lookup FOR UPDATE, "
    "ORM merge); a hypertable cannot keep that id unique, so these write paths must be "
    "keyed on (id, period_start_utc) first, the same prerequisite ADR Decision 24 names "
    "for monthly partitioning"
)

#: High-volume tables doc 19 names that are deliberately not converted, with the reason.
SKIPPED_TABLES: Mapping[str, str] = {
    "flow_observations": _UPSERT_KEYED,
    "capacity_observations": _UPSERT_KEYED,
    "power_observations": _UPSERT_KEYED,
    "storage_observations": _UPSERT_KEYED,
    "lng_observations": _UPSERT_KEYED,
    "market_observations": _UPSERT_KEYED,
    "forecast_observations": _UPSERT_KEYED.replace("observation_id", "forecast_observation_id"),
    "market_events": (
        "the transactional outbox: market_event_deliveries references it by foreign key, and "
        "its idempotence rests on UNIQUE (event_key, revision) and UNIQUE (event_id), which "
        "cannot include a time column without losing the guarantee (ADR Decision 28)"
    ),
    "market_event_deliveries": (
        "PRIMARY KEY (consumer, event_seq) has no time column, it references market_events "
        "by foreign key, and its rows are updated as each consumer processes them"
    ),
    "audit_events": (
        "governed evidence: event_id is the identity audits cite, so its constraints change "
        "only with their own review; at about 10 MB a day (doc 19, scenario B) it is far "
        "from where compression matters"
    ),
}


@dataclass(frozen=True)
class ServerFacts:
    """What the server says about TimescaleDB, read from the catalogue."""

    dialect: str
    available_version: str | None = None
    installed_version: str | None = None
    preloaded: bool = False
    license: str | None = None


@dataclass(frozen=True)
class Decision:
    enabled: bool
    reason: str


@dataclass(frozen=True)
class TableFacts:
    """One table as the catalogue holds it."""

    exists: bool
    primary_key_name: str | None = None
    primary_key: tuple[str, ...] = ()
    time_column_not_null: bool | None = None
    unique_without_time: tuple[str, ...] = ()
    referenced_by: tuple[str, ...] = ()
    is_hypertable: bool = False
    compression_enabled: bool = False


@dataclass
class ApplyReport:
    mode: Mode
    decision: Decision
    converted: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "enabled": self.decision.enabled,
            "reason": self.decision.reason,
            "converted": list(self.converted),
            "already_hypertables": list(self.already),
            "skipped": dict(self.skipped),
            "failed": dict(self.failed),
        }


def mode_from_env(environ: Mapping[str, str] | None = None) -> Mode:
    """Read ``EUROGAS_NEXUS_TIMESCALE``; blank means the default, anything unknown is refused."""

    env = os.environ if environ is None else environ
    raw = env.get(ENV_VAR, "")
    value = raw.strip().lower()
    if not value:
        return DEFAULT_MODE
    if value not in MODES:
        raise ValueError(f"{ENV_VAR} must be one of {', '.join(MODES)}; got {raw!r}")
    return value  # type: ignore[return-value]


def parse_version(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    parts = re.findall(r"\d+", value)
    return tuple(int(part) for part in parts[:3]) if parts else None


def decide(mode: Mode, facts: ServerFacts) -> Decision:
    """Whether to convert, and why not. Pure: the facts are read elsewhere."""

    if mode == "off":
        return Decision(False, f"{ENV_VAR} is off (the default)")
    if facts.dialect != "postgresql":
        return Decision(False, f"the runtime store is {facts.dialect}, not PostgreSQL")
    if facts.installed_version is None and facts.available_version is None:
        return Decision(False, "the timescaledb extension is not installed on this server")
    if facts.installed_version is None and not facts.preloaded:
        return Decision(
            False,
            "the timescaledb package is installed but not in shared_preload_libraries",
        )
    version = parse_version(facts.installed_version or facts.available_version)
    if version is None or version < MIN_VERSION:
        floor = ".".join(str(part) for part in MIN_VERSION)
        shown = facts.installed_version or facts.available_version
        return Decision(False, f"timescaledb {shown} is older than {floor}")
    if facts.license != COMMUNITY_LICENSE:
        return Decision(
            False,
            f"timescaledb.license is {facts.license or 'unset'}, not {COMMUNITY_LICENSE}: "
            "the Apache-2 edition has no compression",
        )
    return Decision(True, "TimescaleDB Community Edition is available")


def catalogue_blockers(facts: TableFacts, plan: HypertablePlan) -> list[str]:
    """Reasons the catalogue gives not to convert ``plan.table``. Empty means go ahead."""

    if not facts.exists:
        return ["the table does not exist"]
    blockers: list[str] = []
    if facts.time_column_not_null is None:
        blockers.append(f"column {plan.time_column} does not exist")
    elif not facts.time_column_not_null:
        blockers.append(f"column {plan.time_column} is nullable")
    expected = {(plan.key_column,), (plan.key_column, plan.time_column)}
    if facts.primary_key not in expected:
        blockers.append(
            f"primary key is ({', '.join(facts.primary_key) or 'none'}), expected "
            f"({plan.key_column})"
        )
    for name in facts.unique_without_time:
        blockers.append(f"unique index {name} does not include {plan.time_column}")
    for name in facts.referenced_by:
        blockers.append(f"referenced by foreign key {name}")
    return blockers


# --- catalogue reads -----------------------------------------------------------------


def _scalar(connection, statement: str, **params: Any) -> Any:
    return connection.execute(text(statement), params).scalar()


def server_facts(connection) -> ServerFacts:
    dialect = connection.dialect.name
    if dialect != "postgresql":
        return ServerFacts(dialect=dialect)
    available = _scalar(
        connection,
        "SELECT default_version FROM pg_available_extensions WHERE name = :name",
        name=EXTENSION,
    )
    installed = _scalar(
        connection, "SELECT extversion FROM pg_extension WHERE extname = :name", name=EXTENSION
    )
    preload = _scalar(connection, "SELECT current_setting('shared_preload_libraries', true)")
    preloaded = EXTENSION in [part.strip() for part in str(preload or "").split(",")]
    license_value = _scalar(connection, "SELECT current_setting('timescaledb.license', true)")
    return ServerFacts(
        dialect=dialect,
        available_version=None if available is None else str(available),
        installed_version=None if installed is None else str(installed),
        preloaded=preloaded,
        license=str(license_value) if license_value else None,
    )


def _hypertable_flags(connection, table: str) -> tuple[bool, bool]:
    if _scalar(connection, "SELECT to_regclass('timescaledb_information.hypertables')") is None:
        return False, False
    row = connection.execute(
        text(
            "SELECT compression_enabled FROM timescaledb_information.hypertables "
            "WHERE hypertable_schema = current_schema() AND hypertable_name = :table"
        ),
        {"table": table},
    ).first()
    return (row is not None, bool(row[0]) if row is not None else False)


def table_facts(connection, plan: HypertablePlan) -> TableFacts:
    relid = _scalar(
        connection,
        "SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = current_schema() AND c.relname = :table AND c.relkind = 'r'",
        table=plan.table,
    )
    if relid is None:
        return TableFacts(exists=False)
    not_null = _scalar(
        connection,
        "SELECT attnotnull FROM pg_attribute WHERE attrelid = :relid AND attname = :column "
        "AND NOT attisdropped",
        relid=relid,
        column=plan.time_column,
    )
    primary = connection.execute(
        text(
            "SELECT con.conname, array_agg(a.attname::text ORDER BY k.ordinality) "
            "FROM pg_constraint con "
            "CROSS JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ordinality) "
            "JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum "
            "WHERE con.conrelid = :relid AND con.contype = 'p' GROUP BY con.conname"
        ),
        {"relid": relid},
    ).first()
    unique_rows = connection.execute(
        text(
            "SELECT i.indexrelid::regclass::text FROM pg_index i "
            "WHERE i.indrelid = :relid AND i.indisunique AND NOT i.indisprimary "
            "AND NOT EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = i.indrelid "
            "AND a.attnum = ANY(i.indkey) AND a.attname = :column)"
        ),
        {"relid": relid, "column": plan.time_column},
    ).all()
    referenced = connection.execute(
        text(
            "SELECT conrelid::regclass::text || '.' || conname FROM pg_constraint "
            "WHERE confrelid = :relid AND contype = 'f'"
        ),
        {"relid": relid},
    ).all()
    is_hypertable, compression = _hypertable_flags(connection, plan.table)
    return TableFacts(
        exists=True,
        primary_key_name=None if primary is None else str(primary[0]),
        primary_key=() if primary is None else tuple(str(name) for name in primary[1]),
        time_column_not_null=None if not_null is None else bool(not_null),
        unique_without_time=tuple(str(row[0]) for row in unique_rows),
        referenced_by=tuple(str(row[0]) for row in referenced),
        is_hypertable=is_hypertable,
        compression_enabled=compression,
    )


# --- conversion ----------------------------------------------------------------------


def _quoted(name: str) -> str:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"not a plain identifier: {name!r}")
    return f'"{name}"'


def conversion_statements(plan: HypertablePlan, facts: TableFacts) -> list[str]:
    """The DDL that converts one table, given what the catalogue holds. Pure, for review."""

    table = _quoted(plan.table)
    statements: list[str] = []
    if not facts.is_hypertable:
        if facts.primary_key == (plan.key_column,):
            name = _quoted(facts.primary_key_name or f"{plan.table}_pkey")
            statements.append(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
            statements.append(
                f"ALTER TABLE {table} ADD CONSTRAINT {name} PRIMARY KEY "
                f"({_quoted(plan.key_column)}, {_quoted(plan.time_column)})"
            )
        statements.append(
            f"SELECT create_hypertable('{plan.table}'::regclass, '{plan.time_column}'::name, "
            f"chunk_time_interval => INTERVAL '{plan.chunk_interval}', "
            f"create_default_indexes => {'true' if plan.default_indexes else 'false'}, "
            "if_not_exists => true, migrate_data => true)"
        )
    if not facts.compression_enabled:
        statements.append(
            f"ALTER TABLE {table} SET (timescaledb.compress, "
            f"timescaledb.compress_segmentby = '{', '.join(plan.segment_by)}', "
            f"timescaledb.compress_orderby = '{plan.order_by}')"
        )
    statements.append(
        f"SELECT add_compression_policy('{plan.table}'::regclass, "
        f"INTERVAL '{plan.compress_after}', if_not_exists => true)"
    )
    return statements


def apply(connection, *, mode: Mode | None = None) -> ApplyReport:
    """Create the extension and convert the planned tables, where the mode and server allow.

    Idempotent. Runs inside the caller's transaction; each table converts inside its own
    savepoint, so under ``auto`` a table that fails is rolled back, logged and left plain
    while the others proceed. Under ``require`` any failure is raised.
    """

    chosen = mode or mode_from_env()
    facts = server_facts(connection)
    decision = decide(chosen, facts)
    report = ApplyReport(mode=chosen, decision=decision)
    if not decision.enabled:
        if chosen == "require":
            raise TimescaleRequiredError(f"{ENV_VAR}=require, but {decision.reason}")
        logger.warning("TimescaleDB not used: %s", decision.reason)
        return report

    if facts.installed_version is None:
        # Needs a role allowed to create the extension (usually a superuser); an operator
        # may instead create it beforehand (docs/deployment/TIMESCALEDB.md).
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        except Exception as exc:
            savepoint.rollback()
            if chosen == "require":
                raise
            report.decision = Decision(
                False, f"CREATE EXTENSION timescaledb failed: {exc.__class__.__name__}"
            )
            logger.warning("TimescaleDB not used: %s (%s)", report.decision.reason, exc)
            return report
        savepoint.commit()
    for plan in HYPERTABLE_PLANS:
        current = table_facts(connection, plan)
        blockers = catalogue_blockers(current, plan)
        if blockers:
            reason = "; ".join(blockers)
            report.skipped[plan.table] = reason
            logger.warning("TimescaleDB: %s not converted: %s", plan.table, reason)
            continue
        if current.is_hypertable and current.compression_enabled:
            report.already.append(plan.table)
        savepoint = connection.begin_nested()
        try:
            for statement in conversion_statements(plan, current):
                connection.execute(text(statement))
        except Exception as exc:
            savepoint.rollback()
            if chosen == "require":
                raise
            report.failed[plan.table] = f"{exc.__class__.__name__}: {exc}"
            logger.error("TimescaleDB: %s not converted: %s", plan.table, exc)
            continue
        savepoint.commit()
        if plan.table not in report.already:
            report.converted.append(plan.table)
            logger.info("TimescaleDB: %s is a hypertable with compression", plan.table)
    for table, reason in SKIPPED_TABLES.items():
        report.skipped.setdefault(table, reason)
        logger.info("TimescaleDB: %s stays a plain table: %s", table, reason)
    return report


# --- runtime status ------------------------------------------------------------------

State = Literal["active", "installed", "available", "absent", "not_postgresql", "unknown"]


def state(connection) -> State:
    """One word for readiness and diagnostics; reads the catalogue only.

    ``active``: the extension is installed and at least one planned table is a hypertable.
    ``installed``: installed, nothing converted. ``available``: the package is on the server
    but the extension is not created. ``absent``: plain PostgreSQL.
    """

    facts = server_facts(connection)
    if facts.dialect != "postgresql":
        return "not_postgresql"
    if facts.installed_version is None:
        return "available" if facts.available_version else "absent"
    for plan in HYPERTABLE_PLANS:
        if _hypertable_flags(connection, plan.table)[0]:
            return "active"
    return "installed"


def is_active(connection) -> bool:
    return state(connection) == "active"


def engine_state(engine) -> State:
    """:func:`state` for an engine; never raises (readiness must not fail on it)."""

    try:
        with engine.connect() as connection:
            return state(connection)
    except Exception:  # noqa: BLE001 - informational
        return "unknown"


def status(connection, *, mode: Mode | None = None) -> dict[str, Any]:
    """Everything an operator needs to see, for ``scripts/ops/timescale.py status``."""

    chosen = mode or mode_from_env()
    facts = server_facts(connection)
    decision = decide(chosen, facts)
    tables: dict[str, Any] = {}
    if facts.dialect == "postgresql":
        for plan in HYPERTABLE_PLANS:
            current = table_facts(connection, plan)
            tables[plan.table] = {
                "hypertable": current.is_hypertable,
                "compression": current.compression_enabled,
                "blockers": catalogue_blockers(current, plan),
            }
    return {
        "mode": chosen,
        "state": state(connection),
        "would_convert": decision.enabled,
        "reason": decision.reason,
        "available_version": facts.available_version,
        "installed_version": facts.installed_version,
        "preloaded": facts.preloaded,
        "license": facts.license,
        "planned": tables,
        "not_converted": dict(SKIPPED_TABLES),
    }
