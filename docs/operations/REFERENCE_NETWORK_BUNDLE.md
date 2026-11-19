# Reference network bundle

The map draws the gas network from `reference_nodes` and `reference_edges`. On a fresh
installation those tables are empty until ENTSOG is first read, and an installation without
outbound network never reads it. The product therefore ships a small north-west Europe
network and loads it at install time.

## What ships

`src/eurogas_nexus/reference_data/nwe_reference_network.json` (package data, version
`2026-11-17`, about 420 KB, one record per line):

| Part | Count | Content |
|---|---|---|
| Points | 318 | ENTSOG interconnection, storage, LNG, production and trading points with an operator in BE, DE, DK, FR, GB, IE, LU, NL or NO, plus every balance landing point |
| with a position | 267 | ENTSOG's map position transformed to approximate lon/lat (`display_approximation`, never `verified`) |
| without a position | 51 | ENTSOG publishes no map position (Dornum ITP-00126/00188, Emden ITP-00080/00081/00160 and others): no coordinate, counted as not located |
| Operator point directions | 683 | operators, adjacent operators, booking platform and product flags |
| Zone links (`virtual`) | 288 | each point to the trading point of its operator's entry-exit zone (TTF, THE, NBP, ZTP, PEG, GTF, IBP); membership of a market area, never drawn as lines |
| Market-area links (`market_area_link`) | 70 | an interconnection point to each market area it joins (37 points); what route pricing walks and the map draws |
| Pipelines (`interconnector`) | 2 | the two ends of a two-point pipeline: IUK (Bacton - Zeebrugge IZT), BBL (Balgzand - Bacton) |

Distribution and final-consumer points are left out. The source, download date and the
citation ENTSOG's terms require are in the file's `source` block and in each seeded row; the
licence position is in `docs/legal/DATA_SOURCE_TERMS.md` ("Reference network bundle").

## Market-area adjacency: what route pricing walks

A route from one hub to another passes through a named interconnection point, or a chain of
them, where the exit of one market area and the entry of the next apply. The bundle's
`market_area_link` and `interconnector` edges say which market areas each interconnection
point joins. They are derived from ENTSOG's published `interconnections` and
`connectionpoints` datasets (read live on 2026-11-17) by the deterministic rule in
`src/eurogas_nexus/reference_data/network_adjacency.py`, recorded in the bundle's
`adjacency` block:

1. One physical point is one point: ENTSOG aliases (`SAME_PHYSICAL_POINT`, Dornum GASPOOL
   is Dornum / NETRA) and physical points ENTSOG assigns to a virtual interconnection point
   (`virtualPointKey`: Haanrade and Dinxperlo into VIP TTF-THE-L, Zandvliet H into VIP BENE,
   Blaregnies and Alveringem into VIRTUALYS) are folded first.
2. Each side of an interconnection row resolves to a pipeline (a TSO system ENTSOG lists at
   exactly two points in all of Europe: IUK, BBL) or to the trading point of its balancing
   zone. Storage, LNG, production and the Norwegian upstream system are supply inside a
   market area, not a neighbour: they prove no adjacency.
3. A located point joining two in-network market areas (or a market area and an
   in-network pipeline) gets one `market_area_link` per market area, carrying the operators
   on that side and the ENTSOG row ids as evidence. Two sides in one market area are an
   internal point.
4. A pipeline whose two located ends each join a market area gets one `interconnector` edge.
5. A side every `interconnections` row leaves blank is named from the operator point
   directions (`operatorpointdirections`, the bundle's `access` rows) at that point in that
   market area's country (`operators_basis: entsog_operator_point_directions`, with the
   access ids). Read 19-11-2026: the THE side of Bunde / Oude Statenzijl (H) I (OGE), ITP-00103,
   is Open Grid Europe ("ENTSOG TP [19-11-2026] https://transparency.entsog.eu/"). The PEG side
   of VIP France - Germany (ITP-00540) stays blank: ENTSOG lists only NaTran Deutschland there,
   so its legs read "unknown TSO".
