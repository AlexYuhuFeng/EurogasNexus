"""Europe's main import supply corridors: where gas from outside the ENTSOG system enters it.

A corridor is an import pipeline (or a group of them landing together) seen from the European
side: the source country, the operator, the ENTSOG point(s) where it enters the European
system, the ENTSOG flow series a reader follows there, the firm technical capacity ENTSOG
publishes, and its current status. The table below (``CORRIDORS``) is curated: which pipeline
lands at which ENTSOG point. Every figure and every status comes from a cited source and is
written into the shipped file ``supply_corridors.json`` by
``scripts/ops/build_supply_corridors.py``:

- **entry points, operators, positions**: ENTSOG Transparency Platform ``connectionpoints``,
  ``operatorpointdirections`` and ``operators`` (positions are ENTSOG's map positions,
  transformed for display, never surveyed);
- **capacity**: ENTSOG ``operationaldatas``, indicator Firm Technical, the build's gas day, as
  the operator published it (kWh/d);
- **status**: ENTSOG ``operationaldatas``, indicator Physical Flow at the corridor's entry
  series. A corridor with physical flow in the last 30 closed gas days is ``in_service``; one
  without is ``out_of_service`` since the day after the last gas day with flow ENTSOG
  publishes in the probed window (``status_rule``). No status is typed by hand;
- **pipeline facts** (from, to, length, diameter, first gas): the operator's own pipeline page
  where one could be read (Gassco for the Norwegian pipelines), with the URL and read date;
- **geometry**: SciGRID_gas IGGIELGN (CC BY 4.0) where its lines join the corridor's source
  and entry (``geometry_basis: reference_pipeline_direction``); otherwise a straight
  schematic line (``geometry_basis: schematic``). A source position is the SciGRID node
  nearest the named place, or the approximate place itself (``source_position_quality``).

A corridor is presentation and fundamentals data: route pricing never reads it. The ENTSOG
flow series keys (``flow_series``: point key, operator key, direction) are those the ENTSOG
flow ingestion stores (``flow_observations.point_id`` and ``metadata_json.operatorKey``), so the
map reads the corridor's live flow from the store.

本模块：欧洲主要进口供气走廊（挪威、北非、南部走廊、俄罗斯管线）的入口点、流量序列键、容量与状态。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

RESOURCE = "supply_corridors.json"
SCHEMA = "eurogas-nexus/supply-corridors/1"
STATUSES = frozenset({"in_service", "out_of_service", "not_published"})
GEOMETRY_BASES = frozenset({"reference_pipeline_direction", "schematic"})
#: Closed gas days read for the current status.
RECENT_DAYS = 30
STATUS_RULE = (
    "ENTSOG Physical Flow at the corridor's entry series (the European operator's entry): "
    f"in_service when any series has flow above zero on one of the last {RECENT_DAYS} closed "
    "gas days before the build; otherwise out_of_service, since the day after the last gas day "
    "with flow above zero ENTSOG publishes in the probed window (none found: the window's "
    "start is a bound, stated as 'no flow published since at least'); not_published when "
    "ENTSOG publishes no flow figure at all for the entry series in the last "
    f"{RECENT_DAYS} days and no earlier flow was probed (the status is unknown, not zero)."
)

GASSCO_READ = "2026-11-26"


@dataclass(frozen=True)
class EntrySeries:
    """One ENTSOG flow series at a corridor's entry: the European operator's entry."""

    point_key: str
    operator_key: str
    direction: str = "entry"


@dataclass(frozen=True)
class Corridor:
    id: str
    name: str
    group: str  # norway | north_africa | southern_corridor | russia
    source_country: str  # ISO 3166 alpha-2 of the gas's source
    #: The upstream operator as ENTSOG lists it at the entry point (the other side).
    operator_key: str | None
    #: The ENTSOG point(s) drawn as the corridor's landing (positions come from here).
    landing_points: tuple[str, ...]
    entry_series: tuple[EntrySeries, ...]
    #: Named place at the far end and an approximate position for it (lon, lat), used only to
    #: find the SciGRID node there; stored as approximate when no node is close.
    source_place: str | None = None
    source_hint: tuple[float, float] | None = None
    #: First gas day of the window probed for the last flow when the corridor has none now.
    probe_from: str | None = None
    probe_to: str | None = None
    facts: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None
    #: The landing point's flow series also carries other gas (e.g. Langeled at Easington,
    #: which also receives UK shelf gas): the point's whole flow is not this corridor's.
    shared_entry_point: bool = False


def _gassco(slug: str, **facts: Any) -> dict[str, Any]:
    return {
        **facts,
        "source": f"Gassco, pipeline page https://gassco.eu/en/rorledningsnettverk/{slug}/",
        "read": GASSCO_READ,
    }


#: The corridors (owner's list, 2026-11-26). Entry series are the European operators' entry
#: series at each landing (``application/pipeline_supply.LANDING_POINTS`` for the Norwegian
#: landings); a landing ENTSOG publishes as one point per downstream operator (Emden, Dornum,
#: Greifswald) lists each.
CORRIDORS: tuple[Corridor, ...] = (
    Corridor(
        "langeled", "Langeled", "norway", "NO", "NO-TSO-0001",
        ("ITP-00091",), (EntrySeries("ITP-00091", "UK-TSO-0001"),),
        "Nyhamna", (7.0, 62.85),
        facts=_gassco(
            "langeled-south",
            route="Nyhamna - Sleipner - Easington",
            length_km=1116,
            diameter_inch="42 (Nyhamna - Sleipner), 44 (Sleipner - Easington)",
            first_gas="2006 (Sleipner - Easington), 2007 (Nyhamna - Sleipner)",
        ),
        notes="Easington also receives UK shelf gas: the entry series is the terminal's.",
        shared_entry_point=True,
    ),
    Corridor(
        "vesterled", "Vesterled", "norway", "NO", "NO-TSO-0001",
        ("ITP-00022",), (EntrySeries("ITP-00022", "UK-TSO-0001"),),
        "Heimdal", (2.23, 59.57),
        facts=_gassco("vesterled", route="Heimdal - St Fergus", length_km=361,
                      diameter_inch="32", first_gas="1976 (as Frigg Norwegian Pipeline)"),
        notes="St Fergus also receives UK shelf gas (FLAGS, SAGE): the entry series is the "
        "terminal's.",
        shared_entry_point=True,
    ),
    Corridor(
        "europipe-1", "Europipe I", "norway", "NO", "NO-TSO-0001",
        ("ITP-00209",),
        (
            EntrySeries("ITP-00160", "NL-TSO-0001"),
            EntrySeries("ITP-00081", "DE-TSO-0005"),
            EntrySeries("ITP-00080", "DE-TSO-0009"),
        ),
        "Draupner E", (2.47, 57.53),
        facts=_gassco("europipe", route="Draupner E - Dornum - Emden", length_km=620,
                      diameter_inch="40 (42 Dornum - Emden)", first_gas="1995"),
        notes="Landing published by ENTSOG as Emden (EPT1), one point per downstream TSO.",
    ),
    Corridor(
        "europipe-2", "Europipe II", "norway", "NO", "NO-TSO-0001",
        ("ITP-00208",),
        (EntrySeries("ITP-00188", "DE-TSO-0005"), EntrySeries("ITP-00126", "DE-TSO-0009")),
        "Kårstø", (5.53, 59.27),
        facts=_gassco("europipe-ii", route="Kårstø - Dornum", length_km=658,
                      diameter_inch="42", first_gas="1999"),
        notes="Landing published by ENTSOG as Dornum / NETRA, one point per downstream TSO.",
    ),
    Corridor(
        "norpipe", "Norpipe", "norway", "NO", "NO-TSO-0001",
        ("ITP-00210",),
        (
            EntrySeries("ITP-00161", "NL-TSO-0001"),
            EntrySeries("ITP-00086", "DE-TSO-0005"),
            EntrySeries("ITP-00075", "DE-TSO-0002"),
        ),
        "Ekofisk", (3.22, 56.54),
        facts=_gassco("norpipe", route="Ekofisk - Emden", length_km=431,
                      diameter_inch="36", first_gas="1977"),
        notes="Landing published by ENTSOG as Emden (NPT), one point per downstream TSO.",
    ),
    Corridor(
        "zeepipe", "Zeepipe", "norway", "NO", "NO-TSO-0001",
        ("ITP-00106",), (EntrySeries("ITP-00106", "BE-TSO-0001"),),
        "Sleipner", (1.9, 58.37),
        facts=_gassco("zeepipe", route="Sleipner - Zeebrugge", length_km=813,
                      diameter_inch="40", first_gas="1993"),
    ),
    Corridor(
        "franpipe", "Franpipe", "norway", "NO", "NO-TSO-0001",
        ("ITP-00045",), (EntrySeries("ITP-00045", "FR-TSO-0003"),),
        "Draupner E", (2.47, 57.53),
        facts=_gassco("franpipe", route="Draupner E - Dunkerque", length_km=840,
                      diameter_inch="42", first_gas="1998-07-01"),
    ),
    Corridor(
        "baltic-pipe-north-sea", "Baltic Pipe (North Sea entry)", "norway", "NO", None,
        ("ITP-00630",), (EntrySeries("ITP-00630", "DK-TSO-0001"),),
        "Kårstø (via Europipe II)", (5.53, 59.27),
        notes="Norwegian gas taken off Europipe II into Denmark (ENTSOG 'North Sea Entry'); "
        "it continues to Poland at the Baltic Pipe interconnection point (ITP-10009). ENTSOG "
        "names no upstream operator at the point.",
    ),
    Corridor(
        "medgaz", "Medgaz", "north_africa", "DZ", "ES-TSO-0001",
        ("ITP-00048",), (EntrySeries("ITP-00048", "ES-TSO-0006"),),
        "Beni Saf", (-1.38, 35.30),
    ),
    Corridor(
        "transmed", "TransMed", "north_africa", "DZ", "TN-TSO-0001",
        ("ITP-00093",), (EntrySeries("ITP-00093", "IT-TSO-0001"),),
        "Cap Bon (El Haouaria)", (11.0, 37.05),
        notes="Algerian gas through Tunisia; ENTSOG lists the Tunisian section's operator.",
    ),
    Corridor(
        "greenstream", "Greenstream", "north_africa", "LY", "LY-TSO-0001",
        ("ITP-00074",), (EntrySeries("ITP-00074", "IT-TSO-0001"),),
        "Mellitah", (12.25, 32.90),
    ),
    Corridor(
        "maghreb-europe", "Maghreb-Europe (GME)", "north_africa", "DZ", "MA-TSO-0001",
        ("ITP-00082",), (EntrySeries("ITP-00082", "ES-TSO-0006"),),
        "Strait of Gibraltar (Moroccan coast)", (-5.6, 35.85),
        probe_from="2021-10-01", probe_to="2021-11-30",
        notes="Algerian gas through Morocco. Since 2022 the point has been used Spain to "
        "Morocco (exit), which is not an import: the status reads the Spanish entry only.",
    ),
    Corridor(
        "tap", "TANAP - TAP", "southern_corridor", "AZ", "AL-TSO-0001",
        ("ITP-00274", "ITP-00008"),
        (EntrySeries("ITP-00274", "AL-TSO-0001"), EntrySeries("ITP-00008", "IT-TSO-0001")),
        None, None,
        notes="Azerbaijani gas: TANAP hands over to TAP at Kipoi (Greek-Turkish border); TAP "
        "delivers into Greece, Albania and Italy (Melendugno). Drawn Kipoi - Melendugno.",
    ),
    Corridor(
        "turkstream", "TurkStream (European string)", "southern_corridor", "RU", "TR-TSO-0004",
        ("ITP-00549",), (EntrySeries("ITP-00549", "BG-TSO-0001"),),
        "Russkaya (Anapa)", (37.35, 45.0),
        notes="Russian gas through the Black Sea and Turkey, entering the EU at Strandzha 2.",
    ),
    Corridor(
        "nord-stream-1", "Nord Stream 1", "russia", "RU", "RU-TSO-0002",
        ("ITP-00120",),
        (
            EntrySeries("ITP-00247", "DE-TSO-0001"),
            EntrySeries("ITP-00247", "DE-TSO-0017"),
            EntrySeries("ITP-00251", "DE-TSO-0001"),
            EntrySeries("ITP-00251", "DE-TSO-0016"),
            EntrySeries("ITP-00491", "DE-TSO-0005"),
            EntrySeries("ITP-00297", "DE-TSO-0018"),
            EntrySeries("ITP-00250", "DE-TSO-0015"),
            EntrySeries("ITP-00454", "DE-TSO-0020"),
        ),
        "Portovaya (Vyborg)", (28.37, 60.55),
        probe_from="2022-08-01", probe_to="2022-10-15",
        notes="Landing at Greifswald, published by ENTSOG one point per downstream pipeline "
        "(NEL, OPAL, GUD, Fluxys, GOAL, LBTG).",
    ),
    Corridor(
        "nord-stream-2", "Nord Stream 2", "russia", "RU", "RU-TSO-0003",
        ("ITP-00501",),
        (
            EntrySeries("ITP-00501", "DE-TSO-0001"),
            EntrySeries("ITP-00501", "DE-TSO-0003"),
            EntrySeries("ITP-00501", "DE-TSO-0005"),
            EntrySeries("ITP-00501", "DE-TSO-0018"),
        ),
        "Ust-Luga (Narva Bay)", (28.05, 59.63),
        probe_from="2021-09-01", probe_to="2022-10-15",
        notes="Landing at Lubmin II. ENTSOG publishes no physical flow there in the probed "
        "window: the pipeline was never put into commercial service.",
    ),
    Corridor(
        "ukraine-transit", "Ukraine transit (Brotherhood)", "russia", "RU", "UA-TSO-0001",
        ("ITP-00184", "ITP-00117"),
        (EntrySeries("ITP-00117", "SK-TSO-0001"),),
        None, None,
        probe_from="2024-12-01", probe_to="2025-01-31",
        notes="Russian gas entering Ukraine at Sudzha (ITP-00184) and the EU at Velké "
        "Kapušany (ITP-00117). Drawn Sudzha - Velké Kapušany; the status reads the Slovak "
        "entry at Velké Kapušany.",
    ),
    Corridor(
        "yamal", "Yamal-Europe", "russia", "RU", "PL-TSO-0001",
        ("ITP-00096",), (EntrySeries("ITP-00096", "DE-TSO-0001"),),
        "Kondratki (Belarus - Poland border)", (23.47, 52.39),
        probe_from="2022-04-01", probe_to="2022-07-31",
        notes="Russian gas through Belarus and Poland's transit system (TGPS) to Germany at "
        "Mallnow. ENTSOG no longer publishes the Belarus - Poland entry (Kondratki, read "
        "2026-11-26), so the status reads the German entry at Mallnow; flow from Germany to "
        "Poland there since 2022 is an exit, not an import.",
    ),
)


def corridors_path() -> Path:
    return Path(str(resources.files("eurogas_nexus.reference_data").joinpath(RESOURCE)))


def load_corridors(path: str | Path | None = None) -> dict[str, Any]:
    return json.loads(Path(path or corridors_path()).read_text(encoding="utf-8"))


def classify_status(
    recent_flow_days: int,
    last_flow_day: str | None,
    *,
    probe_from: str | None,
    recent_from: str,
    recent_published_days: int = 1,
) -> dict[str, Any]:
    """The corridor's status from ENTSOG physical flow (``STATUS_RULE``)."""

    from datetime import date, timedelta

    if recent_flow_days > 0:
        return {"status": "in_service", "since": None, "since_basis": None}
    if recent_published_days == 0 and not last_flow_day and not probe_from:
        return {"status": "not_published", "since": None, "since_basis": None}
    if last_flow_day:
        since = (date.fromisoformat(last_flow_day) + timedelta(days=1)).isoformat()
        return {"status": "out_of_service", "since": since, "since_basis": "last_flow_day"}
    return {
        "status": "out_of_service",
        "since": probe_from or recent_from,
        "since_basis": "no_flow_in_window",
    }


