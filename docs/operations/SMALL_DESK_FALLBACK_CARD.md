# When Eurogas Nexus is down: desk fallback card

For the traders and their managers. Chinese version:
[SMALL_DESK_FALLBACK_CARD-CN.md](SMALL_DESK_FALLBACK_CARD-CN.md).

Eurogas Nexus is a second screen. It never places orders, nominates or settles, and the ETRM
stays the official record. When it is down, **trading carries on exactly as before, on the
trading screen (Trayport) and the execution tool**.

## How you can tell it is down

- The browser shows an error, or the page does not load.
- Or the page loads but the figures are marked **stale** with an old time: the product is
  running but a data source or the network has dropped. The last known prices and position stay
  on screen, with their time; they are not live.

## What to do

1. Carry on with the trading screen and the execution tool alone.
2. Tell the helpdesk ("Eurogas Nexus is down" is enough). They follow the helpdesk card.
3. Keep your deals as you normally would: the exchange and broker records and the end-of-day
   ETRM entry are not affected.

## What you lose while it is down

| Lost while down | Not lost |
| --- | --- |
| The intraday estimate of position and profit and loss | Your deals: they are on the exchange, the broker and the ETRM |
| Spreads, alerts and public data views (storage, flows, outages, weather) | Everything recorded before it went down (backed up every night) |
| The end-of-day ETRM entry sheet and the managers' email (once the desk uses them), until it is back | The trading screen and the execution tool, which do not depend on it |

If it was down at end of day, run the end-of-day steps once it is back; the deal files from the
exchanges are imported as usual. If the database had to be restored from a backup, anything
entered in Eurogas Nexus after that backup must be entered again (the helpdesk is told which
backup was used).

## How you can tell it is back

- The page loads and the figures are no longer marked stale (the time next to them is recent).
- Or ask the helpdesk: `sudo nexus status` says **HEALTHY**.

Public data (storage, flows, outages) refreshes on each source's own schedule, so some views
may stay marked stale for up to an hour after the product is back.
