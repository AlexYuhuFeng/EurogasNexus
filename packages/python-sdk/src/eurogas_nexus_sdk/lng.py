"""SDK client for /api/lng.

The current GIE ALSI read surface publishes TWh measurements keyed by
``terminal_id``/``terminal_name``. Only source measurements carrying explicit
energy data are represented as TWh; a raw LNG volume is not converted without a
calorific factor. The coordinates and mcm capacity carried by the original SDK
models are not part of that payload: they remain explicit, optional legacy fields
and are never derived from the actual TWh fields.
"""

from pydantic import BaseModel

from eurogas_nexus_sdk import _http


class LngTerminal(BaseModel):
    """An LNG terminal returned by ``GET /api/lng/terminals``.

    Attributes:
        terminal_id: Stable identifier of the terminal.
        name: Display name of the terminal.
        country: Country code published with the terminal row.
        inventory_twh: Latest inventory in TWh, populated only when the source
            carries an explicit ``gwh`` value; None when only an LNG volume or
            no measurement is published.
        send_out_twh_d: Latest send-out in TWh/day, converted from the source's
            scalar GWh/day value; None when not published.
        dtmi_twh: Declared Total Maximum Inventory (DTMI) in TWh, populated
            only when the source carries an explicit ``gwh`` value. DTMI is not
            a days-to-monitor estimate; None when only an LNG volume or no
            measurement is published.
        observed_at_utc: Capture time of the observation the row aggregates;
            None only for legacy constructions.
        source_system: Source that produced the row; None only for legacy
            constructions.
        status: Status published by the API (``observed``). The default keeps
            the original carrier usable for legacy callers.
        lat: Legacy latitude. The API publishes no coordinates, so this is
            None unless a caller explicitly supplies a legacy value.
        lon: Legacy longitude; see ``lat``.
        capacity_mcm_d: Legacy regasification capacity in mcm/day. Never
            converted from the TWh fields.
        storage_capacity_mcm: Legacy LNG storage capacity in mcm. Never
            converted from the TWh fields.
    """

    terminal_id: str
    name: str
    country: str
    inventory_twh: float | None = None
    send_out_twh_d: float | None = None
    dtmi_twh: float | None = None
    observed_at_utc: str | None = None
    source_system: str | None = None
    status: str = "operational"
    # Legacy carriers only: the actual API publishes neither geo coordinates
    # nor mcm capacity, so these stay None instead of being invented.
    lat: float | None = None
    lon: float | None = None
    capacity_mcm_d: float | None = None
    storage_capacity_mcm: float | None = None


class LngObservation(BaseModel):
    """One ALSI observation returned by ``GET /api/lng/observations``.

    Attributes:
        observation_id: Stable observation identifier.
        terminal_id: ALSI terminal code from the API.
        terminal_name: Terminal display name.
        country: Country code supplied with the terminal row; None only for
            legacy constructions that predate the field.
        source_dataset: Source dataset label (for example ``ALSI``).
        inventory_twh: Gas inventory in TWh, populated only when the source
            carries an explicit ``gwh`` value; None when only an LNG volume or
            no measurement is published.
        send_out_twh_d: Send-out rate in TWh/day, converted from the source's
            scalar GWh/day value; None when absent.
        dtmi_twh: Declared Total Maximum Inventory (DTMI) in TWh, populated
            only when the source carries an explicit ``gwh`` value. DTMI is not
            a days-to-monitor estimate; None when only an LNG volume or no
            measurement is published.
        period_start_utc: UTC period start supplied by the API.
        period_end_utc: UTC period end supplied by the API.
        observed_at_utc: Capture time; None only for legacy constructions.
        source_system: Source system; None only for legacy constructions.
        source_reference: Source reference; None only for legacy constructions.
        freshness: Source freshness verdict; None only for legacy constructions.
        research_only: Research-only flag published by the API.
        observation_type: Legacy observation kind. The current API does not
            publish it, so API rows leave it as None.
        value_mcm: Legacy mcm value. This is never converted from the TWh
            fields.
    """

    observation_id: str
    terminal_id: str
    terminal_name: str
    country: str | None = None
    source_dataset: str | None = None
    inventory_twh: float | None = None
    send_out_twh_d: float | None = None
    dtmi_twh: float | None = None
    period_start_utc: str = ""
    period_end_utc: str = ""
    observed_at_utc: str | None = None
    source_system: str | None = None
    source_reference: str | None = None
    freshness: str | None = None
    research_only: bool = True
    # Legacy carriers only: accepted for existing callers, never fabricated
    # for an API row and never converted between mcm and TWh.
    observation_type: str | None = None
    value_mcm: float | None = None


def _get(url: str) -> dict:
    """GET a JSON envelope and return the parsed payload."""

    r = _http.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_lng_terminals(base_url: str) -> list[LngTerminal]:
    """Return all LNG regasification terminals.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All LNG terminals currently exposed by the backend.
    """

    return [LngTerminal(**t) for t in _get(f"{base_url}/api/lng/terminals")["data"]]


def fetch_lng_observations(base_url: str) -> list[LngObservation]:
    """Return all LNG send-out and inventory observations.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All LNG observations currently exposed by the backend.
    """

    url = f"{base_url}/api/lng/observations"
    return [LngObservation(**o) for o in _get(url)["data"]]
