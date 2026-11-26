"""Personal preferences (/api/me/preferences) and organisation defaults.

The user owns their preferences; the platform administrator owns the organisation
defaults. Neither changes what a person may see: they choose how permitted data is shown.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from eurogas_nexus.domain.ai.register import AI_FEATURES_SETTING
from eurogas_nexus.domain.pricing.financial_institutions import SETTING as INSTITUTIONS_SETTING
from eurogas_nexus.domain.pricing.source_precedence import SETTING as SOURCE_PRECEDENCE_SETTING
from eurogas_nexus.domain.settings.preferences import (
    SettingsError,
    effective_preferences,
    validate_organisation_defaults,
    validate_preferences,
)
from eurogas_nexus.governance.four_eyes import FOUR_EYES_SETTING
from eurogas_nexus.security.authorization import Permission, authorize

MERGED_SETTINGS = frozenset(
    {AI_FEATURES_SETTING, FOUR_EYES_SETTING, SOURCE_PRECEDENCE_SETTING, INSTITUTIONS_SETTING}
)

router = APIRouter(tags=["preferences"])


def _env(data: object) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": False,
            "source_references": ["runtime-postgresql"],
            "warnings": [],
        },
    }


def _principal_id(request: Request) -> str:
    principal = getattr(request.state, "identity", None)
    principal_id = getattr(principal, "principal_id", None)
    if not principal_id or getattr(principal, "auth_method", "") == "legacy_public_token":
        # The shared compatibility token is not a person; it has no preferences.
        raise HTTPException(status_code=401, detail={"code": "named_principal_required"})
    return str(principal_id)


def _session():
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_required"})
    return get_session_factory()()


def _organisation(session) -> dict[str, Any]:
    from eurogas_nexus.db.models import OrganisationSettingRecord

    return {row.setting_key: row.value_json for row in session.query(OrganisationSettingRecord)}


def _payload(session, principal_id: str) -> dict[str, Any]:
    from eurogas_nexus.db.models import PrincipalPreferenceRecord

    organisation = _organisation(session)
    row = session.get(PrincipalPreferenceRecord, principal_id)
    personal = dict(row.preferences_json) if row else {}
    return {
        "personal": personal,
        "organisation_defaults": organisation,
        "effective": effective_preferences(organisation, personal),
        "updated_at_utc": row.updated_at_utc.isoformat() if row else None,
    }


@router.get("/api/me/preferences")
def read_preferences(request: Request) -> dict:
    """The caller's own choices, the organisation defaults, and what takes effect.

    返回本人偏好、组织默认值与最终生效值。
    """

    principal_id = _principal_id(request)
    with _session() as session:
        return _env(_payload(session, principal_id))


@router.put("/api/me/preferences")
def write_preferences(body: dict[str, Any], request: Request) -> dict:
    """Merge the caller's choices; ``null`` clears one back to the organisation default.

    Raises:
        HTTPException: 422 ``preference_invalid`` for an unknown key or value.
    """

    from eurogas_nexus.db.models import PrincipalPreferenceRecord

    principal_id = _principal_id(request)
    try:
        accepted = validate_preferences(body)
    except SettingsError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "preference_invalid", "message": str(exc)}
        ) from exc
    cleared = {key for key, value in body.items() if value is None}
    with _session() as session:
        row = session.get(PrincipalPreferenceRecord, principal_id)
        merged = {**(row.preferences_json if row else {}), **accepted}
        merged = {key: value for key, value in merged.items() if key not in cleared}
        now = datetime.now(UTC)
        if row is None:
            session.add(
                PrincipalPreferenceRecord(
                    principal_id=principal_id, preferences_json=merged, updated_at_utc=now
                )
            )
        else:
            row.preferences_json = merged
            row.updated_at_utc = now
        session.commit()
        return _env(_payload(session, principal_id))


@router.get("/api/settings/organisation")
def read_organisation_settings(request: Request) -> dict:
    """Organisation defaults every signed-in user starts from."""

    with _session() as session:
        return _env(_organisation(session))


@router.put("/api/settings/organisation")
def write_organisation_settings(body: dict[str, Any], request: Request) -> dict:
    """Set organisation defaults (platform administrators only); audited.

    Raises:
        HTTPException: 403 without identity administration; 422 ``setting_invalid``.
    """

    from eurogas_nexus.db.models import OrganisationSettingRecord

    principal = getattr(request.state, "identity", None)
    if principal is None or not authorize(principal, Permission.IDENTITY_MANAGE).allowed:
        raise HTTPException(status_code=403, detail={"code": "permission_denied"})
    try:
        accepted = validate_organisation_defaults(body)
    except SettingsError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "setting_invalid", "message": str(exc)}
        ) from exc
    with _session() as session:
        before = _organisation(session)
        now = datetime.now(UTC)
        for key, value in accepted.items():
            row = session.get(OrganisationSettingRecord, key)
            if (
                key in MERGED_SETTINGS
                and row is not None
                and isinstance(row.value_json, dict)
            ):
                # Switches merge: turning one AI use (or one write's four eyes) off leaves the
                # others as they were.
                # TAR-2: the source order and the banks merge per kind / institution too; a
                # bank set to null is removed.
                value = {
                    k: v for k, v in {**row.value_json, **value}.items() if v is not None
                }
            if isinstance(value, dict) and key in MERGED_SETTINGS:
                value = {k: v for k, v in value.items() if v is not None}
            if row is None:
                session.add(
                    OrganisationSettingRecord(
                        setting_key=key,
                        value_json=value,
                        updated_by=principal.principal_id,
                        updated_at_utc=now,
                    )
                )
            else:
                row.value_json = value
                row.updated_by = principal.principal_id
                row.updated_at_utc = now
        from eurogas_nexus.application.audit_service import record_governed_audit

        session.flush()
        after = _organisation(session)
        # GOV-1 (P5): organisation defaults include the AI switches, a governed write: the
        # audit row is part of it and the change fails without it.
        record_governed_audit(
            session,
            event_type="governance.settings",
            principal=principal.principal_id,
            action="settings.organisation.update",
            resource="organisation_settings",
            outcome="updated",
            detail=json.dumps({"before": before, "after": after}, sort_keys=True)[:4000],
            source_system="settings-api",
            now_utc=now,
            before_summary=before or None,
            after_summary=after,
        )
        session.commit()
        return _env(_organisation(session))
