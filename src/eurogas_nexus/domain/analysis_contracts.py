"""Content-addressed manifests and task-specific interval readiness."""

import hashlib
import json
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


def content_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def analysis_manifest(
    kind: str,
    engine: str,
    inputs: dict,
    *,
    versions: dict[str, str] | None = None,
    scopes: tuple[str, ...] = (),
) -> dict:
    manifest = {
        "schema": "analysis-manifest/1",
        "kind": kind,
        "engine_version": engine,
        "input_hash": content_hash(inputs),
        "version_refs": versions or {},
        "required_source_scopes": sorted(set(scopes)),
        "input_basis": "EXPLICIT_FROZEN_INPUTS",
    }
    return {**manifest, "manifest_hash": content_hash(manifest)}


def compare_analysis(left: dict, right: dict) -> dict:
    keys = sorted(set(left) | set(right))
    return {
        "changed": [
            {"field": key, "left": left.get(key), "right": right.get(key)}
            for key in keys
            if left.get(key) != right.get(key)
        ],
        "same_engine": left.get("engine_version") == right.get("engine_version"),
        "same_inputs": left.get("input_hash") == right.get("input_hash"),
    }


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    requirement_id: str = Field(min_length=1, max_length=80)
    series_id: str = Field(min_length=1, max_length=160)
    entity_id: str = Field(min_length=1, max_length=160)
    product: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=40)
    start: AwareDatetime
    end: AwareDatetime
    maximum_age_seconds: int = Field(ge=0, le=366 * 86400)
    source_priority: tuple[str, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def valid_window(self):
        if self.end <= self.start or len(set(self.source_priority)) != len(self.source_priority):
            raise ValueError("invalid readiness window/source priority")
        return self


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    series_id: str = Field(min_length=1, max_length=160)
    entity_id: str = Field(min_length=1, max_length=160)
    product: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=40)
    start: AwareDatetime
    end: AwareDatetime
    record_id: str = Field(min_length=1, max_length=160)
    source: str = Field(min_length=1, max_length=80)
    available_at: AwareDatetime
    observed_at: AwareDatetime
    revision: int = Field(ge=0)
    record_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    quality_status: Literal["VALIDATED", "UNKNOWN", "REJECTED"] = "UNKNOWN"

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end <= self.start or self.observed_at > self.available_at:
            raise ValueError("invalid evidence interval or availability clock")
        return self


class ReadinessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of: AwareDatetime
    requirements: tuple[Requirement, ...] = Field(min_length=1, max_length=64)
    evidence: tuple[Evidence, ...] = Field(default=(), max_length=4096)

    @model_validator(mode="after")
    def unique_identities(self):
        if len({r.requirement_id for r in self.requirements}) != len(self.requirements):
            raise ValueError("duplicate readiness requirement identifier")
        if len({r.record_id for r in self.evidence}) != len(self.evidence):
            raise ValueError("duplicate evidence record identifier")
        return self


def evaluate_readiness(payload: ReadinessRequest, checkpoint=lambda: None) -> dict:
    output = []
    for need in payload.requirements:
        checkpoint()
        eligible = [
            row
            for row in payload.evidence
            if (row.series_id, row.entity_id, row.product, row.unit)
            == (need.series_id, need.entity_id, need.product, need.unit)
            and row.source in need.source_priority
            and row.quality_status == "VALIDATED"
            and row.available_at <= payload.as_of
            and row.observed_at <= payload.as_of
            and (payload.as_of - row.observed_at).total_seconds() <= need.maximum_age_seconds
            and row.start < need.end
            and row.end > need.start
        ]
        selected = {}
        for row in eligible:
            key = (row.source, row.start, row.end)
            old = selected.get(key)
            if old is None or (row.revision, row.available_at, row.record_id) > (
                old.revision,
                old.available_at,
                old.record_id,
            ):
                selected[key] = row
        # Select independently per atomic interval; sources never silently override priority.
        boundaries = sorted(
            {
                need.start,
                need.end,
                *(max(need.start, r.start) for r in selected.values()),
                *(min(need.end, r.end) for r in selected.values()),
            }
        )
        gaps, used = [], {}
        for start, end in zip(boundaries, boundaries[1:], strict=False):
            checkpoint()
            rows = [r for r in selected.values() if r.start <= start and r.end >= end]
            if not rows:
                gaps.append({"start": start.isoformat(), "end": end.isoformat()})
                continue
            row = min(
                rows,
                key=lambda r: (
                    need.source_priority.index(r.source),
                    -r.revision,
                    -r.available_at.timestamp(),
                    r.record_id,
                ),
            )
            used[row.record_id] = row.record_hash
        output.append(
            {
                "requirement_id": need.requirement_id,
                "ready": not gaps,
                "missing_intervals": gaps,
                "record_versions": used,
                "backfill_windows": [
                    {
                        "series_id": need.series_id,
                        "entity_id": need.entity_id,
                        "product": need.product,
                        "source_priority": list(need.source_priority),
                        **gap,
                    }
                    for gap in gaps
                ],
            }
        )
    return {
        "ready": all(row["ready"] for row in output),
        "requirements": output,
        "dependency_hash": content_hash(output),
        "basis": "DECLARED_EVIDENCE_AS_OF",
    }
