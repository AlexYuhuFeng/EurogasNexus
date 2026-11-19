"""Which ENTSOG points the tariff read covers besides the market-area graph's crossings.

Route pricing walks the reference bundle's market-area graph (north-west Europe:
``network_adjacency.py``); the tariff read covers every point of that graph
(``ingestion/entsog_tariffs.tariff_points``). The product also covers market areas the graph
does not join yet (CEGH, CZ, PSV, PVB, and Swiss transit), and supply that enters a market
area without crossing from another (LNG terminals, Norwegian landing points). Their tariffs
are read too, so the register holds them before the graph does:

- ``CORRIDOR_POINTS``: interconnection points outside the graph where both sides are
  transmission systems in two different covered balancing zones (ENTSOG ``interconnections``,
  ``fromBzKey``/``toBzKey``);
- ``LNG_ENTRY_POINTS``: LNG terminal points feeding a covered zone's transmission system;
- ``NORWAY_LANDING_POINTS``: points where the Norwegian upstream system (Gassco,
  ``NO-TSO-0001``, no balancing zone) lands into a covered zone.

Derived from ENTSOG TP ``interconnections`` read on 19-11-2026 (cited "ENTSOG TP [19-11-2026]
https://transparency.entsog.eu/", TP Terms of Use Art. 5); the values are the market areas
each point joins (``CH`` is Swiss transit, ``IUK`` the Interconnector). Refresh by re-reading
the dataset when ENTSOG adds a point.

本模块列出市场区域图之外仍需读取费率的 ENTSOG 点位：走廊互联点、LNG 接收站入口与挪威登陆点。
"""

from __future__ import annotations

SCOPE_CITATION = "ENTSOG TP [19-11-2026] https://transparency.entsog.eu/"

CORRIDOR_POINTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ITP-00007": ("Überackern SUDAL (AT) / Überackern 2 (DE)", ("CEGH", "THE")),
    "ITP-00010": ("Brandov-OPAL (DE)", ("CZ", "THE")),
    "ITP-00015": ("Hora Svaté Kateřiny (CZ) / Deutschneudorf (Sayda) (DE)", ("CZ", "THE")),
    "ITP-00018": ("Larrau", ("PEG", "PVB")),
    "ITP-00019": ("Überackern ABG (AT) / Überackern (DE)", ("CEGH", "THE")),
    "ITP-00033": ("Biriatou (FR) / Irun (ES)", ("PEG", "PVB")),
    "ITP-00039": ("Oltingue (FR) / Rodersdorf (CH)", ("CH", "PEG")),
    "ITP-00040": ("Tarvisio (IT) / Arnoldstein (AT)", ("CEGH", "PSV")),
    "ITP-00070": ("Kiefersfelden", ("CEGH", "THE")),
    "ITP-00071": ("Haanrade", ("THE", "TTF")),
    "ITP-00088": ("Zandvliet H-gas", ("TTF", "ZTP")),
    "ITP-00123": ("Brandov STEGAL (CZ) / Stegal (DE)", ("CZ", "THE")),
    "ITP-00135": ("Ellund", ("ETF", "THE")),
    "ITP-00136": ("Griespass (CH) / Passo Gries (IT)", ("CH", "PSV")),
    "ITP-00139": ("Waidhaus", ("CZ", "THE")),
    "ITP-00140": ("Oberkappel", ("CEGH", "THE")),
    "ITP-00150": ("Olbernhau (DE) / Hora Svaté Kateřiny (CZ)", ("CZ", "THE")),
    "ITP-00152": ("Blaregnies (BE) / Taisnières (H) (FR) (Segeo/Troll)", ("PEG", "ZTP")),
    "ITP-00206": ("Pfronten", ("CEGH", "THE")),
    "ITP-00227": ("RC Lindau", ("CEGH", "THE")),
    "ITP-00228": ("RC Basel", ("CH", "THE")),
    "ITP-00229": ("RC Thayngen-Fallentor", ("CH", "THE")),
    "ITP-00278": ("Bizzarone", ("CH", "PSV")),
    "ITP-00281": ("Jura", ("CH", "PEG")),
    "ITP-00282": ("Kiefersfelden-Kufstein", ("CEGH", "THE")),
    "ITP-00291": ("VIP Kiefersfelden-Pfronten", ("CEGH", "THE")),
    "ITP-00294": ("Wallbach", ("CH", "THE")),
    "ITP-00304": ("VIP PIRINEOS", ("PEG", "PVB")),
    "ITP-00305": ("Dinxperlo", ("THE", "TTF")),
    "ITP-00535": ("Deutschneudorf EUGAL Brandov", ("CZ", "THE")),
    "ITP-00537": ("VIP Brandov", ("CZ", "THE")),
    "ITP-00538": ("VIP Waidhaus", ("CZ", "THE")),
    "ITP-00539": ("VIP Oberkappel", ("CEGH", "THE")),
    "ITP-00544": ("VIP Germany-CH", ("CH", "THE")),
}

