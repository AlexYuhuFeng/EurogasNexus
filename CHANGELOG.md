# Changelog

All notable changes to Eurogas Nexus are listed here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/) as described in
[docs/release/RELEASE_CHANNELS.md](docs/release/RELEASE_CHANNELS.md). The current package version `0.7.0`
is on the `preview` channel and is not a production (GA) release.

Each entry says what changed for the people using the product. Engineering detail for a
version lives under [docs/release/notes](docs/release/notes).

## [Unreleased]

### Added

- **Contract currency**: a supply contract's price is recorded in GBP, EUR or USD
  (the workbench offers the delivery hub's own currency first). Positions mark a EUR
  contract at TTF against TTF in EUR, and translate a price in another currency at the
  latest ECB reference rate, saying so; route costs translate into GBP or leave the
  contract out when no rate exists. PDF intake fills the currency it reads instead of
  asking for the price to be kept in notes.

- **Live map selection** (Market → Network): click a hub, a place or a cargo and its card
  docks on the right while the map highlights it and what it relates to. A hub shows its
  day-ahead and month-ahead prices, its zone's outages (including those one pipeline
  upstream), measured flows and our supply. A place shows its roles in words (Easington:
  entry point · gas terminal · Langeled pipeline · NBP zone · our supply), operator, flow
  against capacity, outages, our contracts, cargoes heading in and our regas slots. A
  cargo shows its voyage, ETA, size and the slot waiting for it, with its track and leg
  ahead drawn.
- **Topology over geometry**: every known connection is drawn, as a schematic curve where
  no surveyed route exists, and a topology check flags connections to unknown points,
  border crossings that do not land at an entry or interconnection point, unconnected
  points and duplicates.

### Changed

- The Network page is map-first (full width; rails below it); the duplicate top-bar map
  search is gone; layer chips are labelled; LNG terminals and entry and interconnection
  points show by default; generic points and clusters are neutral grey (blue means ours).

### Fixed

- The legend floated over the zoom controls; facility kinds and route warnings showed as
  codes.
- Market → Overview priced TTF in GBP and showed each hub's latest observation of any
  tenor, so one hub had two unexplained prices; it now shows day-ahead (else month-ahead)
  in the hub's own unit, named, from the same rows as the hub board. Counts of loaded rows
  ("Flow rows 0") gave way to "Today on the network" (outages now and scheduled, our
  cargoes at sea, regas slots, measured entry flows, contracts); the context line no
  longer runs its labels and values together.

## [0.7.0] - 2026-11-01

### Added

- **User manual by role**: what every role does in a day, walked through in the product
  and written up with screenshots in the [user manual](docs/user/manual/README.md).
- **Daily gas balance** (Portfolio → Resources): per gas day at a hub, expected supply
  (contracts corrected by how they deliver), exchange and bilateral purchases and sales,
  the residual still to close, and what the TSO's cash-out would cost if it is left open.
- **Day-ahead sell-down plan**: how much of tomorrow's supply to sell day-ahead and how
  much to keep for within-day, from the contracts' measured delivery and the cost of
  being short or long.
- **Credit lines and trader mandates** (Portfolio → Exposure): counterparty exposure
  (replacement, receivable, collateral) against limits; mandates by book, hub, size,
  tenor, hedge band (e.g. a legal 80 % cap) and allowed instruments (no options).
- **Deal hedge approvals**: risk approves a hedge band per contract (80 % for one deal,
  50 % for another) with its committee reference; the cover is measured month by month
  from the trades linked to the contract.
- **Contract lifecycle**: contracts are retired with a reason and reinstated, never
  deleted; history and audit stay. Contract terms are chosen from lists (hubs, network
  points, sale routes, index, law) instead of typed.
- **Contract PDF intake**: a signed confirmation is read into a draft, every term with
  its page and wording, for a person to check before saving.
- **Delivery against nominations** per contract, with shortfalls against tolerance.
- **LNG cargo bid** across terminals, with each terminal's published tariff regime and
  the document it was read from (Fluxys monthly indexed slot, Elengy ATTM7 term and SMART
  SPOT by cargo class, DET auction results), refreshed daily.
- **TSO tariff publications**: per TSO and gas year, indicative or final, the NC TAR
  deadline, and an email when the publication page changes.
- **Report a problem** (top bar "?"): goes to the IT desk with diagnostics attached; the
  IT desk works reports under Admin → Runtime → Problem reports.
- **Email notifications** (Settings → Notifications): alerts, IT desk reports, limit
  breaches, tariff deadlines and source outages through the firm's SMTP relay.
- **Desk glossary**: 74 terms with unit, formula, worked example and where each appears.
- **Branding**: one mark everywhere, a branded installer (English and Chinese), splash
  and sign-in screen.
- **User manual** by role, and a [platform strategy](docs/product/PLATFORM_STRATEGY.md)
  for macOS, iPad, iPhone, Android and HarmonyOS.
- Excel and PDF exports beside CSV on every report table.

### Changed

- Every button and select follows the design system; the top bar keeps every control on
  screen from 1280 px to 2560 px for every role; wide monitors use the extra width.
- The administration workspace is "Admin".
- Screens name people, not internal ids.

### Fixed

- PostgreSQL rejected ENTSOG runs ending "succeeded with warnings" (a column was too
  narrow); nine more drifted columns widened, and CI now compares models with the
  migrated schema.
- National Gas, ECMWF and EEX downloads ignored the corporate proxy.
- A new contract draft carried invented facts that could be saved as recorded terms.
- Trades adding to a position showed as a negative hedge; a trader with two mandates saw
  one book's trade flagged against the other mandate; filled trades showed 0 MWh.

### Known limits

- Contract prices are recorded in GBP/MWh: a contract delivered at a euro hub is shown
  in positions but not marked to market. Keep its valuation in the ETRM.

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
