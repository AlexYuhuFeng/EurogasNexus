# Trader guide

**You land on Market → Curves.** Prices first, in desk units: NBP in p/th, continental hubs
in EUR/MWh, volumes in MWh/d (th/d for NBP).

## Daily use

| Task | Where |
|---|---|
| Hub board: bid/ask, mid, change, spread to TTF, WD/DA/WE/MA | Market → Curves |
| Execution-screen ladder (products down, hubs across) | Market → Curves → layout *Ladder*, or Settings → Quote layout |
| Product strip (WD, DA, WE, BOM, M+n, Q+n, seasons, Cal), unit and FX converter | Market → Curves → Trader desk |
| Storage against the EU target | Market → Curves → Trader desk |
| Flows, capacity and maintenance | Market → Network, Market → Capacity & Events |
| Spread or benchmark analysis and a quick rule backtest | Strategy Lab → Spread |
| Position by hub and month, hedge ratio, MtM | Portfolio → Exposure → Position ladder |
| Opportunities and alerts | Decision Center, Alerts (top bar) |

## Getting your prices in

The product ships no live price feed: Trayport, ICE and EEX prices are licensed to you.
Export your screen to CSV (once or on a timer) and import it, or ask IT to connect your
licensed feed. See [LIVE_PRICE_SOURCES.md](../operations/LIVE_PRICE_SOURCES.md).

## Shortcuts

`Ctrl+Shift+1…6` workspaces, `Ctrl+K` palette, arrow keys move in the ladder, `Esc` closes,
`?` lists them all.

## Not here

No order entry, no nominations, no settlement. Decisions are recorded for review, not executed.
