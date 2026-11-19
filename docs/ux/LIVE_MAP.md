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

## The Network page: map and panel, one selection

Desk → Network is one task: the map and what used to be the separate "Outages & capacity"
page (AGENTS rule 9: a capability does not earn a page). It sits in the same page frame as
Today and Prices (width, gutters, header, context strip), so switching Desk tabs does not move
the page; the map is a panel inside that frame and, at desktop sizes, map and panel fill the
height below the header without a page scroll. Full screen stays the deliberate edge-to-edge
view (below).

| Width | Layout |
|---|---|
| Desktop | One toolbar row (view, reset, layers, situation chips, Full screen) above the map (about 63 %) and the information panel (about 37 %) |
| Phone | The map on top (about 45 % of the screen) and the panel below as a sheet; its handle (drag or press) raises the sheet to about 78 % and lowers it again; choosing a row brings the map back into view |

**Panel tabs** (the tab is in the URL: `?workspace=market&task=network&panel=capacity`):

| Tab | Rows | Units |
|---|---|---|
| **Outages** (default) | One row per outage event (below); filter Live · Out now · Planned · Ended recently (7 days); sorted by capacity offline, largest first; Why and Report on every row | Offline in GWh/d, the desk unit, through the server's unit authority; a message with no daily figure shows "–" and its published figure in the cell's tooltip |
| **Capacity** | Points · Storage · LNG. Points is the operating board (flow, firm technical, utilisation, headroom, posture; search, country, TSO, preset order and posture filter; pages of 50); a selected point shows its stack, booking products, tariffs and source above the rows. The native ENTSOG query and the declared capacity profiles are one line each until opened | mcm/d as the board's standardised basis; storage TWh and %; LNG TWh and TWh/d |
| **Flows** | Closed-gas-day flow at each located point (the map's Flows layer), largest first | GWh/d |
| **Our book** | Only in the "Our book" view and only with book permission: the book list (in progress, next 7 days, later, history with replay), upstream portfolio, the optimiser hand-off, the Decision · P&L · Warnings · Evidence tabs and the resource paths | Native per panel |

The tab labels count what the current filter shows. The retired addresses keep working:
`?workspace=capacity` and `?workspace=market&task=capacity` open Network with the Capacity tab
and are rewritten to the canonical address.

**One selection, both ways.**

- Choosing a row (outage, capacity point, flow point) selects its object on the map and flies
  there; an outage the map cannot place has nothing to fly to, and says so in the row.
  Hovering a row draws a quiet ring where it is.
- Selecting an object on the map (hub, point, facility, terminal) filters the panel to it, a
  hub to its zone (its countries' points and the outages in its balancing zone), and a line
  "Showing: TTF zone ×" clears it. The object's card heads the panel, above its rows: the
  object's detail has one place, and the card leaves the outages to the list below it.
- **Follow map** (on by default, remembered per browser): the lists hold what is in the map's
  current view; off, everything. A selection filters instead while it lasts. A row with no
  position (an outage at a known facility with no published position, or one not located at
  all) is never hidden by the view: it cannot be in or out of it.

**One row per event.** REMIT publishes messages, not events: an operator may publish the same
reduction several times, and both operators at an interconnection point publish their side.
The server collapses them (`remit_umm.outage_events`, `GET /api/physical/outages?grouped=true`),
and Today's outage list uses the same rule. Two rows (each already the latest version of its
message) are one event when they name the same asset (the same EIC, or the same name compared
without case, spaces or punctuation), for the same period (start and stop to the minute) and
the same size (GWh/d to 0.1, or the published figure and unit where no daily figure exists);
direction is not compared. The event row is the latest-published member and names every
operator; its tooltip lists every message. The four GRTgaz Deutschland messages for 81 GWh/d
off VIP France - Germany from 1 Oct 2026 to 1 Oct 2029 are one row. A window that leaves the
current year or spans years shows its years ("1 Oct 2026 – 1 Oct 2029"); a window of a week or
more drops the clock.

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
| Global | Bundled basemap (Natural Earth land, coast, borders and names, labels in the bundled Inter) | Served by the application: no third-party request, works offline and air-gapped; land, borders and names fade in when the map loads (at once under reduced motion); names follow the app language |
| Mainland China | Bundled outline (Natural Earth, public domain) | Foreign tile services are often unreachable and published maps of China need approval. The outline is served by the application, covers Europe, North Africa and the Middle East only, and draws no Chinese territory and no borders |
| Air-gapped | Bundled outline, or the firm's own tile server | Nothing leaves the network |

For street-level detail in mainland China the operator chooses a licensed domestic
provider: **Tianditu** (government service, free key; confirm the current terms for
enterprise use) or **AMap / 高德**, whose enterprise use requires its paid commercial
licence (public reports put the basic tier at about CNY 50,000 a year; confirm with AMap).
AMap's public endpoint is listed for evaluation only. The outline is rebuilt with
`scripts/ui/build_offline_basemap.py`; its `--natural-earth` mode rebuilds the bundled
basemap's borders and names, and `scripts/ui/build_map_glyphs.mjs` its Inter label glyphs.
An operator who wants street-level detail names an external style
(`EUROGAS_NEXUS_MAP_DEFAULT_PROVIDER=openfreemap` or `versatiles`, a licensed or own tile
service, or Settings → Map per user). `scripts/uat/map_no_third_party.mjs` checks in a browser
that the default map makes no request to another host.

## Selecting: what each thing tells you

Like a control tower, the map has one selection at a time. Hovering shows a name and one
figure; clicking selects. The selected object's card docks on the map's right edge, the
object and what it relates to are drawn on top in the accent colour, and everything else
steps back to 30 %. Escape, the card's × (on the Network page: the panel's "Showing:" ×), or a
click on empty map clears it. On the Network page the card heads the information panel rather
than floating over the map (see above). The card is
the map's quick context; **Inspect** hands a network point to the app's Inspector for full
detail and provenance, so the map never grows a second detail page.

