# ruff: noqa: E402, I001
"""Bounded trusted-operator entrypoint for the read-only weather-demand runtime.

This command is deliberately outside the public SDK/CLI surface.  It accepts one
explicit local JSON request (at most 1 MiB), builds the immutable
``WeatherDemandRuntimeRequest`` from actual nested domain types, and invokes the
existing runtime on a PostgreSQL session in a read-only transaction.  It never
commits, flushes, predicts, promotes a model, activates a source or fetches over
the network.

Credentials are resolved only through the existing database environment helper.
No database URL is accepted on the command line and no URL is written to output.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from eurogas_nexus.application.research.demand_target_inputs import (  # noqa: E402
    SUPPORTED_SOURCE_FORMATS,
    DemandTargetAmbiguityError,
    DemandTargetDuplicateConflict,
)
from eurogas_nexus.application.research.weather_demand_inputs import (  # noqa: E402
    ForecastBridgeAmbiguityError,
    ForecastFieldRevisionConflictError,
    ForecastPointBinding,
    WeatherDemandBridgeConfig,
)
from eurogas_nexus.application.research.weather_demand_runtime import (  # noqa: E402
    MAX_BRIDGE_DAYS,
    RESEARCH_ONLY_LABEL,
    WeatherDemandRuntimeError,
    WeatherDemandRuntimeRequest,
    WeatherDemandRuntimeResult,
    WeatherDemandRuntimeStatus,
    run_weather_demand_runtime,
)
from eurogas_nexus.db.session import get_session_factory  # noqa: E402
from eurogas_nexus.domain.ontology.vocabulary import (  # noqa: E402
    TargetScope,
    TemperatureDerivationMethod,
    WeatherFeature,
)
from eurogas_nexus.domain.research.weather_demand import (  # noqa: E402
    AmbiguousWeatherInputError,
    DemandModelPolicy,
    DegreeDayFeaturePolicy,
    DegreeDayPolicy,
    MissingNumpyError,
    RegionLocationWeight,
    ValidationBasis,
    WeatherDemandInputError,
)

REQUEST_SCHEMA = "weather-demand-operator-request/v1"
SUMMARY_SCHEMA = "weather-demand-operator-summary/v1"
MAX_REQUEST_BYTES = 1024 * 1024
_DECIMAL_TEXT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_SAFE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")

_ROOT_REQUIRED = frozenset(
    {
        "schema",
        "model_policy",
        "degree_day_policy",
        "bridge_configs",
        "point_bindings",
        "provider_item_id",
        "source_format",
        "target_gas_day_from",
        "target_gas_day_to",
        "allow_provisional_targets",
        "regional_weighting_evidence_ref",
    }
)
_ROOT_OPTIONAL = frozenset({"work_budget"})
_MODEL_REQUIRED = frozenset(
    {
        "target_scope",
        "region",
        "target_unit",
        "gas_day_calendar",
        "training_cutoff",
        "validation_as_of",
        "ridge_lambda",
        "model_version",
        "validation_basis",
        "weather_features",
        "expected_feature_policy",
        "min_training_rows",
        "min_validation_folds",
        "min_validation_predictions",
        "min_oos_coverage",
        "min_relative_mae_improvement",
        "min_fold_win_fraction",
        "min_residuals_for_interval",
        "interval_level",
        "max_training_rows",
        "max_features",
        "max_folds",
    }
)
_FEATURE_REQUIRED = frozenset(
    {
        "region",
        "heating_base_c",
        "cooling_base_c",
        "max_gap_minutes",
        "min_covered_fraction",
        "location_weights",
        "gas_day_calendar",
        "temporal_method",
        "method_version",
    }
)
_DEGREE_REQUIRED = frozenset(
    {
        "heating_base_c",
        "cooling_base_c",
        "max_gap_minutes",
        "min_covered_fraction",
        "method_version",
    }
)
_BRIDGE_REQUIRED = frozenset({"prediction_origin", "gas_days", "max_hold_minutes"})
_BRIDGE_OPTIONAL = frozenset(
    {
        "max_rows",
        "max_points",
        "max_window_days",
        "max_cross_product",
        "max_intervals",
    }
)
_BINDING_REQUIRED = frozenset(
    {"point_id", "series_id", "entity_id", "location_id", "region"}
)
_BUDGET_OPTIONAL = frozenset({"target_read_limit", "forecast_read_limit"})
_AMBIGUITY_ERRORS = (
    DemandTargetAmbiguityError,
    DemandTargetDuplicateConflict,
    ForecastBridgeAmbiguityError,
    ForecastFieldRevisionConflictError,
    AmbiguousWeatherInputError,
)


class OperatorFailure(Exception):
    """A stable operator failure code that never carries raw exception text."""

    def __init__(
        self,
        code: str,
        exit_code: int,
        status: str,
        *,
        category: str,
        field: str | None = None,
    ) -> None:
        self.code = code
        self.exit_code = exit_code
        self.status = status
        self.category = category
        self.field = field
        super().__init__(code)


class _RequestFailure(OperatorFailure):
    def __init__(self, code: str, field: str | None = None) -> None:
        super().__init__(
            code,
            2,
            "REQUEST_INVALID",
            category="REQUEST",
            field=field,
        )


class _DuplicateKeyError(ValueError):
    """JSON contained the same object key twice."""


class _NonFiniteJsonError(ValueError):
    """JSON contained an explicit NaN/Infinity token."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _RequestFailure("CLI_ARGUMENTS_INVALID", "argv")


