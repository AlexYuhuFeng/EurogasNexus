"""Add REST evidence fields to National Gas actual-demand revisions.

The upgrade is additive: existing CSV revisions keep their values, timestamps
and identities and receive the CSV/default flags.  A downgrade is refused while
REST provenance or blank-value evidence exists, because dropping the new columns
would silently discard that evidence.
"""

import sqlalchemy as sa

from alembic import op

revision = "0043_national_gas_rest_evidence"
down_revision = "0042_national_gas_actual_demand"
branch_labels = None
depends_on = None

_VALUE_TEXT_CHECK = (
    "length(value_text) <= 64 AND "
    "((value_is_blank AND length(value_text) = 0) OR "
    "(NOT value_is_blank AND length(value_text) > 0))"
)
_LEGACY_VALUE_TEXT_CHECK = "length(value_text) > 0 AND length(value_text) <= 64"


def _table(*, with_rest_columns: bool) -> sa.Table:
    """Return the explicit copy source used by SQLite batch operations.

    SQLite does not reflect CHECK constraints.  Supplying the existing table
    definition keeps the 0042 constraints and indexes when batch mode rebuilds
    the table.
    """

    metadata = sa.MetaData()
    columns = [
        sa.Column("record_id", sa.String(64), primary_key=True),
        sa.Column("source_publication_id", sa.String(64), nullable=False, unique=True),
        sa.Column("provider_item_id", sa.String(32), nullable=False),
        sa.Column("series_key", sa.String(64), nullable=False),
        sa.Column("region", sa.String(16), nullable=False),
        sa.Column("term", sa.String(8), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("gas_day", sa.Date(), nullable=False),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applicable_at_raw", sa.String(32), nullable=False),
        sa.Column("generated_at_raw", sa.String(32), nullable=False),
        sa.Column("applicable_at_naive", sa.DateTime(timezone=False), nullable=False),
        sa.Column("generated_at_naive", sa.DateTime(timezone=False), nullable=False),
        sa.Column("quality_indicator", sa.String(8), nullable=True),
        sa.Column("provisional_status", sa.String(40), nullable=False),
        sa.Column("is_provisional", sa.Boolean(), nullable=True),
        sa.Column("raw_sha256", sa.String(64), nullable=False),
        sa.Column("source_url", sa.String(512), nullable=False),
        sa.Column("hash_schema", sa.String(64), nullable=False),
    ]
    constraints = [
        sa.CheckConstraint("region = 'GB_NTS'", name="ck_ng_actual_demand_region"),
        sa.CheckConstraint("unit = 'mscm'", name="ck_ng_actual_demand_unit"),
        sa.CheckConstraint("term IN ('D+1', 'D+6')", name="ck_ng_actual_demand_term"),
        sa.CheckConstraint(
            _VALUE_TEXT_CHECK if with_rest_columns else _LEGACY_VALUE_TEXT_CHECK,
            name="ck_ng_actual_demand_value_text",
        ),
        sa.CheckConstraint(
            "quality_indicator IS NULL OR "
            "(length(quality_indicator) > 0 AND length(quality_indicator) <= 8)",
            name="ck_ng_actual_demand_quality",
        ),
    ]
    if with_rest_columns:
        columns.extend(
            [
                sa.Column(
                    "value_is_blank",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
                sa.Column(
                    "source_format",
                    sa.String(8),
                    nullable=False,
                    server_default="CSV",
                ),
                sa.Column("rest_provenance", sa.JSON(), nullable=True),
            ]
        )
        constraints.extend(
            [
                sa.CheckConstraint(
                    "source_format IN ('CSV', 'REST')",
                    name="ck_ng_actual_demand_source_format",
                ),
                sa.CheckConstraint(
                    "source_format != 'REST' OR rest_provenance IS NOT NULL",
                    name="ck_ng_actual_demand_rest_provenance",
                ),
            ]
        )

    return sa.Table(
        "national_gas_actual_demand",
        metadata,
        *columns,
        *constraints,
        sa.Index(
            "ix_national_gas_actual_demand_series_gas_day",
            "series_key",
            "gas_day",
        ),
        sa.Index(
            "ix_national_gas_actual_demand_published_utc",
            "published_at_utc",
        ),
    )


def _ensure_indexes() -> None:
    """Restore the 0042 indexes if a SQLite batch rebuild did not copy them."""

    inspector = sa.inspect(op.get_bind())
    existing = {
        index["name"]
        for index in inspector.get_indexes("national_gas_actual_demand")
        if index.get("name")
    }
    indexes = (
        (
            "ix_national_gas_actual_demand_series_gas_day",
            ["series_key", "gas_day"],
        ),
        (
            "ix_national_gas_actual_demand_published_utc",
            ["published_at_utc"],
        ),
    )
    for name, columns in indexes:
        if name not in existing:
            op.create_index(name, "national_gas_actual_demand", columns)


def _upgrade_columns(batch_op) -> None:
    batch_op.add_column(
        sa.Column(
            "value_is_blank",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        )
    )
    batch_op.add_column(
        sa.Column(
            "source_format",
            sa.String(8),
            nullable=False,
            server_default="CSV",
        )
    )
    batch_op.add_column(sa.Column("rest_provenance", sa.JSON(), nullable=True))
    batch_op.drop_constraint("ck_ng_actual_demand_value_text", type_="check")
    batch_op.create_check_constraint(
        "ck_ng_actual_demand_value_text",
        _VALUE_TEXT_CHECK,
    )
    batch_op.create_check_constraint(
        "ck_ng_actual_demand_source_format",
        "source_format IN ('CSV', 'REST')",
    )
    batch_op.create_check_constraint(
        "ck_ng_actual_demand_rest_provenance",
        "source_format != 'REST' OR rest_provenance IS NOT NULL",
    )


def _downgrade_columns(batch_op) -> None:
    batch_op.drop_constraint("ck_ng_actual_demand_source_format", type_="check")
    batch_op.drop_constraint("ck_ng_actual_demand_rest_provenance", type_="check")
    batch_op.drop_constraint("ck_ng_actual_demand_value_text", type_="check")
    batch_op.create_check_constraint(
        "ck_ng_actual_demand_value_text",
        _LEGACY_VALUE_TEXT_CHECK,
    )
    batch_op.drop_column("rest_provenance")
    batch_op.drop_column("source_format")
    batch_op.drop_column("value_is_blank")


def _column_batch(*, with_rest_columns: bool):
    """Open a batch operation that works on both SQLite and PostgreSQL.

    PostgreSQL needs no table rebuild, so ``recreate="auto"`` emits ordinary
    ``ALTER TABLE`` statements.  SQLite still receives the explicit ``copy_from``
    definition that preserves the 0042 CHECK constraints during its rebuild.
    """

    kwargs = {}
    if op.get_bind().dialect.name == "sqlite":
        kwargs["copy_from"] = _table(with_rest_columns=with_rest_columns)
    return op.batch_alter_table(
        "national_gas_actual_demand",
        recreate="auto",
        **kwargs,
    )


def upgrade():
    with _column_batch(with_rest_columns=False) as batch_op:
        _upgrade_columns(batch_op)
    _ensure_indexes()


def downgrade():
    bind = op.get_bind()
    table = sa.Table(
        "national_gas_actual_demand",
        sa.MetaData(),
        autoload_with=bind,
    )
    has_rest_or_blank_evidence = bind.execute(
        sa.select(sa.literal(1))
        .select_from(table)
        .where(
            sa.or_(
                table.c.source_format == "REST",
                table.c.value_is_blank.is_(True),
                table.c.rest_provenance.is_not(None),
            )
        )
        .limit(1)
    ).first()
    if has_rest_or_blank_evidence is not None:
        raise RuntimeError(
            "National Gas actual-demand REST or blank-value evidence cannot be "
            "downgraded without silently discarding provenance; restore an "
            "approved pre-migration backup instead."
        )

    with _column_batch(with_rest_columns=True) as batch_op:
        _downgrade_columns(batch_op)
    _ensure_indexes()
