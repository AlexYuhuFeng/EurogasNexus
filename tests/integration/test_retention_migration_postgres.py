"""Migration 0096 (retention by data class) on PostgreSQL: its downgrade refuses to lose pages.

After 0096 a raw-page receipt no longer carries its page; the page lives once in
``raw_payload_contents``. Dropping that table would lose the page, so the downgrade refuses
while any receipt has no inline page, and goes through once ``scripts/ops/retention.py
inline-raw-pages`` (here: the page put back by hand) has run. Opt-in: a throwaway server in
``EUROGAS_NEXUS_SCRATCH_PG_URL`` (tests/support/scratch_postgres.py); run by
scripts/ci/run_postgres_ci.sh.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from tests.support.scratch_postgres import SCRATCH_PG_ENV, scratch_postgres_database

pytestmark = pytest.mark.skipif(
    not os.environ.get(SCRATCH_PG_ENV), reason=f"{SCRATCH_PG_ENV} is not set"
)


def _revision(url: str) -> str:
    from eurogas_nexus.db.session import get_engine

    engine = get_engine(url, one_off=True, statement_timeout=None)
    try:
        with engine.connect() as connection:
            return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def test_the_downgrade_below_0096_refuses_while_a_receipt_has_no_inline_page() -> None:
    from alembic import command
    from eurogas_nexus.application.database_upgrade import alembic_config
    from eurogas_nexus.db.session import get_engine

    with scratch_postgres_database(os.environ[SCRATCH_PG_ENV], prefix="ret0096") as url:
        config = alembic_config(url)
        # To this migration, not to head: head moves with every later migration.
        command.upgrade(config, "0096_retention_by_class")
        assert _revision(url) == "0096_retention_by_class"
        engine = get_engine(url, one_off=True, statement_timeout=None)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO raw_payload_archives (archive_id, source_system, dataset, "
                        "source_reference, payload_sha256, record_count, received_at_utc, "
                        "research_only, human_review_required) VALUES ('rpa-1', 'test', 'test', "
                        "'ref', :digest, 1, now(), false, false)"
                    ),
                    {"digest": "0" * 64},
                )
            with pytest.raises(RuntimeError, match="inline-raw-pages"):
                command.downgrade(config, "0095_security_hardening")
            assert _revision(url) == "0096_retention_by_class"
            # The page back on its receipt (what inline-raw-pages does): the way down is open.
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE raw_payload_archives SET payload_text = 'page' "
                        "WHERE archive_id = 'rpa-1'"
                    )
                )
        finally:
            engine.dispose()
        command.downgrade(config, "0095_security_hardening")
        assert _revision(url) == "0095_security_hardening"
        # To this migration, not to head: head moves with every later migration.
        command.upgrade(config, "0096_retention_by_class")
        assert _revision(url) == "0096_retention_by_class"
