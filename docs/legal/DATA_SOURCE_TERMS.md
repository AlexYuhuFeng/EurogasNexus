# Data-source and service terms for commercial use

Code dependencies are covered by [DEPENDENCY_LICENSE_REVIEW.md](DEPENDENCY_LICENSE_REVIEW.md) and gated in CI.
Data feeds and hosted services are governed by their providers' terms instead. This
table is the engineering summary the product enforces, not legal advice; legal should
confirm each provider's current terms before a production deployment.

| Source | Use in product | Commercial-use position | How the product enforces it |
|---|---|---|---|
| ENTSOG Transparency Platform | flows, capacity, tariffs (`tariffsfulls`: the reserve prices TSOs publish per interconnection point, stored in the tariff register for route pricing) | Free public data; TP Terms of Use Art. 5 (see "Reference network bundle" below): store and use with the source and download date cited | Live ingest gated by a provider certification record; every tariff row cites "ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/" and its ENTSOG row id, and keeps the figure as the operator published it (read per MWh only when priced). Tariffs are read one point per query, 2 s apart (`--entsog-pace-seconds`). Fair use: the TP API manual (v2.1, read 2026-11-18) asks that queries be filtered by dates, points and indicators to stay within its 60-second timeout and share the platform fairly; it states no other rate limit. The landing-point history (`scripts/ops/backfill_entsog_landings.py`, run after a successful scheduled ENTSOG read) reads one quarter of physical flow at the ten landing point-directions per query, at most 8 queries a run, 3 s apart, through the same approval and certification gate; `GET /api/fundamentals/flows` returns the citation |
| ENTSOG Transparency Platform, shipped reference bundle | European network points (every active ENTSOG balancing zone), operators, balancing-zone positions and approximate point positions on a fresh or offline installation | TP Terms of Use (Rev. 3, 10 Nov 2026) Art. 5: download, store and use in good faith with the source and download date cited; no clause excludes commercial use or redistribution (see "Reference network bundle" below) | `src/eurogas_nexus/reference_data/nwe_reference_network.json` carries the citation; positions marked approximate; links marked schematic |
| ENTSOG Transparency Platform, supply corridors | Import corridors' landing points, upstream operators, firm technical capacity and status from physical flow (`reference_data/supply_corridors.json`) | Same TP Terms of Use (Rev. 3) Art. 5: download, store and use, citing the source and date | Built by `scripts/ops/build_supply_corridors.py` (one point and window per query, 2 s apart); the citation and date are in the file and on every corridor |
| Gassco pipeline pages (gassco.eu, Norwegian export pipelines) | Facts only for the Norwegian corridors: route, length, diameter, first gas | The site publishes no reuse terms (only a privacy policy, checked 2026-11-26); bare facts are stored with the page URL and read date, no text or image is reproduced. Confirm with Gassco before relying on more than these facts | `supply_corridors.CORRIDORS[*].facts`, `source` and `read` per corridor |
| ENTSOG Transparency Platform, urgent market messages | transmission outages (REMIT UMMs TSOs publish to ENTSOG) | Same TP Terms of Use (Rev. 3) Art. 5 as the rows above: download, store and use, citing "ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/" | `src-entsog-umm`, `scripts/ops/ingest_remit_entsog.py`; the download date is in every stored message's source reference and the citation is returned with each outage row (`attribution`) |
| GIE AGSI+/ALSI | storage, LNG (daily, by country and the EU total, history included); facility listing (EIC, name, country, operator) as facility identity | Free with a registered API key. Reuse, commercial included, with GIE named as the source: "All data published on AGSI & ALSI can be used or repackaged in any way you see fit but a clear indication on GIE as data source is mandatory. A mention of GIE, AGSI or ALSI (as applicable) as data source is a minimum requirement." (https://agsi.gie.eu/account, "API data usage", read 2026-11-17; no clause limits history or commercial use). The API documentation is available only after registration; GIE publishes no rate limit | Key held server-side; certification gate; the listing is loaded by `scripts/ops/ingest_gie_facilities.py` into the identity tables (no position: GIE publishes none). History is backfilled one gas year per read at a 2-second pace by `scripts/ops/backfill_gie_history.py` through the same gated path; `GET /api/fundamentals/storage` returns the attribution with every read |
| ENTSOG website, CAM NC auction calendar (entsog.eu, yearly `.xlsx`) | Capacity auction dates (yearly, quarterly, monthly; firm and interruptible; offer-level publication days) on the desk's calendar and in the capacity notices | entsog.eu website terms Art. 4.1: "You may download, store and use the contents of this Website" with its notices intact; Art. 4.2: not made available to another party (see "Watched publications, checked 2026-11-28") | Fetched daily by the publication watch (`application/publication_watch.py`, robots.txt read first); kept for the firm's own use, never redistributed; every item carries "Source: ENTSOG and/or its members, CAM NC Auction Calendar" and its fetch time; no ENTSOG file is committed (the tests use a workbook written for them) |
| ECB reference rates, €STR | FX, €STR fixings | Free; reuse permitted with source attribution | Public baseline family `ECB` |
| Bank of England (SONIA) | SONIA fixings | Free; administrator terms (attribution, no endorsement) | Public baseline family `BOE`; attribution returned with every resolved rate |
| NY Fed (SOFR) | SOFR fixings | Free; NY Fed terms of use (attribution) | Public baseline family `NYFED`; attribution returned |
| ECMWF Open Data | weather forecasts | CC-BY-4.0: commercial use with attribution | Certified source; attribution in evidence |
| Eurostat (`nrg_chdd_m` heating degree days by country, monthly; `nrg_cb_gas` gas use by sector) | Shipped NW Europe degree-day reference for the forward balance (CP-25): 30-year monthly HDD normals and their spread, country weights from households' and services' gas use | Eurostat data © European Union; reuse, commercial reuse included, authorised with the source acknowledged (Commission reuse policy, CC BY 4.0). No key, no terms to accept. Confirm the current copyright notice before a production deployment | A versioned file built by `scripts/ops/build_hdd_reference.py` (diff reviewed when Eurostat publishes a year); the attribution travels in every forward-balance read (`weather_reference.attribution`) |
| ENTSO-E Transparency Platform | power prices, load, generation by fuel | Free with a registered token; the platform's terms permit reuse with attribution to ENTSO-E (confirm the current terms at go-live) | Public baseline family `ENTSOE`; token held server-side |
| Elexon Insights Solution (BMRS) | GB generation by fuel, demand outturn, market index price | Free, no key; BMRS Data Licence permits reuse including commercial use with the attribution "Contains BMRS data © Elexon Limited copyright and database right" (confirm the current terms at go-live) | Public baseline family `ELEXON`; attribution in the connector description and evidence |
| REMIT UMMs (EEX Transparency, GIE IIP, Gassco UMM and other inside-information platforms) | gas facility outages | Inside information operators must publish; each platform sets reuse terms, confirm commercial reuse for the platform used | Public baseline family `REMIT`; import records the platform; platforms without published reuse terms (EEX Transparency, Gassco, PRISMA) need written confirmation (`--terms-confirmed`); GIE IIP permits reuse with source credit ("All data published on IIP can be used or repackaged in any way you see fit but a clear indication on GIE as data source is mandatory", iip.gie.eu API page, checked 2026-11-14); its API needs a registered key (the GIE AGSI/ALSI key is accepted) and is collected by `scripts/ops/ingest_remit_iip.py` |
| Official news feeds (NEWS-1): GOV.UK DESNZ (Open Government Licence v3.0), European Commission DG Energy (CC BY 4.0), EUR-Lex (EUR-Lex reuse policy), ACER (legal notice, titles only) | news, policy and regulation items with links, cited in the news note | Commercial reuse with attribution, terms quoted and dated in [NEWS_SOURCE_REGISTRY.md](../integration/NEWS_SOURCE_REGISTRY.md) (read 2026-11-24) | `domain/news/sources.py`: polled only with reuse permitted, a recorded feed address on the publisher's host and robots.txt allowing; licence note and attribution on every item; wire services, EEX website and LNG operators' sites excluded with the reason |
| US EIA open data | Henry Hub daily spot | US government work, public domain; free API key | Public baseline family `EIA`; key held server-side |
| US EIA Henry Hub futures (NYMEX contracts 1-4, `RNGC1`-`RNGC4`) | Henry Hub forward for a cargo's pricing month (CP-12) | Checked 2026-11-18: EIA content is public domain (its "Copyrights and Reuse" page), but the futures table states "Futures prices after April 5, 2024, are not available": EIA no longer publishes them | **Not ingested.** A Henry Hub forward comes from the customer's licensed exchange data (the `ICE Endex, EEX, CME` row) or the firm's own mark; otherwise the cargo model uses the held EIA daily spot as a flat proxy, class "indicative", labelled "spot proxy" |
| LNG voyage distances (sea routes, CP-12 `freight_route`) | Nautical miles per load port, discharge port and routing | No openly licensed sea-distance table chosen yet; vendor distance tables are licensed per user | **Shipped empty.** The firm enters each route with where the distance came from (versioned, audited); the product ships no distances of its own until the owner picks a source |
| ICE Endex, EEX, CME, NGX settlements | Gas, carbon (EUA, UKA), API2 coal, power, Henry Hub, AECO | Exchange licence held by the customer; non-display use for analytics must be covered | Licensed families `ICE_ENDEX`, `EEX`, `CME`, `NGX`; granted per user by an administrator |
| National Gas (GB) | demand; storage and LNG stock, storage withdrawal/injection and LNG send-out (data portal, keyless CSV) | Open data licence; attribution | Certified source (demand); public baseline family `NATIONAL_GAS` (storage, LNG) |
| Imbalance (cash-out) prices: National Gas SAP and SMP buy/sell (GB, NBP), Trading Hub Europe VTP daily average and positive/negative imbalance prices (DE, THE), other zones' neutral or imbalance prices | Today → My gas day: the cost of leaving a hub's net open; the board's NBP and THE within-day rows (SAP, VTP daily average: reference indices) | National Gas and THE: **fetched under the publisher's written consent** reported by the owner on 2026-11-28 (own use, no resale; see "Written consents reported by the owner, 2026-11-28"). The website terms found on 2026-11-19 and 2026-11-28 stand for anyone without that consent. Other zones: not verified, not ingested | `the-imbalance-prices`, `national-gas-smp` (documented APIs; source families `THE`, `NATIONAL_GAS_PRICES`, internal use only). My gas day values an open net at the newest published cash-out premium (SMP buy over SAP, THE's negative imbalance price over the VTP daily average; the discount likewise), with its gas day and source; without one, at the firm's approved assumption set (`balancing.short_premium`, `balancing.long_discount`), labelled as an assumption |
| EEX public market data (TTF NGP reference, natural gas trading and holiday calendars) | the board's TTF within-day row (the TTF neutral gas price, a reference index); the desk's calendar | The website terms (see "EEX website terms, checked 2026-11-18" below) permit only a single copy for personal, non-commercial use without EEX's written approval. EEX's written consent to the firm's own use of what it makes publicly available, no resale, was reported by the owner on 2026-11-28 (see "Written consents reported by the owner, 2026-11-28"): the NGP 60-day file and the calendars are **fetched under that consent**. Exchange settlements and anything behind a login still need the customer's EEX DataSource licence | Consented family `EEX_PUBLIC` (internal use only, never in a file or report for outside the firm, never to an anonymous caller); the licensed family `EEX` and its data-scope grant are unchanged |
| WM/Reuters (LSEG), Bloomberg BFIX | FX fixes | Licensed; the subscriber's own entitlement | Operator import only; families `WMR`/`BFIX` need a grant |
| Trayport, ICE, ICIS, Platts, Argus, Kpler | prices, assessments | Licensed per subscriber | Commercial families; no data shipped; a connector uses the customer's own credentials |
| Norwegian Offshore Directorate (Sodir) FactMaps | field, platform and pipeline locations | NLOD 2.0: commercial reuse with attribution | Infrastructure import records licence and attribution per facility |
| North Sea Transition Authority open data | UK offshore installation locations | Open Government Licence v3: commercial reuse with attribution | As above |
| Global Energy Monitor trackers | LNG terminal, storage and pipeline locations | CC BY 4.0: commercial use with attribution | As above |
| SciGRID_gas IGGIELGN (DLR Institute of Networked Energy Systems, v1.1.2, doi:10.5281/zenodo.4767098) | map presentation only: generalised European trunk lines drawn faintly, and the line of each import supply corridor where its segments join source and landing under the connections, and the general direction of each drawn connection leg | CC BY 4.0 (licence text in the dataset's `LICENSE`, checked 2026-11-17): commercial use, adaptation and redistribution with attribution; no share-alike | Built once into the bundle and `clients/web/public/map/context-pipelines.geojson` with source, version, DOI, licence and file SHA-256; attribution "Pipelines: SciGRID_gas IGGIELGN (DLR), CC BY 4.0" on the map and in the line key; never priced (see "Presentation geometry" below) |
| OpenStreetMap extracts | infrastructure gap filling | ODbL 1.0: attribution and share-alike for the database | As above; the import refuses non-commercial licences such as CC BY-NC |
| LNG terminal operators' tariff documents: Fluxys LNG (Zeebrugge), Elengy (Montoir, Fos Cavaou, Fos Tonkin), Deutsche Energy Terminal (Brunsbüttel, Wilhelmshaven) | Regulated regasification tariffs, cargo-class totals, gas in kind, auction results (the public LNG terminal tariff register, CP-11) | Checked 2026-11-18. Fluxys legal notice: "No reproduction, rental, lease, download ... without the prior written consent of Fluxys"; extracts only for private, non-commercial use. Elengy legal notice: reproduction "without the express permission of Elengy is strictly forbidden"; the notice binds by use of the site. DET: the imprint publishes no reuse terms | **Needs the firm's terms.** No operator document is read until the firm records that operator's permission (who, when, reference) in Admin → Data sources; the product never records it. The figures themselves are regulated tariffs the regulators also publish (CREG, CRE); whether the regulators' publications allow commercial reuse is not yet checked and would be the alternative route. No operator document is committed as a fixture |
| Kpler, Spire, MarineTraffic vessel data | LNG cargo positions, tracks, ETAs (the map's "LNG vessels" layer) | Licensed per subscriber; not redistributable; no AIS source is used whose terms this register has not reviewed for commercial use | Loaded only from the customer's own export or connector; market cargoes need the source's data scope (family `Kpler`); without it the map says the entitlement is missing. Demo vessels are `Kpler_Sim`, fictional and marked simulated |
| Natural Earth 1:50m land (github.com/nvkelso/natural-earth-vector, v5.2.0-pre, read 2026-11-18) | the bundled offline basemap: land and coast only, with no country borders and no place names | Public domain ("Everything here is public domain … use the maps in any manner … for personal, educational, and commercial purposes"; crediting unnecessary), credited anyway | Built by `scripts/ui/build_offline_basemap.py` into `clients/web/public/basemaps/land-trading-region.geojson` and served by the application; "Natural Earth" in the map's attribution. Because the outline carries no borders or names, a mainland China installation can use it |
| Inter (labels of the bundled basemap) | map label glyphs | OFL-1.1 (`clients/web/src/assets/fonts/fonts.json`, `THIRD_PARTY_NOTICES.md`): embedding and redistribution allowed, commercial use included; glyphs built from it are a font derivative distributed under the same licence | `scripts/ui/build_map_glyphs.mjs` renders SDF glyph ranges into `clients/web/public/basemaps/glyphs/Inter Regular/`; no remote glyph server; CJK names are drawn from the device's own fonts |
| Map tiles | basemap | OpenFreeMap serves OpenStreetMap data (ODbL) with OpenMapTiles styles; free for commercial use, no key, attribution required. The OSM Foundation tile servers (`tile.openstreetmap.org`, usage policy excludes commercial products) and CARTO public tiles are not used | One basemap: OpenFreeMap, attribution "© OpenStreetMap contributors, © OpenMapTiles" in the map corner. The bundled Natural Earth outline (public domain, served by the application) is the automatic fallback when OpenFreeMap is unreachable and the basemap of a mainland China installation (`EUROGAS_NEXUS_MAP_DEFAULT_PROVIDER=outline`). No provider choice in Settings |
| DeepSeek API (optional) | alert explanations | Provider API terms; prompts leave the deployment | Off unless an API key is configured server-side; payloads exclude licensed raw data |

Simulated price sources (`*_Sim`) generate synthetic numbers locally. They carry no
third-party data, but they must never be shown as market prices. They are disabled in
`trial` and `release` environments (`simulated_sources_allowed()`).

## Imbalance prices, checked 2026-11-19

*Superseded for the firm's own use on 2026-11-28 by the written consents of National Gas and
Trading Hub Europe (see "Written consents reported by the owner, 2026-11-28"); the finding below
is kept as it was read.*

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

*Superseded for the firm's own use of what EEX makes publicly available on 2026-11-28 by EEX's
written consent (see "Written consents reported by the owner, 2026-11-28"); the finding below
still holds for exchange settlements and for anything else EEX sells or puts behind a login.*

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

## Watched publications, checked 2026-11-28

Owner's principle (2026-11-28): what the desk needs and is publicly published, the product gets
from where it is published and tells the desk; nobody types it in. Bounded by rule 18:
publicly viewable is not the same as free to collect. Each publication below is one entry of
`src/eurogas_nexus/domain/publications/registry.py`; a test holds the two in step, and an
entry without a finding here is never fetched. Pages were read from the build environment on
2026-11-28 unless marked "not verified". Nobody accepted terms, registered or signed up
anywhere.

Verdicts: **fetched** (the terms allow storing it for the firm's own use), **fetched under
written consent** (the website terms forbid storing it, but the publisher's written consent
reported by the owner on 2026-11-28 covers the firm's own use, no resale: see the next
section; the website-terms finding is kept in the "Terms, as read" column),
**consented, not yet implemented** (covered by a consent, no reader written yet), **consented,
but the site refuses automated reading** (none at present), **hand-maintained** (the terms
forbid storing it: the desk keeps a file and the product reminds them, with the link, to check
it by a date; the exchange calendars were hand-maintained until 2026-11-28 and the file stays
as their fallback), **link only** (viewable, not storable, or the terms could not be read).

| Id | Publication | Terms, as read | Verdict |
|---|---|---|---|
| `entsog-cam-auction-calendar` | ENTSOG CAM NC auction calendar, `.xlsx` linked from https://www.entsog.eu/capacity-allocation-mechanisms-nc | https://www.entsog.eu/privacy-policy-and-terms-use Art. 4.1: "You may download, store and use the contents of this Website provided you keep intact all trademark, copyright and other proprietary notices indicated." Art. 4.2: "You shall not ... make the contents or any part of It, of this Website available to any other party ... without ENTSOG's express prior written consent". Art. 4.4: indicate the source "ENTSOG and/or its members" and the section's title. robots.txt disallows only `/core/`, `/profiles/` and `/README.md` | **Fetched**, daily. Kept for the firm's own use on its own installation; not passed to anyone; source and section cited on every item. This replaces the earlier "read by a person" note in the tariff publisher registry, which rested on Art. 4.2 alone |
| `eex-trading-calendar` | EEX Natural Gas Trading Calendar `<year>` (`.xlsx`) linked from https://www.eex.com/en/trading-resources/trading-information/calendar | The EEX finding of 2026-11-18: only "a single copy for exclusive personal, non-commercial use" | **Fetched under written consent** (EEX), daily: natural gas futures exchange holidays and each maturity's last trading day. Replaces the hand file's `EEX` venue for the years it covers; the hand file is the fallback |
| `eex-holiday-calendar` | EEX Holiday Calendar, Derivatives & Emissions Spot (`.pdf`), same page | As above | **Fetched under written consent** (EEX), daily. It states: "Gas and Freight derivatives are offered for trading on 24th and 31st December from 08:00 am to 13:00 CET" and "The calendar is applicable continuously for all years until further notice". This resolves the hand file's open question: on 24 and 31 December EEX gas trades 08:00-13:00 CET (an early close), it is not closed |
| `ice-endex-trading-schedule` | ICE Endex Trading Schedule, https://www.ice.com/publicdocs/ICE_Endex_Trading_Schedule.pdf | https://www.ice.com/terms-of-use: "we hereby grant you a limited license ... to download and print copies of any content ... but only for your own personal, non-commercial use ... The foregoing license does not include use of any data mining, robots or similar data gathering or extraction methods"; and no "systematic retrieval to create collections, compilations, databases" without ICE's written permission. robots.txt allows `/publicdocs/` | **Fetched under written consent** (ICE), daily: closed days and early settlements or closes (key A to D). Replaces the hand file's `ICE_ENDEX` venue for the years it covers |
| `ice-futures-europe-trading-schedule` | IFEU Trading Schedule (UK natural gas), https://www.ice.com/publicdocs/Trading_Schedule.pdf | as ICE above | **Fetched under written consent** (ICE), daily: the days UK natural gas is closed and, from the Christmas appendices, its shortened settlement period and close. Replaces the hand file's `ICE_FUTURES_EUROPE` venue for the years it covers |
| `ice-futures-end-of-day` | ICE end-of-day TTF and UK NBP futures prices on the product pages, e.g. https://www.ice.com/products/27996665/Dutch-TTF-Natural-Gas-Futures/data | as ICE above | **Consented, not yet implemented.** The product page's own text carries the contract calendar but no price; prices are drawn by the page's script from a data service ICE does not document for automated reading, which the product does not read. ice.com sits behind a bot filter that on 2026-11-28 once answered the product's robots.txt read with HTTP 200 and a page titled "Attention Required! \| Cloudflare" ("Sorry, you have been blocked"), then answered normally. Ask ICE how they prefer end-of-day prices to be read |
| `eex-market-data` | EEX public market data tables (natural gas spot and futures), https://www.eex.com/en/market-data/natural-gas | The EEX finding of 2026-11-18 | **Consented, not yet implemented.** The pages carry no prices themselves; a script draws the tables from a data service EEX does not document for automated reading. Ask EEX for a file or a documented address |
| `prisma-auctions` | PRISMA capacity platform, https://www.prisma-capacity.eu/ | The public site publishes no reuse terms (imprint and legal documents pages read); offers and results need a platform account under the PRISMA GTCs | **Consented, not yet implemented.** Only what PRISMA publishes without an account is covered; auction dates follow ENTSOG's calendar (fetched above) |
| `gsa-platform-auctions` | GSA Platform (GAZ-SYSTEM), https://gsaplatform.eu/ | Not verified: the site answered with a web-firewall error page | **Link only**; none of the desk's five hubs; not covered by the consents |
| `rbp-auctions` | Regional Booking Platform (FGSZ), https://rbp.eu/ | Not verified: a script application with no terms readable without signing in; `www.rbp.eu` not reachable (proxy 502) | **Link only**; none of the desk's five hubs; not covered by the consents |
| `fluxys-lng-zeebrugge-slots` | Fluxys LNG, Zeebrugge slots | Fluxys legal notice (checked 2026-11-18, see the LNG terminal row above): no reproduction or download without written consent | **Consented, not yet implemented** |
| `dunkerque-lng-slots` | Dunkerque LNG capacity booking (now on fluxys.com) | Fluxys legal notice, as above | **Consented, not yet implemented** |
| `grain-lng-uioli-board` | Isle of Grain LNG UIOLI bulletin board, https://www.grainlng.com/operational-information | https://www.grainlng.com/terms-and-conditions: "You may make a print copy for personal use ... You may not distribute, reverse engineer, or commercially exploit Website or Services content except as permitted by law." Bids go by e-mail | **Consented, not yet implemented** |
| `gate-terminal-slots` | Gate terminal, https://www.gate.nl/ | Not verified: proxy 502 for `www.gate.nl` and `gate.nl` | **Consented, not yet implemented** |
| `det-lng-auctions` | Deutsche Energy Terminal, https://energy-terminal.de/en/capacity-marketing/trader-information | The imprint publishes no reuse terms; auctions run on PRISMA | **Consented, not yet implemented** |
| `deutsche-regas-mukran` | Deutsche ReGas, https://deutsche-regas.de/en/ | Not verified: a script application; the imprint did not load as text | **Consented, not yet implemented** |
| `enagas-lng-capacity`, `enagas-storage` | Enagás GTS capacity allocation, https://www.enagas.es/en/energy-transition/gas-network/infrastructure-supply-capacity-allocation/ | https://www.enagas.es/en/legal-notice/ §6: contents "may not be subject to further modification, copying, alteration, transformation, reproduction ... without the express authorization of their owners" | **Consented, not yet implemented** |
| `uniper-storage-offers` | Uniper Energy Storage, https://www.uniper.energy/ | Not verified: the site answered 403 | **Link only**; not covered by the consents |
| `fluxys-loenhout-storage` | Loenhout storage (Fluxys Belgium) | Fluxys legal notice, as above | **Consented, not yet implemented** |
| `the-imbalance-prices` | THE prices through the DataExport API, https://api.tradinghub.eu/api/dataexport/xmlexport/PricesEnergyImbalance (manual https://api.tradinghub.eu/api/dataexport/manual/en) | Website disclaimer (https://www.tradinghub.eu/en-gb/Home/Disclaimer): "Die Vervielfältigung von Informationen oder Daten ... bedarf der vorherigen schriftlichen Zustimmung von Trading Hub Europe." The API manual says every export is "reachable without credentials, keys or registration ... published market data, open to everyone" with fair-use limits (standard tier 20 a second, 300 a minute, 3,000 an hour), asks every client to send a User-Agent naming itself, but grants no reuse licence; the portal terms of use cover registered portal users only | **Fetched under written consent** (THE), every six hours: the VTP daily average price and the positive and negative imbalance prices per gas day, history from gas day 2021-10-01 read once |
| `national-gas-smp` | National Gas SAP and SMP buy/sell, Gas Operational Data API, https://api.nationalgas.com/operationaldata/v1/publications/gasday (documented at https://data.nationalgas.com/ under APIs) | https://www.nationalgas.com/our-policies/terms-and-conditions: no reuse licence; "developed for information purposes only and not for financial analysis purposes"; the Gas Data Portal states none of its own | **Fetched under written consent** (National Gas), every six hours: SAP, SMP Buy and SMP Sell, Actual Day (PUBOB603-605), five years of history read once |
| `mibgas-prices` | MIBGAS PVB daily prices, `MIBGAS_Data_<year>.csv` on https://www.mibgas.es/en/file-access | https://www.mibgas.es/en/cccontent/legal-notice: "Sin citar la fuente queda prohibida la reproducción total o parcial ... y cualquier otro acto que no haya sido expresamente autorizado" | **Fetched under written consent** (MIBGAS), every six hours: day-ahead, month-ahead, Q+1 and Y+1 at PVB, history from 2021 (the CSV files of 2016 to 2020 answer 404) read once |
| `eex-ngp` | EEX TTF neutral gas price, https://gasandregistry.eex.com/Gas/NGP/TTF_NGP_60_Days.csv linked from https://www.eex.com/en/markets/natural-gas/gas-market-transparency | The EEX finding of 2026-11-18 stands for anyone without EEX's consent | **Fetched under written consent** (EEX), every six hours: sixty delivery days per file, kept from the first read on |

Hosts the build environment could not read on 2026-11-28 (the proxy answered 502, or the site
refused): `www.gate.nl`, `gate.nl`, `www.rbp.eu`, `www.uniper.energy` (403),
`gsaplatform.eu` (firewall page). Their findings are marked "not verified".

E-mail-only or e-mail-first announcements (not read; see
`docs/integration/DESK_MAILBOX_DESIGN.md`): Grain LNG slot bids (by e-mail on a Short Term
Access Confirmation Notice), PRISMA's newsletter, and the operators' customer notices to
registered shippers (Gate, Fluxys LNG, DET/Gasfin) that do not appear on a public page.

## Written consents reported by the owner, 2026-11-28

The owner reports that each publisher below, contacted by e-mail and message, gave written
consent to use the data it makes publicly available, "so long as those data are used by us and
we're not reselling them". The owner holds the written consents and hands them to the desk's
organisation when the product goes live. **The development team has not seen the documents**;
each record below is the owner's report, not a reviewed licence. The records ship as data in
`src/eurogas_nexus/reference_data/publisher_consents.toml` (a test holds the two in step); the
earlier findings they supersede stay in this register as they were read.

| Publisher | Scope (as stated) | Basis | Reported | Supersedes |
|---|---|---|---|---|
| Trading Hub Europe | publicly available data; the firm's own use; no resale or redistribution | written consent held by the owner; not seen by the development team | 2026-11-28 | "Watched publications, checked 2026-11-28" (`the-imbalance-prices`: link only, the disclaimer asks for prior written consent); "Imbalance prices, checked 2026-11-19" |
| MIBGAS | as above | as above | 2026-11-28 | "Watched publications, checked 2026-11-28" (`mibgas-prices`: link only) |
| National Gas | as above | as above | 2026-11-28 | "Watched publications, checked 2026-11-28" (`national-gas-smp`: link only); "Imbalance prices, checked 2026-11-19" |
| Fluxys | as above | as above | 2026-11-28 | "Watched publications, checked 2026-11-28" (`fluxys-lng-zeebrugge-slots`, `dunkerque-lng-slots`, `fluxys-loenhout-storage`: link only) |
| Grain LNG | as above | as above | 2026-11-28 | "Watched publications, checked 2026-11-28" (`grain-lng-uioli-board`: link only) |
| Gate terminal | as above | as above | 2026-11-28 | "Watched publications, checked 2026-11-28" (`gate-terminal-slots`: link only) |
| Enagás | as above | as above | 2026-11-28 | "Watched publications, checked 2026-11-28" (`enagas-lng-capacity`, `enagas-storage`: link only) |
| Deutsche Energy Terminal (DET) | as above | as above | 2026-11-28 | "Watched publications, checked 2026-11-28" (`det-lng-auctions`: link only) |
| Deutsche ReGas | as above | as above | 2026-11-28 | "Watched publications, checked 2026-11-28" (`deutsche-regas-mukran`: link only) |
| PRISMA | as above | as above | 2026-11-28 | "Watched publications, checked 2026-11-28" (`prisma-auctions`: link only) |
| EEX | as above | as above | 2026-11-28 | "EEX website terms, checked 2026-11-18"; "Watched publications, checked 2026-11-28" (`eex-trading-calendar`: hand-maintained; `eex-ngp`: link only) |
| ICE | as above | as above | 2026-11-28 | "Watched publications, checked 2026-11-28" (`ice-endex-trading-schedule`, `ice-futures-europe-trading-schedule`: hand-maintained) |

**How the product holds to the scope** (enforced in code, not only stated here):

- *Fetching.* A publication whose website terms forbid storing it is fetched only while its
  publisher has a record here (`domain/publications/registry.fetch_refusal`) and an
  administrator has not withdrawn it in Admin → Data sources → Watched publications
  (`application/publisher_consents`, table `publisher_consent_states`). A withdrawal is
  audited, stops fetching at once, and leaves the data held in place, marked "consent
  withdrawn on <date>" wherever it is shown. Only what the publisher shows without a login or
  an account is read; nobody signs up, registers or accepts terms on the owner's behalf.
- *Polite reading*, whatever the consent: a generic client name
  (`EurogasNexus-PublicationWatch/1.0`, no person, firm or place), robots.txt read first on
  every host, documented APIs where the publisher offers one (THE's DataExport API, National
  Gas's Gas Operational Data API), conditional requests where supported (ETag, Last-Modified),
  one request at a time two seconds apart, every six hours for prices and daily for calendars,
  the history read once and then only the last days, the wait doubled after each failed check
  (at most a day) and never shorter than a publisher's Retry-After. A site that refuses
  automated reading is not worked around: it stays "consented, but the site refuses automated
  reading; ask the publisher how they prefer to be read", with the exact response recorded.
- *The firm's own use.* Data fetched under consent is stored under its own source families
  (`THE`, `NATIONAL_GAS_PRICES`, `MIBGAS`, `EEX_PUBLIC`, `ICE_PUBLIC`). Every identified user of
  the firm reads it (the board, the chart, My gas day, the SDK and API with the user's own
  key); a caller that presented no credential (a deployment that trusts its network) does not
  (`security/identity.consented_row_allowed`).
- *No resale or redistribution.* Every export decision treats these families as **internal use
  only** (`governance/entitlement.file_export_decision`, `application/licensed_use`): a CSV,
  XLSX or PDF that carries them says "internal-use-only, no-redistribution", and a report for
  distribution outside the firm (`audience = shareable`) that would carry them is refused,
  whatever a licence record says (`application/reports/engine.redistributable_families`).
- *The daily packs* go to the firm's own managers and risk function, including the remote
  office: that is the firm's own use and is allowed. They carry the internal-use-only mark.

**Questions for the owner to settle with the publishers** (the scope as reported does not
answer them): whether "publicly available" includes an open API that has terms of its own
(THE's DataExport, National Gas's Gas Operational Data API); whether the firm's own use covers
a figure derived from the data in a report to a counterparty, a broker or an auditor; whether
EEX's and ICE's consents cover the exchanges' publicly displayed end-of-day prices or only the
documents (calendars, neutral gas price files); whether Fluxys's and DET's consents also cover
the LNG terminal tariff documents (the LNG terminal row above still asks the firm to record
that permission); and how each publisher prefers to be read where the product does not read
them yet (EEX's and ICE's price tables).

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