def _request_error(code: str, field: str | None = None) -> _RequestFailure:
    return _RequestFailure(code, field)


def _object(
    value: object,
    path: str,
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _request_error("REQUEST_INVALID_VALUE", path)
    keys = set(value)
    missing = required - keys
    if missing:
        name = sorted(missing)[0]
        raise _request_error("REQUEST_MISSING_FIELD", f"{path}.{name}" if path else name)
    if keys - required - optional:
        raise _request_error("REQUEST_UNKNOWN_FIELD", path or "request")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _request_error("REQUEST_INVALID_VALUE", path)
    return value


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise _request_error("REQUEST_INVALID_VALUE", path)
    return value


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool):
        raise _request_error("REQUEST_BOOLEAN_COUNT", path)
    if not isinstance(value, int):
        raise _request_error("REQUEST_INVALID_VALUE", path)
    return value


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _request_error("REQUEST_INVALID_VALUE", path)
    resolved = float(value)
    if not math.isfinite(resolved):
        raise _request_error("REQUEST_NON_FINITE_NUMBER", path)
    return resolved


def _decimal(value: object, path: str) -> Decimal:
    if not isinstance(value, str) or not _DECIMAL_TEXT.fullmatch(value):
        raise _request_error("REQUEST_INVALID_VALUE", path)
    try:
        resolved = Decimal(value)
    except InvalidOperation:
        raise _request_error("REQUEST_INVALID_VALUE", path) from None
    if not resolved.is_finite():
        raise _request_error("REQUEST_NON_FINITE_NUMBER", path)
    return resolved


def _calendar_date(value: object, path: str) -> date:
    if not isinstance(value, str):
        raise _request_error("REQUEST_INVALID_VALUE", path)
    try:
        if "T" in value or " " in value:
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise _request_error("REQUEST_INVALID_VALUE", path) from None


def _instant(value: object, path: str) -> datetime:
    if not isinstance(value, str):
        raise _request_error("REQUEST_INVALID_VALUE", path)
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        resolved = datetime.fromisoformat(candidate)
    except ValueError:
        raise _request_error("REQUEST_INVALID_VALUE", path) from None
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise _request_error("REQUEST_NAIVE_DATETIME", path)
    return resolved.astimezone(UTC)


def _list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise _request_error("REQUEST_INVALID_VALUE", path)
    return value


def _enum(value: object, enum_type: type[Any], path: str) -> Any:
    if not isinstance(value, str):
        raise _request_error("REQUEST_INVALID_VALUE", path)
    try:
        return enum_type(value)
    except ValueError:
        raise _request_error("REQUEST_INVALID_VALUE", path) from None


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise _NonFiniteJsonError


