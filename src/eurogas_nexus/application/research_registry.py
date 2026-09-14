"""Shared canonical-registry resolution for a DatasetSpec (CR14-SEMANTICS-001).

Both ``POST /api/research/datasets/validate`` and every build path (the HTTP
route and the ``dataset.build`` capability) resolve a spec's registry ids through
this module, so a spec that validates can never fail differently at build time
and an unknown id can never pass validation.

Design notes:

- Resolution is read-only and works on the *requested* ids only, so one corrupt
  unrelated registry row cannot break an otherwise valid request.
- Every failure is a structured field-level issue ``{"field", "code",
  "message"}``. Messages are bounded and safe: they never contain SQL, stack
  traces, or raw exception text.
- Entity ids are resolved to ``CanonicalEntityRecord`` rows and returned in the
  exact canonical form the builder filters on, so ``spec.entity_ids`` has real
  runtime effect instead of being accepted and ignored.
- The resampling policy is resolved by the requested ``resampling_policy_id``
  (never "the first registry row"), and a policy the point-in-time builder
  cannot honour exactly is reported as a structured error rather than ignored.
- Resolution never authorizes anything. Source authorization stays in
  ``security.research_entitlement`` and is evaluated independently at build and
  export time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from eurogas_nexus.domain.research.datasets import DatasetSpec
from eurogas_nexus.domain.research.features import FeatureDefinition
from eurogas_nexus.domain.research.ontology import canonical_entity_id
from eurogas_nexus.domain.research.resampling import (
    ResamplingPolicy,
    builder_support_issues,
)
from eurogas_nexus.domain.research.targets import TargetDefinition
from eurogas_nexus.security.research_entitlement import definition_for_runtime_source

if TYPE_CHECKING:  # pragma: no cover - import boundary: the API must not import SQLAlchemy
    from sqlalchemy.orm import Session

ISSUE_FIELD_MAX_LENGTH = 128


@dataclass(frozen=True)
class DatasetRegistryResolution:
    """One spec's resolved registry inputs plus structured resolution issues."""

    features: dict[str, FeatureDefinition] = field(default_factory=dict)
    targets: dict[str, TargetDefinition] = field(default_factory=dict)
    resampling_policy: ResamplingPolicy | None = None
    entity_ids: tuple[str, ...] = ()
    issues: tuple[dict[str, str], ...] = ()

    @property
    def ok(self) -> bool:
        return not self.issues

    def issue_list(self) -> list[dict[str, str]]:
        return [dict(issue) for issue in self.issues]

    def issue_messages(self) -> list[str]:
        return [issue["message"] for issue in self.issues]


class DatasetRegistryError(ValueError):
    """Raised when a build is requested with unresolvable registry ids."""

    error_code = "dataset_registry_invalid"

    def __init__(self, issues: list[dict[str, str]] | tuple[dict[str, str], ...]) -> None:
        self.issues = [dict(issue) for issue in issues]
        detail = "; ".join(issue.get("message", "") for issue in self.issues)
        super().__init__(detail or "dataset registry resolution failed")


def _issue(field_name: str, code: str, message: str) -> dict[str, str]:
    return {"field": field_name, "code": code, "message": message}


def _echo(value: Any) -> str:
    return str(value)[:ISSUE_FIELD_MAX_LENGTH]