6. Of the points joining the same pair, one is marked `representative`: the map draws it
   by default and route pricing uses it when a route names no point. It is the point with
   the largest firm technical capacity ENTSOG publishes for the build's gas day
   (`operationaldatas`, indicator Firm Technical, read with the adjacency): VIP TTF-THE-H
   (816 GWh/d) over the L-gas VIP, VIP THE-ZTP, VIP BENE, Obergailbach. Ties fall to a VIP,
   then the most ENTSOG rows. The capacity is kept on the edge for the map's border card.

Nothing is inferred from names, distances or countries; a point whose other side cannot be
proven is listed in `adjacency.unconnected`, not connected.

| Market areas joined | Points | Interconnection points (drawn by default in bold) |
|---|---|---|
| GTF – THE | 1 | **VIP DK-THE** |
| IBP – NBP | 1 | **Moffat** |
| NBP – BBL | 1 | **Bacton (BBL)** |
| NBP – IUK | 1 | **Bacton (IUK)** |
| PEG – THE | 2 | **Obergailbach (FR) / Medelsheim (DE)**; VIP France - Germany |
| TTF – BBL | 1 | **Julianadorp (GTS) /Balgzand (BBL)** |
| TTF – THE | 19 | Bocholtz-Vetschau; Bunde (DE) / Oude Statenzijl (H) (NL) (GASCADE); Winterswijk; Bunde (DE) / Oude Statenzijl (H) (NL) (GUD); Bunde (DE) / Oude Statenzijl (H) (NL) I (OGE); Bunde (DE) / Oude Statenzijl (L) (NL) (GUD); Bunde (DE) / Oude Statenzijl (L) (NL) (GTG Nord); Vlieghuis; Bocholtz; Tegelen; Zevenaar; Bunde (DE) / Oude Statenzijl (H) (NL) (GTG Nord); Zone Oude Statenzijl H; VIP TTF-NCG H; VIP TTF-NCG L; VIP TTF-GASPOOL L; VIP TTF-GASPOOL H; VIP TTF-THE-L; **VIP TTF-THE-H** |
| TTF – ZTP | 4 | Zelzate; Zelzate (Zebra Pijpleiding); 's Gravenvoeren Dilsen (BE) // 's Gravenvoeren/Obbicht (NL); **VIP BENE** |
| ZTP – IUK | 1 | **Zeebrugge IZT** |
| ZTP – PEG | 1 | **VIRTUALYS** |
| ZTP – THE | 5 | Remich; Eynatten 1 (BE) // Lichtenbusch / Raeren (DE); Eynatten 2 (BE) // Lichtenbusch / Raeren (DE); VIP Belgium - NCG; **VIP THE-ZTP** |

| Pipeline | Ends |
|---|---|
| Interconnector (IUK, UK-TSO-0003) | Bacton (IUK) – Zeebrugge IZT |
| BBL company (Netherlands, UK-TSO-0004) | Julianadorp (GTS) /Balgzand (BBL) – Bacton (BBL) |

