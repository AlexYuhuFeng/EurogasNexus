# Data-source and service terms for commercial use

Code dependencies are covered by [DEPENDENCY_LICENSE_REVIEW.md](DEPENDENCY_LICENSE_REVIEW.md) and gated in CI.
Data feeds and hosted services are governed by their providers' terms instead. This
table is the engineering summary the product enforces, not legal advice; legal should
confirm each provider's current terms before a production deployment.

| Source | Use in product | Commercial-use position | How the product enforces it |
|---|---|---|---|
| ENTSOG Transparency Platform | flows, capacity, tariffs | Free public data; attribution | Live ingest gated by a provider certification record |
| GIE AGSI+/ALSI | storage, LNG | Free with a registered API key; attribution | Key held server-side; certification gate |
| ECB reference rates, €STR | FX, €STR fixings | Free; reuse permitted with source attribution | Public baseline family `ECB` |
| Bank of England (SONIA) | SONIA fixings | Free; administrator terms (attribution, no endorsement) | Public baseline family `BOE`; attribution returned with every resolved rate |
| NY Fed (SOFR) | SOFR fixings | Free; NY Fed terms of use (attribution) | Public baseline family `NYFED`; attribution returned |
| ECMWF Open Data | weather forecasts | CC-BY-4.0: commercial use with attribution | Certified source; attribution in evidence |
| ENTSO-E Transparency Platform | power prices, load, generation by fuel | Free with a registered token; the platform's terms permit reuse with attribution to ENTSO-E (confirm the current terms at go-live) | Public baseline family `ENTSOE`; token held server-side |
| REMIT UMMs (EEX Transparency, GIE IIP, Gassco UMM and other inside-information platforms) | gas facility outages | Inside information operators must publish; each platform sets reuse terms, confirm commercial reuse for the platform used | Public baseline family `REMIT`; operator file import |
| US EIA open data | Henry Hub daily spot | US government work, public domain; free API key | Public baseline family `EIA`; key held server-side |
| ICE Endex, EEX, CME, NGX settlements | Gas, carbon (EUA, UKA), API2 coal, power, Henry Hub, AECO | Exchange licence held by the customer; non-display use for analytics must be covered | Licensed families `ICE_ENDEX`, `EEX`, `CME`, `NGX`; granted per user by an administrator |
| National Gas (GB) | demand | Open data licence; attribution | Certified source |
| EEX public market data (TTF NGP reference) | reference index | Display/internal use only; redistribution and derived products need an EEX licence | Commercial family `EEX`; data-scope grant required |
| WM/Reuters (LSEG), Bloomberg BFIX | FX fixes | Licensed; the subscriber's own entitlement | Operator import only; families `WMR`/`BFIX` need a grant |
| Trayport, ICE, ICIS, Platts, Argus, Kpler | prices, assessments | Licensed per subscriber | Commercial families; no data shipped; a connector uses the customer's own credentials |
| Norwegian Offshore Directorate (Sodir) FactMaps | field, platform and pipeline locations | NLOD 2.0: commercial reuse with attribution | Infrastructure import records licence and attribution per facility |
| North Sea Transition Authority open data | UK offshore installation locations | Open Government Licence v3: commercial reuse with attribution | As above |
| Global Energy Monitor trackers | LNG terminal, storage and pipeline locations | CC BY 4.0: commercial use with attribution | As above |
| OpenStreetMap extracts | infrastructure gap filling | ODbL 1.0: attribution and share-alike for the database | As above; the import refuses non-commercial licences such as CC BY-NC |
| Kpler, Spire, MarineTraffic vessel data | LNG cargo positions, tracks, ETAs | Licensed per subscriber; not redistributable | Loaded only from the customer's own export or connector; market cargoes need the source's data scope |
| Map tiles | basemap | OSM Foundation and CARTO public tiles are not for commercial embedding; OpenFreeMap and VersaTiles allow commercial use (OpenStreetMap data, ODbL attribution) | Default is OpenFreeMap; none in a China installation; an operator may configure a licensed or self-hosted service |
| DeepSeek API (optional) | alert explanations | Provider API terms; prompts leave the deployment | Off unless an API key is configured server-side; payloads exclude licensed raw data |

Simulated price sources (`*_Sim`) generate synthetic numbers locally. They carry no
third-party data, but they must never be shown as market prices. They are disabled in
`trial` and `release` environments (`simulated_sources_allowed()`).
