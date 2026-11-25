"""Migration 0084 on SQLite: the NEWS-1 tables match the models, up and down.

0084 follows SCHED-1's ``0085_sched1_nomination_matching``, merged first.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"tests.migration_{name[:4]}", VERSIONS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_up_down_and_model_match():
    from eurogas_nexus.db.models import NewsItemRecord, NewsSourcePollRecord

    module = _load("0084_news_items.py")
    assert module.revision == "0084_news_items"
    assert DB_SCHEMA_REVISION == "0087_lng4_options_demurrage"
    assert module.down_revision == "0085_sched1_nomination_matching"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        inspector = inspect(connection)
        for model in (NewsItemRecord, NewsSourcePollRecord):
            columns = {c["name"] for c in inspector.get_columns(model.__tablename__)}
            assert columns == set(model.__table__.columns.keys()), model.__tablename__
            indexes = {i["name"] for i in inspector.get_indexes(model.__tablename__)}
            assert {i.name for i in model.__table__.indexes} <= indexes
        module.downgrade()
        assert inspect(connection).get_table_names() == []