| Point | Would join | Why not connected |
|---|---|---|
| Überackern SUDAL (AT) / Überackern 2 (DE) (ITP-00007) | THE, Austria | other side has no trading point in the bundle: Austria |
| Brandov-OPAL (DE) (ITP-00010) | THE, Czech, pipeline:DE-TSO-0020 | other side has no trading point in the bundle: Czech, pipeline:DE-TSO-0020 |
| LBTG pipeline (ITP-00010/ITP-00120) | ITP-00010, ITP-00120 | the pipeline does not join two market areas of the bundle at both ends |
| Hora Svaté Kateřiny (CZ) / Deutschneudorf (Sayda) (DE) (ITP-00015) | THE, Czech | other side has no trading point in the bundle: Czech |
| Überackern ABG (AT) / Überackern (DE) (ITP-00019) | THE, Austria | other side has no trading point in the bundle: Austria |
| Oltingue (FR) / Rodersdorf (CH) (ITP-00039) | PEG, Switzerland | other side has no trading point in the bundle: Switzerland |
| GNI (UK) pipeline (ITP-00077/ITP-00090) | ITP-00077, ITP-00090 | the pipeline does not join two market areas of the bundle at both ends |
| Mallnow (ITP-00096) | THE, TGPS (YAMAL) | other side has no trading point in the bundle: TGPS (YAMAL) |
| Blaregnies L (BE) / Taisnières B (FR) (ITP-00115) | PEG, L-Zone | other side has no trading point in the bundle: L-Zone |
| Brandov STEGAL (CZ) / Stegal (DE) (ITP-00123) | THE, Czech | other side has no trading point in the bundle: Czech |
|  (ITP-00135) | GTF, THE | not in the bundle |
|  (ITP-00139) | THE, Czech | not in the bundle |
|  (ITP-00140) | THE, Austria | not in the bundle |
| Olbernhau (DE) / Hora Svaté Kateřiny (CZ) (ITP-00150) | THE, Czech | other side has no trading point in the bundle: Czech |
| South North CSEP (ITP-00222) | IBP, NI | other side has no trading point in the bundle: NI |
| RC Lindau (ITP-00227) | THE, Austria | other side has no trading point in the bundle: Austria |
| RC Basel (ITP-00228) | THE, Switzerland | other side has no trading point in the bundle: Switzerland |
| RC Thayngen-Fallentor (ITP-00229) | THE, Switzerland | other side has no trading point in the bundle: Switzerland |
| Jura (ITP-00281) | PEG, Switzerland | other side has no trading point in the bundle: Switzerland |
| Kiefersfelden-Kufstein (ITP-00282) | THE, Austria | other side has no trading point in the bundle: Austria |
| BE Quality Conversion Point H-Zone (ITP-00289) | ZTP, L-Zone | other side has no trading point in the bundle: L-Zone |
| BE Quality Conversion Point L-Zone (ITP-00290) | ZTP, L-Zone | other side has no trading point in the bundle: L-Zone |
| VIP Kiefersfelden-Pfronten (ITP-00291) | THE, Austria | other side has no trading point in the bundle: Austria |
| Wallbach (ITP-00294) | THE, Switzerland | other side has no trading point in the bundle: Switzerland |
| VIP PIRINEOS (ITP-00304) | PEG, Spain | other side has no trading point in the bundle: Spain |
| GCP GAZ-SYSTEM/ONTRAS (ITP-00497) | THE, Poland H-gas | other side has no trading point in the bundle: Poland H-gas |
| Deutschneudorf EUGAL Brandov (ITP-00535) | THE, Czech | other side has no trading point in the bundle: Czech |
| VIP Brandov (ITP-00537) | THE, Czech | other side has no trading point in the bundle: Czech |
| VIP Waidhaus (ITP-00538) | THE, Czech | other side has no trading point in the bundle: Czech |
| VIP Oberkappel (ITP-00539) | THE, Austria | other side has no trading point in the bundle: Austria |
| VIP Germany-CH (ITP-00544) | THE, Switzerland | other side has no trading point in the bundle: Switzerland |
| VIP BENE-L (ITP-00648) | TTF, L-Zone | other side has no trading point in the bundle: L-Zone |
| Faxe (ITP-10009) | GTF, Poland H-gas | other side has no trading point in the bundle: Poland H-gas |

Route pricing (`domain/route_cost/route_adjacency.py`, applied by `list_route_candidates`)
prices a network route only along this graph: exit from the first market area at the
point, the pipeline's own charges where the route crosses IUK or BBL, entry to the next
market area, chained hop by hop. A leg whose tariff the register does not hold is reported
missing, never priced at zero; a route between market areas with no proven path gets no
legs and is blocked (`ROUTE_NOT_CONNECTED`).

**Every store draws the same adjacency.** The edge reader (`SqlAlchemyEdgeRepository`) serves
the shipped bundle's zone links and adjacency between the nodes the store holds, in place of
any stored bundle edges: a store seeded from the bundle and a store holding a live ENTSOG read
(where the seed is skipped) draw the graph route pricing walks
(`tests/unit/test_reference_network_bundle.py`).

**Tariffs for the crossings.** Each leg is named as ENTSOG publishes the tariff (operator,
point, direction); `scripts/ops/ingest_public_sources.py --source entsog-tariffs` reads
`tariffsfulls` for every adjacency point into the tariff register (the figure as the operator
published it, every standard product, period, FINAL or INDICATIVE, citation per row;
`ingestion/entsog_tariffs.py`); route pricing reads it per MWh for the stated product and load
factor (`domain/route_cost/tariff_units.py`). Read 2026-11-19: every route to or from NBP lacks
the National Gas leg (ENTSOG files National Gas's per-day prices under a per-year unit, so
those rows are refused) and TTF - NBP through BBL also lacks the GTS exit at Balgzand, which
ENTSOG does not publish; those routes report the legs as missing.
`scripts/ops/tariff_coverage.py` prints, per crossing and direction, which legs are held.