| Selected | The card leads with | Highlighted |
|---|---|---|
| **Hub** (NBP, TTF …) | Day-ahead and month-ahead prices from the same rows as the hub board, change on the previous close, source and time; the zone today: outages now and planned, outages one pipeline upstream (Nyhamna feeding NBP through Langeled), flow measured in and out at the zone's points, our supply delivering in the zone | The hub, and its zone's points ringed at full strength while the rest step back. No line is drawn from the hub to its points |
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

## Two views: the network and our book

**Network (default).** The infrastructure is the stage, not the subject. Points are small
and muted (hubs a little stronger), connections are thin and faint, and utilisation
widens a busy pipe only slightly: lines show how gas can move, which helps reading the
picture, but they are not what a decision turns on. Everything stays clickable. What
carries colour is the live situation and our positions: outages in red and amber, flows,
cargoes, and our contracts and slots in the accent.

**Our book.** Only the firm's own deals that still need a decision, in the order they
need it. A list on the left groups them:

| Group | Cargo | Regas slot | Supply contract |
|---|---|---|---|
| In progress | loading, at sea, discharging | window open now | inside its gas year |
| Next 7 days | sails within a week | opens within a week | gas year starts within a week |
| Later | sails later | opens later | starts later |
| History (folded) | delivered | window ended | gas year ended |

Within a group the soonest comes first (ETA, window, start). The map draws only what is
in play: our cargoes with their voyage, our slots and contracts at every zoom (not folded
into country totals), and outages in force, since they can stop a delivery; other
companies' cargoes and flows stay in the network view, and the network steps further
back. Completed deals never sit in the live picture; they are history. Clicking an item
selects it on the map with its card, as a click on the map does.

**What relates to our deals (design basis 2, J.5).** The book view also shows everything on
the network that relates, or could relate, to the deals, derived by the server from the store
and the pricing graph (`application/map_book.py`, `book_relevance` in
`GET /api/portfolio/map-situation`), never from a hand list:

- **ours** (full emphasis): each active contract's delivery point and market area, the
  interconnection points on the path it is priced along to its allowed exits (drawn as our
  contracts' priced routes, width by contract MWh/d), booked capacity (capacity profiles and
  owned entry capacity), held storage, expected cargoes with their terminal, held regas slots;
  counterparties named on the delivery point;
