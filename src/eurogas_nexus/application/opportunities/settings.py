"""The organisation's opportunity thresholds (decision L5 defaults), stored and audited."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.domain.opportunities.controls import Thresholds, thresholds_from

SETTING_KEY = "thresholds"


def load_thresholds(session) -> Thresholds:
    """The stored thresholds over the defaults (defaults when none are stored)."""

    from eurogas_nexus.db.models import OpportunitySettingRecord

    row = session.get(OpportunitySettingRecord, SETTING_KEY)
    if row is None:
        return Thresholds()
    try:
        return thresholds_from(dict(row.value_json or {}))
    except ValueError:
        # A stored value outside today's bounds falls back to the defaults, never to nothing.
        return Thresholds()


def save_thresholds(session, values: dict[str, Any], *, actor: str) -> Thresholds:
    """Validate and store changed settings; audited with the values before and after.

    Raises:
        ThresholdError: a setting outside its bounds.
    """

    from eurogas_nexus.application.audit_service import record_governed_audit
    from eurogas_nexus.db.models import OpportunitySettingRecord

    before = load_thresholds(session)
    after = thresholds_from(values, before)
    now = datetime.now(UTC)
    stored = {
        key: value
        for key, value in after.to_json().items()
        if key not in {"min_margin", "min_value"}
    }
    stored["min_margin"] = after.min_margin.to_json()["value"]
    stored["min_value"] = after.min_value.to_json()["value"]
    row = session.get(OpportunitySettingRecord, SETTING_KEY)
    if row is None:
        session.add(
            OpportunitySettingRecord(
                setting_key=SETTING_KEY, value_json=stored, updated_by=actor, updated_at_utc=now
            )
        )
    else:
        row.value_json = stored
        row.updated_by = actor
        row.updated_at_utc = now
    record_governed_audit(
        session,
        event_type="governance.settings",
        principal=actor,
        action="opportunities.thresholds.update",
        resource="opportunity_settings:thresholds",
        outcome="updated",
        detail=json.dumps({"before": before.to_json(), "after": after.to_json()}, sort_keys=True),
        source_system="opportunities-api",
        now_utc=now,
    )
    session.flush()
    return after