def _build_feature_policy(value: object, path: str) -> DegreeDayFeaturePolicy:
    raw = _object(value, path, required=_FEATURE_REQUIRED)
    raw_weights = _list(raw["location_weights"], f"{path}.location_weights")
    if not raw_weights:
        raise _request_error("REQUEST_INVALID_VALUE", f"{path}.location_weights")
    weights: list[RegionLocationWeight] = []
    for index, item in enumerate(raw_weights):
        item_path = f"{path}.location_weights[{index}]"
        weight = _object(
            item,
            item_path,
            required=frozenset({"location_id", "weight"}),
        )
        try:
            weights.append(
                RegionLocationWeight(
                    location_id=_string(
                        weight["location_id"], f"{item_path}.location_id"
                    ),
                    weight=_decimal(weight["weight"], f"{item_path}.weight"),
                )
            )
        except (TypeError, ValueError):
            raise _request_error("REQUEST_POLICY_INVALID", item_path) from None
    try:
        return DegreeDayFeaturePolicy(
            region=_string(raw["region"], f"{path}.region"),
            heating_base_c=_number(raw["heating_base_c"], f"{path}.heating_base_c"),
            cooling_base_c=_number(raw["cooling_base_c"], f"{path}.cooling_base_c"),
            max_gap_minutes=_integer(raw["max_gap_minutes"], f"{path}.max_gap_minutes"),
            min_covered_fraction=_number(
                raw["min_covered_fraction"], f"{path}.min_covered_fraction"
            ),
            location_weights=tuple(weights),
            gas_day_calendar=_string(raw["gas_day_calendar"], f"{path}.gas_day_calendar"),
            temporal_method=_enum(
                raw["temporal_method"],
                TemperatureDerivationMethod,
                f"{path}.temporal_method",
            ),
            method_version=_string(raw["method_version"], f"{path}.method_version"),
        )
    except (TypeError, ValueError):
        raise _request_error("REQUEST_POLICY_INVALID", path) from None


def _build_degree_day_policy(value: object, path: str) -> DegreeDayPolicy:
    raw = _object(value, path, required=_DEGREE_REQUIRED)
    try:
        return DegreeDayPolicy(
            heating_base_c=_number(raw["heating_base_c"], f"{path}.heating_base_c"),
            cooling_base_c=_number(raw["cooling_base_c"], f"{path}.cooling_base_c"),
            max_gap_minutes=_integer(raw["max_gap_minutes"], f"{path}.max_gap_minutes"),
            min_covered_fraction=_number(
                raw["min_covered_fraction"], f"{path}.min_covered_fraction"
            ),
            method_version=_string(raw["method_version"], f"{path}.method_version"),
        )
    except (TypeError, ValueError):
        raise _request_error("REQUEST_POLICY_INVALID", path) from None