def resolve_dataset_registry(session: Session, spec: DatasetSpec) -> DatasetRegistryResolution:
    """Resolve every registry id a DatasetSpec references, without side effects."""

    from eurogas_nexus.db.models import (
        CanonicalEntityRecord,
        FeatureDefinitionRecord,
        ResamplingPolicyRecord,
        TargetDefinitionRecord,
    )

    issues: list[dict[str, str]] = []
    features: dict[str, FeatureDefinition] = {}
    targets: dict[str, TargetDefinition] = {}
    entity_ids: list[str] = []
    resampling_policy: ResamplingPolicy | None = None

    if not spec.target_ids:
        issues.append(
            _issue(
                "target_ids",
                "target_required",
                "at least one target_id is required",
            )
        )

    for feature_id in spec.feature_ids:
        row = session.get(FeatureDefinitionRecord, feature_id)
        if row is None:
            issues.append(
                _issue(
                    "feature_ids",
                    "unknown_feature_id",
                    f"unknown feature_id: {_echo(feature_id)}",
                )
            )
            continue
        try:
            features[feature_id] = FeatureDefinition.model_validate(row.definition_json)
        except Exception:
            issues.append(
                _issue(
                    "feature_ids",
                    "feature_definition_invalid",
                    f"stored feature definition is invalid: {_echo(feature_id)}",
                )
            )

    for target_id in spec.target_ids:
        row = session.get(TargetDefinitionRecord, target_id)
        if row is None:
            issues.append(
                _issue(
                    "target_ids",
                    "unknown_target_id",
                    f"unknown target_id: {_echo(target_id)}",
                )
            )
            continue
        try:
            targets[target_id] = TargetDefinition.model_validate(row.definition_json)
        except Exception:
            issues.append(
                _issue(
                    "target_ids",
                    "target_definition_invalid",
                    f"stored target definition is invalid: {_echo(target_id)}",
                )
            )

    overlap = sorted(set(spec.feature_ids) & set(spec.target_ids))
    if overlap:
        issues.append(
            _issue(
                "feature_ids",
                "target_used_as_feature",
                f"target ids used as features: {_echo(overlap)}",
            )
        )

    for entity_id in spec.entity_ids:
        row = session.get(CanonicalEntityRecord, entity_id)
        if row is None:
            issues.append(
                _issue(
                    "entity_ids",
                    "unknown_entity_id",
                    f"unknown canonical entity_id: {_echo(entity_id)}",
                )
            )
            continue
        expected = canonical_entity_id(row.entity_type, row.canonical_code)
        if expected != row.canonical_entity_id:
            issues.append(
                _issue(
                    "entity_ids",
                    "entity_registry_inconsistent",
                    f"canonical entity row does not match its identity: {_echo(entity_id)}",
                )
            )
            continue
        if row.canonical_entity_id not in entity_ids:
            entity_ids.append(row.canonical_entity_id)

    for source_id in spec.source_restrictions:
        if definition_for_runtime_source(source_id) is None:
            issues.append(
                _issue(
                    "source_restrictions",
                    "unknown_source_id",
                    f"unknown registered source provider: {_echo(source_id)}",
                )
            )

    policy_row = session.get(ResamplingPolicyRecord, spec.resampling_policy_id)
    if policy_row is None:
        issues.append(
            _issue(
                "resampling_policy_id",
                "unknown_resampling_policy_id",
                f"unknown resampling_policy_id: {_echo(spec.resampling_policy_id)}",
            )
        )
    else:
        try:
            # The registry row key is the authoritative policy identity, so the
            # stored definition cannot silently claim a different policy_id.
            resampling_policy = ResamplingPolicy.model_validate(
                {**(policy_row.definition_json or {}), "policy_id": policy_row.policy_id}
            )
        except Exception:
            resampling_policy = None
            issues.append(
                _issue(
                    "resampling_policy_id",
                    "resampling_policy_definition_invalid",
                    "stored resampling policy definition is invalid: "
                    f"{_echo(spec.resampling_policy_id)}",
                )
            )
        if resampling_policy is not None:
            unsupported = builder_support_issues(resampling_policy)
            if unsupported:
                issues.append(
                    _issue(
                        "resampling_policy_id",
                        "resampling_policy_unsupported",
                        "the requested resampling policy cannot be honoured: "
                        + "; ".join(unsupported),
                    )
                )

    return DatasetRegistryResolution(
        features=features,
        targets=targets,
        resampling_policy=resampling_policy,
        entity_ids=tuple(entity_ids),
        issues=tuple(issues),
    )


def require_dataset_registry(session: Session, spec: DatasetSpec) -> DatasetRegistryResolution:
    """Resolve a spec's registry ids, raising when the spec cannot be built."""

    resolution = resolve_dataset_registry(session, spec)
    if not resolution.ok:
        raise DatasetRegistryError(resolution.issues)
    return resolution
