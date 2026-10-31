# Live map

The network map is the visual base everyone else reads: managers scan it for what needs
attention, risk staff for where the firm's exposure lands, and traders glance at it for
context before going back to the ladder. It answers one question at a glance: **what is
happening on the network, and where does it touch us?**

## What it shows

| Layer (chip) | What is drawn | Located by | Data |
|---|---|---|---|
| Hubs, LNG, IPs, Network | Network points and verified pipelines | ENTSOG connection points | public (ENTSOG terms) |
| **Outages** | Red dot = capacity out now, amber = scheduled; size grows with the share of technical capacity out; a slow pulse on outages that are live | The asset's EIC code on a network point (the REMIT key), else exact name | REMIT UMMs |
| **Flows** | Ring at each point sized by the latest physical flow (GWh/d); gas moving along pipelines that report flow | ENTSOG point key | ENTSOG operational data |
| **Our positions** | Contract pin at each delivery point (several contracts share one pin); our LNG cargoes with the track sailed and a dashed leg to the destination; a ring on terminals where we hold regas slots | Point name; the coordinates the vessel feed or ETRM supplied | Upstream contracts, `lng_cargoes`, `regas_slots` (book-scoped) |
| **Infrastructure** | Platforms, fields, storage, liquefaction and plants, from zoom 5 | Published coordinates | Openly licensed datasets (below) |

Hovering any item shows a compact card in desk units: an outage's unavailable and
technical capacity, window, zone and reason; the contracts landing at a point with MWh/d
and entry capacity held; a cargo's route, ETA, size and when its position was reported; the
regas windows and send-out held at a terminal. Clicking a network point still hands it to
the Inspector, so the map never grows a second detail pane.

A status strip states the picture in one line: "Live · 2 out now · 1 scheduled · 3
contracts · 1 own cargo at sea · 1 regas slot · as of 09:30 UTC · 1 not located". The map
re-reads the situation every five minutes; a failed read keeps the last picture.

## Zooming in

The map behaves like a city map: scroll, pinch or double-click to zoom, and the detail grows
with it.