def validate_corridors(data: dict[str, Any]) -> list[str]:
    """Integrity problems, empty when the file is sound."""

    problems: list[str] = []
    if data.get("schema") != SCHEMA:
        problems.append(f"schema is {data.get('schema')!r}")
    for key in ("attribution", "downloaded"):
        if not (data.get("source") or {}).get(key):
            problems.append(f"source {key} missing")
    ids = [item.get("id") for item in data.get("corridors") or []]
    if len(ids) != len(set(ids)) or not ids:
        problems.append("corridor ids missing or not unique")
    for item in data.get("corridors") or []:
        cid = item.get("id")
        if item.get("status") not in STATUSES:
            problems.append(f"{cid}: status {item.get('status')!r}")
        if item["status"] == "out_of_service" and not item.get("since"):
            problems.append(f"{cid}: out of service without a since date")
        if not (item.get("status_source") or {}).get("citation"):
            problems.append(f"{cid}: status without its source")
        if not item.get("flow_series"):
            problems.append(f"{cid}: no flow series")
        for series in item.get("flow_series") or []:
            if not (series.get("point_key") and series.get("operator_key")):
                problems.append(f"{cid}: flow series without point or operator")
        if not item.get("landing_points"):
            problems.append(f"{cid}: no landing point")
        geometry = item.get("geometry") or {}
        if geometry.get("basis") not in GEOMETRY_BASES:
            problems.append(f"{cid}: geometry basis {geometry.get('basis')!r}")
        coords = geometry.get("coordinates")
        if coords is not None and not (
            isinstance(coords, list)
            and len(coords) >= 2
            and all(
                isinstance(p, list)
                and len(p) == 2
                and -180 <= p[0] <= 180
                and -90 <= p[1] <= 90
                for p in coords
            )
        ):
            problems.append(f"{cid}: geometry is not a line of [lon, lat] points")
        if geometry.get("basis") == "reference_pipeline_direction" and not geometry.get(
            "licence"
        ):
            problems.append(f"{cid}: pipeline geometry without its licence")
        capacity = item.get("capacity") or {}
        if capacity.get("firm_technical_kwh_d") is not None and not capacity.get("citation"):
            problems.append(f"{cid}: capacity without its source")
        facts = item.get("facts") or {}
        if facts and not (facts.get("source") and facts.get("read")):
            problems.append(f"{cid}: pipeline facts without their source")
    return problems
