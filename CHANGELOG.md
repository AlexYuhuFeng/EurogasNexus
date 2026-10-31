# Changelog

All notable changes to Eurogas Nexus are listed here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/) as described in
[docs/release/RELEASE_CHANNELS.md](docs/release/RELEASE_CHANNELS.md). The current package version `0.6.0`
is on the `preview` channel and is not a production (GA) release.

Each entry says what changed for the people using the product. Engineering detail for a
version lives under [docs/release/notes](docs/release/notes).

## [Unreleased]

### Added

- Credit and mandates (Portfolio → Exposure): counterparty credit lines with exposure
  (netted replacement cost, receivables, collateral) and utilisation; trader mandates
  (books, hubs, size per hub-month, tenor, product) with breaches. Maintained by risk
  (REVIEWER), audited, never one's own mandate.
- Delivery against nominations (Portfolio → Resources): bilateral supply allocations
  against nominations and DCQ, with shortfalls, imbalance volume, volatility and the
  7-day trend; loaded daily with `scripts/ops/import_contract_deliveries.py`.
- LNG cargo bid (Portfolio → Routes): the most the firm can pay DES at each terminal from
  the hub forward less regas, entry, fuel, port, boil-off and charter, ranked in one
  currency with the range for a slipped arrival.
- Contract PDF intake: upload a signed contract or confirmation and every recognised term
  arrives in the draft with its page and wording; scanned PDFs are read when the server
  has Tesseract. Nothing is saved until a person reviews it.
- Excel and PDF exports beside CSV on every report table.
- Guide: [support, bug reports and updates](docs/guides/SUPPORT_AND_UPDATES.md); review:
  [customer acceptance by role](docs/product/CUSTOMER_ACCEPTANCE_REVIEW.md).

## [0.6.0] - 2026-10-31

### Added

- Monthly forward curve per hub built from month, quarter, season and year quotes; the
  position ladder marks each month on it and shows how every mark was obtained.
- REMIT outage messages (UMMs): import from the desk's inside-information platform,
  every version kept, live and upcoming outages under Market → Capacity & Events.
- Position ladder for physical and financial positions by hub and month, with hedge
  ratio, mark-to-market and indicative one-day VaR.
- ENTSO-E power data (prices, load, wind, solar, gas generation) and gas-for-power
  measures (residual load, spark and dark spreads, fuel switch).
- Point-in-time training datasets over prices, power, storage, LNG and flows, with
  declared lag and rolling features and walk-forward folds.
- Spread lab for benchmark and spread analysis with a declared-rule backtest.
- Benchmark rates SONIA, €STR and SOFR for contract financing; named FX fixes including
  WM/Reuters and BFIX (customer licence).
- Import of quotes from the desk's own licensed screen (Trayport, ICE, EEX exports).
- Account menu with per-user preferences and organisation defaults: language, theme,
  quote layout, profit and loss colours (green-up or red-up).
- Declared job functions (trader, analyst, risk, middle and back office, compliance,
  management, IT) with four-eyes approval; job functions never grant access.
- Weather-driven GB demand: ECMWF forecasts, degree days, frozen model fits and
  point-in-time demand labels.
- Exact ENTSOG native rates without assumed calorific values; bounded native history in
  the web client and SDK.
- Guides by role and a trading-house assessment of coverage and gaps.
- Market reference model: commodities (gas, LNG, power, emissions, coal), regions and
  pricing points, including planned AECO, Alberta power and TIER credits for a Canada desk;
  North American (NAESB) gas day.
- Carbon (EUA, UKA), API2 coal, power and gas settlement import from the firm's ICE Endex,
  EEX, CME, NGX, Argus or Platts licence; Henry Hub daily spot from EIA.
- Gas for power per bidding zone: clean spark and dark spreads, fuel-switch gas price,
  implied gas burn (Market → Overview).
- North-west Europe balance: the call on Norway, LNG and storage, measured and forecast,
  with Norwegian REMIT outages applied and a storage fill trajectory.
- Market-data licence register: licensed data scopes are granted only against a licence
  the firm holds, with seat and office checks and a holder report for vendor audits.
- Trading books (legal entity, region, business, book) and position roll-ups from firm to
  book in one reporting currency.
- Design system: one token set and type scale, a calm sticky shell with search (Ctrl/Cmd K), consistent tabs, tables and badges, motion that respects reduced-motion, WCAG AA in both themes.
- Common foundation for currencies (ISO 4217, quote units such as GBp and CNH, dated FX tables), units with dimensions, and time (UTC instants, market calendars, office zones).
- Gateway single sign-on for dedicated networks (SAML, Kerberos, vendor SSO agents) alongside OIDC.
- Company directory accounts are inherited in a dedicated network
  (`EUROGAS_NEXUS_OIDC_PROVISIONING_MODE=directory`): people sign in with their SSO account,
  and their roles, data scopes and office follow their directory groups at every sign-in.