def _build_model_policy(value: object, path: str) -> DemandModelPolicy:
    if isinstance(value, dict) and "expected_feature_policy" not in value:
        raise _request_error("REQUEST_MISSING_POLICY", f"{path}.expected_feature_policy")
    raw = _object(value, path, required=_MODEL_REQUIRED)
    feature_policy = _build_feature_policy(
        raw["expected_feature_policy"], f"{path}.expected_feature_policy"
    )
    raw_features = _list(raw["weather_features"], f"{path}.weather_features")
    if not raw_features:
        raise _request_error("REQUEST_INVALID_VALUE", f"{path}.weather_features")
    features = tuple(
        _enum(item, WeatherFeature, f"{path}.weather_features[{index}]")
        for index, item in enumerate(raw_features)
    )
    basis = _enum(raw["validation_basis"], ValidationBasis, f"{path}.validation_basis")
    if basis is ValidationBasis.SYNTHETIC_NOT_REAL:
        raise _request_error(
            "SYNTHETIC_VALIDATION_BASIS_REJECTED",
            f"{path}.validation_basis",
        )
    try:
        return DemandModelPolicy(
            target_scope=_enum(raw["target_scope"], TargetScope, f"{path}.target_scope"),
            region=_string(raw["region"], f"{path}.region"),
            target_unit=_string(raw["target_unit"], f"{path}.target_unit"),
            gas_day_calendar=_string(raw["gas_day_calendar"], f"{path}.gas_day_calendar"),
            training_cutoff=_instant(raw["training_cutoff"], f"{path}.training_cutoff"),
            validation_as_of=_instant(raw["validation_as_of"], f"{path}.validation_as_of"),
            ridge_lambda=_number(raw["ridge_lambda"], f"{path}.ridge_lambda"),
            model_version=_string(raw["model_version"], f"{path}.model_version"),
            validation_basis=basis,
            weather_features=features,
            expected_feature_policy=feature_policy,
            min_training_rows=_integer(raw["min_training_rows"], f"{path}.min_training_rows"),
            min_validation_folds=_integer(
                raw["min_validation_folds"], f"{path}.min_validation_folds"
            ),
            min_validation_predictions=_integer(
                raw["min_validation_predictions"],
                f"{path}.min_validation_predictions",
            ),
            min_oos_coverage=_number(raw["min_oos_coverage"], f"{path}.min_oos_coverage"),
            min_relative_mae_improvement=_number(
                raw["min_relative_mae_improvement"],
                f"{path}.min_relative_mae_improvement",
            ),
            min_fold_win_fraction=_number(
                raw["min_fold_win_fraction"], f"{path}.min_fold_win_fraction"
            ),
            min_residuals_for_interval=_integer(
                raw["min_residuals_for_interval"],
                f"{path}.min_residuals_for_interval",
            ),
            interval_level=_number(raw["interval_level"], f"{path}.interval_level"),
            max_training_rows=_integer(
                raw["max_training_rows"], f"{path}.max_training_rows"
            ),
            max_features=_integer(raw["max_features"], f"{path}.max_features"),
            max_folds=_integer(raw["max_folds"], f"{path}.max_folds"),
        )
    except (TypeError, ValueError):
        raise _request_error("REQUEST_POLICY_INVALID", path) from None


def _build_bridges(
    value: object,
    path: str,
    feature_policy: DegreeDayFeaturePolicy,
) -> tuple[WeatherDemandBridgeConfig, ...]:
    raw_bridges = _list(value, path)
    if not 1 <= len(raw_bridges) <= MAX_BRIDGE_DAYS:
        raise _request_error("REQUEST_INVALID_VALUE", path)
    bridges: list[WeatherDemandBridgeConfig] = []
    for index, item in enumerate(raw_bridges):
        item_path = f"{path}[{index}]"
        raw = _object(
            item,
            item_path,
            required=_BRIDGE_REQUIRED,
            optional=_BRIDGE_OPTIONAL,
        )
        raw_days = _list(raw["gas_days"], f"{item_path}.gas_days")
        if len(raw_days) != 1:
            raise _request_error("REQUEST_INVALID_VALUE", f"{item_path}.gas_days")
        days = tuple(
            _calendar_date(day, f"{item_path}.gas_days[{day_index}]")
            for day_index, day in enumerate(raw_days)
        )
        optional_values = {
            name: _integer(raw[name], f"{item_path}.{name}")
            for name in _BRIDGE_OPTIONAL
            if name in raw
        }
        try:
            bridges.append(
                WeatherDemandBridgeConfig(
                    feature_policy=feature_policy,
                    prediction_origin=_instant(
                        raw["prediction_origin"], f"{item_path}.prediction_origin"
                    ),
                    gas_days=days,
                    max_hold_minutes=_integer(
                        raw["max_hold_minutes"], f"{item_path}.max_hold_minutes"
                    ),
                    **optional_values,
                )
            )
        except (TypeError, ValueError):
            raise _request_error("REQUEST_POLICY_INVALID", item_path) from None
    return tuple(bridges)


def _build_bindings(
    value: object,
    path: str,
) -> tuple[ForecastPointBinding, ...]:
    raw_bindings = _list(value, path)
    if not raw_bindings:
        raise _request_error("REQUEST_INVALID_VALUE", path)
    bindings: list[ForecastPointBinding] = []
    for index, item in enumerate(raw_bindings):
        item_path = f"{path}[{index}]"
        raw = _object(item, item_path, required=_BINDING_REQUIRED)
        bindings.append(
            ForecastPointBinding(
                point_id=_string(raw["point_id"], f"{item_path}.point_id"),
                series_id=_string(raw["series_id"], f"{item_path}.series_id"),
                entity_id=_string(raw["entity_id"], f"{item_path}.entity_id"),
                location_id=_string(raw["location_id"], f"{item_path}.location_id"),
                region=_string(raw["region"], f"{item_path}.region"),
            )
        )
    return tuple(bindings)


