"""DatasetSpec, immutable DatasetSnapshot metadata, and point-in-time builder.

The builder owns forecast-origin alignment, bounded feature computation,
target labelling, leakage validation, quality reporting, and content hashing.
It does not own model training.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from eurogas_nexus.domain.research.features import FeatureDefinition
from eurogas_nexus.domain.research.leakage import LeakageValidator
from eurogas_nexus.domain.research.resampling import ResamplingPolicy
from eurogas_nexus.domain.research.targets import TargetDefinition
from eurogas_nexus.domain.research.temporal import (
    DatasetMode,
    DatasetPointInTimePolicy,
    ObservationKind,
    TemporalIntegrityState,
    as_of_eligible,
    forecast_vintage_at,
)


def _json_safe(value: Any) -> Any:
    """Make metadata JSON-serializable without losing temporal semantics."""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class DatasetSplitType(StrEnum):
    TIME_SPLIT = "TIME_SPLIT"


class DatasetSplit(BaseModel):
    """One time-based split specification."""

    name: str
    split_type: DatasetSplitType = DatasetSplitType.TIME_SPLIT
    start: datetime
    end: datetime
    embargo_before: timedelta = Field(default=timedelta(0))
    gap_after: timedelta = Field(default=timedelta(0))

    def contains(self, value: datetime) -> bool:
        value_utc = _utc(value)
        return _utc(self.start) <= value_utc < _utc(self.end)


class DatasetSpec(BaseModel):
    """Declarative, versioned dataset definition."""

    dataset_spec_id: str
    name: str
    description: str
    version: str = "dataset-spec/v1"
    target_ids: list[str]
    feature_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    start: datetime
    end: datetime
    history_lookback: timedelta = Field(default=timedelta(days=7))
    forecast_origin_frequency: str = "1h"
    timezone: str = "UTC"
    point_in_time_policy: DatasetPointInTimePolicy = Field(default_factory=DatasetPointInTimePolicy)
    resampling_policy_id: str = "resampling/v1"
    missing_data_policy: str = "mask"
    minimum_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    source_restrictions: list[str] = Field(default_factory=list)
    entitlement_envelope: dict[str, str] = Field(default_factory=dict)
    split_specs: list[DatasetSplit] = Field(default_factory=list)
    output_format: str = "long"
    ontology_version: str = "energy-ontology/v1"

    def content_hash(self) -> str:
        encoded = json.dumps(self.model_dump(mode="json"), sort_keys=True, default=str).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()

    def qualified_version(self) -> str:
        return f"{self.dataset_spec_id}@{self.version}@{self.content_hash()[:8]}"


class DatasetEvidenceRecord(BaseModel):
    """One point-in-time evidence record consumed by the builder."""

    record_id: str
    series_id: str
    entity_id: str | None = None
    observed_at: datetime
    available_at: datetime | None = None
    ingested_at: datetime | None = None
    value: float
    unit: str
    currency: str | None = None
    observation_kind: ObservationKind = ObservationKind.ACTUAL
    temporal_integrity: TemporalIntegrityState = TemporalIntegrityState.TEMPORAL_VERIFIED
    source_reference: str = "synthetic"
    forecast_issued_at: datetime | None = None
    forecast_valid_start: datetime | None = None
    forecast_valid_end: datetime | None = None
    quality_state: str = "OBSERVED"
    is_observed: bool = True
    is_imputed: bool = False
    imputation_method: str | None = None
    source_age_seconds: float | None = None
    export_policy: str = "EXPORT_ALLOWED"


@dataclass
class DatasetBuildResult:
    """Immutable materialization result."""

    dataset_snapshot_id: str
    spec: DatasetSpec
    rows: list[dict[str, Any]]
    columns: list[str]
    quality_report: dict[str, Any]
    leakage_issues: list[dict[str, Any]]
    lineage: list[str]
    content_hash: str
    warnings: list[str] = field(default_factory=list)

    def as_metadata(self) -> dict[str, Any]:
        return {
            "dataset_snapshot_id": self.dataset_snapshot_id,
            "dataset_spec_id": self.spec.dataset_spec_id,
            "dataset_spec_version": self.spec.qualified_version(),
            "ontology_version": self.spec.ontology_version,
            "row_count": len(self.rows),
            "column_count": len(self.columns),
            "columns": self.columns,
            "content_hash": self.content_hash,
            "quality_report": self.quality_report,
            "lineage": self.lineage,
            "warnings": self.warnings,
            "temporal_integrity": self.quality_report.get("temporal_integrity"),
            "source_cutoff_utc": _json_safe(self.spec.end),
            "entitlement_envelope": _json_safe(self.spec.entitlement_envelope),
            "leakage_issues": _json_safe(self.leakage_issues),
        }


FeatureComputer = Callable[
    [FeatureDefinition, dict[str, list[float]], dict[str, Any]], float | None
]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _origins(spec: DatasetSpec) -> list[datetime]:
    current = _utc(spec.start)
    end = _utc(spec.end)
    if spec.forecast_origin_frequency.endswith("h"):
        step = timedelta(hours=int(spec.forecast_origin_frequency[:-1]))
    elif spec.forecast_origin_frequency.endswith("d"):
        step = timedelta(days=int(spec.forecast_origin_frequency[:-1]))
    else:
        raise ValueError(f"unsupported forecast_origin_frequency: {spec.forecast_origin_frequency}")
    origins = []
    while current < end:
        origins.append(current)
        current += step
    return origins


def _records_by_series(
    records: list[DatasetEvidenceRecord], origin: datetime, *, spec: DatasetSpec
) -> dict[str, DatasetEvidenceRecord | None]:
    grouped: dict[str, list[DatasetEvidenceRecord]] = {}
    for record in records:
        grouped.setdefault(record.series_id, []).append(record)
    selected: dict[str, DatasetEvidenceRecord | None] = {}
    for series_id, candidates in grouped.items():
        eligible = [
            record
            for record in candidates
            if as_of_eligible(record, origin, policy=spec.point_in_time_policy)[0]
            and (
                spec.point_in_time_policy.allow_simulated
                or record.observation_kind is not ObservationKind.SIMULATED
            )
        ]
        if not eligible:
            selected[series_id] = None
            continue
        forecasts = [
            record
            for record in eligible
            if record.observation_kind is ObservationKind.FORECAST
            and spec.point_in_time_policy.allow_forecast_vintages
        ]
        if forecasts:
            selected[series_id] = forecast_vintage_at(forecasts=forecasts, cutoff=origin)
        else:
            selected[series_id] = max(eligible, key=lambda item: _utc(item.observed_at))
    return selected


def _feature_temporal_integrity(
    selected: dict[str, DatasetEvidenceRecord | None],
    dependency_ids: list[str],
) -> str:
    """Propagate the weakest temporal integrity of the inputs actually used."""

    states: list[str] = []
    for series_id in dependency_ids:
        record = selected.get(series_id)
        if record is None:
            return TemporalIntegrityState.TEMPORAL_INSUFFICIENT.value
        states.append(str(record.temporal_integrity.value))
    if any(state == TemporalIntegrityState.TEMPORAL_INSUFFICIENT.value for state in states):
        return TemporalIntegrityState.TEMPORAL_INSUFFICIENT.value
    if any(state == TemporalIntegrityState.TEMPORAL_APPROXIMATE.value for state in states):
        return TemporalIntegrityState.TEMPORAL_APPROXIMATE.value
    return TemporalIntegrityState.TEMPORAL_VERIFIED.value


def _compute_builtin_feature(
    feature: FeatureDefinition,
    series_values: dict[str, list[float]],
    context: dict[str, Any],
) -> float | None:
    feature_id = feature.feature_id
    if feature_id == "NBP_TTF_DA_SPREAD":
        nbp = series_values.get("market.price.NBP.DAY_AHEAD", [])
        ttf = series_values.get("market.price.TTF.DAY_AHEAD", [])
        if not nbp or not ttf or nbp[-1] is None or ttf[-1] is None:
            return None
        return round(float(nbp[-1]) - float(ttf[-1]), 4)
    if feature_id == "ROUTE_MARGIN":
        price = series_values.get("market.price.NBP.DAY_AHEAD", [])
        cost = context.get("route_cost_gbp_mwh")
        if not price or price[-1] is None or cost is None:
            return None
        return round(float(price[-1]) - float(cost), 4)
    return None


def _target_series_ids(target: TargetDefinition) -> list[str]:
    """Map a semantic target metric to canonical series ids.

    Keep this mapping explicit and versioned with TargetDefinition; it is a
    label-calculation contract, not implicit string matching.
    """

    metric = str(target.metric).strip().upper()
    if metric == "NBP_DA_PRICE_D1":
        return ["market.price.NBP.DAY_AHEAD"]
    if metric == "TTF_DA_PRICE_D1":
        return ["market.price.TTF.DAY_AHEAD"]
    if metric == "NBP_TTF_SPREAD_D1":
        return ["market.price.NBP.DAY_AHEAD", "market.price.TTF.DAY_AHEAD"]
    return [target.metric]


def _compute_target_value(
    target: TargetDefinition,
    records: list[DatasetEvidenceRecord],
    origin: datetime,
    *,
    allow_simulated: bool = False,
) -> tuple[float | None, list[str], bool]:
    """Compute a realized target label strictly after origin + horizon.

    Target realization is intentionally future knowledge used only in the
    target column; feature construction is point-in-time and never sees it.
    Simulated inputs are allowed only when the versioned point-in-time policy
    explicitly opts in, and the resulting label is flagged as simulated.
    """

    allowed_kinds = {ObservationKind.ACTUAL}
    if allow_simulated:
        allowed_kinds.add(ObservationKind.SIMULATED)
    delta = _target_delta(target)
    threshold = _utc(origin) + delta
    series_ids = _target_series_ids(target)
    candidates = [
        record
        for record in records
        if record.series_id in series_ids
        and record.observation_kind in allowed_kinds
        and _utc(record.observed_at) >= threshold
    ]
    if not candidates:
        return None, [], False
    if len(series_ids) == 2:
        left_series, right_series = series_ids
        left = min(
            (record for record in candidates if record.series_id == left_series),
            key=lambda record: _utc(record.observed_at),
            default=None,
        )
        right = min(
            (record for record in candidates if record.series_id == right_series),
            key=lambda record: _utc(record.observed_at),
            default=None,
        )
        if left is None or right is None:
            return None, [], False
        value = round(float(left.value) - float(right.value), 4)
        simulated = (
            left.observation_kind is ObservationKind.SIMULATED
            or right.observation_kind is ObservationKind.SIMULATED
        )
        return value, [left.source_reference, right.source_reference], simulated
    selected = min(candidates, key=lambda record: _utc(record.observed_at))
    return (
        selected.value,
        [selected.source_reference],
        selected.observation_kind is ObservationKind.SIMULATED,
    )


def _target_delta(target: TargetDefinition) -> timedelta:
    horizon = target.horizon
    if horizon.endswith("h"):
        return timedelta(hours=int(horizon[:-1]))
    if horizon.endswith("d"):
        return timedelta(days=int(horizon[:-1]))
    return timedelta(hours=1)


def build_dataset(
    spec: DatasetSpec,
    records: list[DatasetEvidenceRecord],
    features: dict[str, FeatureDefinition],
    targets: dict[str, TargetDefinition],
    resampling_policy: ResamplingPolicy,
    *,
    feature_computers: dict[str, FeatureComputer] | None = None,
    snapshot_id: str | None = None,
) -> DatasetBuildResult:
    """Build a point-in-time dataset and return an immutable result."""

    issues = []
    if spec.minimum_coverage < 0 or spec.minimum_coverage > 1:
        issues.append("minimum_coverage must be between 0 and 1")
    for feature_id in spec.feature_ids:
        if feature_id not in features:
            issues.append(f"unknown feature_id: {feature_id}")
    for target_id in spec.target_ids:
        if target_id not in targets:
            issues.append(f"unknown target_id: {target_id}")
    overlap = set(spec.feature_ids) & set(spec.target_ids)
    if overlap:
        issues.append(f"target ids used as features: {sorted(overlap)}")
    if issues:
        raise ValueError("; ".join(issues))

    origins = _origins(spec)
    rows: list[dict[str, Any]] = []
    lineage = [record.source_reference for record in records]
    validator = LeakageValidator(mode=spec.point_in_time_policy.mode.value)
    computers = feature_computers or {}

    for origin in origins:
        selected = _records_by_series(records, origin, spec=spec)
        series_values: dict[str, list[float | None]] = {}
        for series_id, record in selected.items():
            series_values.setdefault(series_id, []).append(
                record.value if record is not None else None
            )
        for feature_id in spec.feature_ids:
            feature = features[feature_id]
            values = {
                series_id: series_values.get(series_id, [None])
                for series_id in feature.input_dependencies
            }
            computer = computers.get(feature_id)
            value = (
                computer(feature, values, {})
                if computer
                else _compute_builtin_feature(feature, values, {})
            )
            row_source_refs = sorted(
                {
                    record.source_reference
                    for series_id in feature.input_dependencies
                    if (record := selected.get(series_id)) is not None
                }
            )
            row = {
                "forecast_origin": origin,
                "feature_id": feature_id,
                "value": value,
                "unit": feature.output_unit,
                "availability_class": feature.availability_class.value,
                "is_observed": value is not None,
                "is_imputed": False,
                "quality_state": "OBSERVED" if value is not None else "MISSING",
                "available_at": origin,
                "temporal_integrity": _feature_temporal_integrity(
                    selected, feature.input_dependencies
                ),
                "source_refs": row_source_refs,
            }
            rows.append(row)
        for target_id in spec.target_ids:
            target = targets[target_id]
            target_value, source_refs, is_simulated = _compute_target_value(
                target,
                records,
                origin,
                allow_simulated=spec.point_in_time_policy.allow_simulated,
            )
            rows.append(
                {
                    "forecast_origin": origin,
                    "target_id": target_id,
                    "target_value": target_value,
                    "unit": target.unit,
                    "is_observed": target_value is not None,
                    "is_simulated": is_simulated,
                    "quality_state": "OBSERVED" if target_value is not None else "MISSING",
                    "available_at": origin,
                    "temporal_integrity": "TEMPORAL_VERIFIED",
                    "source_refs": source_refs,
                }
            )

    leakage = validator.validate(rows, target_ids=set(spec.target_ids))
    leakage_issues = [issue.as_dict() for issue in leakage]
    blockers = [issue for issue in leakage_issues if issue["severity"] == "BLOCKER"]
    warnings = [issue for issue in leakage_issues if issue["severity"] == "WARNING"]

    quality = _quality_report(spec, rows, records, origins)
    content_hash = _hash_rows(rows, spec)
    resolved_snapshot_id = snapshot_id or (
        f"dataset-snapshot-{content_hash[:12]}-{spec.dataset_spec_id}"
    )

    result = DatasetBuildResult(
        dataset_snapshot_id=resolved_snapshot_id,
        spec=spec,
        rows=rows,
        columns=sorted({key for row in rows for key in row}),
        quality_report=quality,
        leakage_issues=leakage_issues,
        lineage=list(dict.fromkeys(lineage)),
        content_hash=content_hash,
        warnings=[
            f"EXPLORATORY_DATASET:{spec.point_in_time_policy.mode.value}"
            if spec.point_in_time_policy.mode is DatasetMode.EXPLORATORY
            else None,
            *warnings,
        ],
    )
    if blockers and spec.point_in_time_policy.mode is DatasetMode.STRICT:
        result.quality_report["build_blocked"] = True
    return result


def _quality_report(
    spec: DatasetSpec,
    rows: list[dict[str, Any]],
    records: list[DatasetEvidenceRecord],
    origins: list[datetime],
) -> dict[str, Any]:
    total = len(rows)
    observed = sum(1 for row in rows if row.get("is_observed"))
    missing = total - observed
    temporal_states = {str(record.temporal_integrity.value) for record in records}
    return {
        "rows": total,
        "origins": len(origins),
        "observed_values": observed,
        "missing_values": missing,
        "missing_percentage": round(missing / total * 100, 2) if total else 0.0,
        "temporal_integrity": (
            "TEMPORAL_VERIFIED"
            if temporal_states <= {"TEMPORAL_VERIFIED"}
            else "TEMPORAL_APPROXIMATE"
            if "TEMPORAL_INSUFFICIENT" not in temporal_states
            else "TEMPORAL_INSUFFICIENT"
        ),
        "minimum_coverage": spec.minimum_coverage,
        "coverage": round(observed / total, 4) if total else 0.0,
        "build_blocked": False,
        "source_count": len({record.source_reference for record in records}),
    }


def _hash_rows(rows: list[dict[str, Any]], spec: DatasetSpec) -> str:
    payload = {"spec": spec.qualified_version(), "rows": rows}
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