- **reachable** (medium, dashed): every neighbouring market area within two crossings of an
  "ours" hub along the proven ENTSOG adjacency, with the crossing points, firm technical
  capacity where published, the published tariffs the register holds and, when both hub prices
  and every tariff are held, the spread net of them in GBP/MWh. Always marked indicative, a
  simulated price marked sim; a missing tariff (named by operator, direction and point) or price
  is stated, never estimated; no advice wording and no order entry;
- **opportunity**: the legs of actionable opportunities come from the opportunity core when it
  lands (`book_opportunity_paths` is the seam); none yet.

Everything else dims. Outages located at an "ours" or "reachable" point say "touches our
book". The "Our book" tab lists both classes; selecting a row or an object on the map opens its
card with "On our book because": "Delivery point of Kestrel supply (TTF) with Rhinmark Handel
GmbH · 18,000 MWh/d", "Reachable from TTF to NBP via Julianadorp, Bacton (BBL): spread −2.57,
tariff 1.60, net −4.17 GBP/MWh (indicative, sim)". The optimiser's decision rail, P&L,
warnings and evidence stack left the Network page with the optimiser pages (CP-21).

**The panel.** The right-hand panel collapses to a slim rail of its tabs with their counts
(the handle at its top left; remembered per user on the device), so the map takes the full
width; a tab in the rail opens the panel on that tab. At phone width collapsing lowers the
sheet to its row of tabs. Full screen is the map alone, with the panel as a drawer from the
right ("Panel"; Escape closes it). While another Desk task or page shows, nothing the map
opened stays above it: full screen ends, the drawer, key and status popovers close and an
Inspector opened from the map closes; the selection is kept for coming back.

**The status line** is the same for everyone: Live, Out now, Contracts, LNG vessels. The
maintenance line (topology checks, network points without a published position, items not
located) is in the panel's "Map data" fold, for data operations only.

**Replay.** A completed cargo with a timed track (the vessel feed's positions with their
times) can be replayed from History: the map frames the voyage, draws the whole route
faintly and the part sailed by the replay clock in the accent, and moves the vessel
along it. The whole voyage plays in about eight seconds; the slider scrubs it and shows
the date and time; under reduced motion it opens on the finished voyage and the slider
still works. Only reported, timed positions are replayed; the path between untimed
points is not invented. The map asks for 120 days of completed deals in the book view.

## Full screen: the wall view

The map normally sits on the Network page beside its information panel: a cockpit, where the
trader reads the map next to the lists. A desk also wants it on a wall screen or a second
monitor, watching the day: cargoes moving along their tracks, regas windows open, outages,
measured entry flows. **Full screen** (the last chip on the toolbar) shows the whole Network
instrument edge to edge on the display:

- The toolbar, the map with its place finder, live strip and line key, and the panel with the
  selected object's card come along. The page header and the rest of the shell do not.
- It stays current the same way as the page (see "How the map stays current"). The strip says when the
  situation is as of and when this screen last read it; when reads keep failing it says
  so ("Not refreshed: showing the last good read") instead of showing an old picture as
  live.
- The strip adds what a wall view watches: regas slots open now and the measured entry flow
  of the latest gas day in GWh/d, next to outages, contracts and cargoes at sea.
- It uses the browser's own full screen (the desktop app, Edge, Chrome, Safari on iPad),
  so Esc leaves it. Where the browser has no element full screen (Safari on iPhone), the
  map expands over the page instead and Esc or the same chip closes it.

It is a view, not a mode: it holds no state of its own and grants nothing.

## Phone width, who sees what, and keeping the map

- **At phone width the map shows the map.** The place finder is a search icon until tapped;
  the status is one compact line ("Live · Out now 3") that opens the full status on tap; the
  line key and the basemap credit sit behind an info button (bottom right); the zoom buttons
  give way to pinch zoom. Nothing else is overlaid.