def _parse_request_payload(payload: object) -> WeatherDemandRuntimeRequest:
    if not isinstance(payload, dict):
        raise _request_error("REQUEST_ROOT_NOT_OBJECT", "request")
    for policy_name in ("model_policy", "degree_day_policy"):
        if policy_name not in payload:
            raise _request_error("REQUEST_MISSING_POLICY", policy_name)
    root = _object(
        payload,
        "request",
        required=_ROOT_REQUIRED,
        optional=_ROOT_OPTIONAL,
    )
    if root["schema"] != REQUEST_SCHEMA:
        raise _request_error("REQUEST_SCHEMA_UNSUPPORTED", "schema")

    model_policy = _build_model_policy(root["model_policy"], "model_policy")
    degree_day_policy = _build_degree_day_policy(
        root["degree_day_policy"], "degree_day_policy"
    )
    bridges = _build_bridges(
        root["bridge_configs"],
        "bridge_configs",
        model_policy.expected_feature_policy,
    )
    bindings = _build_bindings(root["point_bindings"], "point_bindings")
    source_format = _string(root["source_format"], "source_format")
    if source_format not in SUPPORTED_SOURCE_FORMATS:
        raise _request_error("REQUEST_INVALID_VALUE", "source_format")

    budget: dict[str, int] = {}
    if "work_budget" in root:
        raw_budget = _object(
            root["work_budget"],
            "work_budget",
            required=frozenset(),
            optional=_BUDGET_OPTIONAL,
        )
        for name in _BUDGET_OPTIONAL:
            if name in raw_budget:
                budget[name] = _integer(raw_budget[name], f"work_budget.{name}")

    try:
        return WeatherDemandRuntimeRequest(
            model_policy=model_policy,
            degree_day_policy=degree_day_policy,
            bridge_configs=bridges,
            point_bindings=bindings,
            provider_item_id=_string(root["provider_item_id"], "provider_item_id"),
            source_format=source_format,
            target_gas_day_from=_calendar_date(
                root["target_gas_day_from"], "target_gas_day_from"
            ),
            target_gas_day_to=_calendar_date(
                root["target_gas_day_to"], "target_gas_day_to"
            ),
            allow_provisional_targets=_boolean(
                root["allow_provisional_targets"], "allow_provisional_targets"
            ),
            regional_weighting_evidence_ref=_string(
                root["regional_weighting_evidence_ref"],
                "regional_weighting_evidence_ref",
            ),
            **budget,
        )
    except (TypeError, ValueError):
        raise _request_error("REQUEST_VALIDATION_FAILED", "request") from None


