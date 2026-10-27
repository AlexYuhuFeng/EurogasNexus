"""SDK client for /api/storage.

The current GIE AGSI read surface publishes TWh measurements keyed by
``facility_id``/``facility_name``. The coordinates and mcm capacity carried by
the original SDK models are not part of that payload: they remain explicit,
optional legacy fields and are never derived from the actual TWh fields.
"""

from typing import Any, Self

from pydantic import BaseModel, model_validator

from eurogas_nexus_sdk import _http


class StorageSite(BaseModel):
    """A storage site returned by ``GET /api/storage/sites``.

    Attributes:
        site_id: Facility code the API uses as the site identifier.
        name: Facility display name.
        country: Country code published with the facility row.
        working_capacity_twh: Working gas capacity in TWh; None when the
            source does not publish it for this facility.
        fill_pct: Latest fill percentage; None when not published.
        observed_at_utc: Capture time of the observation the site row
            aggregates; None only for legacy constructions.
        source_system: Source that produced the row; None only for legacy
            constructions.
        status: Status published by the API (``observed``). The default keeps
            the original carrier usable for legacy callers.
        lat: Legacy latitude. The API publishes no coordinates, so this is
            None unless a caller explicitly supplies a legacy value.
        lon: Legacy longitude; see ``lat``.
        working_capacity_mcm: Legacy mcm capacity. This is never converted from
            ``working_capacity_twh``.
    """

    site_id: str
    name: str
    country: str
    working_capacity_twh: float | None = None
    fill_pct: float | None = None
    observed_at_utc: str | None = None
    source_system: str | None = None
    status: str = "operational"
    # Legacy carriers only: the actual API publishes neither geo coordinates
    # nor mcm capacity, so these stay None instead of being invented.
    lat: float | None = None
    lon: float | None = None
    working_capacity_mcm: float | None = None


class StorageObservation(BaseModel):
    """One AGSI observation returned by ``GET /api/storage/observations``.

    Attributes:
        observation_id: Stable observation identifier.
        facility_id: AGSI facility code from the API.
        facility_name: Facility display name.
        country: Country code supplied with the facility row; None only for
            legacy constructions that predate the field.
        source_dataset: Source dataset label (for example ``AGSI``).
        inventory_twh: Gas in storage in TWh; None when not published.
        working_capacity_twh: Working gas capacity in TWh; None when absent.
        fill_pct: Fill percentage; None when absent.
        injection_twh_d: Injection rate in TWh/day; None when absent.
        withdrawal_twh_d: Withdrawal rate in TWh/day; None when absent.
        period_start_utc: UTC period start supplied by the API.
        period_end_utc: UTC period end supplied by the API.
        observed_at_utc: Capture time; None only for legacy constructions.
        source_system: Source system; None only for legacy constructions.
        source_reference: Source reference; None only for legacy constructions.
        freshness: Source freshness verdict; None only for legacy constructions.
        research_only: Research-only flag published by the API.
        site_id: Legacy identifier alias for ``facility_id``; accepted as input
            and mirrored from the canonical field.
        site_name: Legacy name alias for ``facility_name``.
        observation_type: Legacy observation kind. The current API does not
            publish it, so API rows leave it as None.
        volume_mcm: Legacy mcm volume. This is never converted from the TWh
            fields.
    """

    observation_id: str
    facility_id: str
    facility_name: str
    country: str | None = None
    source_dataset: str | None = None
    inventory_twh: float | None = None
    working_capacity_twh: float | None = None
    fill_pct: float | None = None
    injection_twh_d: float | None = None
    withdrawal_twh_d: float | None = None
    period_start_utc: str = ""
    period_end_utc: str = ""
    observed_at_utc: str | None = None
    source_system: str | None = None
    source_reference: str | None = None
    freshness: str | None = None
    research_only: bool = True
    # Legacy carriers only: accepted for existing callers, never fabricated
    # for an API row and never converted between mcm and TWh.
    site_id: str | None = None
    site_name: str | None = None
    observation_type: str | None = None
    volume_mcm: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_identifiers(cls, data: Any) -> Any:
        """Map the original ``site_*`` names onto the API's ``facility_*`` names."""

        if not isinstance(data, dict):
            return data
        values = dict(data)
        if not values.get("facility_id") and values.get("site_id"):
            values["facility_id"] = values["site_id"]
        if not values.get("facility_name") and values.get("site_name"):
            values["facility_name"] = values["site_name"]
        return values

    @model_validator(mode="after")
    def _mirror_legacy_identifiers(self) -> Self:
        """Keep the legacy aliases populated for objects built from API rows."""

        if self.site_id is None:
            self.site_id = self.facility_id
        if self.site_name is None:
            self.site_name = self.facility_name
        return self


def _get(url: str) -> dict:
    """GET a JSON envelope and return the parsed payload."""

    r = _http.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_storage_sites(base_url: str) -> list[StorageSite]:
    """Return all storage sites.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All storage sites currently exposed by the backend.
    """

    return [StorageSite(**s) for s in _get(f"{base_url}/api/storage/sites")["data"]]


def fetch_storage_observations(base_url: str) -> list[StorageObservation]:
    """Return all storage observations.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All storage observations currently exposed by the backend.
    """

    url = f"{base_url}/api/storage/observations"
    return [StorageObservation(**o) for o in _get(url)["data"]]
