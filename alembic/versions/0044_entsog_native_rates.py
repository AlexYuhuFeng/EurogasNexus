"""Add versioned ENTSOG native-rate evidence to flow and capacity observations.

The upgrade is additive: legacy volume rows keep their values, identities,
timestamps and indexes.  A native row may omit the volume only when it carries
the supported normalizer version and a native JSON payload.  Downgrade refuses
any native evidence or null volume before changing either table, because
dropping the new columns would destroy evidence that cannot be reconstructed
from a legacy binary Float.
"""

import re

import sqlalchemy as sa

from alembic import op

revision = "0044_entsog_native_rates"
down_revision = "0043_national_gas_rest_evidence"
branch_labels = None
depends_on = None

_NATIVE_NORMALIZER_VERSION = "entsog-native-units-v1"
_TABLES = (
    ("flow_observations", "flow_mcm_d", "ck_flow_observations_native_rate_evidence"),
    (
        "capacity_observations",
        "capacity_mcm_d",
        "ck_capacity_observations_native_rate_evidence",
    ),
)


def _native_rate_check(volume_column: str) -> str:
    return (
        "("
        "normalizer_version IS NULL AND native_rate_json IS NULL "
        f"AND {volume_column} IS NOT NULL"
        ") OR ("
        "normalizer_version IS NOT NULL AND native_rate_json IS NOT NULL "
        f"AND normalizer_version = '{_NATIVE_NORMALIZER_VERSION}'"
        ")"
    )


def _index_snapshot(
    bind: sa.Connection,
) -> dict[str, list[tuple[str, tuple[str, ...], bool]]]:
    """Capture legacy indexes before a SQLite table rebuild."""

    inspector = sa.inspect(bind)
    snapshot = {}
    for table_name, _, _ in _TABLES:
        indexes = []
        for index in inspector.get_indexes(table_name):
            name = index.get("name")
            columns = index.get("column_names")
            if not name or not columns or index.get("duplicates_constraint"):
                continue
            indexes.append(
                (name, tuple(columns), bool(index.get("unique")))
            )
        snapshot[table_name] = indexes
    return snapshot


def _ensure_indexes(
    bind: sa.Connection,
    snapshot: dict[str, list[tuple[str, tuple[str, ...], bool]]],
) -> None:
    """Restore captured indexes if a SQLite batch rebuild dropped them."""

    inspector = sa.inspect(bind)
    for table_name, indexes in snapshot.items():
        existing = {
            index["name"]
            for index in inspector.get_indexes(table_name)
            if index.get("name")
        }
        available = {
            column["name"]
            for column in inspector.get_columns(table_name)
        }
        for name, columns, unique in indexes:
            if name not in existing and set(columns) <= available:
                op.create_index(
                    name,
                    table_name,
                    list(columns),
                    unique=unique,
                )


def _skip_quoted(sql: str, start: int) -> int:
    quote = sql[start]
    closing = "]" if quote == "[" else quote
    index = start + 1
    while index < len(sql):
        if sql[index] == closing:
            if (
                closing != "]"
                and index + 1 < len(sql)
                and sql[index + 1] == closing
            ):
                index += 2
                continue
            return index + 1
        index += 1
    return len(sql)


def _balanced_parentheses(sql: str, start: int) -> tuple[str, int]:
    depth = 0
    index = start
    while index < len(sql):
        character = sql[index]
        if character in "'\"`[":
            index = _skip_quoted(sql, index)
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return sql[start + 1 : index], index + 1
        index += 1
    raise ValueError("unbalanced SQLite CHECK constraint")


def _constraint_name(prefix: str) -> str | None:
    match = re.search(
        r'\bCONSTRAINT\s+("[^"]+"|`[^`]+`|\[[^\]]+\]|[A-Za-z_][A-Za-z0-9_]*)\s*$',
        prefix,
        re.IGNORECASE,
    )
    if match is None:
        return None
    token = match.group(1)
    if token[0] in '"`[':
        return token[1:-1]
    return token


