"""API/application tests for the shadow research runtime."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.shadow_runtime import (
    create_shadow_monitor,
    run_due_shadow_evaluations,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    MarketObservationRecord,
    StrategyShadowAlertRecord,
)
from eurogas_nexus.db.repositories import shadow as shadow_repository
from eurogas_nexus.db.repositories import strategy_registry
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.strategy_lab.registry import (
    StrategyComponentSpec,
    StrategyVersionDefinition,
)

PUBLIC_TOKEN = "test-public-api-token"


def _configure_db(tmp_path, monkeypatch) -> tuple[str, TestClient]:
    db_path = tmp_path / "shadow.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url, TestClient(create_app())


def _create_version(
    session: Session,
    *,
    strategy_id: str = "shadow-strategy",
    freeze: bool = True,
) -> str:
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    strategy_registry.create_strategy(
        session,
        strategy_id=strategy_id,
        name="Shadow strategy",
        description="",
        created_by="operator",
        now_utc=now,
    )
    definition = StrategyVersionDefinition(
        components=[
            StrategyComponentSpec(
                component_id="c1",
                component_type="OCM_VS_DAY_AHEAD",
                hubs=["NBP"],
                extension_json={
                    "weight": 1.0,
                    "day_ahead_price_names": ["SAP"],
                    "intraday_price_names": ["ICE_OCM"],
                    "positive_spread_threshold_gbp_mwh": 0.0,
                    "negative_spread_threshold_gbp_mwh": 0.0,
                    "target_bar_minutes": 5,
                    "time_window_start": "05:00",
                    "time_window_end": "05:30",
                },
            )
        ]
    )
    version = strategy_registry.create_strategy_version(
        session,
        strategy_id=strategy_id,
        definition=definition,
        hypothesis="",
        created_by="operator",
        now_utc=now,
        definition_overrides={
            "strategy_name": "Shadow strategy",
            "run_mode": "BACKTEST",
            "resource_contexts": [
                {
                    "resource_id": "res-1",
                    "available_quantity_mwh_per_day": 100.0,
                    "all_in_cost_gbp_mwh": 20.0,
                }
            ],
            "price_observations": [],
            "existing_shadow_pnl_gbp": 0.0,
            "economic_assumptions": {
                "fill_price_policy": "NEXT_ELIGIBLE",
                "missing_data_policy": "FAIL",
                "cost_components": [],
            },
        },
    )
    if freeze:
        strategy_registry.freeze_strategy_version(
            session,
            strategy_version_id=version.strategy_version_id,
            frozen_by="operator",
            now_utc=now,
        )
    session.commit()
    return version.strategy_version_id


def _seed_observations(
    session: Session,
    *,
    observed_at: datetime | None = None,
    ice_age_hours: float = 0.5,
    sap_age_hours: float = 0.5,
) -> None:
    observed = observed_at or datetime(2026, 7, 1, 9, 30, tzinfo=UTC)
    ice = observed - timedelta(hours=ice_age_hours)
    sap = observed - timedelta(hours=sap_age_hours)
    for oid, source, venue, price, tenor, at in [
        ("ice", "ICE_OCM_Sim", "ICE OCM", 30.0, "within-day", ice),
        ("sap", "SAP_Sim", "SAP", 25.0, "day-ahead", sap),
    ]:
        session.add(
            MarketObservationRecord(
                observation_id=f"shadow-{oid}",
                market_venue=venue,
                product=f"NBP {oid}",
                price=price,
                unit="GBP/MWh",
                currency="GBP",
                period_start_utc=at,
                period_end_utc=at + timedelta(days=1),
                observed_at_utc=at,
                source_system=source,
                source_reference=f"shadow:{oid}",
                freshness="simulated_live",
                quality_score=0.6,
                research_only=True,
                metadata_json={
                    "hub": "NBP",
                    "tenor": tenor,
                    "simulated": True,
                },
            )
        )
    session.flush()


def _monitor_payload(version_id: str) -> dict:
    return {
        "strategy_version_id": version_id,
        "schedule": {"type": "INTERVAL", "interval_seconds": 3600, "missed_policy": "SKIP"},
    }


def test_draft_version_cannot_activate_and_frozen_can(tmp_path, monkeypatch) -> None:
    database_url, client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        draft_id = _create_version(session, freeze=False)
        frozen_id = _create_version(
            session, strategy_id="shadow-frozen", freeze=True
        )

    draft = client.post("/api/shadow-monitors", json=_monitor_payload(draft_id))
    assert draft.status_code == 422
    assert draft.json()["detail"]["code"] == "shadow_activation_blocked"

    frozen = client.post("/api/shadow-monitors", json=_monitor_payload(frozen_id))
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["data"]["state"] == "ACTIVE"
    monitor_id = frozen.json()["data"]["shadow_monitor_id"]

    fetched = client.get(f"/api/shadow-monitors/{monitor_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["state"] == "ACTIVE"


def test_pause_resume_retire_lifecycle(tmp_path, monkeypatch) -> None:
    database_url, client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        version_id = _create_version(session)
    created = client.post("/api/shadow-monitors", json=_monitor_payload(version_id))
    monitor_id = created.json()["data"]["shadow_monitor_id"]

    assert client.post(f"/api/shadow-monitors/{monitor_id}/pause").status_code == 200
    assert client.get(f"/api/shadow-monitors/{monitor_id}").json()["data"]["state"] == "PAUSED"
    assert client.post(f"/api/shadow-monitors/{monitor_id}/resume").status_code == 200
    assert client.get(f"/api/shadow-monitors/{monitor_id}").json()["data"]["state"] == "ACTIVE"
    assert client.post(f"/api/shadow-monitors/{monitor_id}/retire").status_code == 200
    assert client.get(f"/api/shadow-monitors/{monitor_id}").json()["data"]["state"] == "RETIRED"


def test_due_monitor_evaluates_once_and_persists_candidate(tmp_path, monkeypatch) -> None:
    database_url, _client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        version_id = _create_version(session)
        _seed_observations(session, observed_at=now)
        payload = create_shadow_monitor(
            session,
            strategy_version_id=version_id,
            baseline_run_id=None,
            schedule_json={"type": "INTERVAL", "interval_seconds": 3600, "missed_policy": "SKIP"},
            created_by="operator",
            now_utc=now,
            activate=True,
        )
        monitor_id = payload["shadow_monitor_id"]
        monitor = shadow_repository.get_monitor(session, monitor_id)
        monitor.next_evaluation_at_utc = now - timedelta(seconds=1)
        session.flush()

        first = run_due_shadow_evaluations(session, now_utc=now)
        second = run_due_shadow_evaluations(session, now_utc=now)
        session.commit()

    assert first["claimed_count"] == 1
    assert first["completed_count"] == 1
    assert second["claimed_count"] == 0
    assert second["duplicate_claim_count"] == 0

    with Session(engine) as session:
        evaluations = shadow_repository.list_evaluations(session, monitor_id=monitor_id)
        assert len(evaluations) == 1
        assert evaluations[0]["state"] == "COMPLETED_WITH_WARNINGS"
        assert evaluations[0]["candidate_id"] is not None
        assert evaluations[0]["decision_time_utc"] is not None
        assert evaluations[0]["snapshot_id"] is not None


def test_paused_and_future_monitors_are_not_evaluated(tmp_path, monkeypatch) -> None:
    database_url, _client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        version_id = _create_version(session)
        payload = create_shadow_monitor(
            session,
            strategy_version_id=version_id,
            baseline_run_id=None,
            schedule_json={"type": "INTERVAL", "interval_seconds": 3600, "missed_policy": "SKIP"},
            created_by="operator",
            now_utc=now,
            activate=True,
        )
        monitor_id = payload["shadow_monitor_id"]
        monitor = shadow_repository.get_monitor(session, monitor_id)
        next_at = monitor.next_evaluation_at_utc
        if next_at.tzinfo is None:
            next_at = next_at.replace(tzinfo=UTC)
        assert next_at > now
        assert run_due_shadow_evaluations(session, now_utc=now)["claimed_count"] == 0

        shadow_repository.pause_monitor(session, monitor_id=monitor_id, now_utc=now)
        monitor.next_evaluation_at_utc = now - timedelta(seconds=1)
        session.flush()
        assert run_due_shadow_evaluations(session, now_utc=now)["claimed_count"] == 0


def test_stale_required_data_blocks_without_candidate(tmp_path, monkeypatch) -> None:
    database_url, _client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        version_id = _create_version(session)
        _seed_observations(session, observed_at=now, ice_age_hours=5, sap_age_hours=5)
        payload = create_shadow_monitor(
            session,
            strategy_version_id=version_id,
            baseline_run_id=None,
            schedule_json={"type": "INTERVAL", "interval_seconds": 3600, "missed_policy": "SKIP"},
            created_by="operator",
            now_utc=now,
            activate=True,
        )
        monitor = shadow_repository.get_monitor(session, payload["shadow_monitor_id"])
        monitor.next_evaluation_at_utc = now - timedelta(seconds=1)
        session.flush()
        run_due_shadow_evaluations(session, now_utc=now)

        evaluations = shadow_repository.list_evaluations(
            session, monitor_id=monitor.shadow_monitor_id
        )
    assert evaluations[0]["state"] == "BLOCKED"
    assert evaluations[0]["candidate_id"] is None
    assert any(item.startswith("DATA_STALE") for item in evaluations[0]["missing_inputs"])


def test_alert_acknowledge_and_dedupe(tmp_path, monkeypatch) -> None:
    database_url, client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        version_id = _create_version(session)
        payload = create_shadow_monitor(
            session,
            strategy_version_id=version_id,
            baseline_run_id=None,
            schedule_json={"type": "INTERVAL", "interval_seconds": 3600, "missed_policy": "SKIP"},
            created_by="operator",
            now_utc=now,
            activate=True,
        )
        monitor = shadow_repository.get_monitor(session, payload["shadow_monitor_id"])
        first, created = shadow_repository.upsert_alert(
            session,
            monitor_id=monitor.shadow_monitor_id,
            evaluation_id=None,
            alert_type="DATA_STALE",
            severity="WARNING",
            fingerprint=f"{monitor.shadow_monitor_id}|DATA_STALE|ice",
            summary="ICE stale",
            evidence_refs=[],
            now_utc=now,
        )
        second, created_again = shadow_repository.upsert_alert(
            session,
            monitor_id=monitor.shadow_monitor_id,
            evaluation_id=None,
            alert_type="DATA_STALE",
            severity="WARNING",
            fingerprint=f"{monitor.shadow_monitor_id}|DATA_STALE|ice",
            summary="ICE stale",
            evidence_refs=[],
            now_utc=now,
        )
        assert created is True
        assert created_again is False
        assert first.alert_id == second.alert_id
        assert second.occurrence_count == 2
        alert_id = first.alert_id
        session.commit()

    acknowledged = client.post(
        f"/api/shadow-alerts/{alert_id}/acknowledge", json={"actor": "operator"}
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["data"]["state"] == "ACKNOWLEDGED"


def test_shadow_runtime_status_and_drift_surface(tmp_path, monkeypatch) -> None:
    database_url, client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        version_id = _create_version(session)
        payload = create_shadow_monitor(
            session,
            strategy_version_id=version_id,
            baseline_run_id=None,
            schedule_json={"type": "INTERVAL", "interval_seconds": 3600, "missed_policy": "SKIP"},
            created_by="operator",
            now_utc=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
            activate=True,
        )
        monitor_id = payload["shadow_monitor_id"]
        session.commit()
    status = client.get("/api/shadow-runtime/status")
    assert status.status_code == 200
    drift = client.get(f"/api/shadow-monitors/{monitor_id}/drift")
    assert drift.status_code == 200


def test_stale_running_evaluation_recovers_as_failed(tmp_path, monkeypatch) -> None:
    database_url, _client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        version_id = _create_version(session)
        payload = create_shadow_monitor(
            session,
            strategy_version_id=version_id,
            baseline_run_id=None,
            schedule_json={"type": "INTERVAL", "interval_seconds": 3600, "missed_policy": "SKIP"},
            created_by="operator",
            now_utc=now,
            activate=True,
        )
        monitor = shadow_repository.get_monitor(session, payload["shadow_monitor_id"])
        monitor_id = monitor.shadow_monitor_id
        evaluation = shadow_repository.create_evaluation(
            session,
            monitor_id=monitor.shadow_monitor_id,
            strategy_version_id=version_id,
            scheduled_for_utc=now,
            now_utc=now - timedelta(seconds=600),
        )
        evaluation.started_at_utc = now - timedelta(seconds=600)
        session.flush()
        from eurogas_nexus.application.shadow_runtime import recover_stale_evaluations

        recovered = recover_stale_evaluations(session, now_utc=now)
        session.commit()
    assert recovered == 1
    with Session(engine) as session:
        rows = shadow_repository.list_evaluations(session, monitor_id=monitor_id)
    assert rows[0]["state"] == "FAILED"


# --- acknowledgement attribution (Architecture V2 C13 rule) -----------------


def _identity_headers(bearer: str) -> dict[str, str]:
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


def _analyst_bearer(session: Session, *, name: str) -> tuple[str, str]:
    row = create_identity_principal(
        session,
        name=name,
        display_name=name.title(),
        role="ANALYST",
        data_scopes=["*"],
    )
    _key, bearer = create_identity_api_key(session, row.principal_id, display_name="shadow-ack")
    return row.principal_id, bearer


def _seed_shadow_alert(session: Session, *, fingerprint_suffix: str = "ice") -> str:
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    version_id = _create_version(session)
    payload = create_shadow_monitor(
        session,
        strategy_version_id=version_id,
        baseline_run_id=None,
        schedule_json={"type": "INTERVAL", "interval_seconds": 3600, "missed_policy": "SKIP"},
        created_by="operator",
        now_utc=now,
        activate=True,
    )
    monitor = shadow_repository.get_monitor(session, payload["shadow_monitor_id"])
    alert, _created = shadow_repository.upsert_alert(
        session,
        monitor_id=monitor.shadow_monitor_id,
        evaluation_id=None,
        alert_type="DATA_STALE",
        severity="WARNING",
        fingerprint=f"{monitor.shadow_monitor_id}|DATA_STALE|{fingerprint_suffix}",
        summary="ICE stale",
        evidence_refs=[],
        now_utc=now,
    )
    return alert.alert_id


def _acknowledgement_audit_rows(database_url: str) -> list[AuditEventRecord]:
    with Session(create_engine(database_url, future=True)) as session:
        return (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.action == "shadow.alert.acknowledge")
            .all()
        )


def test_shadow_acknowledgement_records_the_authenticated_principal_not_body_actor(
    tmp_path,
    monkeypatch,
) -> None:
    """The body's ``actor`` is accepted for compatibility and never believed (finding C13)."""

    database_url, client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        alert_id = _seed_shadow_alert(session)
        analyst_id, analyst_bearer = _analyst_bearer(session, name="shadow-analyst")
        session.commit()

    response = client.post(
        f"/api/shadow-alerts/{alert_id}/acknowledge",
        json={"actor": "spoofed-name"},
        headers=_identity_headers(analyst_bearer),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "ACKNOWLEDGED"
    assert response.json()["data"]["acknowledged_by"] == analyst_id
    assert response.json()["data"]["acknowledged_by"] != "spoofed-name"

    rows = _acknowledgement_audit_rows(database_url)
    assert len(rows) == 1
    assert rows[0].principal == analyst_id
    assert rows[0].resource == f"shadow_alert:{alert_id}"
    assert rows[0].correlation_id == response.headers["x-request-id"]


def test_shadow_repeat_acknowledgement_preserves_original_attribution(
    tmp_path,
    monkeypatch,
) -> None:
    database_url, client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        alert_id = _seed_shadow_alert(session, fingerprint_suffix="repeat")
        first_id, first_bearer = _analyst_bearer(session, name="shadow-first")
        _second_id, second_bearer = _analyst_bearer(session, name="shadow-second")
        session.commit()

    first = client.post(
        f"/api/shadow-alerts/{alert_id}/acknowledge",
        json={"actor": "first-name"},
        headers=_identity_headers(first_bearer),
    )
    assert first.status_code == 200

    repeat = client.post(
        f"/api/shadow-alerts/{alert_id}/acknowledge",
        json={"actor": "second-name"},
        headers=_identity_headers(second_bearer),
    )
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["data"]["state"] == "ACKNOWLEDGED"
    assert repeat.json()["data"]["acknowledged_by"] == first_id
    assert (
        repeat.json()["data"]["acknowledged_at_utc"]
        == first.json()["data"]["acknowledged_at_utc"]
    )
    assert len(_acknowledgement_audit_rows(database_url)) == 1


def test_resolved_shadow_alert_cannot_be_acknowledged(tmp_path, monkeypatch) -> None:
    database_url, client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        alert_id = _seed_shadow_alert(session, fingerprint_suffix="resolved")
        _analyst_id, analyst_bearer = _analyst_bearer(session, name="shadow-resolved")
        row = session.get(StrategyShadowAlertRecord, alert_id)
        row.state = "RESOLVED"
        row.resolved_at_utc = datetime(2026, 7, 1, 11, 0, tzinfo=UTC)
        session.commit()

    response = client.post(
        f"/api/shadow-alerts/{alert_id}/acknowledge",
        json={"actor": "operator"},
        headers=_identity_headers(analyst_bearer),
    )

    assert response.status_code == 404
    with Session(engine) as session:
        row = session.get(StrategyShadowAlertRecord, alert_id)
        assert row.state == "RESOLVED"
        assert row.acknowledged_by is None
        assert row.acknowledged_at_utc is None
    assert _acknowledgement_audit_rows(database_url) == []


def test_missing_shadow_alert_is_a_404_without_an_audit_record(tmp_path, monkeypatch) -> None:
    database_url, client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        _analyst_id, analyst_bearer = _analyst_bearer(session, name="shadow-missing")
        session.commit()

    response = client.post(
        "/api/shadow-alerts/shadow-alert-absent/acknowledge",
        json={"actor": "operator"},
        headers=_identity_headers(analyst_bearer),
    )

    assert response.status_code == 404
    assert _acknowledgement_audit_rows(database_url) == []


def test_shadow_acknowledgement_rolls_back_when_the_audit_cannot_be_written(
    tmp_path,
    monkeypatch,
) -> None:
    database_url, _client = _configure_db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        alert_id = _seed_shadow_alert(session, fingerprint_suffix="rollback")
        _analyst_id, analyst_bearer = _analyst_bearer(session, name="shadow-rollback")
        session.commit()

    def _fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit trail unavailable")

    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.shadow._record_acknowledgement_audit",
        _fail_audit,
    )
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        f"/api/shadow-alerts/{alert_id}/acknowledge",
        json={"actor": "operator"},
        headers=_identity_headers(analyst_bearer),
    )

    assert response.status_code == 500
    with Session(engine) as session:
        row = session.get(StrategyShadowAlertRecord, alert_id)
        assert row.state == "OPEN"
        assert row.acknowledged_by is None
        assert row.acknowledged_at_utc is None
    assert _acknowledgement_audit_rows(database_url) == []
