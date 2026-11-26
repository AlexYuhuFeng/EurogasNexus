"""Migration 0086 on SQLite: the LNG-3 disruption tables match the models, up and down."""

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
    from eurogas_nexus.db.models import (
        LngCapacityOfferRecord,
        LngDeliveryObligationRecord,
        LngDisruptionDecisionRecord,
        LngDisruptionRunRecord,
        LngSlotTermsRecord,
        LngVoyageTermsRecord,
        PipelineSupplyRecord,
    )

    module = _load("0086_lng_disruption.py")
    assert module.revision == "0086_lng_disruption"
    assert DB_SCHEMA_REVISION == "0087_job_progress_steps"
    assert module.down_revision == "0084_news_items"
    models = (
        LngSlotTermsRecord,
        LngCapacityOfferRecord,
        LngDeliveryObligationRecord,
        LngVoyageTermsRecord,
        PipelineSupplyRecord,
        LngDisruptionRunRecord,
        LngDisruptionDecisionRecord,
    )
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        inspector = inspect(connection)
        for model in models:
            columns = {c["name"] for c in inspector.get_columns(model.__tablename__)}
            assert columns == set(model.__table__.columns.keys()), model.__tablename__
            indexes = {i["name"] for i in inspector.get_indexes(model.__tablename__)}
            assert {i.name for i in model.__table__.indexes} <= indexes
        module.downgrade()
        assert inspect(connection).get_table_names() == []