- **On a wide screen too, the line key opens from the info button** beside the zoom buttons,
  so it never covers the map or collides with the zoom card; the zoom card ("Region · Fit our
  positions") sits top right, clear of the status panel.
- **Data operations stay with data operations.** Topology checks ("Topology: N to check"),
  point coverage ("Network points 853 · 64 without a published position", "Not located")
  and the topology-status card with its point counts are shown only to identities that run
  the sources (`source.run`) or administer the installation (`identity.manage`), not on a
  trader's map.
- **LNG vessels** are their own layer ("LNG vessels"), beside "Our positions" (the firm's
  own cargoes). Market vessels come only from the customer's licensed vessel feed (Kpler or
  an AIS provider, `docs/legal/DATA_SOURCE_TERMS.md`); without that entitlement the status
  says "LNG vessels: needs your Kpler (or AIS) entitlement — Admin → Data sources" instead of
  showing an empty sea (`vessel_feed` in `GET /api/portfolio/map-situation`). The demo desk
  carries five simulated vessels (`Kpler_Sim`, marked sim) heading to Gate, Eemshaven,
  Zeebrugge, Isle of Grain and Dunkerque; a terminal's card lists the cargoes heading to it.
  Finding or clicking a vessel opens its card in the right-hand panel (name, status, load
  port → destination terminal, ETA, departed, cargo in GWh and m³ LNG, "Simulated" for a
  simulated feed) with a "Send-out at <terminal>" link to the terminal's own card.
  They are removed once a real vessel feed delivers.
- **Leaving and coming back keeps the map**, from any page: see "How the map stays current".

## How the map stays current

The owner asked whether the Network page reloads everything each time the tab is opened, or
loads once and syncs the difference. The answer, measured with `scripts/uat/map_sync_measure.mjs`
(demo desk, `demo.trader`, the built client served by the API from one origin as the hosted
demo is; before = integrate `2148adc`, after = this change):

| | Before | After |
| --- | --- | --- |
| First visit: map drawn / all layers | 2.5 s / 5.5–6.1 s | 1.6–2.2 s / 3.1–3.3 s |
| First visit: transferred | 4.5 MB (static files uncompressed) | 1.5 MB |
| Back from another Desk tab | 26–28 ms, nothing read (already kept) | 27–40 ms, nothing read |
| Back from another mode (Deals) | 1.6–1.7 s / 1.7–2.0 s, map rebuilt, 11 reads, 432 KB | 31–39 ms, map kept, nothing read |
| Left open on the map for 65 s | 18 reads, 374 KB | 25 reads, 32 KB (24 "not modified") |
| A cargo, outage, flow, slot or opportunity changes | seen at the next 5-minute re-read | re-read about 4 s later |

**Before.** Within Desk the page was kept (hidden, not unmounted); leaving the mode unmounted it,
and the return rebuilt the WebGL map, re-read the situation and infrastructure and re-downloaded
the basemap. The situation was re-read every 5 minutes even while hidden; the shell re-read the
market context, FX and sources every 10 s (62 KB each time) whether or not anything had changed.
No read carried an ETag, so nothing could be answered "not modified"; the bundle and the
geometry files were served uncompressed. The map's points waited for the whole workspace batch,
which commits when its slowest read answers (about 5.5 s).

**Now: kept alive, cache-first, changes pushed.**

1. **Kept, not rebuilt.** Desk → Network is rendered once at the shell and shown by the Desk
   page's slot (`app/data/keepAlive.tsx`, `<Kept>` / `<KeptSlot>`); on any other page it is
   parked, hidden, with its timers paused. Returning shows the same map, sources, camera,
   selection and open card at once. It is released on sign-out or a change of principal, and
   after 30 minutes parked (the stand-in for memory pressure, which browsers do not signal).
2. **Cache-first reads.** The situation and the located infrastructure read through the shell's
   read cache (`app/data/readCache.ts`): the last answer shows at once and a newer one is read
   behind it; an answer equal to the one shown keeps the shown object, so nothing redraws.
   Reference geometry (network nodes and edges, infrastructure) is read once a session; the
   basemap, glyphs and context pipelines are cached by the browser for the session (an hour,
   then revalidated by ETag) and started before the map asks for them.
3. **Conditional requests.** Every JSON read carries an ETag of its content (the moments it was
   computed, such as `as_of_utc` or `evaluated_at_utc`, are left out) with
   `Cache-Control: private, no-cache`; an unchanged read is a `304` with no body
   (`api/middleware/conditional.py`). Static files get the same, and travel compressed.
