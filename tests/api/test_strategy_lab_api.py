"""Strategy-lab API tests."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.models import StrategyRunRecord


class _FakeQuery:
    def __init__(self, rows: list[StrategyRunRecord]) -> None:
        self.rows = list(rows)

    def filter(self, *_args, **_kwargs) -> _FakeQuery:
        return self

    def order_by(self, *_args, **_kwargs) -> _FakeQuery:
        return self

    def limit(self, limit: int) -> _FakeQuery:
        self.rows = self.rows[:limit]
        return self

    def all(self) -> list[StrategyRunRecord]:
        return self.rows


class _FakeSession:
    def __init__(self, run: StrategyRunRecord) -> None:
        self.run = run

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_args) -> None:
        return None

    def query(self, _model) -> _FakeQuery:
        return _FakeQuery([self.run])

    def get(self, _model, run_id: str) -> StrategyRunRecord | None:
        return self.run if run_id == self.run.run_id else None


class _FakeSessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    def __call__(self) -> _FakeSession:
        return self.session


def _history_run() -> StrategyRunRecord:
    return StrategyRunRecord(
        run_id="run-1",
        strategy_id="sap-icis-ocm",
        run_mode="SHADOW_RUN",
        status="SUCCESS",
        started_at_utc=datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC),
        finished_at_utc=datetime(2026, 7, 22, 10, 1, 0, tzinfo=UTC),
        input_snapshot={"strategy_name": "Input Name"},
        result_snapshot={
            "strategy_name": "Snapshot Name",
            "paper_pnl_gbp": 0.0,
            "cumulative_pnl_gbp": -2.5,
            "hit": False,
            "weighted_score": -0.1,
            "day_ahead_average_gbp_mwh": 30.0,
            "intraday_average_gbp_mwh": 29.5,
            "intraday_vs_day_ahead_spread_gbp_mwh": -0.5,
            "candidate_action_for_review": "REVIEW_HIGHER_DAY_AHEAD_ALLOCATION",
            "allocation_targets": [],
        },
        source_refs=["fixture:source"],
        warnings=[],
        missing_inputs=[],
        research_only=True,
        human_review_required=True,
    )


def test_strategy_lab_evaluate_endpoint_returns_paper_allocation_targets() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/strategy-lab/evaluate",
        json={
            "strategy_id": "sap-icis-ocm",
            "strategy_name": "SAP ICIS vs OCM",
            "run_mode": "SHADOW_RUN",
            "resource_contexts": [
                {
                    "resource_id": "ttf-bbl-portfolio",
                    "resource_name": "TTF to NBP BBL portfolio",
                    "available_quantity_mwh_per_day": 10000,
                    "all_in_cost_gbp_mwh": 24.0,
                    "required_tso_access": ["BBL Company"],
                    "company_accessible_tsos": ["BBL Company"],
                }
            ],
            "price_observations": [
                {
                    "observation_id": "sap-1",
                    "source_system": "operator-fixture",
                    "venue": "assessment",
                    "hub": "NBP",
                    "product": "day-ahead",
                    "price_name": "SAP",
                    "price_gbp_mwh": 27.0,
                    "observed_at_utc": "2026-01-15T16:00:00Z",
                    "delivery_start_utc": "2026-01-16T00:00:00Z",
                    "delivery_end_utc": "2026-01-17T00:00:00Z",
                    "bar_minutes": 5,
                    "source_reference": "fixture:sap",
                },
                {
                    "observation_id": "icis-1",
                    "source_system": "operator-fixture",
                    "venue": "assessment",
                    "hub": "NBP",
                    "product": "day-ahead",
                    "price_name": "ICIS_HEREN_DAY_AHEAD",
                    "price_gbp_mwh": 27.2,
                    "observed_at_utc": "2026-01-15T16:30:00Z",
                    "delivery_start_utc": "2026-01-16T00:00:00Z",
                    "delivery_end_utc": "2026-01-17T00:00:00Z",
                    "bar_minutes": 5,
                    "source_reference": "fixture:icis",
                },
                {
                    "observation_id": "ocm-1",
                    "source_system": "operator-fixture",
                    "venue": "ICE OCM",
                    "hub": "NBP",
                    "product": "within-day",
                    "price_name": "ICE_OCM",
                    "price_gbp_mwh": 29.4,
                    "observed_at_utc": "2026-01-15T16:45:00Z",
                    "delivery_start_utc": "2026-01-16T00:00:00Z",
                    "delivery_end_utc": "2026-01-17T00:00:00Z",
                    "bar_minutes": 5,
                    "source_reference": "fixture:ocm",
                },
            ],
            "components": [
                {
                    "component_id": "window",
                    "component_type": "OCM_VS_DAY_AHEAD",
                    "time_window_start": "15:00",
                    "time_window_end": "17:00",
                    "target_bar_minutes": 5,
                    "positive_spread_threshold_gbp_mwh": 0.2,
                }
            ],
            "risk_control": {"max_ocm_allocation_pct": 70, "min_day_ahead_allocation_pct": 20},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["research_only"] is True
    assert body["meta"]["human_review_required"] is True
    assert body["data"]["run_id"].startswith("run-")
    assert body["data"]["paper_pnl_gbp"] > 0
    assert body["data"]["hit"] is True
    assert body["data"]["candidate_action_for_review"] == "REVIEW_HIGHER_OCM_ALLOCATION"
    assert body["data"]["allocation_targets"][0]["market_bucket"] == "ICE_OCM"
    assert body["data"]["allocation_targets"][0]["target_quantity_mwh_per_day"] > 0
    assert "STRATEGY_RUN_NOT_PERSISTED" in body["meta"]["warnings"]


def test_strategy_lab_runs_and_detail_expose_history_fields_via_serializer(
    monkeypatch,
) -> None:
    """List and detail routes run the repository serializer on a real row."""
    run = _history_run()
    session = _FakeSession(run)
    monkeypatch.setattr(
        "eurogas_nexus.db.session.resolve_database_url",
        lambda: "postgresql+pg8000://test:test@localhost/test",
    )
    monkeypatch.setattr(
        "eurogas_nexus.db.session.get_session_factory",
        lambda: _FakeSessionFactory(session),
    )

    client = TestClient(create_app())
    list_response = client.get("/api/strategy-lab/runs")
    detail_response = client.get("/api/strategy-lab/runs/run-1")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    list_run = list_response.json()["data"][0]
    detail_run = detail_response.json()["data"]
    assert list_run["run_id"] == "run-1"
    assert detail_run["run_id"] == "run-1"
    assert list_run["strategy_name"] == "Snapshot Name"
    assert detail_run["strategy_name"] == "Snapshot Name"
    assert list_run["day_ahead_average_gbp_mwh"] == 30.0
    assert detail_run["day_ahead_average_gbp_mwh"] == 30.0
    assert list_run["intraday_average_gbp_mwh"] == 29.5
    assert detail_run["intraday_average_gbp_mwh"] == 29.5
    assert list_run["intraday_vs_day_ahead_spread_gbp_mwh"] == -0.5
    assert detail_run["intraday_vs_day_ahead_spread_gbp_mwh"] == -0.5
    assert list_run["candidate_action_for_review"] == "REVIEW_HIGHER_DAY_AHEAD_ALLOCATION"
    assert detail_run["candidate_action_for_review"] == "REVIEW_HIGHER_DAY_AHEAD_ALLOCATION"
    assert list_run["paper_pnl_gbp"] == 0.0
    assert detail_run["paper_pnl_gbp"] == 0.0
    assert list_run["cumulative_pnl_gbp"] == -2.5
    assert detail_run["cumulative_pnl_gbp"] == -2.5
    assert list_run["hit"] is False
    assert detail_run["hit"] is False
    assert list_run["started_at_utc"].endswith("+00:00")
    assert detail_run["finished_at_utc"].endswith("+00:00")
    assert list_run["source_refs"] == ["fixture:source"]
    assert detail_run["source_refs"] == ["fixture:source"]
    assert list_run["research_only"] is True
    assert detail_run["research_only"] is True
    assert list_run["human_review_required"] is True
    assert detail_run["human_review_required"] is True


def test_strategy_lab_runs_and_detail_legacy_serializer_fields_are_null(
    monkeypatch,
) -> None:
    """Legacy rows expose null optional fields through list and detail routes."""
    run = _history_run()
    run.result_snapshot = {
        "paper_pnl_gbp": 10.0,
        "cumulative_pnl_gbp": 10.0,
        "hit": True,
        "weighted_score": 0.4,
    }
    session = _FakeSession(run)
    monkeypatch.setattr(
        "eurogas_nexus.db.session.resolve_database_url",
        lambda: "postgresql+pg8000://test:test@localhost/test",
    )
    monkeypatch.setattr(
        "eurogas_nexus.db.session.get_session_factory",
        lambda: _FakeSessionFactory(session),
    )

    client = TestClient(create_app())
    list_response = client.get("/api/strategy-lab/runs")
    detail_response = client.get("/api/strategy-lab/runs/run-1")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    list_run = list_response.json()["data"][0]
    detail_run = detail_response.json()["data"]
    assert list_run["strategy_name"] == "Input Name"
    assert detail_run["strategy_name"] == "Input Name"
    assert list_run["day_ahead_average_gbp_mwh"] is None
    assert detail_run["day_ahead_average_gbp_mwh"] is None
    assert list_run["intraday_average_gbp_mwh"] is None
    assert detail_run["intraday_average_gbp_mwh"] is None
    assert list_run["intraday_vs_day_ahead_spread_gbp_mwh"] is None
    assert detail_run["intraday_vs_day_ahead_spread_gbp_mwh"] is None
    assert list_run["candidate_action_for_review"] is None
    assert detail_run["candidate_action_for_review"] is None
    assert list_run["run_id"] == "run-1"
    assert detail_run["run_id"] == "run-1"
    assert list_run["source_refs"] == ["fixture:source"]
    assert detail_run["source_refs"] == ["fixture:source"]
    assert list_run["research_only"] is True
    assert detail_run["research_only"] is True
    assert list_run["human_review_required"] is True
    assert detail_run["human_review_required"] is True


def test_strategy_lab_runs_endpoint_db_unavailable() -> None:
    client = TestClient(create_app())

    response = client.get("/api/strategy-lab/runs")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert "RUNTIME_DB_NOT_CONFIGURED" in body["meta"]["warnings"]


def test_strategy_lab_run_endpoint_db_unavailable() -> None:
    client = TestClient(create_app())

    response = client.get("/api/strategy-lab/runs/run-unknown")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] is None
    assert "RUNTIME_DB_NOT_CONFIGURED" in body["meta"]["warnings"]


def test_strategy_lab_summary_endpoint_db_unavailable() -> None:
    client = TestClient(create_app())

    response = client.get("/api/strategy-lab/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["run_count"] == 0
    assert body["data"]["cumulative_pnl_gbp"] == 0.0
    assert "RUNTIME_DB_NOT_CONFIGURED" in body["meta"]["warnings"]
