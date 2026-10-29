"""Focused mechanics for the trusted weather-demand operator entrypoint.

All request data and model results here are explicitly synthetic.  These tests
exercise the actual request parser, the controlled PostgreSQL session seam, the
read-only/rollback contract and stable operator summaries.  They are not provider
evidence, model accuracy evidence or a real regional weighting review.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from eurogas_nexus.application.research import weather_demand_runtime as runtime
from eurogas_nexus.application.research.demand_target_inputs import (
    DemandTargetAmbiguityError,
    RevisionOrderPolicy,
)
from eurogas_nexus.application.research.weather_demand_inputs import WeatherDemandDiagnosticCode
from eurogas_nexus.domain.market.gas_day import DEFAULT_GAS_DAY_CALENDAR
from eurogas_nexus.domain.ontology.vocabulary import TargetScope
from eurogas_nexus.domain.research.weather_demand import (
    DEGREE_DAY_METHOD_VERSION,
    DEMAND_MODEL_METHOD_VERSION,
    ModelKind,
    ModelSelectionStatus,
    ModelUseStatus,
    PromotionStatus,
)

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "fit_weather_demand.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "fit_weather_demand_operator",
    _SCRIPT_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
operator_cli = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(operator_cli)

_DAYS = ("2026-01-01", "2026-01-02", "2026-01-03")
_WEIGHT_EVIDENCE = "operator-input://synthetic-example/not-real-regional-weighting"


def _payload() -> dict[str, object]:
    feature_policy = {
        "region": "GB_NTS",
        "heating_base_c": 15.5,
        "cooling_base_c": 22.0,
        "max_gap_minutes": 240,
        "min_covered_fraction": 1.0,
        "location_weights": [
            {"location_id": "SYNTHETIC_LOCATION", "weight": "1"}
        ],
        "gas_day_calendar": DEFAULT_GAS_DAY_CALENDAR,
        "temporal_method": "EXPLICIT_DERIVED_HOLD",
        "method_version": DEGREE_DAY_METHOD_VERSION,
    }
    return {
        "schema": operator_cli.REQUEST_SCHEMA,
        "model_policy": {
            "target_scope": "GB_NTS_THROUGHPUT",
            "region": "GB_NTS",
            "target_unit": "MSCM",
            "gas_day_calendar": DEFAULT_GAS_DAY_CALENDAR,
            "training_cutoff": "2026-01-10T00:00:00Z",
            "validation_as_of": "2026-01-11T00:00:00Z",
            "ridge_lambda": 1e-8,
            "model_version": "synthetic-operator-test/v1",
            "validation_basis": "GENUINE_FORECAST_VINTAGE_OOS",
            "weather_features": ["HDD_MEAN"],
            "expected_feature_policy": feature_policy,
            "min_training_rows": 3,
            "min_validation_folds": 1,
            "min_validation_predictions": 1,
            "min_oos_coverage": 0.5,
            "min_relative_mae_improvement": 0.0,
            "min_fold_win_fraction": 0.5,
            "min_residuals_for_interval": 0,
            "interval_level": 0.8,
            "max_training_rows": 100,
            "max_features": 32,
            "max_folds": 5,
        },
        "degree_day_policy": {
            "heating_base_c": 15.5,
            "cooling_base_c": 22.0,
            "max_gap_minutes": 240,
            "min_covered_fraction": 1.0,
            "method_version": DEGREE_DAY_METHOD_VERSION,
        },
        "bridge_configs": [
            {
                "prediction_origin": "2025-12-31T23:00:00Z",
                "gas_days": [day],
                "max_hold_minutes": 240,
                "max_rows": 100,
                "max_points": 8,
                "max_window_days": 7,
                "max_cross_product": 1000,
                "max_intervals": 1000,
            }
            for day in _DAYS
        ],
        "point_bindings": [
            {
                "point_id": "SYNTHETIC_POINT_1",
                "series_id": "SYNTHETIC_SERIES",
                "entity_id": "SYNTHETIC_ENTITY",
                "location_id": "SYNTHETIC_LOCATION",
                "region": "GB_NTS",
            }
        ],
        "provider_item_id": "PUBOB637",
        "source_format": "REST",
        "target_gas_day_from": _DAYS[0],
        "target_gas_day_to": _DAYS[-1],
        "allow_provisional_targets": False,
        "regional_weighting_evidence_ref": _WEIGHT_EVIDENCE,
        "work_budget": {"target_read_limit": 100, "forecast_read_limit": 100},
    }


def _write_request(
    tmp_path: Path,
    *,
    payload: object | None = None,
    raw: str | None = None,
) -> Path:
    path = tmp_path / "request.json"
    content = raw if raw is not None else json.dumps(payload or _payload())
    path.write_text(content, encoding="utf-8")
    return path


def _csv_opt_in(payload: dict[str, object]) -> None:
    payload["source_format"] = "CSV"
    payload["target_revision_order_policy"] = (
        RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1.value
    )


class _FakeSession:
    def __init__(
        self,
        *,
        dialect: str = "postgresql",
        execute_failure: Exception | None = None,
    ) -> None:
        self.calls: list[str] = []
        self.autoflush = True
        self.rolled_back = False
        self.closed = False
        self._dialect = dialect
        self._execute_failure = execute_failure

    def get_bind(self) -> SimpleNamespace:
        return SimpleNamespace(dialect=SimpleNamespace(name=self._dialect))

    def execute(self, statement: object) -> None:
        if self._execute_failure is not None:
            raise self._execute_failure
        self.calls.append(str(statement))

    def rollback(self) -> None:
        self.rolled_back = True
        self.calls.append("ROLLBACK")

    def close(self) -> None:
        self.closed = True
        self.calls.append("CLOSE")

    def commit(self) -> None:
        raise AssertionError("the operator must never commit")


def _provider(
    session: _FakeSession,
    calls: list[str] | None = None,
) -> object:
    def provide() -> object:
        if calls is not None:
            calls.append("PROVIDER")
        return lambda: session

    return provide


def _evidence(request: object, *, ready: bool) -> SimpleNamespace:
    request_hash = request.request_hash
    return SimpleNamespace(
        feature_policy_hash=request.model_policy.expected_feature_policy.policy_hash,
        baseline_model_hash="b" * 64 if ready else None,
        candidate_model_hash="c" * 64 if ready else None,
        selected_model_hash="a" * 64 if ready else None,
        model_selection_hash="d" * 64 if ready else None,
        regional_weighting_evidence_ref=request.regional_weighting_evidence_ref,
        regional_weighting_evidence_basis=runtime.REGIONAL_WEIGHTING_EVIDENCE_BASIS,
        validation_basis=request.model_policy.validation_basis,
        training_cutoff=request.model_policy.training_cutoff,
        validation_as_of=request.model_policy.validation_as_of,
        target_revision_ids=("revision-1", "revision-2"),
        target_source_refs=("national-gas:synthetic",),
        forecast_observation_ids=("forecast-observation-1",),
        feature_source_refs=("ecmwf:synthetic",),
        degree_day_source_refs=("degree-day:synthetic",),
        selected_vintage_ids=("ECMWF/ifs/run-1@2025-12-31T12:00:00+00:00",),
        degree_day_method_version=DEGREE_DAY_METHOD_VERSION,
        request_hash=request_hash,
        target_revision_order_policy=request.target_revision_order_policy,
    )


def _ready_result(request: object) -> SimpleNamespace:
    selected = SimpleNamespace(
        kind=ModelKind.WEATHER_CALENDAR_RIDGE,
        use_status=ModelUseStatus.UNVALIDATED_OOS_RESEARCH_OUTPUT,
        target_scope=TargetScope.GB_NTS_THROUGHPUT,
        region=request.model_policy.region,
        model_version=request.model_policy.model_version,
        method_version=DEMAND_MODEL_METHOD_VERSION,
        training_rows=10,
        model_hash="a" * 64,
    )
    model_result = SimpleNamespace(
        selection_status=ModelSelectionStatus.CANDIDATE_SELECTED,
        selected_model=selected,
        baseline_model=SimpleNamespace(
            kind=ModelKind.CALENDAR_BASELINE,
            model_hash="b" * 64,
        ),
        candidate_model=SimpleNamespace(
            kind=ModelKind.WEATHER_CALENDAR_RIDGE,
            model_hash="c" * 64,
        ),
        selection_hash="d" * 64,
    )
    return SimpleNamespace(
        status=runtime.WeatherDemandRuntimeStatus.READY,
        request_hash=request.request_hash,
        research_only=True,
        research_label=runtime.RESEARCH_ONLY_LABEL,
        production_promotion=PromotionStatus.NOT_PROMOTED,
        native_unit="MSCM",
        source_format=request.source_format,
        provider_item_id=request.provider_item_id,
        target_revision_count=2,
        target_distinct_gas_days=2,
        feature_day_count=2,
        forecast_raw_count=4,
        paired_eligible_training_day_count=2,
        selected_vintages=(SimpleNamespace(),),
        omitted_days=(),
        diagnostics=(),
        model_result=model_result,
        evidence=_evidence(request, ready=True),
    )


def _non_ready_result(
    request: object,
    status: object,
    *,
    diagnostic_code: object,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        request_hash=request.request_hash,
        research_only=True,
        research_label=runtime.RESEARCH_ONLY_LABEL,
        production_promotion=PromotionStatus.NOT_PROMOTED,
        native_unit="MSCM",
        source_format=request.source_format,
        provider_item_id=request.provider_item_id,
        target_revision_count=2,
        target_distinct_gas_days=2,
        feature_day_count=0,
        forecast_raw_count=0,
        paired_eligible_training_day_count=0,
        selected_vintages=(),
        omitted_days=(
            SimpleNamespace(
                reason=runtime.WeatherDemandOmissionReason.FORECAST_BRIDGE_MISSING,
                gas_day=date(2026, 1, 1),
                bridge_diagnostics=(
                    SimpleNamespace(
                        code=WeatherDemandDiagnosticCode.NO_ELIGIBLE_FORECAST
                    ),
                ),
            ),
        ),
        diagnostics=(
            SimpleNamespace(
                code=diagnostic_code,
                gas_day=None,
            ),
        ),
        model_result=None,
        evidence=_evidence(request, ready=False),
    )


def _summary(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert captured.out.count("\n") == 1
    return json.loads(captured.out)


def test_ready_run_uses_read_only_postgresql_and_reports_actual_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_request(tmp_path)
    request = operator_cli.load_request(str(path))
    session = _FakeSession()
    calls: list[str] = []

    def fake_runtime(active_session: object, active_request: object) -> SimpleNamespace:
        assert active_session is session
        assert active_session.calls == ["SET TRANSACTION READ ONLY"]
        assert active_session.autoflush is False
        assert active_request.request_hash == request.request_hash
        calls.append("RUNTIME")
        return _ready_result(active_request)

    monkeypatch.setattr(operator_cli, "run_weather_demand_runtime", fake_runtime)

    exit_code = operator_cli.run(
        ["--request-json", str(path)],
        session_factory_provider=_provider(session, calls),
    )
    summary = _summary(capsys)

    assert exit_code == 0
    assert summary["status"] == "READY"
    assert summary["counts"] == {
        "diagnostic_count": 0,
        "feature_day_count": 2,
        "forecast_raw_count": 4,
        "omitted_day_count": 0,
        "paired_eligible_training_day_count": 2,
        "selected_vintage_count": 1,
        "target_distinct_gas_days": 2,
        "target_revision_count": 2,
    }
    assert summary["hashes"]["request_hash"] == request.request_hash
    assert summary["hashes"]["selected_model_hash"] == "a" * 64
    assert summary["model"]["selection_status"] == "CANDIDATE_SELECTED"
    assert summary["model"]["selected_model_kind"] == "WEATHER_CALENDAR_RIDGE"
    assert summary["model"]["native_unit"] == "MSCM"
    assert summary["database"] == {
        "required_dialect": "postgresql",
        "read_only_transaction": True,
        "commit_issued": False,
    }
    assert (
        summary["source_basis"]["regional_weighting_evidence_basis"]
        == runtime.REGIONAL_WEIGHTING_EVIDENCE_BASIS
    )
    assert (
        summary["source_basis"]["target_revision_order_policy"]
        == "DERIVED_RECEIPT_ORDER"
    )
    assert (
        summary["source_basis"]["target_availability_basis"]
        == "ACTUAL_RECEIPT_AVAILABLE_AT"
    )
    encoded = json.dumps(summary)
    assert "coefficients" not in encoded
    assert "prediction" not in encoded
    assert calls == ["PROVIDER", "RUNTIME"]
    assert session.calls == ["SET TRANSACTION READ ONLY", "ROLLBACK", "CLOSE"]
    assert session.autoflush is False
    assert session.rolled_back is True
    assert session.closed is True


def test_request_hash_and_result_hashes_repeat(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_request(tmp_path)
    monkeypatch.setattr(
        operator_cli,
        "run_weather_demand_runtime",
        lambda _session, request: _ready_result(request),
    )
    summaries = []
    for _ in range(2):
        session = _FakeSession()
        assert (
            operator_cli.run(
                ["--request-json", str(path)],
                session_factory_provider=_provider(session),
            )
            == 0
        )
        summaries.append(_summary(capsys))

    assert summaries[0]["request_hash"] == summaries[1]["request_hash"]
    assert summaries[0]["hashes"] == summaries[1]["hashes"]
    assert summaries[0]["counts"] == summaries[1]["counts"]


def test_opt_in_policy_is_explicit_reported_and_legacy_hash_is_unchanged(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_path = _write_request(tmp_path)
    default_request = operator_cli.load_request(str(default_path))

    explicit_default_payload = _payload()
    explicit_default_payload["target_revision_order_policy"] = (
        RevisionOrderPolicy.DERIVED_RECEIPT_ORDER.value
    )
    explicit_default_path = tmp_path / "explicit-default.json"
    explicit_default_path.write_text(
        json.dumps(explicit_default_payload),
        encoding="utf-8",
    )
    explicit_default_request = operator_cli.load_request(
        str(explicit_default_path)
    )

    opt_in_payload = _payload()
    opt_in_payload["target_revision_order_policy"] = (
        RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1.value
    )
    opt_in_path = tmp_path / "opt-in.json"
    opt_in_path.write_text(json.dumps(opt_in_payload), encoding="utf-8")
    opt_in_request = operator_cli.load_request(str(opt_in_path))

    assert default_request.target_revision_order_policy is (
        RevisionOrderPolicy.DERIVED_RECEIPT_ORDER
    )
    assert explicit_default_request.request_hash == default_request.request_hash
    assert opt_in_request.target_revision_order_policy is (
        RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1
    )
    assert opt_in_request.request_hash != default_request.request_hash

    monkeypatch.setattr(
        operator_cli,
        "run_weather_demand_runtime",
        lambda _session, request: _ready_result(request),
    )
    session = _FakeSession()

    assert (
        operator_cli.run(
            ["--request-json", str(opt_in_path)],
            session_factory_provider=_provider(session),
        )
        == 0
    )
    summary = _summary(capsys)
    assert summary["schema"] == operator_cli.SUMMARY_SCHEMA
    assert summary["source_basis"]["target_revision_order_policy"] == (
        RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1.value
    )
    assert summary["source_basis"]["target_availability_basis"] == (
        "ACTUAL_RECEIPT_AVAILABLE_AT"
    )
    assert summary["source_evidence"]["target_revision_order_policy"] == (
        RevisionOrderPolicy.DERIVED_REST_APPLICABILITY_ORDER_V1.value
    )
    assert summary["source_evidence"]["target_availability_basis"] == (
        "ACTUAL_RECEIPT_AVAILABLE_AT"
    )
    assert summary["research_only"] is True
    assert summary["production_promotion"] == "NOT_PROMOTED"
    assert "accuracy" not in json.dumps(summary).lower()


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda payload: payload.update({"unexpected": True}), "REQUEST_UNKNOWN_FIELD"),
        (
            lambda payload: payload["model_policy"].update({"unexpected": True}),
            "REQUEST_UNKNOWN_FIELD",
        ),
        (lambda payload: payload.pop("degree_day_policy"), "REQUEST_MISSING_POLICY"),
        (
            lambda payload: payload["model_policy"].pop("expected_feature_policy"),
            "REQUEST_MISSING_POLICY",
        ),
        (
            lambda payload: payload["model_policy"].update(
                {"training_cutoff": "2026-01-10T00:00:00"}
            ),
            "REQUEST_NAIVE_DATETIME",
        ),
        (
            lambda payload: payload["work_budget"].update({"target_read_limit": True}),
            "REQUEST_BOOLEAN_COUNT",
        ),
        (
            lambda payload: payload["model_policy"].update(
                {"validation_basis": "SYNTHETIC_NOT_REAL"}
            ),
            "SYNTHETIC_VALIDATION_BASIS_REJECTED",
        ),
        (
            lambda payload: payload.update(
                {"target_revision_order_policy": "UNSUPPORTED_POLICY"}
            ),
            "REQUEST_INVALID_VALUE",
        ),
        (_csv_opt_in, "REQUEST_INVALID_VALUE"),
    ],
)
def test_invalid_request_is_refused_before_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutate: object,
    expected_code: str,
) -> None:
    payload = _payload()
    mutate(payload)
    path = _write_request(tmp_path, payload=payload)
    calls: list[str] = []

    def provider() -> object:
        calls.append("PROVIDER")
        return lambda: _FakeSession()

    exit_code = operator_cli.run(
        ["--request-json", str(path)],
        session_factory_provider=provider,
    )
    summary = _summary(capsys)

    assert exit_code == 2
    assert summary["status"] == "REQUEST_INVALID"
    assert summary["error"]["code"] == expected_code
    assert summary["counts"] is None
    assert calls == []


def test_duplicate_json_key_is_refused_before_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.dumps(_payload())
    raw = raw[:-1] + ',"provider_item_id":"PUBOB637"}'
    path = _write_request(tmp_path, raw=raw)
    calls: list[str] = []

    def provider() -> object:
        calls.append("PROVIDER")
        return lambda: _FakeSession()

    assert (
        operator_cli.run(
            ["--request-json", str(path)],
            session_factory_provider=provider,
        )
        == 2
    )
    summary = _summary(capsys)
    assert summary["error"]["code"] == "REQUEST_DUPLICATE_KEY"
    assert calls == []


def test_non_finite_json_number_is_refused_before_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.dumps(_payload()).replace(str(1e-8), "NaN")
    path = _write_request(tmp_path, raw=raw)
    calls: list[str] = []

    def provider() -> object:
        calls.append("PROVIDER")
        return lambda: _FakeSession()

    assert (
        operator_cli.run(
            ["--request-json", str(path)],
            session_factory_provider=provider,
        )
        == 2
    )
    summary = _summary(capsys)
    assert summary["error"]["code"] == "REQUEST_NON_FINITE_NUMBER"
    assert calls == []


def test_oversized_request_file_is_refused_before_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b"{" + b" " * operator_cli.MAX_REQUEST_BYTES + b"}")
    calls: list[str] = []

    def provider() -> object:
        calls.append("PROVIDER")
        return lambda: _FakeSession()

    assert (
        operator_cli.run(
            ["--request-json", str(path)],
            session_factory_provider=provider,
        )
        == 2
    )
    summary = _summary(capsys)
    assert summary["error"]["code"] == "REQUEST_FILE_TOO_LARGE"
    assert calls == []


def test_sqlite_session_is_refused_before_runtime(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_request(tmp_path)
    session = _FakeSession(dialect="sqlite")
    runtime_calls: list[str] = []

    def forbidden_runtime(_session: object, _request: object) -> object:
        runtime_calls.append("RUNTIME")
        raise AssertionError("runtime must not run on SQLite")

    monkeypatch.setattr(
        operator_cli,
        "run_weather_demand_runtime",
        forbidden_runtime,
    )

    assert (
        operator_cli.run(
            ["--request-json", str(path)],
            session_factory_provider=_provider(session),
        )
        == 2
    )
    summary = _summary(capsys)
    assert summary["status"] == "DATABASE_ERROR"
    assert summary["error"]["code"] == "POSTGRESQL_REQUIRED"
    assert runtime_calls == []
    assert "SET TRANSACTION READ ONLY" not in session.calls
    assert session.rolled_back is True
    assert session.closed is True


def test_source_ambiguity_has_explicit_code_and_no_fabricated_counts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_request(tmp_path)
    session = _FakeSession()

    def ambiguous(_session: object, _request: object) -> object:
        raise DemandTargetAmbiguityError("secret raw provider text")

    monkeypatch.setattr(operator_cli, "run_weather_demand_runtime", ambiguous)

    assert (
        operator_cli.run(
            ["--request-json", str(path)],
            session_factory_provider=_provider(session),
        )
        == 1
    )
    summary = _summary(capsys)
    assert summary["status"] == "SOURCE_AMBIGUITY"
    assert summary["error"]["code"] == "AMBIGUOUS_RECEIPT_TIE"
    assert summary["counts"] is None
    assert summary["model"] is None
    assert "secret raw provider text" not in json.dumps(summary)
    assert session.rolled_back is True
    assert session.closed is True


def test_database_failure_is_stable_and_does_not_leak_secret(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _write_request(tmp_path)
    secret = "postgresql://operator:supersecret@example.test/db"
    failure = OperationalError(
        "SET TRANSACTION READ ONLY",
        {},
        RuntimeError(secret),
    )
    session = _FakeSession(execute_failure=failure)

    assert (
        operator_cli.run(
            ["--request-json", str(path)],
            session_factory_provider=_provider(session),
        )
        == 2
    )
    summary = _summary(capsys)
    assert summary["status"] == "DATABASE_ERROR"
    assert summary["error"]["code"] == "DATABASE_READ_ONLY_TRANSACTION_FAILED"
    assert summary["counts"] is None
    assert secret not in json.dumps(summary)
    assert session.rolled_back is True
    assert session.closed is True


def test_unexpected_runtime_failure_is_stable_two_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_request(tmp_path)
    session = _FakeSession()

    def broken(_session: object, _request: object) -> object:
        raise RuntimeError("operator-secret-value")

    monkeypatch.setattr(operator_cli, "run_weather_demand_runtime", broken)

    assert (
        operator_cli.run(
            ["--request-json", str(path)],
            session_factory_provider=_provider(session),
        )
        == 2
    )
    summary = _summary(capsys)
    assert summary["status"] == "INTERNAL_ERROR"
    assert summary["error"]["code"] == "INTERNAL_ERROR"
    assert "operator-secret-value" not in json.dumps(summary)
    assert session.rolled_back is True
    assert session.closed is True


@pytest.mark.parametrize(
    ("status", "diagnostic_code", "missing_code"),
    [
        (
            runtime.WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY,
            runtime.WeatherDemandRuntimeDiagnosticCode.INSUFFICIENT_TRAINING_HISTORY,
            "INSUFFICIENT_TRAINING_HISTORY",
        ),
        (
            runtime.WeatherDemandRuntimeStatus.NUMPY_NOT_INSTALLED,
            runtime.WeatherDemandRuntimeDiagnosticCode.NUMPY_NOT_INSTALLED,
            "NUMPY_NOT_INSTALLED",
        ),
    ],
)
def test_non_ready_result_exits_one_without_model(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    status: object,
    diagnostic_code: object,
    missing_code: str,
) -> None:
    path = _write_request(tmp_path)

    def non_ready(_session: object, request: object) -> SimpleNamespace:
        return _non_ready_result(
            request,
            status,
            diagnostic_code=diagnostic_code,
        )

    monkeypatch.setattr(operator_cli, "run_weather_demand_runtime", non_ready)
    session = _FakeSession()

    assert (
        operator_cli.run(
            ["--request-json", str(path)],
            session_factory_provider=_provider(session),
        )
        == 1
    )
    summary = _summary(capsys)
    assert summary["status"] == status.value
    assert summary["model"] is None
    assert summary["hashes"]["selected_model_hash"] is None
    assert any(
        item.get("code") == missing_code for item in summary["missing_inputs"]
    )


def test_database_url_argument_is_rejected_without_provider_call(
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    def provider() -> object:
        calls.append("PROVIDER")
        return lambda: _FakeSession()

    assert (
        operator_cli.run(
            ["--database-url", "postgresql://operator:supersecret@example.test/db"],
            session_factory_provider=provider,
        )
        == 2
    )
    summary = _summary(capsys)
    assert summary["error"]["code"] == "CLI_ARGUMENTS_INVALID"
    assert "supersecret" not in json.dumps(summary)
    assert calls == []
