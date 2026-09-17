"""Architecture V2 finding C8 - AI runs under the caller's own authority.

``02_ARCHITECTURE_CONSTITUTION.md`` rule 22 and
``08_DECISION_APPLICATION_AI.md`` section 4: AI inherits the invoking user's
authority, is re-authorised per call, and its runs are recorded as observable
actions. Before this slice, ``POST /api/monitoring/alerts/{alert_id}/analysis``
loaded the backend provider credential and returned model output composed from
commercial evidence with no principal, scope or entitlement decision anywhere in
the call, and the analysis provider path checked entitlement on the payload but
not on the invocation.

These tests pin the decision at both levels: the route registry classifies the
path as policy-gated (not a read), and the handler refuses a caller whose own
authority does not include analysis - without ever reaching the provider.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.dependencies.ai_authority import (
    AI_AUTHORITY_DENIED,
    AI_AUTHORITY_PERMISSION,
    ai_authority_denial,
    ai_caller,
)
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord, MonitoringAlertRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.llm import DeepSeekCallResult
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    Role,
    legacy_public_token_principal,
)
from eurogas_nexus.security.permissions import Permission, permission_for_path

PUBLIC_TOKEN = "test-public-api-token"

ANALYSIS_PATH = "/api/monitoring/alerts/alert-test/analysis"


def _principal(role: Role, *, principal_type: str = "USER") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=f"principal-{role.value.lower()}",
        name=role.value.title(),
        principal_type=principal_type,
        role=role.value,
        status="ACTIVE",
        data_scopes=("ENTSOG",),
        roles=(role.value,),
    )


def _alert() -> MonitoringAlertRecord:
    now = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
    return MonitoringAlertRecord(
        alert_id="alert-test",
        fingerprint="test:alert",
        category="data_source",
        alert_type="ingestion_failed",
        severity="warning",
        status="open",
        title_en="ENTSOG ingestion failed",
        title_zh_cn="ENTSOG 数据更新失败",
        message_en="Latest run failed.",
        message_zh_cn="最近一次更新失败。",
        entity_type="data_source",
        entity_id="ENTSOG",
        event_time_utc=now,
        detected_at_utc=now,
        updated_at_utc=now,
        acknowledged_at_utc=None,
        resolved_at_utc=None,
        occurrence_count=1,
        evidence_snapshot={"run_id": "run-test"},
        source_refs=["ingestion-run:run-test"],
        warnings=[],
        llm_provider_id="DEEPSEEK",
        llm_status="pending",
        llm_summary_en=None,
        llm_summary_zh_cn=None,
        llm_last_attempt_at_utc=None,
        simulated=False,
        human_review_required=True,
    )


def _prepare_db(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'ai_authority.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(_alert())
        session.add(
            MarketObservationRecord(
                observation_id="m-1",
                market_venue="ENTSOG",
                product="NBP Day-Ahead",
                price=31.0,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=now,
                period_end_utc=now,
                observed_at_utc=now,
                source_system="ENTSOG",
                source_reference="test:ENTSOG",
                source_record_id="ENTSOG-1",
                freshness="live",
                quality_score=0.9,
                research_only=True,
                metadata_json={"hub": "NBP"},
            )
        )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)


def _bearer(session: Session, *, name: str, roles: list[str], scopes: list[str]) -> str:
    row = create_identity_principal(
        session,
        name=name,
        display_name=name.title(),
        role=roles[0],
        data_scopes=scopes,
    )
    row.roles = list(roles)
    _key, bearer = create_identity_api_key(session, row.principal_id, display_name="ai-authority")
    return bearer


def _headers(bearer: str | None = None) -> dict[str, str]:
    headers = {"X-Eurogas-Api-Key": PUBLIC_TOKEN}
    if bearer:
        headers["X-Eurogas-Identity"] = bearer
    return headers


def test_live_analysis_is_a_policy_gated_path_not_a_monitoring_read() -> None:
    """The alert analysis route is GOVERNED; the rest of `/api/monitoring/` stays READ."""

    assert permission_for_path("/api/monitoring/alerts/alert-test/analysis") is Permission.GOVERNED
    assert permission_for_path("/api/monitoring/alerts") is Permission.READ
    assert permission_for_path("/api/monitoring/summary") is Permission.READ


def test_ai_authority_denies_identities_without_analysis_authority() -> None:
    """A user needs the analysis capability; administration is not a super-user."""

    assert ai_authority_denial(_principal(Role.ANALYST)) == ""
    assert ai_authority_denial(_principal(Role.OPERATOR)) != ""
    assert ai_authority_denial(_principal(Role.VIEWER)) != ""
    assert ai_authority_denial(_principal(Role.REVIEWER)) != ""
    # Platform administration holds no commercial analysis capability (V2 section 7).
    assert ai_authority_denial(_principal(Role.ADMIN)) != ""
    # A service principal is not a user identity and holds no capability of its own.
    assert ai_authority_denial(_principal(Role.ANALYST, principal_type="SERVICE")) != ""
    # The documented single-trust-domain deployment token keeps its posture: bounding
    # it is finding C5, which this check neither widens nor narrows.
    assert ai_authority_denial(legacy_public_token_principal()) == ""
    assert AI_AUTHORITY_PERMISSION.value == "analysis.query"


def test_viewer_cannot_spend_a_provider_credential_on_alert_analysis(
    tmp_path,
    monkeypatch,
) -> None:
    """Every layer refuses before the provider is reached, and the AI gate is load-bearing.

    Three identities reach three different layers, which is the point of the layered
    check: a viewer is stopped by the route's role floor, an administration-only
    identity by the commercial-data boundary, and an administrator who *also* holds a
    read-only commercial role by the AI authority gate itself - rank and a commercial
    read do not add up to authority to spend a provider credential.
    """

    _prepare_db(tmp_path, monkeypatch)
    url = f"sqlite+pysqlite:///{(tmp_path / 'ai_authority.sqlite').as_posix()}"
    with Session(create_engine(url, future=True)) as session:
        viewer_bearer = _bearer(session, name="ai-viewer", roles=["VIEWER"], scopes=["ENTSOG"])
        admin_bearer = _bearer(session, name="ai-admin", roles=["ADMIN"], scopes=[])
        admin_viewer_bearer = _bearer(
            session,
            name="ai-admin-viewer",
            roles=["ADMIN", "VIEWER"],
            scopes=["ENTSOG"],
        )
        session.commit()

    calls: list[dict] = []
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.monitoring.load_provider_api_key",
        lambda _provider: "never-returned-test-key",
    )
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.monitoring.invoke_deepseek",
        lambda **kwargs: calls.append(kwargs)
        or DeepSeekCallResult(status="success", content="should not happen"),
    )
    client = TestClient(create_app(Settings(api_profile="release")))

    expected = {
        "viewer": "identity_role_forbidden",
        "administration-only": "commercial_access_not_granted",
        "administration plus read-only commercial role": AI_AUTHORITY_DENIED,
    }
    bearers = {
        "viewer": viewer_bearer,
        "administration-only": admin_bearer,
        "administration plus read-only commercial role": admin_viewer_bearer,
    }

    for label, bearer in bearers.items():
        response = client.post(
            ANALYSIS_PATH,
            json={"question": "What should the trader verify?", "language": "en"},
            headers=_headers(bearer),
        )
        assert response.status_code == 403, label
        detail = response.json()["detail"]
        assert detail["error"] == expected[label], (label, detail)
        if label == "administration plus read-only commercial role":
            assert detail["permission_required"] == "analysis.query"
            assert detail["principal_id"]

    # The refusals are complete: no provider credential was used and no model output
    # exists to leak.
    assert calls == []


def test_analyst_alert_analysis_runs_and_records_the_identity_it_ran_under(
    tmp_path,
    monkeypatch,
) -> None:
    """An entitled analyst still gets the answer, and the run names its actor."""

    _prepare_db(tmp_path, monkeypatch)
    url = f"sqlite+pysqlite:///{(tmp_path / 'ai_authority.sqlite').as_posix()}"
    with Session(create_engine(url, future=True)) as session:
        analyst_bearer = _bearer(
            session,
            name="ai-analyst",
            roles=["ANALYST"],
            scopes=["ENTSOG"],
        )
        session.commit()

    persisted: list[dict] = []
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.monitoring.load_provider_api_key",
        lambda _provider: "never-returned-test-key",
    )
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.monitoring._persist_analysis_run",
        lambda **kwargs: persisted.append(kwargs),
    )
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.monitoring.invoke_deepseek",
        lambda **_kwargs: DeepSeekCallResult(
            status="success",
            content="Check the ingestion endpoint and retry schedule.",
        ),
    )
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.post(
        ANALYSIS_PATH,
        json={"question": "What should the trader verify?", "language": "en"},
        headers=_headers(analyst_bearer),
    )

    assert response.status_code == 200
    assert response.json()["data"]["provider_status"] == "success"
    assert "never-returned-test-key" not in response.text

    # The run is an observable action: who ran it, under which authority.
    assert len(persisted) == 1
    actor = persisted[0]["actor"]
    assert actor["principal_id"].startswith("PRN-") or actor["principal_id"]
    assert actor["role"] == "ANALYST"
    assert actor["auth_method"]


def test_legacy_deployment_token_keeps_its_documented_ai_posture(tmp_path, monkeypatch) -> None:
    """The static deployment token is unchanged by this check (finding C5 is separate)."""

    _prepare_db(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.monitoring.load_provider_api_key",
        lambda _provider: "never-returned-test-key",
    )
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.monitoring.invoke_deepseek",
        lambda **_kwargs: DeepSeekCallResult(status="success", content="ok"),
    )
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.post(
        ANALYSIS_PATH,
        json={"question": "What should the trader verify?", "language": "en"},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.json()["data"]["provider_status"] == "success"


def test_analysis_provider_path_checks_the_invocation_not_only_the_payload(
    monkeypatch,
) -> None:
    """`/api/analysis/query` refuses an unentitled caller's authority before the call."""

    from eurogas_nexus.api.routes.public import analysis as analysis_route
    from eurogas_nexus.domain.analysis import AnalysisRequest, AnalysisSnapshot

    class _Settings:
        llm_external_provider_enabled = True

    monkeypatch.setattr(
        "eurogas_nexus.core.config.get_settings",
        lambda: _Settings(),
    )

    snapshot = AnalysisSnapshot(
        snapshot_id="snapshot-test",
        source="runtime-postgresql",
        created_at_utc=datetime(2026, 7, 22, 8, 0, tzinfo=UTC),
        ontology={},
    )
    body = AnalysisRequest(question="What is the current spread?", invoke_provider=True)

    for principal, expected in (
        (_principal(Role.VIEWER), "AI_AUTHORITY_DENIED"),
        (_principal(Role.ADMIN), "AI_AUTHORITY_DENIED"),
        (_principal(Role.ANALYST), "LLM_PROVIDER_CREDENTIAL_MISSING"),
    ):
        text, status = analysis_route._maybe_invoke_provider(
            body,
            snapshot,
            request_id="test-request",
            principal=principal,
        )
        assert text is None
        assert status == expected, principal.role

    # Without a principal the helper keeps its previous behaviour: the callers that
    # have one pass it, and this test pins that the gate is not silently skipped.
    _text, unstated = analysis_route._maybe_invoke_provider(body, snapshot)
    assert unstated != "AI_AUTHORITY_DENIED"


def test_ai_caller_prefers_the_authenticated_identity() -> None:
    """The invocation runs as the resolved identity, not as a service fallback."""

    class _State:
        identity = _principal(Role.ANALYST)

    class _Request:
        state = _State()

    assert ai_caller(_Request()).principal_id == "principal-analyst"

    class _AnonymousState:
        identity = None

    class _AnonymousRequest:
        state = _AnonymousState()

    assert ai_caller(_AnonymousRequest()).principal_id == legacy_public_token_principal().principal_id


if __name__ == "__main__":  # pragma: no cover - manual invocation guard
    raise SystemExit(pytest.main([__file__]))