def load_request(path_value: str) -> WeatherDemandRuntimeRequest:
    """Read one bounded local JSON file and build the immutable runtime request."""

    path = Path(path_value)
    try:
        if not path.is_file():
            raise _request_error("REQUEST_FILE_NOT_FOUND", "request_json")
        if path.stat().st_size > MAX_REQUEST_BYTES:
            raise _request_error("REQUEST_FILE_TOO_LARGE", "request_json")
        with path.open('rb') as stream:
            raw_bytes = stream.read(MAX_REQUEST_BYTES + 1)
    except OperatorFailure:
        raise
    except OSError:
        raise _request_error("REQUEST_FILE_READ_ERROR", "request_json") from None
    if len(raw_bytes) > MAX_REQUEST_BYTES:
        raise _request_error("REQUEST_FILE_TOO_LARGE", "request_json")
    try:
        text_value = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise _request_error("REQUEST_FILE_ENCODING_INVALID", "request_json") from None
    try:
        payload = json.loads(
            text_value,
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except _DuplicateKeyError:
        raise _request_error("REQUEST_DUPLICATE_KEY", "request") from None
    except _NonFiniteJsonError:
        raise _request_error("REQUEST_NON_FINITE_NUMBER", "request") from None
    except json.JSONDecodeError:
        raise _request_error("REQUEST_JSON_INVALID", "request") from None
    except (RecursionError, ValueError):
        raise _request_error("REQUEST_JSON_INVALID", "request") from None
    return _parse_request_payload(payload)


def _parse_args(argv: Sequence[str] | None) -> str:
    parser = _ArgumentParser(
        description=(
            "Run the read-only weather-demand research runtime for one explicit "
            "operator JSON request."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--request-json", required=True, metavar="PATH")
    args = parser.parse_args(argv)
    return args.request_json


def _safe_code(exc: Exception, fallback: str) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and _SAFE_CODE.fullmatch(code):
        return code
    return fallback


def _enforce_no_autoflush(session: Any) -> None:
    if getattr(session, "autoflush", None) is not False:
        try:
            session.autoflush = False
        except Exception:
            raise OperatorFailure(
                "SESSION_AUTOFLUSH_REQUIRED",
                2,
                "DATABASE_ERROR",
                category="DATABASE",
            ) from None
    if getattr(session, "autoflush", None) is not False:
        raise OperatorFailure(
            "SESSION_AUTOFLUSH_REQUIRED",
            2,
            "DATABASE_ERROR",
            category="DATABASE",
        )


def _require_postgresql(session: Any) -> None:
    try:
        dialect_name = session.get_bind().dialect.name
    except Exception:
        raise OperatorFailure(
            "DATABASE_DIALECT_UNKNOWN",
            2,
            "DATABASE_ERROR",
            category="DATABASE",
        ) from None
    if dialect_name != "postgresql":
        raise OperatorFailure(
            "POSTGRESQL_REQUIRED",
            2,
            "DATABASE_ERROR",
            category="DATABASE",
        )


def _rollback_and_close(session: Any) -> Exception | None:
    failure: Exception | None = None
    try:
        session.rollback()
    except Exception as exc:
        failure = exc
    try:
        session.close()
    except Exception as exc:
        if failure is None:
            failure = exc
    return failure


def _execute(
    request: WeatherDemandRuntimeRequest,
    session_factory_provider: Callable[[], Callable[[], Any]],
) -> WeatherDemandRuntimeResult:
    try:
        session_factory = session_factory_provider()
    except ValueError:
        raise OperatorFailure(
            "DATABASE_URL_MISSING",
            2,
            "DATABASE_ERROR",
            category="DATABASE",
        ) from None
    except Exception:
        raise OperatorFailure(
            "DATABASE_CONFIGURATION_ERROR",
            2,
            "DATABASE_ERROR",
            category="DATABASE",
        ) from None

    try:
        session = session_factory()
    except Exception:
        raise OperatorFailure(
            "DATABASE_SESSION_ERROR",
            2,
            "DATABASE_ERROR",
            category="DATABASE",
        ) from None

    result: WeatherDemandRuntimeResult | None = None
    rollback_failure: Exception | None = None
    try:
        _enforce_no_autoflush(session)
        _require_postgresql(session)
        try:
            session.execute(text("SET TRANSACTION READ ONLY"))
        except Exception:
            raise OperatorFailure(
                "DATABASE_READ_ONLY_TRANSACTION_FAILED",
                2,
                "DATABASE_ERROR",
                category="DATABASE",
            ) from None
        try:
            result = run_weather_demand_runtime(session, request)
        except MissingNumpyError:
            raise OperatorFailure(
                "NUMPY_NOT_INSTALLED",
                1,
                "NUMPY_NOT_INSTALLED",
                category="SOURCE",
            ) from None
        except _AMBIGUITY_ERRORS as exc:
            raise OperatorFailure(
                _safe_code(exc, "SOURCE_AMBIGUITY"),
                1,
                "SOURCE_AMBIGUITY",
                category="SOURCE",
            ) from None
        except WeatherDemandInputError as exc:
            raise OperatorFailure(
                _safe_code(exc, "SOURCE_INPUT_REFUSED"),
                1,
                "SOURCE_REFUSED",
                category="SOURCE",
            ) from None
        except WeatherDemandRuntimeError:
            raise OperatorFailure(
                "REQUEST_VALIDATION_FAILED",
                2,
                "REQUEST_INVALID",
                category="REQUEST",
            ) from None
        except SQLAlchemyError:
            raise OperatorFailure(
                "DATABASE_ERROR",
                2,
                "DATABASE_ERROR",
                category="DATABASE",
            ) from None
        except Exception:
            raise OperatorFailure(
                "INTERNAL_ERROR",
                2,
                "INTERNAL_ERROR",
                category="INTERNAL",
            ) from None
    finally:
        rollback_failure = _rollback_and_close(session)

    if rollback_failure is not None:
        raise OperatorFailure(
            "DATABASE_ROLLBACK_OR_CLOSE_FAILED",
            2,
            "DATABASE_ERROR",
            category="DATABASE",
        ) from None
    if result is None:
        raise OperatorFailure(
            "INTERNAL_ERROR",
            2,
            "INTERNAL_ERROR",
            category="INTERNAL",
        )
    return result


def _database_evidence(*, read_only: bool) -> dict[str, object]:
    return {
        "required_dialect": "postgresql",
        "read_only_transaction": read_only,
        "commit_issued": False,
    }


def _missing_inputs(result: WeatherDemandRuntimeResult) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if result.status is WeatherDemandRuntimeStatus.NUMPY_NOT_INSTALLED:
        items.append({"code": MissingNumpyError.code})
        return items
    if result.status is not WeatherDemandRuntimeStatus.INSUFFICIENT_REAL_HISTORY:
        return items
    for diagnostic in result.diagnostics:
        item: dict[str, object] = {
            "code": diagnostic.code.value,
            "scope": "diagnostic",
        }
        if diagnostic.gas_day is not None:
            item["gas_day"] = diagnostic.gas_day.isoformat()
        items.append(item)
    for omission in result.omitted_days:
        items.append(
            {
                "code": omission.reason.value,
                "scope": "omitted_day",
                "gas_day": omission.gas_day.isoformat(),
                "bridge_codes": [
                    diagnostic.code.value for diagnostic in omission.bridge_diagnostics
                ],
            }
        )
    return items


def _model_summary(result: WeatherDemandRuntimeResult) -> dict[str, object] | None:
    model_result = result.model_result
    if model_result is None:
        return None
    selected = model_result.selected_model
    return {
        "selection_status": model_result.selection_status.value,
        "selected_model_kind": selected.kind.value,
        "selected_use_status": selected.use_status.value,
        "native_unit": result.native_unit,
        "target_scope": selected.target_scope.value,
        "region": selected.region,
        "model_version": selected.model_version,
        "method_version": selected.method_version,
        "training_rows": selected.training_rows,
        "baseline_model_kind": model_result.baseline_model.kind.value,
        "candidate_model_present": model_result.candidate_model is not None,
    }


def _result_summary(result: WeatherDemandRuntimeResult) -> dict[str, object]:
    evidence = result.evidence
    return {
        "schema": SUMMARY_SCHEMA,
        "status": result.status.value,
        "research_only": result.research_only,
        "research_label": result.research_label,
        "production_promotion": result.production_promotion.value,
        "request_hash": result.request_hash,
        "counts": {
            "target_revision_count": result.target_revision_count,
            "target_distinct_gas_days": result.target_distinct_gas_days,
            "feature_day_count": result.feature_day_count,
            "forecast_raw_count": result.forecast_raw_count,
            "paired_eligible_training_day_count": (
                result.paired_eligible_training_day_count
            ),
            "selected_vintage_count": len(result.selected_vintages),
            "omitted_day_count": len(result.omitted_days),
            "diagnostic_count": len(result.diagnostics),
        },
        "hashes": {
            "request_hash": result.request_hash,
            "feature_policy_hash": evidence.feature_policy_hash,
            "baseline_model_hash": evidence.baseline_model_hash,
            "candidate_model_hash": evidence.candidate_model_hash,
            "selected_model_hash": evidence.selected_model_hash,
            "model_selection_hash": evidence.model_selection_hash,
        },
        "model": _model_summary(result),
        "source_evidence": {
            "provider_item_id": result.provider_item_id,
            "source_format": result.source_format,
            "native_unit": result.native_unit,
            "target_revision_ids": list(evidence.target_revision_ids),
            "target_source_refs": list(evidence.target_source_refs),
            "forecast_observation_ids": list(evidence.forecast_observation_ids),
            "feature_source_refs": list(evidence.feature_source_refs),
            "degree_day_source_refs": list(evidence.degree_day_source_refs),
            "selected_vintage_ids": list(evidence.selected_vintage_ids),
            "feature_policy_hash": evidence.feature_policy_hash,
            "degree_day_method_version": evidence.degree_day_method_version,
            "training_cutoff": evidence.training_cutoff.isoformat(),
            "validation_as_of": evidence.validation_as_of.isoformat(),
            "validation_basis": evidence.validation_basis.value,
            "regional_weighting_evidence_ref": (
                evidence.regional_weighting_evidence_ref
            ),
            "regional_weighting_evidence_basis": (
                evidence.regional_weighting_evidence_basis
            ),
        },
        "source_basis": {
            "provider_item_id": result.provider_item_id,
            "source_format": result.source_format,
            "validation_basis": evidence.validation_basis.value,
            "regional_weighting_evidence_ref": (
                evidence.regional_weighting_evidence_ref
            ),
            "regional_weighting_evidence_basis": (
                evidence.regional_weighting_evidence_basis
            ),
        },
        "missing_inputs": _missing_inputs(result),
        "database": _database_evidence(read_only=True),
        "error": None,
    }


def _failure_summary(
    failure: OperatorFailure,
    request: WeatherDemandRuntimeRequest | None,
) -> dict[str, object]:
    request_hash = request.request_hash if request is not None else None
    return {
        "schema": SUMMARY_SCHEMA,
        "status": failure.status,
        "research_only": True,
        "research_label": RESEARCH_ONLY_LABEL,
        "production_promotion": "NOT_PROMOTED",
        "request_hash": request_hash,
        "counts": None,
        "hashes": {
            "request_hash": request_hash,
            "feature_policy_hash": None,
            "baseline_model_hash": None,
            "candidate_model_hash": None,
            "selected_model_hash": None,
            "model_selection_hash": None,
        },
        "model": None,
        "source_evidence": None,
        "source_basis": None,
        "missing_inputs": [],
        "database": _database_evidence(read_only=False),
        "error": {
            "code": failure.code,
            "category": failure.category,
            "field": failure.field,
        },
    }


def _emit(summary: Mapping[str, object]) -> None:
    encoded = json.dumps(
        summary,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    sys.stdout.write(encoded + "\n")


def run(
    argv: Sequence[str] | None = None,
    *,
    session_factory_provider: Callable[[], Callable[[], Any]] = get_session_factory,
) -> int:
    """Execute one operator request and return the stable exit code."""

    request: WeatherDemandRuntimeRequest | None = None
    try:
        request = load_request(_parse_args(argv))
    except OperatorFailure as failure:
        _emit(_failure_summary(failure, request))
        return failure.exit_code
    except Exception:
        failure = OperatorFailure(
            "INTERNAL_ERROR",
            2,
            "INTERNAL_ERROR",
            category="INTERNAL",
        )
        _emit(_failure_summary(failure, request))
        return 2

    try:
        result = _execute(request, session_factory_provider)
    except OperatorFailure as failure:
        _emit(_failure_summary(failure, request))
        return failure.exit_code
    except Exception:
        failure = OperatorFailure(
            "INTERNAL_ERROR",
            2,
            "INTERNAL_ERROR",
            category="INTERNAL",
        )
        _emit(_failure_summary(failure, request))
        return 2

    if (result.status is WeatherDemandRuntimeStatus.READY) != (
        result.model_result is not None
    ):
        failure = OperatorFailure(
            "INTERNAL_ERROR",
            2,
            "INTERNAL_ERROR",
            category="INTERNAL",
        )
        _emit(_failure_summary(failure, request))
        return 2

    try:
        summary = _result_summary(result)
    except Exception:
        failure = OperatorFailure(
            "INTERNAL_ERROR",
            2,
            "INTERNAL_ERROR",
            category="INTERNAL",
        )
        _emit(_failure_summary(failure, request))
        return 2
    _emit(summary)
    return 0 if result.status is WeatherDemandRuntimeStatus.READY else 1


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
