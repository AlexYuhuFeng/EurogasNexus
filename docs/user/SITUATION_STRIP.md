# The situational strip

The line under the top bar tells you what needs *you* now, for your role, and nothing else. It is
static: it does not scroll, flash or move. When nothing qualifies and your role has no standing
fact, there is no line at all; the alerts bell keeps the full list and its count.

## What you see

| State | What it looks like |
|---|---|
| Nothing for you | No line. |
| Quiet | One muted line with a standing fact for your role (below). Select it to open where it lives. |
| Urgent | A coloured mark and edge, the most important item with its size ("563 of 758 GWh/d"), and **+n more**. Select the item to open it where the job continues. |
| The list | **+n more** (or **Details** for a single item) opens up to seven items: a popover on a desktop, a sheet from the bottom on a phone. Each item names its source and how long ago it happened, says in one line why you see it, and offers **Hide**, **Acknowledge** (only if your role may acknowledge alerts), **Why** and **Report**. The arrow keys move between items; **Esc** closes the list. |

An item is urgent for six hours after it happened or materially changed (a revised outage, a
larger breach). After that it is a standing state: the bell lists it, the strip does not. A new
urgent item is announced once to a screen reader; a standing one is never announced again.

## What qualifies, by role

Your role is your declared job function (Administration → Access → Job profile); with none, it
follows your permissions.

| Role | Urgent | Quiet line |
|---|---|---|
| Trader | Unplanned outage at or above your size threshold (GWh/d or share of the asset) in a zone where your book holds a position or at a focus hub; a breach of your own mandate or of a credit line your books trade against | Trades booked today from the ETRM import (read-only; a count when the import holds no booking times), else the next nomination window |
| Originator | A decision recorded on a case you opened | Your cases awaiting review, and the nearest due time |
| Analyst | A large unplanned outage anywhere in north-west Europe; a shadow-strategy alert | None |
| Risk manager | Any limit breach; a credit line moving onto watch; a decision case past its due time | Breach and watch counts and decisions waiting |
| Operations | An outage in a zone where the book delivers; a nomination window closing within the hour (information only: nominations are made in the TSO or shipper system) | The next window and its time to close |
| Finance | None | None |
| Compliance | None | Cases decided this week |
| Desk head | Any limit breach; an unplanned outage touching the book; a case waiting past half its time | The day's P&L change and the breach count |
| Administrator, data operations | A source failing, or held back by its approval, in the last six hours | Sources needing attention |

Data-source and ingestion problems appear only on the administrator's and data operator's strip.
Limits items behind books you cannot see are never shown to you. A figure from the demo desk
carries **sim**.

Nothing on the strip places, amends or cancels an order, nominates or settles: booked trades are
a read-only report of what the ETRM import holds.

## Hide and Acknowledge

- **Hide** takes the item off *your* strip only. It changes nothing about the alert, and others
  still see it. The item comes back if it changes materially (its size or status). Your hidden
  items follow you to other devices.
- **Acknowledge** records, against your name, that you have seen an alert (the same governed
  action as in the alerts list). It is offered only if your role may acknowledge alerts.

## Your preferences

Settings → **Personal preferences** → **Situational strip**. Each line shows the organisation
default; choose **Use organisation default** to follow it. A platform administrator sets the
defaults under **Organisation defaults**.

| Setting | Choices | Default |
|---|---|---|
| Outage size that counts (GWh/d) | 25, 50, 100, 200, 500 | 50 |
| Or share of the asset out | 25 %, 50 %, 75 % | 50 % |
| Price move that counts (vs prior close) | 2 %, 3 %, 5 %, 10 % | 5 % |
| When nothing is urgent | Show one standing fact; Hide the strip | Show |
| Focus hubs | Up to six of TTF, NBP, THE, PEG, ZTP, PSV, CEGH, PVB, ETF, GTF | None: the hubs where your book holds a position, and the hub in your context |

An outage qualifies when it reaches either size. Raising the threshold makes the strip quieter;
lowering it brings smaller outages onto it. Nothing here changes what you may read.

## Not yet on the strip

These rows of the design wait on a server read or alert that does not exist yet; the strip
already handles them and shows them as soon as the server sends them:

- a day-ahead or front-month price move against the prior close at a focus hub;
- a contract delivering short of its nomination beyond tolerance;
- a fundamentals surprise (storage change, supply call or LNG send-out outside its band against
  the seven-day average);
- the analyst's next scheduled data arrival.