4. **Changes pushed, polling as the fallback.** The session's existing alerts stream also carries
   `map` notices (a group and a time, no row) when outages, flows, cargoes, slots or
   opportunities change; the map answers with a conditional read of its situation. A safety
   re-check runs every 5 minutes, every minute while the stream is down, and only while the map
   is on screen and the browser tab is visible; a return re-checks a picture older than 30 s.
5. **Diffs, not teardown.** An update calls `setData` only on the sources whose data changed; no
   layer is removed, so selection, camera and the open card stay.
6. **Trust.** The status line says when the situation was computed and when it was last
   confirmed, "Updating…" while a newer picture is read behind the one shown (never a
   full-page spinner after the first load), and "Not refreshed: showing the last good read"
   when a refresh failed.

No `since` parameter was added: the situation is 9 KB compressed and the 304 already removes the
unchanged case; a delta would cost more than it saves at this size. Other heavy pages use the same
two pieces: `<Kept>` / `<KeptSlot>` to stay alive, `useCachedRead` with conditional reads to stay
current.

## Topology over geometry

What netbacks and flow reasoning need is the topology: which point connects to which,
through which interconnector, into which zone. The map draws it the way a trader reads a
network map:

- **A hub is a market area, not a place.** TTF, THE or NBP is a virtual trading point; it
  is not physically connected to the points of its zone. The zone-membership links of the
  reference bundle (each point to its zone's trading point) are never drawn: they made a
  star of lines on every hub. Selecting a hub rings its zone's points and steps the rest
  back; in the default view only its connections to neighbouring market areas (a few per
  hub) leave it. The key says so: "Hub = market area: select it to see its points".
- **The network is the commercial topology.** What must be right is which market areas
  join where, because route pricing walks exactly that graph: market area -
  interconnection point - market area, and through IUK and BBL, whose two ends are both
  drawn (`docs/operations/REFERENCE_NETWORK_BUNDLE.md`, "Market-area adjacency"). Each
  adjacency is a quiet dashed line from the hub to the interconnection point and on to the
  neighbouring hub (key: "Connection between market areas via interconnection point
  (schematic)"). It follows the general direction of the open reference trunk lines
  (SciGRID_gas, CC BY 4.0) where they run close to both ends, else it is straight; under it,
  with Routes on in the network view, those trunk lines are drawn faintly (key: "Pipelines,
  general direction (SciGRID_gas, CC BY 4.0)"). Neither is a surveyed route, and nothing is
  priced from them; the hover card says so. Of the
  points joining one pair of market areas (19 between TTF and THE) one is drawn by default;
  selecting a hub emphasises its connections and rings every point joining it to a
  neighbour, and its zone's points, without wiring them (no fan).
  The link is a legible dashed stroke (lighter than the land in the dark theme, darker in
  the light one), still under the markers, with the interconnection point as a small node
  on it. Hovering a link opens the border card: the two sides, every interconnection point
  on that border with its firm technical capacity (ENTSOG), and whether the tariff register
  holds its tariffs. The drawn point of a pair is the one with the largest firm technical
  capacity (VIP TTF-THE-H between TTF and THE).
  Points inside a market area (storage, LNG, production) have no line until selected,
  which shows their one link to their own hub. A surveyed pipeline, where one is loaded,
  is drawn along its geometry (key: "Pipeline (surveyed route)").
- **Our book: one line per origin and destination.** Allocated flows between the same two
  places are summed into one line in the accent colour, its width in a few capped steps of
  MWh/d, the volume labelled at the destination and one arrowhead for direction. It
  follows exactly the hub - interconnection point(s) - hub path the route was priced along
  (`route_adjacency.path_node_ids` of the sale option), so what the map shows is what was
  priced. Candidates, blocked options and sales where the gas already is draw no line. A
  delivery at a hub is a volume badge at the hub ("18k MWh/d"), never lines to the hub's
  points (key: "Our flow (width by MWh/d)").
- **Route candidates are trade routes, not pipes.** One is drawn when the book uses it, or
  as context when the server gives its path; candidates from one hub to every other hub are
  not drawn as a star of corridors.

The key lists only the kinds of line on screen. Correctness is checked instead of assumed: a connection must end
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
