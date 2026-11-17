"""Which scheduled public sources need a provider key, and whether it is configured.

The customer runtime runs every scheduled public source through one path: the data-ops
scheduler (``scripts/ops/run_dataops_scheduler.py``). Sources in the key-only and
approval-and-key classes (``domain.ingestion.source_approval``) need the firm's own
registered key, held server-side (environment, key file or the Credentials screen):

- without a key their scheduled attempt does not start the ingest script; it is recorded
  as ``CONFIGURATION credential_missing`` (never retried, shown on Admin -> Data sources);
- a keyed source that is off by default (ENTSO-E, GIE, GIE IIP) and that no operator has
  switched off is switched on at the first scheduler scan after its key is stored
  (:func:`activate_keyed_sources`), so storing the key is the whole set-up step.

The approval class is the ingestion gate's business (``source_not_approved``); this module
never approves anything.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

#: Scheduled source id -> credential provider whose key the source reads with.
SCHEDULED_SOURCE_KEYS: dict[str, str] = {
    "src-eia": "EIA",
    "src-entsoe": "ENTSOE",
    "src-gie": "GIE",
    "src-remit-umm": "GIE",  # GIE IIP accepts the AGSI/ALSI key
}


def key_configured(source_id: str, *, session_factory=None) -> bool | None:
    """Whether the key ``source_id`` reads with is configured; ``None`` if it needs none.

    The resolvers the ingest scripts use: environment, key file, then the encrypted store;
    an operator-disabled stored credential counts as not configured.
    """

    provider = SCHEDULED_SOURCE_KEYS.get(source_id)
    if provider is None:
        return None
    try:
        if provider == "GIE":
            from eurogas_nexus.ingestion.gie_transport import (
                resolve_gie_api_key,
                stored_gie_credential_status,
                stored_gie_credential_value,
            )

            # Whether a key exists, apart from whether the source is switched on: the
            # runtime resolver refuses any key while the GIE operation is off, which is
            # exactly the state a key-gated source starts in. A disabled stored key is none.
            if stored_gie_credential_status(session_factory) == "disabled":
                return False
            return (
                resolve_gie_api_key(
                    credential_lookup=lambda: stored_gie_credential_value(session_factory)
                )
                is not None
            )
        from eurogas_nexus.security.provider_credentials import resolve_provider_credential

        return resolve_provider_credential(provider) is not None
    except Exception:  # noqa: BLE001 - an unreadable key state is not a configured key
        return False


def activate_keyed_sources(
    session, *, now_utc: datetime | None = None, session_factory=None
) -> list[str]:
    """Switch on keyed scheduled sources whose key now exists; returns the source ids.

    Only a source that is off, was never activated, and was not switched off by an operator
    (circuit ``DISABLED``) is switched on: an operator's decision always stands.
    """

    from eurogas_nexus.application.dataops_runtime import set_source_enabled
    from eurogas_nexus.db.models import SourceRuntimeStateRecord
    from eurogas_nexus.domain.dataops.contracts import CircuitState

    now = now_utc or datetime.now(UTC)
    activated: list[str] = []
    for source_id in SCHEDULED_SOURCE_KEYS:
        state: Any = session.get(SourceRuntimeStateRecord, source_id)
        if state is None or state.enabled or state.activated_at_utc is not None:
            continue
        if state.circuit_state == CircuitState.DISABLED.value:
            continue
        if key_configured(source_id, session_factory=session_factory):
            set_source_enabled(session, source_id=source_id, enabled=True, now_utc=now)
            activated.append(source_id)
    return activated