def _sqlite_checks(
    bind: sa.Connection,
    table_name: str,
) -> list[tuple[str | None, str]]:
    """Extract CHECK constraints from SQLite DDL, which reflection omits."""

    sql = bind.execute(
        sa.text(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = :name"
        ),
        {"name": table_name},
    ).scalar()
    if not sql:
        return []

    checks = []
    index = 0
    while index < len(sql):
        character = sql[index]
        if character in "'\"`[":
            index = _skip_quoted(sql, index)
            continue
        if sql[index : index + 5].upper() != "CHECK":
            index += 1
            continue
        before = sql[index - 1] if index else " "
        after = sql[index + 5] if index + 5 < len(sql) else " "
        if before.isalnum() or before == "_" or after.isalnum() or after == "_":
            index += 5
            continue
        cursor = index + 5
        while cursor < len(sql) and sql[cursor].isspace():
            cursor += 1
        if cursor >= len(sql) or sql[cursor] != "(":
            index += 5
            continue
        try:
            expression, end = _balanced_parentheses(sql, cursor)
        except ValueError:
            break
        checks.append((_constraint_name(sql[:index].rstrip()), expression.strip()))
        index = end
    return checks


def _copy_constraints(table: sa.Table, bind: sa.Connection) -> None:
    """Keep legacy unique/check constraints through the SQLite rebuild."""

    inspector = sa.inspect(bind)
    existing = {constraint.name for constraint in table.constraints if constraint.name}
    for constraint in inspector.get_unique_constraints(table.name):
        name = constraint.get("name")
        columns = constraint.get("column_names")
        if not columns or (name and name in existing):
            continue
        table.append_constraint(
            sa.UniqueConstraint(*(table.c[column] for column in columns), name=name)
        )
        if name:
            existing.add(name)
    native_name = (
        "ck_flow_observations_native_rate_evidence"
        if table.name == "flow_observations"
        else "ck_capacity_observations_native_rate_evidence"
    )
    for name, sqltext in _sqlite_checks(bind, table.name):
        if not sqltext or name == native_name or (name and name in existing):
            continue
        table.append_constraint(sa.CheckConstraint(sqltext, name=name))
        if name:
            existing.add(name)


def _copy_indexes(table: sa.Table, bind: sa.Connection) -> None:
    """Keep indexes that SQLite batch recreation would otherwise drop."""

    for name, columns, unique in _index_snapshot(bind)[table.name]:
        sa.Index(
            name,
            *(table.c[column] for column in columns),
            unique=unique,
        )


def _table(
    *,
    with_native_columns: bool,
    bind: sa.Connection | None = None,
) -> sa.Table:
    """Return the explicit copy source used by SQLite batch operations."""

    metadata = sa.MetaData()
    columns = [
        sa.Column("observation_id", sa.String(64), primary_key=True),
        sa.Column("point_id", sa.String(64), nullable=False),
        sa.Column("point_name", sa.String(128), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="actual"),
        sa.Column(
            "flow_mcm_d",
            sa.Float(),
            nullable=with_native_columns,
        ),
        sa.Column("original_value", sa.Float(), nullable=True),
        sa.Column("original_unit", sa.String(32), nullable=True),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(128), nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=True),
        sa.Column("freshness", sa.String(16), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    ]
    constraints = []
    if with_native_columns:
        columns.extend(
            [
                sa.Column("normalizer_version", sa.String(64), nullable=True),
                sa.Column(
                    "native_rate_json",
                    sa.JSON(none_as_null=True),
                    nullable=True,
                ),
            ]
        )
        constraints.append(
            sa.CheckConstraint(
                _native_rate_check("flow_mcm_d"),
                name="ck_flow_observations_native_rate_evidence",
            )
        )

    table = sa.Table(
        "flow_observations",
        metadata,
        *columns,
        *constraints,
    )
    if bind is not None and bind.dialect.name == "sqlite":
        _copy_constraints(table, bind)
        _copy_indexes(table, bind)
    return table