LNG_ENTRY_POINTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "LNG-00004": ("OLT LNG / Livorno", ("PSV",)),
    "LNG-00005": ("Alveringem", ("PEG", "ZTP")),
    "LNG-00007": ("Teesside", ("NBP",)),
    "LNG-00008": ("Isle of Grain", ("NBP",)),
    "LNG-00012": ("Barcelona", ("PVB",)),
    "LNG-00013": ("Bilbao", ("PVB",)),
    "LNG-00015": ("Cavarzere (Porto Levante / Adriatic LNG)", ("PSV",)),
    "LNG-00016": ("Musel", ("PVB",)),
    "LNG-00017": ("Zeebrugge LNG", ("ZTP",)),
    "LNG-00018": ("Huelva", ("PVB",)),
    "LNG-00019": ("PANIGAGLIA TERMINAL", ("PSV",)),
    "LNG-00021": ("Mugardos", ("PVB",)),
    "LNG-00022": ("Cartagena", ("PVB",)),
    "LNG-00023": ("Sagunto", ("PVB",)),
    "LNG-00024": ("Montoir de Bretagne", ("PEG",)),
    "LNG-00027": ("Gate Terminal (I)", ("TTF",)),
    "LNG-00029": ("Fos (Tonkin/Cavaou)", ("PEG",)),
    "LNG-00047": ("Dunkerque LNG", ("PEG", "ZTP")),
    "LNG-00049": ("Milford Haven", ("NBP",)),
    "LNG-00060": ("BRUNSBUETTEL HAFEN (FSRU) (DE)", ("THE",)),
    "LNG-00068": ("Eems Energy Terminal", ("TTF",)),
    "LNG-00069": ("PIOMBINO TERMINAL", ("PSV",)),
    "LNG-00071": ("Le Havre (FR)", ("PEG",)),
    "LNG-00075": ("Baltic Energy Gate (Port) (DE)", ("THE",)),
    "LNG-00078": ("STADE HAFEN (FSRU) - LNG", ("THE",)),
    "LNG-00079": ("Baltic Energy Gate", ("THE",)),
    "LNG-00082": ("RAVENNA TERMINAL", ("PSV",)),
    "LNG-00083": ("Wilhelmshaven, LNG-Zone", ("THE",)),
}

NORWAY_LANDING_POINTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ITP-00022": ("St. Fergus", ("NBP",)),
    "ITP-00045": ("Dunkerque", ("PEG",)),
    "ITP-00091": ("Easington", ("NBP",)),
    "ITP-00106": ("Zeebrugge ZPT", ("ZTP",)),
    "ITP-00208": ("Dornum (EPT1 & EPT2)", ("THE",)),
    "ITP-00209": ("Emden (EPT1)", ("THE", "TTF")),
    "ITP-00210": ("Emden (NPT)", ("THE", "TTF")),
    "ITP-00525": ("Dornum GASPOOL", ("THE",)),
    "ITP-00630": ("North Sea Entry", ("ETF",)),
}


def scope_points() -> dict[str, tuple[str, str, tuple[str, ...]]]:
    """Point key -> (kind, ENTSOG label, market areas joined) for every point listed here."""

    out: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    for kind, table in (
        ("corridor", CORRIDOR_POINTS),
        ("lng_entry", LNG_ENTRY_POINTS),
        ("norway_landing", NORWAY_LANDING_POINTS),
    ):
        for key, (label, areas) in table.items():
            out[key] = (kind, label, areas)
    return out