- Portfolio isolation between offices (`EUROGAS_NEXUS_PORTFOLIO_ISOLATION=true`): head
  office sees every book; a regional office sees only books in its `BOOKS:` scopes.
- Region-aware open-licence basemaps (OpenFreeMap, VersaTiles) chosen by
  `EUROGAS_NEXUS_DEPLOYMENT_REGION`; a mainland China installation defaults to no external
  basemap.
- Live map: REMIT outages located by EIC code, latest physical flows, the firm's upstream
  contracts at their delivery points, LNG cargoes with track and ETA, and regas slots held
  at terminals, with hover cards in desk units, a one-line status strip and motion only
  where gas or cargoes move (off under reduced motion). Cargo and slot imports from the
  customer's vessel-tracking export or ETRM; infrastructure locations from openly licensed
  datasets (Sodir, NSTA, Global Energy Monitor, OpenStreetMap).
- Semantic zoom on the live map: country totals when zoomed out, individual assets at
  regional zoom, key figures beside each asset when zoomed in; "Fit our positions".
- Map zooms like a city map: street level with a detailed basemap, infrastructure icons by
  kind, labels that appear as the view narrows, find-and-fly, click to focus, and a ring
  around approximate positions. A bundled offline outline basemap (Natural Earth) is the
  default in mainland China and air-gapped networks.
- Code signing is no longer a release requirement: each firm decides whether to sign the
  installers with its own certificate; the release records the signing state.
- Compliance tooling: market-abuse surveillance report against REMIT disclosure timing;
  draft record of processing activities from the installation's configuration; REMIT
  imports record the source platform and require confirmed reuse terms.
- Release acceptance automated: clean Windows install/launch/uninstall and upgrade from the
  previous release, backup/restore drill on PostgreSQL 16, container image CVE scan
  (Trivy) at the published digest, and desktop packaging, SBOM and provenance evidence.
- ETRM trade import into books, CSV exports of position, balance and gas-for-power reports, and signed hand-offs of decided cases for ERP/ETRM middleware.

### Changed

- Market board and execution-style ladder follow screen conventions (WD, DA, WE, BOM,
  months, quarters, seasons, Cal) in desk units; simulated prices are labelled and never
  used as marks or risk figures.
- The data-ops scheduler now also runs ENTSO-E power and the SONIA, €STR and SOFR fixings,
  with retries and freshness targets.
- The LLM layer uses a provider-neutral endpoint configured per installation.
- Preview builds are no longer published as GitHub Releases; only release candidates and
  stable versions are.
- The ontology carries its own version, independent of application releases.
- The server bundle is platform-neutral (`Eurogas-Nexus-Server-<version>.zip`) and includes the configuration template.

### Fixed

- Sign-in language was overridden by stored preferences.
- Database migration identifiers longer than the `alembic_version` column.
- Browser acceptance and reproducibility of the weather-model numerical tests in CI.
- Mark-to-market and VaR added GBP and EUR amounts without converting them; each market's
  currency is now converted at ECB reference rates.

### Security

- Dependency licences are gated for commercial use; vulnerability audits run in CI.

## [0.5.0] - Preview release line

The 0.5.0 line was published only as preview builds (tags `v0.5-preview-<run>-<sha>`).
It was a release candidate for the tested local scope, not a production multi-user or
GA deployment.

Highlights:

- PostgreSQL-first backend, API, Python SDK, CLI, Web client, and Tauri desktop shells.
- DB-composed portfolio network optimization and contract-level PnL attribution.
- Intraday opportunity monitoring with persisted alerts and DeepSeek enrichment.
- Storage/nomination assessment workflows (assessment only).
- Local identities, hashed API keys, role authorization, data scopes, and OIDC verification.
- Server and Client-only deployment roles.

See `docs/release/RELEASE_READINESS.md` for the current release status and
production gaps.

## Ontology version changes

Ontology versions are tracked independently of application releases and are
asserted by `tests/contract/test_ontology_version_alignment.py`.

- **0.5.0** — the executable vocabulary under
  `src/eurogas_nexus/domain/ontology/` is the semantic source of truth. It
  models the full GRM role inventory, business processes, commodity taxonomy,
  typed interaction properties, and the human-review decision-support boundary.
  `scripts/ontology/generate_grm_ttl.py` renders the model as OWL/Turtle, and
  `tests/contract/test_ontology_grm_parity.py` verifies that the published
  `docs/ontology/eurogas-nexus-grm.ttl` remains in structural parity with the
  executable vocabulary.
