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

## Semantic zoom: a different question at each scale

Like a navigation or ride-hailing map, the map changes *what* it shows as you zoom, not
only how large it is. A small chip at the bottom right names the current level.

| Level | Zoom | Question it answers | What is drawn |
|---|---|---|---|
| **Overview** | below 5 | How is the portfolio doing, country by country? | One pill per country with activity: our contracted MWh/d, own cargoes inbound, live outages (red border). The tooltip has the full breakdown (slots held, scheduled outages, GWh). Click a pill to zoom into that country. Individual assets are hidden |
| **Region** | 5 to 7.5 | Which assets, where? | Each outage, contract pin, cargo, regas terminal and facility icon, with hover cards |
| **Detail** | from 7.5 | What exactly is happening at this asset? | The key figures beside each asset: "Easington · −300 GWh/d · until 02 Nov", "Arctic Voyager · 980 GWh · ETA 02 Nov", "Gate · slot 02 Nov–07 Nov · 190 GWh/d", "Easington · 24,000 MWh/d". Labels at the same place stack |

Pills sit at the centre of the activity they summarise, not at a capital, and step apart
when countries are close. **Fit our positions** frames every contract, own cargo and
held slot in one move; under *reduce motion* it jumps instead of flying.

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

## Selecting: what each thing tells you

Like a control tower, the map has one selection at a time. Hovering shows a name and one
figure; clicking selects. The selected object's card docks on the map's right edge, the
object and what it relates to are drawn on top in the accent colour, and everything else
steps back to 30 %. Escape, the card's ×, or a click on empty map clears it. The card is
the map's quick context; **Inspect** hands a network point to the app's Inspector for full
detail and provenance, so the map never grows a second detail page.

| Selected | The card leads with | Highlighted |
|---|---|---|
| **Hub** (NBP, TTF …) | Day-ahead and month-ahead prices from the same rows as the hub board, change on the previous close, source and time; the zone today: outages now and planned, outages one pipeline upstream (Nyhamna feeding NBP through Langeled), flow measured in and out at the zone's points, our supply delivering in the zone | The hub |
| **Site** (a place: Easington, Bacton, Isle of Grain …) | Its roles as words; operator; flow in or out today (gas day stated) against capacity, with utilisation only when both are the same point's; tank storage for a terminal; outages (REMIT) with window and reason; our supply there with DCQ and entry capacity; cargoes heading to it; our regas slots; the pipelines connecting it | Its points, every connection to it, the legs of cargoes heading to it |
| **Cargo** | Our or market cargo, status; load port → destination with progress; ETA (or how overdue); size in GWh and m³ LNG; the regas slot waiting for it | Track sailed (solid), indicative leg ahead (dashed), load port and destination ringed and labelled |

**One place, several roles.** Network points and facilities within 3 km are one site,
named by what its points share ("Bacton IUK" and "Bacton BBL" are Bacton). Its roles are
listed as plain chips, in a fixed order: what it is (entry point, interconnection point,
LNG terminal, gas terminal, production, storage), what connects to it ("Langeled
pipeline"), which zone it is in ("NBP zone"), the firm's stake ("Our supply", "Our regas
slot") and its state ("Outage now", "Outage planned"). Easington reads *Entry point · Gas
terminal · Langeled pipeline · NBP zone · Our supply*.

**Roles are words, not colours.** Colour on the map is reserved for state (rule 3), so a
role chip is neutral text unless it is the firm's own (accent) or an outage (red, amber).
A colour per role would need a legend nobody remembers and would collide with state.

**No operator logos.** Operators are named in text. Logos are trademarks that need each
owner's permission in a commercially sold product (AGENTS rule 18), are illegible at map
scale, and add colour that competes with state.

## Full screen: the wall view

The map normally sits on the Network page with the resource and decision rails below it: a
cockpit, where the trader reads the map next to the numbers. A desk also wants the map on
its own, on a wall screen or a second monitor, watching the day: cargoes moving along their
tracks, regas windows open, outages, measured entry flows. **Full screen** (the last chip on
the map's toolbar) shows the map column alone on the display:

- Everything that belongs to the map comes along: the layer chips, the place finder, the
  live strip, the selection card and the line key. Nothing else does.
- It keeps refreshing on the same five-minute cycle as the page. The strip says when the
  situation is as of and when this screen last read it; when reads keep failing it says
  so ("Not refreshed: showing the last good read") instead of showing an old picture as
  live.
- The strip adds what a wall view watches: regas slots open now and the measured entry flow
  of the latest gas day in GWh/d, next to outages, contracts and cargoes at sea.
- It uses the browser's own full screen (the desktop app, Edge, Chrome, Safari on iPad),
  so Esc leaves it. Where the browser has no element full screen (Safari on iPhone), the
  map expands over the page instead and Esc or the same chip closes it.

It is a view, not a mode: it holds no state of its own and grants nothing.

## Topology over geometry

What netbacks and flow reasoning need is the topology: which point connects to which,
through which interconnector, into which zone. A pipe's surveyed path matters little. So
a known connection without surveyed geometry is drawn as a thin curve between its
endpoints (key: "Connection, schematic where no surveyed route"); a surveyed pipeline is
drawn along its geometry. Correctness is checked instead of assumed: a connection must end
at known points, may cross a border only at an entry or interconnection point (or an LNG,
production or storage site), entry and interconnection points must connect to something,
and nothing is recorded twice. Problems show on the status line ("Topology: 2 to check")
with the details on hover.

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
6. **Decluttered by default.** Labelled chips for the network (hubs, LNG, entry and
   interconnection points, other points) and, separately, the situation (outages, flows,
   our positions, infrastructure); production fields and platforms appear only when
   Infrastructure is on; labels only for hubs and the highlighted route; co-located
   contracts share one pin. Generic points and clusters are neutral grey, because blue
   means ours.
7. **Map first.** On the Network page the map takes the full width; the contract list and
   the decision rail sit below it. One way to find a place: the in-map finder.

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
