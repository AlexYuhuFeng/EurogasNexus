"""Native PostgreSQL migration, idempotency and cancel/complete race evidence."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from eurogas_nexus.application import functional_runs as service
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.functional import FunctionalRunRecord
from eurogas_nexus.db.models.jobs import JobRecord
from eurogas_nexus.db.repositories.identity import create_identity_principal
from eurogas_nexus.db.repositories.jobs import cancel_job
from eurogas_nexus.security.identity import AuthenticatedPrincipal
from tests.api.test_nwe_balance_scenario import scenario
from tests.db.test_demand_rest_schema import _migration
from tests.db.test_demand_rest_schema import postgres_migration_engine as postgres_migration_engine


@pytest.fixture
def engine(postgres_migration_engine):
    yield postgres_migration_engine


@pytest.fixture
def store(engine):
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        row = create_identity_principal(
            session,
            name="functional.pg",
            display_name="Functional PG",
            role="ANALYST",
            data_scopes=["*"],
        )
        actor = AuthenticatedPrincipal(
            principal_id=row.principal_id,
            name=row.name,
            principal_type="USER",
            role="ANALYST",
            status="ACTIVE",
            data_scopes=("*",),
            roles=("ANALYST",),
        )
        session.commit()
    return sessionmaker(engine), actor


def test_native_migration_round_trip(engine):
    tables = [t for t in Base.metadata.sorted_tables if not t.name.startswith("functional_")]
    Base.metadata.create_all(engine, tables=tables)
    migration = _migration("0058_functional_runs.py")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert {"functional_runs", "functional_models", "functional_dependencies"}.issubset(
                inspect(connection).get_table_names()
            )
            migration.downgrade()
            assert not any(
                n.startswith("functional_") for n in inspect(connection).get_table_names()
            )
            migration.upgrade()


def test_concurrent_idempotency_creates_one_run_and_one_job(store):
    factory, actor = store
    barrier = Barrier(2)
    request = service.SubmitRun(kind="NWE_BALANCE", inputs=scenario(), idempotency_key="same-key")

    def submit():
        with factory() as session:
            barrier.wait(timeout=10)
            row, created = service.submit(session, actor, request)
            run_id = row.run_id
            session.commit()
            return run_id, created

    with ThreadPoolExecutor(max_workers=2) as pool:
        left, right = list(pool.map(lambda _: submit(), range(2)))
    assert left[0] == right[0]
    assert sum([left[1], right[1]]) == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FunctionalRunRecord)) == 1
        assert session.scalar(select(func.count()).select_from(JobRecord)) == 1


def test_cancel_during_compute_cannot_publish_success(store, monkeypatch):
    factory, actor = store
    with factory() as session:
        row, _ = service.submit(
            session,
            actor,
            service.SubmitRun(kind="NWE_BALANCE", inputs=scenario(), idempotency_key="cancel-race"),
        )
        run_id, job_id = row.run_id, row.job_id
        session.commit()
    entered, release = Event(), Event()
    original = service.compute

    def compute(*args):
        entered.set()
        assert release.wait(timeout=10)
        return original(*args)

    monkeypatch.setattr(service, "compute", compute)
    with ThreadPoolExecutor(max_workers=2) as pool:
        worker = pool.submit(service.execute, factory, run_id)
        assert entered.wait(timeout=10)
        with factory() as session:
            cancel_job(session, job_id)
            session.commit()
        release.set()
        worker.result(timeout=20)
    with factory() as session:
        assert session.get(JobRecord, job_id).status == "CANCELLED"
        assert session.get(FunctionalRunRecord, run_id).result is None
