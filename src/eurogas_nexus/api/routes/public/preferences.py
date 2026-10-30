"""Personal preferences (/api/me/preferences) and organisation defaults.

The user owns their preferences; the platform administrator owns the organisation
defaults. Neither changes what a person may see: they choose how permitted data is shown.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from eurogas_nexus.domain.settings.preferences import (
    SettingsError,
    effective_preferences,
    validate_organisation_defaults,
    validate_preferences,
)
from eurogas_nexus.security.authorization import Permission, authorize

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
        try:
            import json

            from eurogas_nexus.db.repositories.audit import record_audit_event

            record_audit_event(
                session,
                event_type="governance.settings",
                principal=principal.principal_id,
                action="settings.organisation.update",
                resource="organisation_settings",
                outcome="updated",
                detail=json.dumps(
                    {"before": before, "after": {**before, **accepted}}, sort_keys=True
                ),
                source_system="settings-api",
                now_utc=now,
            )
        except Exception:  # noqa: BLE001 - same policy as access administration audit
            pass
        session.commit()
        return _env(_organisation(session))
