# Industry Benchmark Principles

Status: living product evidence. Use official/current public documentation where
possible. This document extracts workflow principles only; Eurogas Nexus does
not copy any vendor's proprietary appearance, workflow, or screen design.

Sources retrieved 2026-09-06:

- [Trayport Joule brochure](http://www.trayport.com/Joule%20Brochure.pdf)
- [Joule Direct User Guide](https://balkangashub.bg/storage/content-files/products/user-guides/Joule_Direct_User_Guide.pdf)
- [Kpler European Gas Intelligence](https://www.kpler.com/product/commodities/european-gas-intelligence)
- [Kpler platform workflow integration](https://www.kpler.com/ja-jp/blog/integrating-commodity-data-into-your-workflows-with-kpler-data-platforms-webinar)
- [TT Backtesting overview](https://library.tradingtechnologies.com/ja/tt-backtesting/tt-backtesting-overview/how-tt-backtesting-works/)
- [TT Running a backtest](https://library.tradingtechnologies.com/tt-backtesting/backtesting-algos/running-a-backtest/)
- [TT Transaction Cost Analysis](https://tradingtechnologies.com/tca/tt-tca/#post-trade)
- [Tallarium OTC energy trading UX case study](https://www.willers.design/tallarium)
- [Traders Seek Desktop Harmony](https://www.tradersmagazine.com/featured_articles/traders-seek-desktop-harmony/)
- [BarraOne institutional portfolio analytics](http://www.msci.com/resources/factsheets/BarraOne%20for%20Asset%20Man%20Jun09.pdf)

Retrieval note: marketing pages and user guides describe workflows, not
implementation contracts. Before a milestone depends on a benchmark, re-open
the current source and keep the evidence date.

## Benchmark extraction

| Benchmark | Trader job-to-be-done | Useful interaction pattern | Missing in Eurogas Nexus today | Intentionally NOT implemented |
|---|---|---|---|---|
| Trayport Joule / Joule Direct | Discover, quote, and negotiate European gas market opportunities across venues from one dense workspace | Dense persistent workspace; instrument/venue filters; linked quote and market panels; keyboard-first navigation; multi-monitor layout support | Persistent cross-workspace selection context; professional linked-widget composition; dense quote/mark grid with source and freshness state | Order routing, execution, trade capture, venue connectivity, negotiation workflow |
| Kpler European Gas / commodity data platforms | Understand physical flows, storage, LNG, and market intelligence to form a view | Map plus synchronized charts; region/hub/commodity selection propagates to related panels; freshness/source posture visible on each panel; local workspace filters | Coherent Market/Network cockpit with hub-driven synchronization; forward curve and basis matrix; outage/maintenance context; route economics in the same flow | Replication of vendor cargo/LNG analytics; proprietary map styling; becoming a maritime tool |
| Trading Technologies backtesting | Validate an automated strategy before any deployment | Versioned algorithm, explicit parameter set, explicit fill/cost assumptions, bounded historical run, inspectable run results and logs | Defensible backtest engine: as-of data, versioned definitions, cost assumptions, OOS/walk-forward, comparable run provenance | Execution deployment, order routing, live venue mutation |
| Professional market terminals (general) | Scan prices, curves, spreads and alerts quickly | Tabular numerals, dense but restrained layout, visible timestamps/units/source, color is never the only signal, keyboard reachability | Consistent professional terminal design system; true table/chart interactivity (sort/filter/crosshair/zoom); 1440/1920/2560 density passes | Consumer SaaS marketing composition; decorative dashboards |
| Quantitative research platforms | Design, backtest, compare, and monitor research strategies reproducibly | Experiment tracking with dataset snapshot and git SHA; parameter sweeps/heatmaps; walk-forward/OOS separation; overfitting reporting; deterministic seeds | Strategy definition lifecycle; immutable run metadata; dataset snapshot/as-of integrity; run comparison; drift indicators for shadow runs | Automatic parameter optimization presented as unbiased; illustrative PnL |
| Institutional risk/portfolio analytics | Understand exposure, PnL attribution, and scenario/stress impact | Position/exposure drill-down; MTM and attribution by component (commodity, FX, transport, capacity, storage); scenario comparison side-by-side | Computed position book and exposure; full PnL attribution; reusable scenario/stress objects; VaR/CVaR and stress results | Settlement/accounting system; ETRM replacement |

## Principles accepted for Eurogas Nexus product work

1. One coherent workstation, not one page per backend capability.
2. Persistent global trader context: portfolio, gas day, tenor, hub, currency,
   unit, as-of time, freshness, source entitlement.
3. Selection propagation, not free-floating windows: selecting a hub, route,
   contract, or strategy run updates bounded contextual panels.
4. Market/Network is a single analytical cockpit with synchronized views.
5. Strategy Lab is a full research lifecycle: definition -> backtest ->
   compare -> shadow run -> review, with human review only and no execution
   semantics.
6. Every run is reproducible and inspectable: strategy version, engine/git SHA,
   dataset snapshot, data cutoff, parameters, assumptions, seed, provenance,
   warnings, status, timestamps, operator.
7. Backtests are scientifically defensible: as-of joins, look-ahead fail-closed,
   explicit frictions, OOS/walk-forward, sensitivity, comparison, overfitting
   disclosure.
8. Shadow runs behave like production monitoring without execution: scheduled,
   restartable, pause/resume/retire, BLOCKED/DEGRADED when data is stale, and
   never generate normal-looking candidates from insufficient data.
9. Numerical truth is deterministic and API/domain-owned; LLM output is an
   auditable analysis layer that cites evidence and never invents data.
10. Institutional visual language: dense, restrained, data-first, precise 8px
    grid, system fonts, tabular numerals, visible axes/units/timestamps/source,
    keyboard and WCAG 2.2 AA accessibility, no gaming or consumer styling.
11. Performance claims require measurements; long-running jobs have explicit
    queued/running/completed/failed/cancelled lifecycle with progress.
12. Security and release claims require external evidence; no code signing,
    security acceptance, or live-provider certification is claimed without it.
