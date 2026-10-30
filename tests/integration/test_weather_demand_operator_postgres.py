"""Real PostgreSQL acceptance for the trusted read-only operator command.

The command under test is the actual ``scripts/ops/fit_weather_demand.py`` entry
point.  These cases persist rows in an owned, uniquely named schema, commit that
fixture setup, and then invoke the actual CLI on a schema-scoped engine whose
sessions use the real runtime, repositories, projection, degree-day bridge and
frozen fitter.  No repository, runtime or fitter is mocked.

All target and forecast values are synthetic mechanics fixtures for exercising
the persisted-row and numerical plumbing.  They are not provider history,
regional forecast accuracy, model promotion or a production-readiness claim.

The fitted case needs the separately reviewed optional NumPy dependency and is
skipped only when it is absent.  The missing-history case deliberately reaches a
nonzero refusal before any fit, so it is independent of NumPy.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord
from eurogas_nexus.db.models.research import ForecastObservationRecord
from eurogas_nexus.domain.research.weather_demand import (
    DemandTargetLabelBasis,
    ValidationBasis,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUMMARY_KEYS = frozenset(
    {
        "schema",
        "status",
        "research_only",
        "research_label",
        "production_promotion",
        "request_hash",
        "counts",
        "hashes",
        "model",
        "source_evidence",
        "source_basis",
        "missing_inputs",
        "database",
        "error",
    }
)
_DATABASE_READ_ONLY = {
    "required_dialect": "postgresql",
    "read_only_transaction": True,
    "commit_issued": False,
}


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_runtime_fixture = _load_module(
    "_weather_demand_operator_runtime_fixture",
    Path(__file__).with_name("test_weather_demand_runtime_postgres.py"),
)
_operator = _load_module(
    "_weather_demand_operator_cli",
    _REPO_ROOT / "scripts" / "ops" / "fit_weather_demand.py",
)
_POSTGRES_URL = _runtime_fixture._POSTGRES_URL

pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="Explicit PostgreSQL test URL required; each test uses an owned schema.",
)


def _engine() -> Engine:
    url = make_url(_POSTGRES_URL)
    connect_args = (
        {"timeout": 5}
        if url.get_driver_name() == "pg8000"
        else {"connect_timeout": 5}
    )
    return create_engine(url, future=True, connect_args=connect_args)


@contextmanager
def _owned_schema() -> Iterator[tuple[Engine, str]]:
    """Create, migrate and seed one disposable schema, then always remove it."""

    engine = _engine()
    schema = f"weatherdemandoperator_{uuid4().hex}"
    created = False
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '20s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True

        bound = engine.execution_options(schema_translate_map={None: schema})
        with bound.begin() as connection:
            NationalGasActualDemandRecord.__table__.create(bind=connection)
            ForecastObservationRecord.__table__.create(bind=connection)
        yield bound, schema
    finally:
        try:
            if created:
                with engine.begin() as connection:
                    connection.execute(text("SET LOCAL statement_timeout = '20s'"))
                    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                    connection.execute(
                        text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                    )
        finally:
            engine.dispose()


def _write_request(path: Path, request: object) -> Path:
    """Build the strict operator JSON from the existing runtime dataclass."""

    raw = dataclasses.asdict(request)
    raw["schema"] = _operator.REQUEST_SCHEMA
    raw["work_budget"] = {
        "target_read_limit": raw.pop("target_read_limit"),
        "forecast_read_limit": raw.pop("forecast_read_limit"),
    }
    # ``target_label_basis`` is a pure RFC-0008 label-clock selector; the strict
    # operator request schema has no such field. Only the default basis has the
    # same meaning as the parser's own ACTUAL_RECEIPT default, so it is the only
    # basis this fixture may omit. A nondefault basis must fail loudly instead of
    # being silently dropped from the wire request.
    model_policy = raw["model_policy"]
    basis = model_policy["target_label_basis"]
    assert basis == DemandTargetLabelBasis.ACTUAL_RECEIPT, (
        "operator request schema has no target_label_basis field; refusing to "
        "silently omit a nondefault RFC-0008 label basis"
    )
    model_policy.pop("target_label_basis")
    # The parser requires the model policy's expected feature policy only; the
    # bridge's internal copy is not part of the explicit operator wire format.
    for config in raw["bridge_configs"]:
        config.pop("feature_policy")

    def _encode(value: object) -> str:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError(f"unsupported request value: {type(value).__name__}")

    path.write_text(
        json.dumps(raw, default=_encode, ensure_ascii=True),
        encoding="utf-8",
    )
    return path


def test_write_request_refuses_nondefault_target_label_basis(
    tmp_path: Path,
) -> None:
    """A nondefault RFC-0008 basis cannot be silently omitted from the wire."""

    day = _runtime_fixture.START
    request = _runtime_fixture._request(
        _runtime_fixture._feature_policy(),
        (day,),
        cutoff=_runtime_fixture._day_end(day),
        validation=_runtime_fixture._day_end(day) + timedelta(hours=1),
    )
    nondefault_model_policy = dataclasses.replace(
        request.model_policy,
        validation_basis=ValidationBasis.REALIZED_WEATHER_CALIBRATION,
        target_label_basis=(
            DemandTargetLabelBasis.RETROSPECTIVE_PROVIDER_APPLICABILITY_RESEARCH
        ),
    )
    nondefault_request = dataclasses.replace(
        request,
        model_policy=nondefault_model_policy,
    )
    request_path = tmp_path / "weather-demand-operator-nondefault-label.json"

    with pytest.raises(AssertionError, match="target_label_basis"):
        _write_request(request_path, nondefault_request)

    assert not request_path.exists()


def _run_operator(
    *,
    bound: Engine,
    request_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, dict[str, Any], list[str]]:
    statements: list[str] = []

    def _capture(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(" ".join(statement.split()).upper())

    event.listen(bound, "before_cursor_execute", _capture)
    try:
        code = _operator.run(
            ["--request-json", str(request_path)],
            session_factory_provider=lambda: sessionmaker(bound),
        )
    finally:
        event.remove(bound, "before_cursor_execute", _capture)

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Traceback" not in captured.out
    assert _POSTGRES_URL not in captured.out
    assert "password" not in captured.out.lower()

    payload = json.loads(captured.out)
    assert set(payload) == _SUMMARY_KEYS
    assert payload["research_only"] is True
    assert payload["production_promotion"] == "NOT_PROMOTED"
    return code, payload, statements


def _assert_read_only_statements(statements: list[str]) -> None:
    assert any(
        statement.startswith("SET TRANSACTION READ ONLY")
        for statement in statements
    )
    write_prefixes = {
        "ALTER",
        "COPY",
        "CREATE",
        "DELETE",
        "DROP",
        "INSERT",
        "MERGE",
        "TRUNCATE",
        "UPDATE",
    }
    for statement in statements:
        assert statement != "COMMIT"
        assert not statement.startswith("COMMIT ")
        assert statement.split(None, 1)[0] not in write_prefixes


def _read_counts(bound: Engine) -> tuple[int, int]:
    """Count rows with a separate session that has its own read-only transaction."""

    with Session(bound) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        targets = session.scalar(
            select(func.count()).select_from(NationalGasActualDemandRecord)
        )
        forecasts = session.scalar(
            select(func.count()).select_from(ForecastObservationRecord)
        )
        session.rollback()
    return int(targets or 0), int(forecasts or 0)


@pytest.mark.skipif(
    not _runtime_fixture._numpy_available(),
    reason=(
        "optional NumPy is absent; the actual frozen fitter needs the separately "
        "reviewed numerical dependency"
    ),
)
def test_ready_operator_runs_actual_fitted_postgres_runtime_read_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    days = tuple(
        _runtime_fixture.START + timedelta(days=index) for index in range(21)
    )
    policy = _runtime_fixture._feature_policy()
    cutoff = _runtime_fixture._day_start(days[14])
    validation = _runtime_fixture._day_end(days[-1]) + timedelta(hours=1)
    request = _runtime_fixture._request(
        policy,
        days,
        cutoff=cutoff,
        validation=validation,
    )
    targets = [
        _runtime_fixture._target_row(
            f"operator-{day.isoformat()}",
            day,
            _runtime_fixture._target_value(day),
            available_at=_runtime_fixture._day_end(day) + timedelta(hours=1),
        )
        for day in days
    ]
    forecasts = [
        row
        for day in days
        for row in _runtime_fixture._eligible_forecast(
            day,
            label=f"operator-run-{day.isoformat()}",
        )
    ]
    expected_forecast_ids = {
        row.forecast_observation_id for row in forecasts
    }

    with _owned_schema() as (bound, _schema):
        with Session(bound) as seed:
            seed.add_all(targets)
            seed.add_all(forecasts)
            seed.commit()

        request_path = _write_request(
            tmp_path / "weather-demand-operator-ready.json",
            request,
        )
        code, payload, statements = _run_operator(
            bound=bound,
            request_path=request_path,
            capsys=capsys,
        )

        assert code == 0
        assert payload["schema"] == _operator.SUMMARY_SCHEMA
        assert payload["status"] == "READY"
        assert payload["research_label"] == _operator.RESEARCH_ONLY_LABEL
        assert payload["request_hash"] == request.request_hash
        assert payload["missing_inputs"] == []
        assert payload["error"] is None
        assert payload["database"] == _DATABASE_READ_ONLY

        counts = payload["counts"]
        assert counts["target_revision_count"] == len(targets) == len(days)
        assert counts["target_distinct_gas_days"] == len(days)
        assert counts["feature_day_count"] == len(days)
        assert counts["forecast_raw_count"] >= len(forecasts)
        assert (
            counts["paired_eligible_training_day_count"]
            >= request.model_policy.min_training_rows
        )
        assert counts["selected_vintage_count"] == len(days)
        assert counts["omitted_day_count"] == 0

        hashes = payload["hashes"]
        for key in (
            "request_hash",
            "feature_policy_hash",
            "baseline_model_hash",
            "selected_model_hash",
            "model_selection_hash",
        ):
            assert isinstance(hashes[key], str)
            assert hashes[key]
        assert hashes["request_hash"] == request.request_hash

        model = payload["model"]
        assert isinstance(model, dict)
        assert model["native_unit"] == "MSCM"
        assert model["training_rows"] >= request.model_policy.min_training_rows
        assert model["selected_use_status"] in {
            "UNVALIDATED_OOS_RESEARCH_OUTPUT",
            "CALENDAR_BASELINE_REFERENCE",
        }

        source = payload["source_evidence"]
        assert source["provider_item_id"] == _runtime_fixture.PROVIDER_ITEM
        assert source["source_format"] == "CSV"
        assert source["native_unit"] == "MSCM"
        assert source["validation_basis"] == "GENUINE_FORECAST_VINTAGE_OOS"
        assert source["training_cutoff"] == cutoff.isoformat()
        assert set(source["forecast_observation_ids"]) == expected_forecast_ids
        assert len(source["target_revision_ids"]) == len(targets)
        assert len(source["selected_vintage_ids"]) == len(days)
        assert source["regional_weighting_evidence_basis"] == (
            "CALLER_DECLARED_PROVENANCE_NOT_REVIEWED"
        )
        basis = payload["source_basis"]
        assert basis["provider_item_id"] == _runtime_fixture.PROVIDER_ITEM
        assert basis["source_format"] == "CSV"
        assert basis["validation_basis"] == "GENUINE_FORECAST_VINTAGE_OOS"

        _assert_read_only_statements(statements)
        assert _read_counts(bound) == (len(targets), len(forecasts))


def test_missing_weather_history_is_read_only_exit_one_and_numpy_independent(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    day = _runtime_fixture.START
    request = _runtime_fixture._request(
        _runtime_fixture._feature_policy(),
        (day,),
        cutoff=_runtime_fixture._day_end(day),
        validation=_runtime_fixture._day_end(day) + timedelta(hours=1),
    )
    target = _runtime_fixture._target_row(
        "operator-history-only",
        day,
        "101.100",
        available_at=_runtime_fixture._day_end(day) + timedelta(hours=1),
    )

    with _owned_schema() as (bound, _schema):
        with Session(bound) as seed:
            seed.add(target)
            seed.commit()

        request_path = _write_request(
            tmp_path / "weather-demand-operator-missing-history.json",
            request,
        )
        code, payload, statements = _run_operator(
            bound=bound,
            request_path=request_path,
            capsys=capsys,
        )

        assert code == 1
        assert payload["schema"] == _operator.SUMMARY_SCHEMA
        assert payload["status"] == "INSUFFICIENT_REAL_HISTORY"
        assert payload["research_label"] == _operator.RESEARCH_ONLY_LABEL
        assert payload["request_hash"] == request.request_hash
        assert payload["hashes"]["request_hash"] == request.request_hash
        assert payload["model"] is None
        assert payload["error"] is None
        assert payload["database"] == _DATABASE_READ_ONLY
        assert payload["counts"]["target_revision_count"] == 1
        assert payload["counts"]["feature_day_count"] == 0
        assert payload["counts"]["forecast_raw_count"] == 0

        missing_codes = {item["code"] for item in payload["missing_inputs"]}
        assert "NO_ELIGIBLE_FEATURES" in missing_codes
        assert "FORECAST_BRIDGE_MISSING" in missing_codes

        _assert_read_only_statements(statements)
        assert _read_counts(bound) == (1, 0)
