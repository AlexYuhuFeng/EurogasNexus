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

from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.application.service_identity import (
    SERVICE_AUTHORITY_INACTIVE_PRINCIPAL,
    SERVICE_AUTHORITY_NOT_CONFIGURED,
    SERVICE_AUTHORITY_NOT_GRANTED,
    SERVICE_AUTHORITY_UNKNOWN_PRINCIPAL,
    SERVICE_PRINCIPAL_ENV,
    configured_service_principal_name,
    resolve_service_authority,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.identity import create_identity_principal
from eurogas_nexus.llm import DeepSeekCallResult


@pytest.fixture()
def session(tmp_path):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'worker.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as opened:
        yield opened


def _provision(session, *, name: str, role: str, status: str = "ACTIVE") -> None:
    row = create_identity_principal(
        session, name=name, display_name=name.title(), role=role, data_scopes=[]
    )
    if status != "ACTIVE":
        row.status = status
    session.commit()


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
    from eurogas_nexus.db.models import AuditEventRecord

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


def test_the_worker_script_reports_the_refusal_instead_of_calling_out() -> None:
    """"A worker that cannot act says so" is a source-level contract too."""

    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "scripts" / "ops" / "run_monitoring_worker.py"
    ).read_text(encoding="utf-8")

    assert "resolve_service_authority" in source
    assert '"enrichment": "refused"' in source
    assert "service_authority=authority" in source
