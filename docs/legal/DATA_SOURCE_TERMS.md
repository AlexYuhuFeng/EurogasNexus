# Data-source and service terms for commercial use

Code dependencies are covered by [DEPENDENCY_LICENSE_REVIEW.md](DEPENDENCY_LICENSE_REVIEW.md) and gated in CI.
Data feeds and hosted services are governed by their providers' terms instead. This
table is the engineering summary the product enforces, not legal advice; legal should
confirm each provider's current terms before a production deployment.

| Source | Use in product | Commercial-use position | How the product enforces it |
|---|---|---|---|
| ENTSOG Transparency Platform | flows, capacity, tariffs (`tariffsfulls`: the reserve prices TSOs publish per interconnection point, stored in the tariff register for route pricing) | Free public data; TP Terms of Use Art. 5 (see "Reference network bundle" below): store and use with the source and download date cited | Live ingest gated by a provider certification record; every tariff row cites "ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/" and its ENTSOG row id, and keeps the figure as the operator published it (read per MWh only when priced). Tariffs are read one point per query, 2 s apart (`--entsog-pace-seconds`). Fair use: the TP API manual (v2.1, read 2026-11-18) asks that queries be filtered by dates, points and indicators to stay within its 60-second timeout and share the platform fairly; it states no other rate limit. The landing-point history (`scripts/ops/backfill_entsog_landings.py`, run after a successful scheduled ENTSOG read) reads one quarter of physical flow at the ten landing point-directions per query, at most 8 queries a run, 3 s apart, through the same approval and certification gate; `GET /api/fundamentals/flows` returns the citation |
| ENTSOG Transparency Platform, shipped reference bundle | NWE network points, operators and approximate positions on a fresh or offline installation | TP Terms of Use (Rev. 3, 10 Nov 2026) Art. 5: download, store and use in good faith with the source and download date cited; no clause excludes commercial use or redistribution (see "Reference network bundle" below) | `src/eurogas_nexus/reference_data/nwe_reference_network.json` carries the citation; positions marked approximate; links marked schematic |
| ENTSOG Transparency Platform, urgent market messages | transmission outages (REMIT UMMs TSOs publish to ENTSOG) | Same TP Terms of Use (Rev. 3) Art. 5 as the rows above: download, store and use, citing "ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/" | `src-entsog-umm`, `scripts/ops/ingest_remit_entsog.py`; the download date is in every stored message's source reference and the citation is returned with each outage row (`attribution`) |
| GIE AGSI+/ALSI | storage, LNG (daily, by country and the EU total, history included); facility listing (EIC, name, country, operator) as facility identity | Free with a registered API key. Reuse, commercial included, with GIE named as the source: "All data published on AGSI & ALSI can be used or repackaged in any way you see fit but a clear indication on GIE as data source is mandatory. A mention of GIE, AGSI or ALSI (as applicable) as data source is a minimum requirement." (https://agsi.gie.eu/account, "API data usage", read 2026-11-17; no clause limits history or commercial use). The API documentation is available only after registration; GIE publishes no rate limit | Key held server-side; certification gate; the listing is loaded by `scripts/ops/ingest_gie_facilities.py` into the identity tables (no position: GIE publishes none). History is backfilled one gas year per read at a 2-second pace by `scripts/ops/backfill_gie_history.py` through the same gated path; `GET /api/fundamentals/storage` returns the attribution with every read |
| ECB reference rates, €STR | FX, €STR fixings | Free; reuse permitted with source attribution | Public baseline family `ECB` |
| Bank of England (SONIA) | SONIA fixings | Free; administrator terms (attribution, no endorsement) | Public baseline family `BOE`; attribution returned with every resolved rate |
| NY Fed (SOFR) | SOFR fixings | Free; NY Fed terms of use (attribution) | Public baseline family `NYFED`; attribution returned |
| ECMWF Open Data | weather forecasts | CC-BY-4.0: commercial use with attribution | Certified source; attribution in evidence |
| Eurostat (`nrg_chdd_m` heating degree days by country, monthly; `nrg_cb_gas` gas use by sector) | Shipped NW Europe degree-day reference for the forward balance (CP-25): 30-year monthly HDD normals and their spread, country weights from households' and services' gas use | Eurostat data © European Union; reuse, commercial reuse included, authorised with the source acknowledged (Commission reuse policy, CC BY 4.0). No key, no terms to accept. Confirm the current copyright notice before a production deployment | A versioned file built by `scripts/ops/build_hdd_reference.py` (diff reviewed when Eurostat publishes a year); the attribution travels in every forward-balance read (`weather_reference.attribution`) |
| ENTSO-E Transparency Platform | power prices, load, generation by fuel | Free with a registered token; the platform's terms permit reuse with attribution to ENTSO-E (confirm the current terms at go-live) | Public baseline family `ENTSOE`; token held server-side |
| Elexon Insights Solution (BMRS) | GB generation by fuel, demand outturn, market index price | Free, no key; BMRS Data Licence permits reuse including commercial use with the attribution "Contains BMRS data © Elexon Limited copyright and database right" (confirm the current terms at go-live) | Public baseline family `ELEXON`; attribution in the connector description and evidence |
| REMIT UMMs (EEX Transparency, GIE IIP, Gassco UMM and other inside-information platforms) | gas facility outages | Inside information operators must publish; each platform sets reuse terms, confirm commercial reuse for the platform used | Public baseline family `REMIT`; import records the platform; platforms without published reuse terms (EEX Transparency, Gassco, PRISMA) need written confirmation (`--terms-confirmed`); GIE IIP permits reuse with source credit ("All data published on IIP can be used or repackaged in any way you see fit but a clear indication on GIE as data source is mandatory", iip.gie.eu API page, checked 2026-11-14); its API needs a registered key (the GIE AGSI/ALSI key is accepted) and is collected by `scripts/ops/ingest_remit_iip.py` |
| US EIA open data | Henry Hub daily spot | US government work, public domain; free API key | Public baseline family `EIA`; key held server-side |
| US EIA Henry Hub futures (NYMEX contracts 1-4, `RNGC1`-`RNGC4`) | Henry Hub forward for a cargo's pricing month (CP-12) | Checked 2026-11-18: EIA content is public domain (its "Copyrights and Reuse" page), but the futures table states "Futures prices after April 5, 2024, are not available": EIA no longer publishes them | **Not ingested.** A Henry Hub forward comes from the customer's licensed exchange data (the `ICE Endex, EEX, CME` row) or the firm's own mark; otherwise the cargo model uses the held EIA daily spot as a flat proxy, class "indicative", labelled "spot proxy" |
| LNG voyage distances (sea routes, CP-12 `freight_route`) | Nautical miles per load port, discharge port and routing | No openly licensed sea-distance table chosen yet; vendor distance tables are licensed per user | **Shipped empty.** The firm enters each route with where the distance came from (versioned, audited); the product ships no distances of its own until the owner picks a source |
| ICE Endex, EEX, CME, NGX settlements | Gas, carbon (EUA, UKA), API2 coal, power, Henry Hub, AECO | Exchange licence held by the customer; non-display use for analytics must be covered | Licensed families `ICE_ENDEX`, `EEX`, `CME`, `NGX`; granted per user by an administrator |
| National Gas (GB) | demand; storage and LNG stock, storage withdrawal/injection and LNG send-out (data portal, keyless CSV) | Open data licence; attribution | Certified source (demand); public baseline family `NATIONAL_GAS` (storage, LNG) |
| Imbalance (cash-out) prices: National Gas SMP buy/sell (GB, NBP), Trading Hub Europe positive/negative imbalance prices (DE, THE), other zones' neutral or imbalance prices | Today → My gas day: the cost of leaving a hub's net open | **Not verified, not ingested** (see "Imbalance prices, checked 2026-11-19" below) | My gas day values an open net only at the cash-out premium or discount the firm enters in its approved assumption set (`balancing.short_premium`, `balancing.long_discount`), labelled as an assumption with the set and version |
| EEX public market data (TTF NGP reference) | reference index | Display/internal use only; redistribution and derived products need an EEX licence. The website terms (see "EEX website terms, checked 2026-11-18" below) permit only a single copy for personal, non-commercial use without EEX's written approval, so **automated retrieval into the product is not covered** until the customer holds an EEX DataSource licence or EEX's written approval | Commercial family `EEX`; data-scope grant required; no bulk or scheduled load from eex.com without that licence |
| WM/Reuters (LSEG), Bloomberg BFIX | FX fixes | Licensed; the subscriber's own entitlement | Operator import only; families `WMR`/`BFIX` need a grant |
| Trayport, ICE, ICIS, Platts, Argus, Kpler | prices, assessments | Licensed per subscriber | Commercial families; no data shipped; a connector uses the customer's own credentials |
| Norwegian Offshore Directorate (Sodir) FactMaps | field, platform and pipeline locations | NLOD 2.0: commercial reuse with attribution | Infrastructure import records licence and attribution per facility |
| North Sea Transition Authority open data | UK offshore installation locations | Open Government Licence v3: commercial reuse with attribution | As above |
| Global Energy Monitor trackers | LNG terminal, storage and pipeline locations | CC BY 4.0: commercial use with attribution | As above |
| SciGRID_gas IGGIELGN (DLR Institute of Networked Energy Systems, v1.1.2, doi:10.5281/zenodo.4767098) | map presentation only: generalised NW Europe trunk lines drawn faintly under the connections, and the general direction of each drawn connection leg | CC BY 4.0 (licence text in the dataset's `LICENSE`, checked 2026-11-17): commercial use, adaptation and redistribution with attribution; no share-alike | Built once into the bundle and `clients/web/public/map/context-pipelines.geojson` with source, version, DOI, licence and file SHA-256; attribution "Pipelines: SciGRID_gas IGGIELGN (DLR), CC BY 4.0" on the map and in the line key; never priced (see "Presentation geometry" below) |
| OpenStreetMap extracts | infrastructure gap filling | ODbL 1.0: attribution and share-alike for the database | As above; the import refuses non-commercial licences such as CC BY-NC |
| LNG terminal operators' tariff documents: Fluxys LNG (Zeebrugge), Elengy (Montoir, Fos Cavaou, Fos Tonkin), Deutsche Energy Terminal (Brunsbüttel, Wilhelmshaven) | Regulated regasification tariffs, cargo-class totals, gas in kind, auction results (the public LNG terminal tariff register, CP-11) | Checked 2026-11-18. Fluxys legal notice: "No reproduction, rental, lease, download ... without the prior written consent of Fluxys"; extracts only for private, non-commercial use. Elengy legal notice: reproduction "without the express permission of Elengy is strictly forbidden"; the notice binds by use of the site. DET: the imprint publishes no reuse terms | **Needs the firm's terms.** No operator document is read until the firm records that operator's permission (who, when, reference) in Admin → Data sources; the product never records it. The figures themselves are regulated tariffs the regulators also publish (CREG, CRE); whether the regulators' publications allow commercial reuse is not yet checked and would be the alternative route. No operator document is committed as a fixture |
| Kpler, Spire, MarineTraffic vessel data | LNG cargo positions, tracks, ETAs (the map's "LNG vessels" layer) | Licensed per subscriber; not redistributable; no AIS source is used whose terms this register has not reviewed for commercial use | Loaded only from the customer's own export or connector; market cargoes need the source's data scope (family `Kpler`); without it the map says the entitlement is missing. Demo vessels are `Kpler_Sim`, fictional and marked simulated |
| Natural Earth 1:50m (land, admin-0 boundary lines, admin-0 countries, populated places; github.com/nvkelso/natural-earth-vector, v5.2.0-pre, read 2026-11-18) | the bundled basemap: land, coast, country borders, country and city names (English and Chinese) | Public domain ("Everything here is public domain … use the maps in any manner … for personal, educational, and commercial purposes"; crediting unnecessary), credited anyway | Built by `scripts/ui/build_offline_basemap.py` into `clients/web/public/basemaps/` and served by the application; "Natural Earth" in the map's attribution. Borders are Natural Earth's de facto lines, so a mainland China installation uses the land-only outline |
| Inter (labels of the bundled basemap) | map label glyphs | OFL-1.1 (`clients/web/src/assets/fonts/fonts.json`, `THIRD_PARTY_NOTICES.md`): embedding and redistribution allowed, commercial use included; glyphs built from it are a font derivative distributed under the same licence | `scripts/ui/build_map_glyphs.mjs` renders SDF glyph ranges into `clients/web/public/basemaps/glyphs/Inter Regular/`; no remote glyph server; CJK names are drawn from the device's own fonts |
| Map tiles | basemap | OSM Foundation and CARTO public tiles are not for commercial embedding; OpenFreeMap and VersaTiles allow commercial use (OpenStreetMap data, ODbL attribution) | Default is the bundled basemap (no third-party request); the land-only outline in a China installation; an operator may name OpenFreeMap or VersaTiles, a licensed or self-hosted service (`EUROGAS_NEXUS_MAP_DEFAULT_PROVIDER`, Settings) |
| DeepSeek API (optional) | alert explanations | Provider API terms; prompts leave the deployment | Off unless an API key is configured server-side; payloads exclude licensed raw data |

Simulated price sources (`*_Sim`) generate synthetic numbers locally. They carry no
third-party data, but they must never be shown as market prices. They are disabled in
`trial` and `release` environments (`simulated_sources_allowed()`).

## Imbalance prices, checked 2026-11-19

My gas day (Today) wants the price a TSO cashes out an imbalance at, to say what leaving a hub
open would cost. No source is used yet, because no publication's reuse terms could be read in
full from this build environment (the hosts were not reachable: `nationalgas.com`,
`www.tradinghub.eu`). What was found, by web search only, on 2026-11-19:

- **National Gas (GB), System Marginal Buy and Sell Prices.** National Gas states that it
  publishes open data through its Gas Data Portal under its system-operator licence: "Under our
  Gas System Operator (GSO) licence, we must provide open data, which we do via our Gas Data
  Portal." (search-result text for https://nationalgas.com/our-businesses/operational-data/gas-data-portal;
  the page itself was not opened). The portal's own licence or terms page was not found, so
  whether SMP may be reused in a commercial product is **not established**. The existing
  "National Gas (GB)" row (demand, storage, LNG) does not extend to these prices by assumption.
- **Trading Hub Europe (DE), imbalance prices.** THE publishes preliminary and final imbalance
  prices (https://www.tradinghub.eu/en-gb/Publications/Prices/Imbalance-Prices) and portal terms
  of use with a "Use of data" section (https://www.tradinghub.eu/Portals/0/Portalnutzungbedingungen/2022_portal%20terms%20of%20use.pdf,
  a 2024 revision is referenced); the text of that section was not read. Not established.

Until a publication's terms are read and recorded here with the quoted sentence, the product
reads no imbalance price; nobody accepts terms or registers an account on the owner's behalf.
The firm's own entered premium and discount (assumption set, approved by a second person) are
the only basis, and the figure says so.

## EEX website terms, checked 2026-11-18

Checked before a requested 60-day load of EEX gas prices, which was **stopped** on this finding.

- Pages the EEX connector uses: https://www.eex.com/en/markets/natural-gas/gas-market-transparency
  (links the public NGP CSV files on `gasandregistry.eex.com`: TTF, ETF, FIN, LTU and LVA-EST,
  each as `*_NGP_15_Mins.csv` and a 60- or 45-day file). These are Neutral Gas Price
  reference indices, not exchange settlements; the page publishes no settlement or futures
  curve files for TTF, THE, PEG, ZTP, CEGH VTP, CZ VTP, PVB or NBP.
- robots.txt: `https://www.eex.com/robots.txt` lists sitemaps and disallows nothing;
  `gasandregistry.eex.com/robots.txt` does not exist (404).
- Terms: https://www.eex.com/en/disclaimer ("Copyright"), read 2026-11-18: "Neither this
  website nor the contents made available therein (including; graphic representations, audio
  and video clips, html code, buttons and text) may be copied, reprinted, published,
  transmitted, transferred, disseminated or distributed in any manner without the prior
  written approval of EEX AG. However, the preparation of a single copy for exclusive
  personal, non-commercial use by downloading onto an individual personal computer [...] are
  expressly permitted."
- End-of-day settlement prices are sold through EEX Group DataSource under its licensing
  conditions (https://www.eex.com/en/market-data/eex-group-datasource/licensing-conditions).

Consequence: storing EEX website data in a commercial product, even for one customer's
internal analysis, is outside the personal, non-commercial permission. EEX data enters the
product only through the customer's own DataSource licence or EEX's written approval (AGENTS.md
rule 18), under the licensed family `EEX` and its data-scope grant. Nobody accepts terms or
registers with EEX on the owner's behalf.

## Reference network bundle (MAP-01, decided 2026-11-14)

The product ships a north-west Europe reference network so the map works on a fresh
installation with no outbound network (`docs/operations/REFERENCE_NETWORK_BUNDLE.md`).

**Dataset.** ENTSOG Transparency Platform reference metadata only: connection points
(point key, EIC, label, type, ENTSOG's own map position `tpMapX/tpMapY`) and operator point
directions (operators, adjacent operators, booking platform, product flags), as read by the
product's own ENTSOG reference ingestion. No flow, capacity or tariff value is shipped.

**Terms, as checked on 2026-11-14.** The ENTSOG website terms (Art. 4.2) forbid
redistributing website content without consent, but state that data published on the
Transparency Platform is governed by the platform's own terms. Those are the "ENTSOG TP
Privacy & T&C of Use", LAG0689-26 Rev. 3 dated 10 November 2026
(entsog.eu, linked from "Privacy Policy and terms of use"). Article 5.1: "you may download,
store and use the contents of the ENTSOG TP in good faith and always complying with good
business practices regarding the re-use of publicly available data, and provided you keep
intact all trademark, copyright and other proprietary notices"; 5.2: cite the source and the
download date as "ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/", and do not imply
ENTSOG endorsement; 5.3: ENTSOG may ask for circulation statistics; 5.5: ENTSOG disclaims
responsibility for processed data. Nothing in the terms excludes commercial use or requires
share-alike. Article 3 reserves property rights "unless otherwise stated", and Article 5 is
that statement for TP data; it is a use permission, not an explicit redistribution licence.

**Decision.** Ship the bundle with the citation "ENTSOG TP [14-11-2026]
https://transparency.entsog.eu/" in the file and in every seeded row's metadata, and present
it as ENTSOG reference metadata, never as ENTSOG-endorsed.

Owner decision, 2026-11-15: the project does not redistribute ENTSOG data; the legal
confirmation step is not pursued. The bundle keeps the ENTSOG TP citation required by
Art. 5.2 ("ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/", with the download date,
in the file and in every seeded row's metadata).

**Positions.** ENTSOG publishes map coordinates, not WGS84. The bundle carries the same
approximate lon/lat transform the live ingestion stores (`display_approximation`, never
`verified`). 51 NWE points (including the Dornum and Emden landings) have no ENTSOG map
position; they carry no coordinate, are counted as "not located" and are never placed.

**Tariffs (decided 2026-11-17).** The TSO tariffs route pricing needs at interconnection
points are read from ENTSOG's `tariffsfulls` dataset under the same TP terms (the owner's
decision above covers ENTSOG data). IUK and BBL publish their own charging statements; the
product does not read their websites, because ENTSOG already publishes both operators'
charges at Bacton and Zeebrugge (IUK) and Bacton (BBL), and their site terms were not
reviewed. A leg no published row covers (the GTS exit at Balgzand, for one: ENTSOG has no
tariff there) stays "tariff not held"; nothing is estimated. The demo desk's simulated
tariffs for such legs are marked `SIMULATOR_ONLY` and removed once a published row covers the
same leg.

**Tariff sources beyond ENTSOG (checked 2026-11-19).** The tariff read covers every point of
the market-area graph plus the corridor (CEGH, CZ, PSV, PVB, Swiss transit), LNG and Norwegian
landing points listed in `reference_data/tariff_scope.py`, for the current and next gas year
and every standard product (`ingestion/entsog_tariffs.py`). ENTSOG TP answered with no tariff
at all for 42 of those 108 points (read 19-11-2026), and its National Gas figures are refused
(filed per year, published per day: see `OPERATOR_REFUSALS`). For the operators below the
product does **not** read the operator's own site: their terms could not be read from the
build environment (the hosts were outside its network allowance on 2026-11-19), so no terms
were reviewed, none accepted and no account registered. Each stays "tariff not held" in route
pricing until a reviewed figure is entered by an administrator; nothing is estimated.

| Operator / source | What ENTSOG lacks | Operator's own publication | Position |
|---|---|---|---|
| National Gas (GB NTS) | every National Gas row is refused (Bacton IUK, Bacton BBL, Moffat entry/exit; St Fergus, Easington, Isle of Grain, Milford Haven, Teesside entry) | IP reserve price notices and charging statements on nationalgas.com (p/kWh/d) | Not automated: site terms not reviewed (nationalgas.com unreachable from the build environment). Administrator entry |
| Interconnector (IUK) | nothing: IUK's entry and exit at Bacton and Zeebrugge are on ENTSOG | charging statement on fluxys.com / interconnector.com | ENTSOG only; site not read |
| BBL company | nothing for BBL itself (both directions at Bacton BBL on ENTSOG) | tariffs on bblcompany.com | ENTSOG only; site not read |
| GTS (Gasunie Transport Services) | exit to BBL at Julianadorp/Balgzand; entry from Gate and Eems LNG; Emden landings | tariff decisions and tables on gasunietransportservices.nl | Not automated: site terms not reviewed (host unreachable). Administrator entry |
| Fluxys Belgium | entry from Zeebrugge LNG, Zeebrugge ZPT (Norway), Dunkerque LNG / Alveringem | tariff lists on fluxys.com (Fluxys legal notice forbids download without consent, see the LNG row above) | Not automated: the notice above excludes it. Administrator entry with the firm's permission |
| NaTran (FR), Enagás (ES) | entry from French and Spanish LNG terminals; Larrau, Biriatou (VIP PIRINEOS is on ENTSOG) | tariff documents on natran.fr, enagas.es | Not automated: terms not reviewed. Administrator entry |
| Gassco / Gassled (Norway) | the Gassled area tariffs upstream of the landing points (regulated by the Norwegian ministry) | gassco.no tariff pages | Not automated: terms not reviewed; ENTSOG holds no Gassled tariff. Administrator entry |
| Swiss transit (FluxSwiss, Swissgas) | the Swiss side at Wallbach, Oltingue, Griespass, VIP Germany-CH | fluxswiss.com tariff pages | Not automated: terms not reviewed. Administrator entry |
| LNG terminal regasification | terminal tariffs are not TSO tariffs | see the LNG terminal row above | Unchanged: the LNG terminal tariff register (CP-11) |

**Administrator entry (2026-11-19).** Admin → Connectors → Access, "Transmission tariffs ENTSOG
does not publish" (`/api/route-cost/tariff-entries`, `application/tso_tariff_entries.py`): a
person reads the operator's published charge and enters it with the source URL, publication date
and the place in the document; a second person reviews it (four eyes). This is a person reading a
public document, not automated retrieval, so the site terms above are not engaged; the firm
decides whether its staff may read a site whose terms it has not reviewed. The figure is stored
as published and cited; a candidate prices as indicative, a reviewed entry as a reviewed public
tariff, and an ENTSOG row for the same leg and period retires it. The product enters nothing by
itself.

**Lines.** ENTSOG's API publishes no route geometry, and its map drawings are ENTSOG
property; no OpenStreetMap or other share-alike geometry is used. The bundle's edges are
schematic: zone links (a point to the trading point of the entry-exit zone its operator
belongs to), which are membership and never drawn, and market-area adjacency (which market
areas an interconnection point joins, and the two ends of the IUK and BBL pipelines), derived
from the TP `interconnections` and `connectionpoints` datasets under the same TP Terms of Use
Art. 5 and cited "ENTSOG TP [16-11-2026] https://transparency.entsog.eu/" in the bundle's
`adjacency` block and every seeded adjacency row. They are drawn as dashed schematic lines,
along the open SciGRID_gas trunk lines where those give the general direction (see
"Presentation geometry"), else straight, and never presented as surveyed pipeline routes.

## Presentation geometry (P2, decided 2026-11-17)

**Dataset.** SciGRID_gas IGGIELGN 1.1.2 (Zenodo record 4767098, published 2021-05-17 by the
DLR Institute of Networked Energy Systems; `IGGIELGN.zip` SHA-256
`a3caa7d94f212da67d69bb0106d893e0ad1548761cfcd185aca78f0a5d745b9f`), an abstracted European gas
transmission network assembled by the SciGRID_gas project from open sources (its INET, GIE,
GSE, IGU, LKD, GB and NO inputs).

**Terms, as checked on 2026-11-17.** The Zenodo record states the licence `cc-by-4.0`; the
archive's `data/LICENSE` says the data was "collated in such a way, that it has a copyright,
that does not restrict the project from making the data available to other users. Hence the
following applies to this data set and the documentation" followed by the full text of
Creative Commons Attribution 4.0 International. CC BY 4.0 permits commercial use, adaptation
and redistribution, requires attribution, a licence reference and an indication of changes,
and imposes no share-alike. The product relies on the publisher's licence for the whole
dataset; some segment ids show their geometry came from public maps (for example
`EntsoG_Map_*`), which the publisher collated under that licence.

**Use.** Presentation only. The bundle build keeps the trunk lines (diameter of at least
600 mm) with an end in north-west Europe, generalised (Douglas-Peucker, about 2 km; positions
to three decimals), and gives each drawn connection leg a path along them where one runs
within 45 km of both ends without a long detour. Changes are indicated in the file's
provenance (`use`, `trunk_lines`). Route pricing, capacity and tariffs never read it (contract
test `tests/contract/test_reference_presentation_geometry.py`); the connections stay dashed
and schematic, and their hover card says they are drawn along the open reference pipelines
for the general direction, not a surveyed route.

**Attribution.** "Pipelines: SciGRID_gas IGGIELGN (DLR), CC BY 4.0" in the map's attribution
control (the context layer's source) and in the line key; source, DOI and licence in the
bundle's `presentation_geometry` block and in the context file's properties.