def _capacity_table(
    *,
    with_native_columns: bool,
    bind: sa.Connection | None = None,
) -> sa.Table:
    """Return the capacity copy source with its legacy columns and indexes."""

    metadata = sa.MetaData()
    columns = [
        sa.Column("observation_id", sa.String(96), primary_key=True),
        sa.Column("point_id", sa.String(64), nullable=False),
        sa.Column("point_name", sa.String(128), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("capacity_type", sa.String(32), nullable=False),
        sa.Column(
            "capacity_mcm_d",
            sa.Float(),
            nullable=with_native_columns,
        ),
        sa.Column("original_value", sa.Float(), nullable=True),
        sa.Column("original_unit", sa.String(32), nullable=True),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(128), nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=True),
        sa.Column("freshness", sa.String(16), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    ]
    constraints = []
    if with_native_columns:
        columns.extend(
            [
                sa.Column("normalizer_version", sa.String(64), nullable=True),
                sa.Column(
                    "native_rate_json",
                    sa.JSON(none_as_null=True),
                    nullable=True,
                ),
            ]
        )
        constraints.append(
            sa.CheckConstraint(
                _native_rate_check("capacity_mcm_d"),
                name="ck_capacity_observations_native_rate_evidence",
            )
        )

    table = sa.Table(
        "capacity_observations",
        metadata,
        *columns,
        *constraints,
    )
    if bind is not None and bind.dialect.name == "sqlite":
        _copy_constraints(table, bind)
        _copy_indexes(table, bind)
    return table


def _column_batch(
    table_name: str,
    *,
    with_native_columns: bool,
):
    """Open a batch operation using ordinary ALTER on PostgreSQL.

    SQLite receives the explicit ``copy_from`` definition so its table rebuild
    preserves the legacy columns, primary key, indexes and native CHECK.
    """

    kwargs = {}
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        table_factory = (
            _table if table_name == "flow_observations" else _capacity_table
        )
        kwargs["copy_from"] = table_factory(
            with_native_columns=with_native_columns,
            bind=bind,
        )
    return op.batch_alter_table(
        table_name,
        recreate="auto",
        **kwargs,
    )


def _upgrade_columns(batch_op, volume_column: str, check_name: str) -> None:
    batch_op.add_column(sa.Column("normalizer_version", sa.String(64), nullable=True))
    batch_op.add_column(
        sa.Column(
            "native_rate_json",
            sa.JSON(none_as_null=True),
            nullable=True,
        )
    )
    batch_op.alter_column(
        volume_column,
        existing_type=sa.Float(),
        nullable=True,
    )
    batch_op.create_check_constraint(check_name, _native_rate_check(volume_column))


def _downgrade_columns(batch_op, volume_column: str, check_name: str) -> None:
    batch_op.drop_constraint(check_name, type_="check")
    batch_op.drop_column("native_rate_json")
    batch_op.drop_column("normalizer_version")
    batch_op.alter_column(
        volume_column,
        existing_type=sa.Float(),
        nullable=False,
    )


def _has_downgrade_evidence(
    bind: sa.Connection,
    table_name: str,
    volume_column: str,
) -> bool:
    table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
    row = bind.execute(
        sa.select(sa.literal(1))
        .select_from(table)
        .where(
            sa.or_(
                table.c.normalizer_version.is_not(None),
                table.c.native_rate_json.is_not(None),
                table.c[volume_column].is_(None),
            )
        )
        .limit(1)
    ).first()
    return row is not None


def _refuse_evidence_loss() -> None:
    """Check both tables before either table receives any DDL."""

    bind = op.get_bind()
    refused = [
        table_name
        for table_name, volume_column, _ in _TABLES
        if _has_downgrade_evidence(bind, table_name, volume_column)
    ]
    if refused:
        raise RuntimeError(
            "ENTSOG native-rate evidence or null volume cannot be downgraded "
            f"from {', '.join(refused)} without silently discarding evidence; "
            "restore an approved pre-migration backup instead."
        )


def upgrade() -> None:
    bind = op.get_bind()
    indexes = _index_snapshot(bind)
    for table_name, volume_column, check_name in _TABLES:
        with _column_batch(
            table_name,
            with_native_columns=False,
        ) as batch_op:
            _upgrade_columns(batch_op, volume_column, check_name)
    _ensure_indexes(bind, indexes)


def downgrade() -> None:
    _refuse_evidence_loss()
    bind = op.get_bind()
    indexes = _index_snapshot(bind)
    for table_name, volume_column, check_name in _TABLES:
        with _column_batch(
            table_name,
            with_native_columns=True,
        ) as batch_op:
            _downgrade_columns(batch_op, volume_column, check_name)
    _ensure_indexes(bind, indexes)
