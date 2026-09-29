"""D7: a headless provider call needs a named service identity, or it does not happen.

The finding this closes is the one place in the platform where a governed action happened with
nobody's authority behind it: the monitoring worker enriched alerts through the provider with no
principal, permission or authority reference at all. These tests pin the decision rather than the
implementation detail - refusal is the default, the grant is an explicit capability, and the actor
is the service principal the deployment provisioned.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.monitoring_service import (
    ENRICHMENT_AUTHORITY_REFUSED,
    enrich_monitoring_alert,
    scan_monitoring_conditions,
)
from eurogas_nexus.application.service_identity import (
    SERVICE_AUTHORITY_ACTOR_MISMATCH,
    SERVICE_AUTHORITY_ACTOR_MISSING,
    SERVICE_AUTHORITY_HUMAN_PRINCIPAL,
    SERVICE_AUTHORITY_INACTIVE_PRINCIPAL,
    SERVICE_AUTHORITY_NOT_CONFIGURED,
    SERVICE_AUTHORITY_NOT_GRANTED,
    SERVICE_AUTHORITY_UNKNOWN_PRINCIPAL,
    SERVICE_PRINCIPAL_ENV,
    ServiceAuthority,
    configured_service_principal_name,
    resolve_service_authority,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    IdentityPrincipalRecord,
    IngestionRunRecord,
    MonitoringAlertRecord,
)
from eurogas_nexus.db.repositories.identity import create_identity_principal
from eurogas_nexus.llm import DeepSeekCallResult
from eurogas_nexus.security.identity import AuthenticatedPrincipal


@pytest.fixture()
def session(tmp_path):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'worker.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as opened:
        yield opened


def _provision(
    session,
    *,
    name: str,
    role: str,
    status: str = "ACTIVE",
    principal_type: str = "SERVICE",
    data_scopes: list[str] | None = None,
) -> IdentityPrincipalRecord:
    row = create_identity_principal(
        session,
        name=name,
        display_name=name.title(),
        role=role,
        principal_type=principal_type,
        data_scopes=data_scopes or [],
    )
    if status != "ACTIVE":
        row.status = status
    session.commit()
    return row


def _forbidden_key_loader(_provider: str) -> str | None:
    raise AssertionError("no credential may be loaded on a refused enrichment")


def _forbidden_provider_call(**_kwargs) -> DeepSeekCallResult:
    raise AssertionError("no provider call may happen on a refused enrichment")


def _failed_ingestion_run(session, now: datetime) -> None:
    session.add(
        IngestionRunRecord(
            run_id=f"run-{now.timestamp()}",
            source_name="ENTSOG",
            status="failed",
            started_at_utc=now,
            finished_at_utc=now,
            notes="timeout",
        )
    )
    session.commit()


def _persisted_alert(session, now: datetime) -> MonitoringAlertRecord:
    """Persist one eligible alert through the real scan (no enrichment) for boundary tests."""

    _failed_ingestion_run(session, now)
    scan_monitoring_conditions(session, now_utc=now, enrich_with_llm=False)
    return session.query(MonitoringAlertRecord).one()


def _audit_rows(session, action: str) -> list[AuditEventRecord]:
    return (
        session.query(AuditEventRecord)
        .filter(AuditEventRecord.action == action)
        .all()
    )


def test_no_configured_principal_means_no_provider_call(monkeypatch, session) -> None:
    monkeypatch.delenv(SERVICE_PRINCIPAL_ENV, raising=False)

    authority = resolve_service_authority(session)

    assert authority.granted is False
    assert authority.refusal == SERVICE_AUTHORITY_NOT_CONFIGURED
    assert SERVICE_PRINCIPAL_ENV in authority.detail
    assert configured_service_principal_name() == ""


def test_an_unknown_or_inactive_principal_is_refused(monkeypatch, session) -> None:
    monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "worker-not-provisioned")
    unknown = resolve_service_authority(session)
    assert unknown.refusal == SERVICE_AUTHORITY_UNKNOWN_PRINCIPAL

    _provision(session, name="worker-disabled", role="ANALYST", status="DISABLED")
    monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "worker-disabled")
    inactive = resolve_service_authority(session)
    assert inactive.refusal == SERVICE_AUTHORITY_INACTIVE_PRINCIPAL


def test_the_capability_has_to_be_granted_not_inherited(monkeypatch, session) -> None:
    # A VIEWER principal is a real identity without commercial analysis capability: the worker must
    # not acquire one by being configured.
    _provision(session, name="worker-viewer", role="VIEWER")
    monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "worker-viewer")

    authority = resolve_service_authority(session)

    assert authority.granted is False
    assert authority.refusal == SERVICE_AUTHORITY_NOT_GRANTED
    assert "analysis.query" in authority.detail


def test_an_analyst_service_principal_is_granted_and_names_itself(monkeypatch, session) -> None:
    _provision(session, name="worker-analyst", role="ANALYST")
    monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "worker-analyst")

    authority = resolve_service_authority(session)

    assert authority.granted is True
    assert authority.principal is not None
    assert authority.principal.name == "worker-analyst"
    assert authority.principal.auth_method == "service_identity"


def test_the_scan_refuses_to_enrich_without_an_authority(monkeypatch, session) -> None:
    """The whole point: no configuration means no provider call, and it is reported."""

    monkeypatch.delenv(SERVICE_PRINCIPAL_ENV, raising=False)
    calls: list[str] = []

    def _provider(**kwargs):
        calls.append("called")
        return DeepSeekCallResult(status="success", answer="should not happen")

    result = scan_monitoring_conditions(
        session,
        now_utc=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
        enrich_with_llm=True,
        max_llm_enrichments=3,
        provider_call=_provider,
    )

    assert calls == []
    assert result["llm_enrichment_refused"] == SERVICE_AUTHORITY_NOT_CONFIGURED
    assert result["llm_enriched_count"] == 0
    # The refusal is an operational event, recorded rather than silent.
    actions = [row.action for row in session.query(AuditEventRecord).all()]
    assert "monitoring.enrichment.refused" in actions


def test_the_scan_enriches_under_the_configured_service_principal(monkeypatch, session) -> None:
    _provision(session, name="worker-analyst", role="ANALYST")
    monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "worker-analyst")
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED", "false")
    authority = resolve_service_authority(session)
    assert authority.granted is True

    result = scan_monitoring_conditions(
        session,
        now_utc=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
        enrich_with_llm=True,
        max_llm_enrichments=0,
        service_authority=authority,
    )

    # No candidates in an empty runtime: the point here is that the authority is accepted and the
    # scan does not report a refusal when one is granted.
    assert result["llm_enrichment_refused"] == ""
    assert "llm_enrichment_refusal_detail" in result


def test_a_user_identity_cannot_masquerade_as_the_service_principal(monkeypatch, session) -> None:
    """A human identity named in the worker configuration is refused, never granted."""

    _provision(session, name="alice-analyst", role="ANALYST", principal_type="USER")
    monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "alice-analyst")

    authority = resolve_service_authority(session)

    assert authority.granted is False
    assert authority.refusal == SERVICE_AUTHORITY_HUMAN_PRINCIPAL
    assert "SERVICE" in authority.detail


def test_the_boundary_refuses_a_missing_actor_before_any_credential_is_loaded(
    monkeypatch, session
) -> None:
    now = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    _provision(session, name="worker-analyst", role="ANALYST")
    monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "worker-analyst")
    alert = _persisted_alert(session, now)

    result = enrich_monitoring_alert(
        session,
        alert,
        now_utc=now,
        api_key_loader=_forbidden_key_loader,
        provider_call=_forbidden_provider_call,
    )

    assert result.status == ENRICHMENT_AUTHORITY_REFUSED
    assert result.error_code == SERVICE_AUTHORITY_ACTOR_MISSING
    # A refusal is not an attempt: no alert mutation, and the refusal is auditable.
    assert alert.llm_status == "pending"
    assert alert.llm_last_attempt_at_utc is None
    audits = _audit_rows(session, "monitoring.enrichment.refused")
    assert len(audits) == 1
    assert audits[0].outcome == "denied"
    assert SERVICE_AUTHORITY_ACTOR_MISSING in audits[0].detail


def test_the_boundary_refuses_an_actor_that_is_not_the_persisted_identity(
    monkeypatch, session
) -> None:
    now = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    row = _provision(session, name="worker-analyst", role="ANALYST")
    monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "worker-analyst")
    alert = _persisted_alert(session, now)

    forged_id = AuthenticatedPrincipal(
        principal_id="service:forged",
        name=row.name,
        principal_type="SERVICE",
        role="ANALYST",
        status="ACTIVE",
        roles=("ANALYST",),
        auth_method="service_identity",
    )
    forged_type = AuthenticatedPrincipal(
        principal_id=row.principal_id,
        name=row.name,
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        roles=("ANALYST",),
        auth_method="identity_key",
    )

    for actor in (forged_id, forged_type):
        result = enrich_monitoring_alert(
            session,
            alert,
            now_utc=now,
            actor=actor,
            api_key_loader=_forbidden_key_loader,
            provider_call=_forbidden_provider_call,
        )
        assert result.status == ENRICHMENT_AUTHORITY_REFUSED
        assert result.error_code == SERVICE_AUTHORITY_ACTOR_MISMATCH

    assert alert.llm_status == "pending"
    assert len(_audit_rows(session, "monitoring.enrichment.refused")) == 2


def test_a_revocation_after_the_scan_resolved_the_authority_refuses_at_the_boundary(
    monkeypatch, tmp_path
) -> None:
    """The scan gate is only a snapshot: the boundary re-reads, so revocation takes effect.

    The worker session keeps loaded rows across commits (``expire_on_commit=False``), which is
    exactly the state in which a cached identity row would hide a revocation.
    """

    now = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'revocation.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as worker:
        row = _provision(worker, name="worker-analyst", role="ANALYST")
        monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "worker-analyst")
        granted = resolve_service_authority(worker)
        assert granted.granted is True
        alert = _persisted_alert(worker, now)

        with Session(engine) as revoker:
            persisted = revoker.get(IdentityPrincipalRecord, row.principal_id)
            persisted.status = "DISABLED"
            revoker.commit()

        result = scan_monitoring_conditions(
            worker,
            now_utc=now,
            enrich_with_llm=True,
            max_llm_enrichments=3,
            api_key_loader=_forbidden_key_loader,
            provider_call=_forbidden_provider_call,
            service_authority=granted,
        )

        assert result["llm_enriched_count"] == 0
        assert result["llm_enrichment_refused"] == SERVICE_AUTHORITY_INACTIVE_PRINCIPAL
        assert "provider boundary" in result["llm_enrichment_refusal_detail"]
        assert alert.llm_status == "pending"
        assert alert.llm_last_attempt_at_utc is None
        audits = _audit_rows(worker, "monitoring.enrichment.refused")
        assert len(audits) == 1
        assert "DISABLED" in audits[0].detail


def test_a_downgrade_after_the_scan_resolved_the_authority_refuses_at_the_boundary(
    monkeypatch, tmp_path
) -> None:
    now = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'downgrade.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as worker:
        row = _provision(worker, name="worker-analyst", role="ANALYST")
        monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "worker-analyst")
        granted = resolve_service_authority(worker)
        assert granted.granted is True
        alert = _persisted_alert(worker, now)

        with Session(engine) as revoker:
            persisted = revoker.get(IdentityPrincipalRecord, row.principal_id)
            persisted.role = "VIEWER"
            persisted.roles = ["VIEWER"]
            revoker.commit()

        result = scan_monitoring_conditions(
            worker,
            now_utc=now,
            enrich_with_llm=True,
            max_llm_enrichments=3,
            api_key_loader=_forbidden_key_loader,
            provider_call=_forbidden_provider_call,
            service_authority=granted,
        )

        assert result["llm_enriched_count"] == 0
        assert result["llm_enrichment_refused"] == SERVICE_AUTHORITY_NOT_GRANTED
        assert alert.llm_status == "pending"
        audits = _audit_rows(worker, "monitoring.enrichment.refused")
        assert len(audits) == 1
        assert "analysis.query" in audits[0].detail


def test_a_forged_granted_authority_cannot_spend_a_credential(monkeypatch, session) -> None:
    """A granted ServiceAuthority dataclass is a claim, not a grant: the boundary re-reads."""

    now = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    _provision(session, name="worker-analyst", role="ANALYST")
    monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "worker-analyst")
    _failed_ingestion_run(session, now)
    forged = ServiceAuthority(
        principal=AuthenticatedPrincipal(
            principal_id="service:forged",
            name="worker-analyst",
            principal_type="SERVICE",
            role="ADMIN",
            status="ACTIVE",
            roles=("ADMIN",),
            auth_method="service_identity",
        ),
        refusal="",
        detail="",
    )

    result = scan_monitoring_conditions(
        session,
        now_utc=now,
        enrich_with_llm=True,
        max_llm_enrichments=3,
        api_key_loader=_forbidden_key_loader,
        provider_call=_forbidden_provider_call,
        service_authority=forged,
    )

    assert result["llm_enriched_count"] == 0
    assert result["llm_enrichment_refused"] == SERVICE_AUTHORITY_ACTOR_MISMATCH
    alert = session.query(MonitoringAlertRecord).one()
    assert alert.llm_status == "pending"
    assert alert.llm_last_attempt_at_utc is None
    # One refusal per scan: the same condition applies to every remaining pending alert.
    assert len(_audit_rows(session, "monitoring.enrichment.refused")) == 1


def test_a_provisioned_least_privilege_scan_attributes_its_provider_call(
    monkeypatch, session
) -> None:
    now = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    row = _provision(session, name="worker-analyst", role="ANALYST", data_scopes=[])
    monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "worker-analyst")
    _failed_ingestion_run(session, now)
    calls: list[dict] = []

    def provider_call(**kwargs) -> DeepSeekCallResult:
        calls.append(kwargs)
        return DeepSeekCallResult(
            status="success",
            content='{"summary_en":"Source check.","summary_zh_cn":"检查数据源。"}',
        )

    result = scan_monitoring_conditions(
        session,
        now_utc=now,
        enrich_with_llm=True,
        max_llm_enrichments=3,
        api_key_loader=lambda _provider: "test-key",
        provider_call=provider_call,
    )

    assert result["llm_enriched_count"] == 1
    assert result["llm_enrichment_refused"] == ""
    assert len(calls) == 1
    assert row.data_scopes == []
    alert = session.query(MonitoringAlertRecord).one()
    assert alert.llm_status == "success"
    assert _audit_rows(session, "monitoring.enrichment.refused") == []
    audits = _audit_rows(session, "monitoring.enrichment.provider_call")
    assert len(audits) == 1
    assert audits[0].principal == "worker-analyst"
    assert audits[0].outcome == "success"
    assert row.principal_id in audits[0].detail
    assert "role=ANALYST" in audits[0].detail


def test_the_boundary_grants_from_the_persisted_row_not_the_dataclass_claim(
    monkeypatch, session
) -> None:
    """An actor claiming ADMIN on the right identity does not escalate: the row grants ANALYST."""

    now = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    row = _provision(session, name="worker-analyst", role="ANALYST")
    monkeypatch.setenv(SERVICE_PRINCIPAL_ENV, "worker-analyst")
    alert = _persisted_alert(session, now)
    escalated = AuthenticatedPrincipal(
        principal_id=row.principal_id,
        name=row.name,
        principal_type="SERVICE",
        role="ADMIN",
        status="ACTIVE",
        roles=("ADMIN",),
        auth_method="service_identity",
    )

    result = enrich_monitoring_alert(
        session,
        alert,
        now_utc=now,
        actor=escalated,
        api_key_loader=lambda _provider: "test-key",
        provider_call=lambda **_kwargs: DeepSeekCallResult(
            status="success",
            content='{"summary_en":"ok","summary_zh_cn":"好"}',
        ),
    )

    assert result.status == "success"
    audits = _audit_rows(session, "monitoring.enrichment.provider_call")
    assert len(audits) == 1
    assert audits[0].principal == "worker-analyst"
    assert "role=ANALYST" in audits[0].detail


def test_the_worker_script_reports_the_refusal_instead_of_calling_out() -> None:
    """"A worker that cannot act says so" is a source-level contract too."""

    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "scripts" / "ops" / "run_monitoring_worker.py"
    ).read_text(encoding="utf-8")

    assert "resolve_service_authority" in source
    assert '"enrichment": "refused"' in source
    assert "service_authority=authority" in source
