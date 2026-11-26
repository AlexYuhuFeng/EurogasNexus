"""Migrations 0086 and 0087 on SQLite: the LNG-3 disruption tables and the LNG-4 columns and
outage links match the models, up and down, and 0087 only expands."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"

#: The columns 0087 adds to the LNG-3 tables (LNG-4).
LNG4_COLUMNS = {
    "lng_voyage_terms": {"demurrage_rate_per_day", "demurrage_currency", "demurrage_terms"},
    "lng_delivery_obligations": {"penalty_terms"},
    "pipeline_supplies": {"depends_on", "outage_mode"},
    "lng_disruption_runs": {"recommended_set"},
    "lng_disruption_decisions": {"recommended_set", "consequences", "fx"},
    "lng_capacity_offers": {"hub"},
    "lng_slot_terms": {"berth_days"},
}
#: The columns 0091 adds to a table 0087 creates (the berth rule's counterparty quote); this
#: test runs 0086 and 0087 only, so the model has them and the table does not.
LATER_COLUMNS = {
    "lng_berth_calls": {"counterparty", "quote_amount", "quote_currency", "quote_reference"},
}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"tests.migration_{name[:4]}", VERSIONS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _models():
    from eurogas_nexus.db.models import (
        LngCapacityOfferRecord,
        LngDeliveryObligationRecord,
        LngDisruptionDecisionRecord,
        LngDisruptionRunRecord,
        LngSlotTermsRecord,
        LngVoyageTermsRecord,
        PipelineSupplyRecord,
    )

    return (
        LngSlotTermsRecord,
        LngCapacityOfferRecord,
        LngDeliveryObligationRecord,
        LngVoyageTermsRecord,
        PipelineSupplyRecord,
        LngDisruptionRunRecord,
        LngDisruptionDecisionRecord,
    )


def test_up_down_and_model_match():
    from eurogas_nexus.db.models import LngBerthCallRecord, PipelineOutageLinkRecord

    lng3 = _load("0086_lng_disruption.py")
    lng4 = _load("0087_lng4_options_demurrage_outages.py")
    assert lng3.revision == "0086_lng_disruption"
    assert lng3.down_revision == "0084_news_items"
    assert lng4.revision == "0087_lng4_options_demurrage"
    assert lng4.down_revision == "0088_tar2_capacity_bookings"
    assert len(lng4.revision) <= 32  # alembic_version.version_num is VARCHAR(32)
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection=connection))
        lng3.op = lng4.op = operations
        lng3.upgrade()
        inspector = inspect(connection)
        for model in _models():
            columns = {c["name"] for c in inspector.get_columns(model.__tablename__)}
            added = LNG4_COLUMNS.get(model.__tablename__, set())
            assert columns == set(model.__table__.columns.keys()) - added, model.__tablename__
        lng4.upgrade()
        inspector = inspect(connection)
        for model in (*_models(), PipelineOutageLinkRecord, LngBerthCallRecord):
            columns = {c["name"] for c in inspector.get_columns(model.__tablename__)}
            later = LATER_COLUMNS.get(model.__tablename__, set())
            assert columns == set(model.__table__.columns.keys()) - later, model.__tablename__
            indexes = {i["name"] for i in inspector.get_indexes(model.__tablename__)}
            assert {i.name for i in model.__table__.indexes} <= indexes
        lng4.downgrade()
        inspector = inspect(connection)
        assert "pipeline_outage_links" not in inspector.get_table_names()
        assert "lng_berth_calls" not in inspector.get_table_names()
        for table, added in LNG4_COLUMNS.items():
            assert not added & {c["name"] for c in inspector.get_columns(table)}, table
        lng3.downgrade()
        assert inspect(connection).get_table_names() == []


def test_0087_only_expands():
    """Every column 0087 adds is nullable, and it drops or alters nothing on the way up."""

    source = (VERSIONS / "0087_lng4_options_demurrage_outages.py").read_text(encoding="utf-8")
    upgrade = source[source.index("def upgrade") : source.index("def downgrade")]
    assert "drop_" not in upgrade and "alter_column" not in upgrade
    assert "nullable=True" in upgrade
    lng4 = _load("0087_lng4_options_demurrage_outages.py")
    assert {(table, name) for table, name, _kind in lng4._COLUMNS} == {
        (table, name) for table, names in LNG4_COLUMNS.items() for name in names
    }
