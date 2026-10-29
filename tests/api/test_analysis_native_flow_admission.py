"""RFC0005 volume admission on the actual analysis-snapshot loader.

The analysis, portfolio-report and glossary surfaces read
``AnalysisSnapshot.flow_observations``. These tests persist real SQLite rows and
call the route's actual ``_load_snapshot`` so the admission boundary is exercised
on the real query/loader path, not only on the pure helper. No LLM provider is
invoked.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public import analysis as analysis_module
from eurogas_nexus.application.physical_native_rates import serialize_native_rate
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FlowObservationRecord,
    StrategyRecord,
    StrategyRunRecord,
)
from eurogas_nexus.db.repositories.identity import create_identity_principal
from eurogas_nexus.ingestion.entsog_native_units import (
    NORMALIZER_VERSION,
    parse_entsog_native_rate,
)

_PERIOD_START = datetime(2026, 6, 1, tzinfo=UTC)
_PERIOD_END = datetime(2026, 6, 2, tzinfo=UTC)
_OBSERVED_AT = datetime(2026, 6, 1, 12, tzinfo=UTC)
_FORBIDDEN_NATIVE_MARKER = "secret-raw-value"
_DB_ENV_NAMES = (
    "RUNTIME_STORE_DATABASE_URL",
    "DATABASE_URL",
    "EUROGAS_NEXUS_DB_DSN",
    "EUROGAS_NEXUS_DATABASE_URL",
    "EUROGAS_NEXUS_RUNTIME_STORE_DATABASE_URL",
)
_ANALYSIS_BODY = {
    "question": "Summarize current TTF context",
    "task": "DB_INQUIRY",
    "invoke_provider": False,
}
_REPORT_BODY = {
    "title": "Current portfolio report",
    "invoke_provider": False,
}


def _database(monkeypatch, tmp_path, name: str):
    """Point the runtime store at a fresh full-metadata SQLite database."""

    database_url = f"sqlite+pysqlite:///{(tmp_path / f'{name}.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    for env_name in _DB_ENV_NAMES:
        if env_name != "RUNTIME_STORE_DATABASE_URL":
            monkeypatch.delenv(env_name, raising=False)
    return engine, database_url


def _native_rate(value_text: str, unit_text: str) -> dict[str, object]:
    return serialize_native_rate(parse_entsog_native_rate(value_text, unit_text))


def _flow_observation(**overrides) -> FlowObservationRecord:
    values = {
        "observation_id": "flow-1",
        "point_id": "point-1",
        "point_name": "Point 1",
        "direction": "entry",
        "kind": "actual",
        "flow_mcm_d": None,
        "period_start_utc": _PERIOD_START,
        "period_end_utc": _PERIOD_END,
        "observed_at_utc": _OBSERVED_AT,
        "source_system": "ENTSOG",
        "source_reference": "entsog-operationaldatas",
        "freshness": "live",
        "research_only": True,
    }
    values.update(overrides)
    return FlowObservationRecord(**values)


def _strategy_run(run_id: str, strategy_id: str, started_at: datetime) -> StrategyRunRecord:
    return StrategyRunRecord(
        run_id=run_id,
        strategy_id=strategy_id,
        run_mode="BACKTEST",
        status="SUCCEEDED",
        started_at_utc=started_at,
        input_snapshot={},
        result_snapshot={},
        source_refs=[],
        warnings=[],
        missing_inputs=[],
        research_only=True,
        human_review_required=True,
    )


def test_load_snapshot_retains_non_entsog_and_valid_native_volume(tmp_path, monkeypatch) -> None:
    engine, _ = _database(monkeypatch, tmp_path, "admitted-volume")
    native = _native_rate("123456789.123456789", "mcm/d")
    canonical_volume = float(native["volume_mcm_per_day"])
    with Session(engine) as session:
        session.add_all(
            [
                _flow_observation(
                    observation_id="non-entsog",
                    point_name="Bacton",
                    source_system="National Gas",
                    source_reference="national-gas",
                    flow_mcm_d=7.5,
                ),
                _flow_observation(
                    observation_id="native-volume",
                    point_name="Zeebrugge",
                    flow_mcm_d=canonical_volume,
                    normalizer_version=native["normalizer_version"],
                    native_rate_json=native,
                ),
            ]
        )
        session.commit()

    snapshot = analysis_module._load_snapshot()

    assert snapshot.source == "runtime-postgresql"
    assert {
        row["point_name"]: row["flow_mcm_d"] for row in snapshot.flow_observations
    } == {
        "Bacton": 7.5,
        "Zeebrugge": canonical_volume,
    }
    assert snapshot.warnings == []


def test_load_snapshot_omits_legacy_entsog_and_native_energy_with_warning(
    tmp_path, monkeypatch
) -> None:
    engine, _ = _database(monkeypatch, tmp_path, "withheld-volume")
    native_energy = _native_rate("987654321.123456789", "kWh/d")
    assert native_energy["quantity_kind"] == "energy"
    with Session(engine) as session:
        session.add_all(
            [
                _flow_observation(
                    observation_id="legacy-entsog",
                    point_name="Legacy ENTSOG",
                    source_system=" entsog ",
                    flow_mcm_d=5.5,
                ),
                _flow_observation(
                    observation_id="native-energy",
                    point_name="Native energy",
                    flow_mcm_d=999.0,
                    normalizer_version=native_energy["normalizer_version"],
                    native_rate_json=native_energy,
                ),
                _flow_observation(
                    observation_id="non-entsog",
                    point_name="Bacton",
                    source_system="National Gas",
                    source_reference="national-gas",
                    flow_mcm_d=7.5,
                ),
            ]
        )
        session.commit()

    snapshot = analysis_module._load_snapshot()

    assert [row["point_name"] for row in snapshot.flow_observations] == ["Bacton"]
    warning_text = " ".join(snapshot.warnings).lower()
    assert "unverified" in warning_text
    assert "incompatible" in warning_text
    assert "not zero" in warning_text
    assert "does not mean" in warning_text

    response = TestClient(create_app()).post("/api/analysis/query", json=_ANALYSIS_BODY)

    assert response.status_code == 200
    payload = response.json()
    for warnings in (payload["data"]["warnings"], payload["meta"]["warnings"]):
        assert any("not zero" in warning.lower() for warning in warnings)
    assert "LLM_PROVIDER_NOT_INVOKED" in payload["data"]["warnings"]


def test_malformed_native_is_typed_503_on_every_analysis_reader(
    tmp_path, monkeypatch
) -> None:
    engine, database_url = _database(monkeypatch, tmp_path, "malformed-native")
    with Session(engine) as session:
        session.add(
            _flow_observation(
                observation_id="malformed-native",
                flow_mcm_d=1.0,
                normalizer_version=NORMALIZER_VERSION,
                native_rate_json={"broken": _FORBIDDEN_NATIVE_MARKER},
            )
        )
        session.commit()

    client = TestClient(create_app())
    for path, body in (
        ("/api/analysis/query", _ANALYSIS_BODY),
        ("/api/reports/portfolio", _REPORT_BODY),
    ):
        response = client.post(path, json=body)

        assert response.status_code == 503
        detail = response.json()["detail"]
        assert detail["code"] == "physical_quantity_invalid"
        assert "Stored physical quantity data failed strict validation" in detail["message"]
        assert _FORBIDDEN_NATIVE_MARKER not in response.text
        assert "sqlite" not in response.text.lower()
        assert database_url not in response.text


def test_load_snapshot_preserves_principal_strategy_owner_scoping(
    tmp_path, monkeypatch
) -> None:
    engine, _ = _database(monkeypatch, tmp_path, "strategy-owner")
    now = datetime.now(UTC)
    with Session(engine) as session:
        owner = create_identity_principal(
            session,
            name="snapshot-owner",
            display_name="Snapshot owner",
            role="ANALYST",
            data_scopes=["*"],
        )
        other = create_identity_principal(
            session,
            name="snapshot-other",
            display_name="Snapshot other",
            role="ANALYST",
            data_scopes=["*"],
        )
        session.add_all(
            [
                StrategyRecord(
                    strategy_id="strategy-owner",
                    name="Owner strategy",
                    owner_principal_id=owner.principal_id,
                    visibility="PRIVATE",
                    created_at_utc=now,
                    updated_at_utc=now,
                ),
                StrategyRecord(
                    strategy_id="strategy-other",
                    name="Other strategy",
                    owner_principal_id=other.principal_id,
                    visibility="PRIVATE",
                    created_at_utc=now,
                    updated_at_utc=now,
                ),
            ]
        )
        session.add_all(
            [
                _strategy_run("run-owner", "strategy-owner", now),
                _strategy_run("run-other", "strategy-other", now),
            ]
        )
        session.commit()
        owner_id = owner.principal_id
        other_id = other.principal_id

    owner_snapshot = analysis_module._load_snapshot(principal_id=owner_id)
    other_snapshot = analysis_module._load_snapshot(principal_id=other_id)

    assert [row["run_id"] for row in owner_snapshot.strategy_runs] == ["run-owner"]
    assert [row["run_id"] for row in other_snapshot.strategy_runs] == ["run-other"]
