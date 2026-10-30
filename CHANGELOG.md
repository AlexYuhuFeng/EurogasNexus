# Changelog

All notable changes to Eurogas Nexus are listed here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/) as described in
[docs/release/RELEASE_CHANNELS.md](docs/release/RELEASE_CHANNELS.md). The current package version `0.6.0`
is on the `preview` channel and is not a production (GA) release.

Each entry says what changed for the people using the product. Engineering detail for a
version lives under [docs/release/notes](docs/release/notes).

## [Unreleased]

## [0.6.0] - 2026-10-30

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

### Fixed

- Sign-in language was overridden by stored preferences.
- Database migration identifiers longer than the `alembic_version` column.
- Browser acceptance and reproducibility of the weather-model numerical tests in CI.

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
