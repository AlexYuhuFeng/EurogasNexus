"""The frozen form of an opportunity: what a version stores and a case carries as evidence."""

from __future__ import annotations

from typing import Any

from eurogas_nexus.domain.opportunities.controls import Assessment
from eurogas_nexus.domain.opportunities.model import TYPE_CODE, Candidate, decimal_text
from eurogas_nexus.domain.valuation.quality import CLASS_LABEL


def freeze(candidate: Candidate, assessment: Assessment) -> dict[str, Any]:
    """Every part of the object B.2 names, as JSON (decimals as text)."""

    def measure(item):
        return None if item is None else item.to_json()

    return {
        "type": candidate.type.value,
        "type_code": TYPE_CODE[candidate.type],
        "lane": candidate.lane.value,
        "key": candidate.key,
        "claim": {
            "key": candidate.claim_key,
            "fields": dict(candidate.claim_fields),
            "text": assessment.claim_text,
        },
        "headline": candidate.headline.to_json(),
        "volume": measure(candidate.volume),
        "value": measure(candidate.value),
        "reporting_value": measure(candidate.value_eur),
        "reporting_margin": measure(candidate.margin_eur),
        "period": {
            "label": candidate.period.label,
            "start": candidate.period.start.isoformat(),
            "end": candidate.period.end.isoformat(),
        },
        "book_ids": list(candidate.book_ids),
        "legs": [leg.to_json() for leg in candidate.legs],
        "assumptions": [item.to_json() for item in candidate.assumptions],
        "falsifiers": [item.to_json() for item in candidate.falsifiers],
        "sensitivity": [item.to_json() for item in candidate.sensitivity],
        "checks": [item.to_json() for item in candidate.checks],
        "quality": {
            "class": candidate.quality.value,
            "label": CLASS_LABEL[candidate.quality],
            "simulated": candidate.simulated,
            "inputs": [
                {
                    "key": item.key,
                    "kind": item.kind.value,
                    "class": item.input_class.value,
                    "label": item.label,
                    "source_family": item.source_family,
                    "source_ref": item.source_ref,
                    "as_of_utc": None if item.as_of_utc is None else item.as_of_utc.isoformat(),
                    "value": decimal_text(item.value),
                    "unit": item.unit,
                }
                for item in candidate.inputs
            ],
        },
        "validity": {
            "expires_at_utc": candidate.expires_at_utc.isoformat(),
            "deadline_utc": (
                None if candidate.deadline_utc is None else candidate.deadline_utc.isoformat()
            ),
        },
        "dependency_keys": list(candidate.dependency_keys),
        "assessment": {
            "state": None if assessment.state is None else assessment.state.value,
            "reasons": list(assessment.reasons),
            "blocker": None if assessment.blocker is None else assessment.blocker.to_json(),
        },
        "evaluator": {"name": candidate.evaluator, "version": candidate.evaluator_version},
    }
