"""CR-10 enterprise identity PostgreSQL integration tests."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    AuditEventRecord,
    IdentityExternalIdRecord,
    IdentityPrincipalRecord,
    UserSessionRecord,
)
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.db.repositories.security import (
    create_external_identity,
    create_session,
    get_active_session_by_token,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL"),
    reason="RUNTIME_STORE_DATABASE_URL not configured; run via scripts/ci/run_postgres_ci.sh",
)


def test_principal_external_identity_and_session_roundtrip() -> None:
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    now = datetime.now(UTC)
    with Session(engine) as session:
        principal = identity_repository.create_identity_principal(
            session,
            name="pg-enterprise-user",
            display_name="PostgreSQL Enterprise User",
            role="ANALYST",
            data_scopes=["EEX"],
            now_utc=now,
        )
        create_external_identity(
            session,
            principal_id=principal.principal_id,
            issuer="https://idp.example.test",
            subject="pg-subject-1",
            provider_id="oidc",
            email="pg@example.test",
            display_name="PostgreSQL Enterprise User",
            now_utc=now,
        )
        token = "pg-session-token"
        create_session(
            session,
            principal_id=principal.principal_id,
            token=token,
            client_type="browser",
            now_utc=now,
        )
        session.commit()
        principal_id = principal.principal_id

    with Session(engine) as session:
        row = session.get(IdentityPrincipalRecord, principal_id)
        assert row is not None
        assert row.identity_source == "LOCAL"
        external = (
            session.query(IdentityExternalIdRecord)
            .filter(IdentityExternalIdRecord.subject == "pg-subject-1")
            .one()
        )
        assert external.principal_id == principal_id
        active = get_active_session_by_token(session, token, now_utc=datetime.now(UTC))
        assert active is not None
        assert active.principal_id == principal_id
        session.query(IdentityExternalIdRecord).filter(
            IdentityExternalIdRecord.subject == "pg-subject-1"
        ).delete(synchronize_session=False)
        session.query(UserSessionRecord).filter(
            UserSessionRecord.principal_id == principal_id
        ).delete(synchronize_session=False)
        session.delete(row)
        session.commit()


def test_extended_audit_columns_persist() -> None:
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    from eurogas_nexus.db.repositories.audit import record_audit_event

    with Session(engine) as session:
        event = record_audit_event(
            session,
            event_type="governance.security-test",
            principal="pg-admin",
            action="access.user.update",
            resource="identity_principal:pg-test",
            outcome="updated",
            permission="identity.manage",
            correlation_id="corr-123",
            client_type="api",
            before_summary={"status": "ACTIVE"},
            after_summary={"status": "DISABLED"},
        )
        session.commit()
        event_id = event.event_id

    with Session(engine) as session:
        row = session.get(AuditEventRecord, event_id)
        assert row is not None
        assert row.permission == "identity.manage"
        assert row.correlation_id == "corr-123"
        assert row.after_summary == {"status": "DISABLED"}
        session.delete(row)
        session.commit()
