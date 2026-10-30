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
| National Gas (GB) | demand | Open data licence; attribution | Certified source |
| EEX public market data (TTF NGP reference) | reference index | Display/internal use only; redistribution and derived products need an EEX licence | Commercial family `EEX`; data-scope grant required |
| WM/Reuters (LSEG), Bloomberg BFIX | FX fixes | Licensed; the subscriber's own entitlement | Operator import only; families `WMR`/`BFIX` need a grant |
| Trayport, ICE, ICIS, Platts, Argus, Kpler | prices, assessments | Licensed per subscriber | Commercial families; no data shipped; a connector uses the customer's own credentials |
| Map tiles | basemap | OSM/CARTO public tiles are not for commercial embedding | Default is no basemap; operator configures a licensed or self-hosted service |
| DeepSeek API (optional) | alert explanations | Provider API terms; prompts leave the deployment | Off unless an API key is configured server-side; payloads exclude licensed raw data |

Simulated price sources (`*_Sim`) generate synthetic numbers locally. They carry no
third-party data, but they must never be shown as market prices. They are disabled in
`trial` and `release` environments (`simulated_sources_allowed()`).
