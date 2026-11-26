"""Migration 0095 on SQLite: the audit chain, dual-control and second-factor tables match their
models, up and down (security review H5, H6, H7)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, MetaData, String, Table, create_engine, inspect

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
TABLES = ("audit_chain", "audit_chain_anchors", "privileged_changes", "identity_mfa")


def test_chain_up_down_and_models_match():
    from eurogas_nexus.db.models import (
        AuditChainAnchorRecord,
        AuditChainRecord,
        IdentityMfaRecord,
        PrivilegedChangeRecord,
    )

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0095", VERSIONS / "0095_security_hardening.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0095_security_hardening"
    assert module.down_revision == "0094_option_settlements"
    models = dict(zip(TABLES, (AuditChainRecord, AuditChainAnchorRecord,
                               PrivilegedChangeRecord, IdentityMfaRecord), strict=True))
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        # The foreign key's parent, as earlier revisions create it.
        Table(
            "identity_principals", MetaData(), Column("principal_id", String(80), primary_key=True)
        ).create(connection)
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        inspector = inspect(connection)
        for table, model in models.items():
            columns = {c["name"] for c in inspector.get_columns(table)}
            assert columns == set(model.__table__.columns.keys()), table
        module.downgrade()
        remaining = set(inspect(connection).get_table_names())
        assert not remaining & set(TABLES)