- **Basemap detail.** With a detailed basemap (OpenFreeMap, VersaTiles, Tianditu or the
  firm's own tiles) the map zooms to street level (zoom 17) with roads and places. The
  bundled outline stops at zoom 10: it holds coastlines only, and zooming further would
  only magnify the error of approximate positions.
- **Icons by kind.** Infrastructure is drawn with a shape per kind and a colour per family:
  triangle = production platform, ring = field, hexagon = processing plant, rounded square
  = LNG terminal or liquefaction, square = storage, diamond = compressor or border point,
  circle = gas-fired power plant. Icons thin out at regional zoom and all show from zoom 8.
- **Names appear progressively.** About 12 labels at continental zoom, 24 regionally and up
  to 60 when local, hubs first, then terminals and points, then infrastructure, never
  overlapping.
- **Find and fly.** "Find a hub, terminal, field or vessel" searches what the active layers
  draw; choosing a result flies there and drops a short-lived pin. Clicking any item flies
  to it and pins its card until closed. Under *reduce motion* the map jumps instead.
- **Honest positions.** ENTSOG point coordinates come from a schematic map. From zoom 7 a
  soft ring around each such point shows that the true position lies somewhere nearby;
  imported infrastructure with published coordinates has no ring.

## Basemaps by country

| Installation | Default | Why |
|---|---|---|
| Global | OpenFreeMap (OpenStreetMap data, free for commercial use with attribution) | Street-level detail, no key |
| Mainland China | Bundled outline (Natural Earth, public domain) | Foreign tile services are often unreachable and published maps of China need approval. The outline is served by the application, covers Europe, North Africa and the Middle East only, and draws no Chinese territory and no borders |
| Air-gapped | Bundled outline, or the firm's own tile server | Nothing leaves the network |

For street-level detail in mainland China the operator chooses a licensed domestic
provider: **Tianditu** (government service, free key; confirm the current terms for
enterprise use) or **AMap / 高德**, whose enterprise use requires its paid commercial
licence (public reports put the basic tier at about CNY 50,000 a year; confirm with AMap).
AMap's public endpoint is listed for evaluation only. The outline is rebuilt with
`scripts/ui/build_offline_basemap.py`.

## Rules

1. **Placed only where a source places it.** An outage is drawn only when its EIC code or
   exact name matches a network point; a contract only when its delivery point matches;
   a cargo only at the position its feed reported. Everything else is counted in the strip
   ("not located") and never put at a guessed position. Coordinates the source marks as
   approximate (ENTSOG's schematic map) keep that label.
2. **The dashed leg is not a route.** From a cargo's last reported position to its
   destination the line is straight and dashed; the hover says so. Routing a ship would
   be a forecast the product does not make.
3. **Colour carries meaning, nothing else.** Red is capacity out now, amber is scheduled,
   the accent colour is the firm's own positions, grey is market information, teal is
   flow. The base map stays muted so these read first.
4. **Motion only where something is moving.** Dashes move along pipelines that report a
   flow and along our laden cargoes' remaining leg; live outages pulse slowly. Nothing
   else animates. Under the operating system's *reduce motion* setting the same layers are
   static.
5. **Same access as the tables.** Contracts, cargoes and slots in books follow portfolio
   isolation (a regional head sees only their books); market cargoes and outages follow
   the caller's data scopes. The map is never a side door.
6. **Decluttered by default.** Four situation chips, separate from the network chips;
   facilities appear only from zoom 5; labels only for hubs and the highlighted route;
   co-located contracts share one pin.

## Decisions

- **No 3D.** Extruded terrain or buildings add nothing to a gas network at country scale
  and cost legibility and battery. The map supports pitch for those who want it, but
  values are never encoded in height, which is hard to read and compare.
- **Flows at points, not invented arrows between countries.** Cross-border direction comes
  from the points' own entry and exit data and from pipelines whose geometry is verified.
  Country-to-country arrows would need a netting the sources do not publish.
- **One read for the picture.** `GET /api/portfolio/map-situation` composes outages, flows,
  contracts, cargoes and slots in one call, so the map is consistent at one moment and
  access is decided in one place.

## Where the locations come from

| What | Source | Licence | How to load |
|---|---|---|---|
| Network points, IPs, LNG and storage points | ENTSOG Transparency Platform | ENTSOG terms (reuse with attribution) | scheduled ENTSOG ingestion |
| Norwegian fields, platforms, pipelines | Norwegian Offshore Directorate (Sodir) FactMaps | NLOD 2.0 | `scripts/ops/import_infrastructure_geojson.py --licence NLOD-2.0` |
| UK offshore installations and pipelines | North Sea Transition Authority open data | OGL v3 | same, `--licence OGL-UK-3.0` |
| LNG terminals, storage, pipelines worldwide | Global Energy Monitor trackers | CC BY 4.0 | same, `--licence CC-BY-4.0` |
| Platforms, plants (gap filling) | OpenStreetMap extracts | ODbL 1.0 | same, `--licence ODbL-1.0` |
| Vessel positions, tracks, ETAs, destinations | The customer's vessel-tracking subscription (Kpler, Spire, MarineTraffic) | Customer licence | `scripts/ops/import_lng_positions.py --kind cargoes --source KPLER` |
| Own cargoes and regas slots | ETRM, terminal capacity confirmations | Firm's own data | `import_lng_positions.py --kind cargoes|slots --source ETRM` |

The infrastructure import refuses any licence that is not cleared for commercial use (for
example CC BY-NC) unless the operator declares it the customer's own (`CUSTOMER`), and
records the licence and attribution on every facility. ENTSO-E's grid map and commercial
vessel feeds are not redistributable and enter only under the customer's licence.

A live Kpler API connector needs the customer's Kpler contract and endpoint access; until
one is configured, the desk exports cargoes from Kpler on a schedule and the import loads
them. The map reads the same tables either way.