Refresh the adjacency on the shipped bundle (no database; ENTSOG read live, retried on a
reset, or from saved responses):

```bash
python scripts/ops/build_reference_network_bundle.py --adjacency-only --version <yyyy-mm-dd> \
    [--entsog-dir <dir with interconnections.json and connectionpoints.json>]
```

## Loading it

```bash
python scripts/ops/seed_reference_network.py --json
```

The server stack runs this as the one-shot `reference-seed` service after `migrate`; the
Windows installer runs it right after the migration. It writes through the live ingestion's
own `upsert_reference_snapshot` (upsert under stable ids, retire rather than delete), so:

- a repeat run converges on the same rows;
- a store that already holds a live ENTSOG reference read is left unchanged
  (`skipped_live_reference_present`);
- a later live ENTSOG read takes over the same ids; the schematic links stay
  (`source_system = EGN_REFERENCE_BUNDLE`).

## On the map

Points draw as approximate positions. The zone links are not drawn: a trading point is a
market area, not a place wired to each of its points, and drawing them put a star of lines
on every hub. They are used to ring a hub's points when the hub is selected, to show a
storage, LNG or production point's link to its own hub when that point is selected, and for
the topology check. The market-area adjacency is drawn as quiet straight dashed segments
hub - interconnection point - hub, one point per pair of market areas; selecting a hub
emphasises them and rings every other point joining it to a neighbour (see `docs/ux/LIVE_MAP.md`, "Topology over
geometry"). The situation strip reads "Network points 318 · 51
without a published position"; the points without one are listed in its tooltip and in
`unlocated_network_points` of `GET /api/portfolio/map-situation` (`unlocated.network_points`;
flows at points with no position count in `unlocated.flows`), following the outage rule:
counted, never placed at a guessed position. Twynholm and Carrickfergus (Northern Ireland)
have no zone trading point in ENTSOG's list and stay unlinked, so the map's topology check
reports them.

## Presentation geometry: the general direction pipes run

The drawn connections follow the open SciGRID_gas IGGIELGN trunk lines (DLR, CC BY 4.0,
doi:10.5281/zenodo.4767098; terms in `docs/legal/DATA_SOURCE_TERMS.md`, "Presentation
geometry"). The build keeps the transmission pipes of at least 600 mm with an end in
north-west Europe, generalised to about 2 km, and writes them to
`clients/web/public/map/context-pipelines.geojson` (about 340 kB, 37 kB compressed; served by
the application, drawn faintly under the connections with Routes on). Each drawn connection
leg (interconnection point - market area) gets a `presentation_path` along them when both ends
are within 45 km of the trunk network and the path is at most 1.5 times the straight distance
plus 40 km (58 of the 72 drawn legs on 2026-11-17); the others, and the subsea IUK and BBL
interconnectors, stay straight. The bundle's
`presentation_geometry` block carries source, version, DOI, licence, the pipe file's SHA-256,
the rule and the counts.

Presentation only: route pricing builds its graph from the adjacency edges and never reads the
geometry (`tests/contract/test_reference_presentation_geometry.py` proves the pricing graph is
identical with and without it); the lines stay dashed and schematic.

```bash
# unpack IGGIELGN.zip from https://zenodo.org/records/4767098 into its own folder, then
python scripts/ops/build_reference_network_bundle.py --presentation-only \
    --scigrid-dir <folder>/data --version <yyyy-mm-dd.n>
```

A full or adjacency-only rebuild without `--scigrid-dir` keeps the shipped path of every leg
whose two ends are unchanged.

## Refreshing it

After a complete ENTSOG reference read on a development store:

```bash
python scripts/ops/build_reference_network_bundle.py --version <yyyy-mm-dd> --downloaded <yyyy-mm-dd>
pytest -q tests/unit/test_reference_network_bundle.py
```

The build is read-only, checks the bundle (unique ids, links between positioned points,
schematic and verified flags) and refuses to write a defective one. Review the line diff
before committing.
