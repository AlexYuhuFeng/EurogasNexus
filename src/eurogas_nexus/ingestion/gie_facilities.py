"""GIE AGSI+/ALSI facility listing: per-facility identity (EIC, name, country, operator).

``https://agsi.gie.eu/api/about?show=listing`` and the ALSI equivalent answer with the
registered GIE key (``x-key``, the key ``src-gie`` already uses): a list of operators
(company name, short name, EIC, country), each with its facilities (name, GIE type code, EIC,
country, operational start and end dates). Live on 2026-11-16: 128 storage and 41 LNG
facility rows, 159 distinct EICs. The listing carries **no coordinates**, so it gives
identity, not a position. GIE's terms: reuse with GIE credited (``docs/legal``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

LISTING_URLS = {
    "storage": "https://agsi.gie.eu/api/about?show=listing",
    "lng": "https://alsi.gie.eu/api/about?show=listing",
}
MAX_LISTING_BYTES = 2 * 1024 * 1024


class GieListingError(RuntimeError):
    """A stable, operator-safe failure (never carries the key or a response body)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class GieFacility:
    eic: str
    name: str
    country: str
    kind: str  # storage | lng
    gie_type: str  # GIE's code: ASF, DSR, ASR, GRP, SRC (storage); LAND, FSRU (LNG)
    operator_name: str
    operator_eic: str
    operational_end_date: str | None

    def metadata(self) -> dict[str, Any]:
        return {
            "source_system": "GIE",
            "eic": self.eic,
            "name": self.name,
            "country": self.country,
            "kind": self.kind,
            "gie_type": self.gie_type,
            "operator_name": self.operator_name,
            "operator_eic": self.operator_eic,
            "operational_end_date": self.operational_end_date,
            # GIE publishes no coordinates; a position comes only from an accepted source.
            "position": None,
        }


def parse_listing(payload: Any, kind: str) -> list[GieFacility]:
    """Facilities of one listing response; raises ``GieListingError`` on a wrong shape."""

    if kind not in LISTING_URLS:
        raise ValueError(f"unknown listing kind {kind!r}")
    if not isinstance(payload, list):
        raise GieListingError("gie_listing_malformed", "the listing is not a list")
    facilities = []
    for company in payload:
        if not isinstance(company, Mapping):
            continue
        for item in company.get("facilities") or []:
            if not isinstance(item, Mapping):
                continue
            eic = str(item.get("eic") or "").strip().upper()
            name = str(item.get("name") or "").strip()
            if not eic or not name:
                continue
            facilities.append(
                GieFacility(
                    eic=eic,
                    name=name,
                    country=str(item.get("country") or company.get("country") or "").upper(),
                    kind=kind,
                    gie_type=str(item.get("type") or ""),
                    operator_name=str(company.get("name") or "").strip(),
                    operator_eic=str(company.get("eic") or "").strip().upper(),
                    operational_end_date=item.get("operational_end_date") or None,
                )
            )
    return facilities


def one_per_eic(facilities: Iterable[GieFacility]) -> tuple[list[GieFacility], list[str]]:
    """One facility per EIC, and the EICs GIE lists more than once.

    GIE lists a few EICs twice (live: 8 of 159), typically a facility's current row beside a
    row closed by ``operational_end_date``. The open row wins; between two open (or two
    closed) rows the first listed is kept and the EIC is reported.
    """

    chosen: dict[str, GieFacility] = {}
    repeated: list[str] = []
    for facility in facilities:
        held = chosen.get(facility.eic)
        if held is None:
            chosen[facility.eic] = facility
            continue
        repeated.append(facility.eic)
        if held.operational_end_date and not facility.operational_end_date:
            chosen[facility.eic] = facility
    return list(chosen.values()), sorted(set(repeated))


def http_listing_getter(api_key: str, *, timeout: float = 60.0):
    """A bounded reader for the two fixed listing URLs; the key goes only in ``x-key``."""

    import json

    import httpx

    from eurogas_nexus.core.outbound_http import client_options

    client = httpx.Client(
        timeout=timeout, follow_redirects=False, trust_env=False,
        **client_options(LISTING_URLS["storage"]),
    )

    def get(kind: str) -> Any:
        try:
            response = client.get(
                LISTING_URLS[kind], headers={"x-key": api_key, "Accept": "application/json"}
            )
        except httpx.HTTPError:
            raise GieListingError("gie_listing_unreachable", "no answer") from None
        if response.status_code != 200:
            raise GieListingError("gie_listing_http_status", f"HTTP {response.status_code}")
        if len(response.content) > MAX_LISTING_BYTES:
            raise GieListingError("gie_listing_too_large", "listing larger than the bound")
        try:
            return json.loads(response.content)
        except ValueError:
            raise GieListingError("gie_listing_malformed", "the listing is not JSON") from None

    get.close = client.close  # type: ignore[attr-defined]
    return get
