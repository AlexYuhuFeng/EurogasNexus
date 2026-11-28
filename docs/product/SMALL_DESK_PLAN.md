# Small-desk plan (owner approved, 2026-11-27)

This file sets the order of work. It replaces the phase order in
`docs/architecture/ARCHITECTURE_V3_PLAN.md` section 6; the architecture decisions in that plan
stand unless this file says otherwise. The owner interviewed the first user's traders and
managers on 2026-11-27. Their identity and specifics are kept out of this repository: the
owner holds a private profile and gives it to the working session.

## 1. Who it is for

A small gas desk, not a trading house with departments.

- A few traders in one office. They are their own analysts, can write some Python and use AI
  services.
- Risk and some managers in another office with **no network route** to the trading office.
  They are reached by email only. Some read Chinese, not English.
- Operations (nominations, scheduling) are outsourced in full.
- Several European hubs; spot, curve and spreads; physical and financial; no options;
  regasification but no cargo trading.
- Trayport Joule as the market screen, an execution tool for order entry, and a trading and
  risk system of record (ETRM) that is filled in only at the end of the day.
- The daily routine that hurts: export trade files from the exchanges, paste them into a
  spreadsheet shaped like the ETRM entry, key that into the ETRM, then email files to managers.
- IT is a helpdesk. One high-end desktop PC on the premises. The developers support remotely,
  by message, not quickly, and never on site.
- An internal tool, not a product for sale to others. No deadline.

## 2. Goal

The traders always know their position and profit and loss, and the end-of-day routine takes
minutes and needs no retyping. Risk and managers get the same facts by email, in their
language, without asking.

In one line, for what the desk should feel: never switch screens, never lose the last known
picture, never fly blind during the day.

## 3. What follows

1. **Everything for the remote office is a file sent by email** (PDF and XLSX, English and
   Chinese). There is no remote sign-in, so no remote risk or manager screen.
2. **Runs itself.** One-step install, starts on boot, backs itself up to a second disk and to
   an office copy, checks itself and says in plain words what is wrong, and writes one
   diagnostic bundle (logs and configuration with secrets removed) that a trader can send to
   the developers or give to an AI. Updates are one command and can be undone.
3. **The small-desk profile is the default.** One process group on one PC, local accounts with
   a second factor. See section 6 for what is parked.
4. **The ETRM stays the official record.** During the day the product shows an estimate of
   position and profit and loss, labelled as an estimate. At end of day it is compared with
   what is entered in the ETRM and the differences are listed.
5. **Orders:** `AGENTS.md` rule 8. Pre-fill only; a trader confirms every order in the
   execution tool.
6. **AI is optional and can be switched off.** The provider is the user's choice, including a
   self-hosted model. No calculation depends on it; its output is a draft a person accepts.
7. **When the feed or the network drops,** the last known prices and position stay on screen,
   marked stale with their time, and the desk falls back to the trading screen alone. The
   product does not promise more than that.

## 4. Order of work

| Step | What the user gets | Depends on |
|---|---|---|
| 1 | **End of day without retyping.** Import the exchange trade exports; a deal blotter; the ETRM-shaped entry sheet; the daily summary for managers in English and Chinese. | Sample exports, the spreadsheet template and one management email, from the owner |
| 2 | **Risk pack by email.** Profit and loss by trader and hub (day, month, year to date); exposure per counterparty against its limit and guarantee, with guarantee expiry; a check that every captured deal is in the ETRM entry; mandate checks (no options, tenor, volume). | An export of limits and guarantees from the ETRM |
| 3 | **Position and profit and loss during the day.** By hub and delivery period, physical and financial, from deals captured so far and live prices. | Step 1; intraday deal capture (repeat the export, or a trade feed if the user's Trayport contract allows) |
| 4 | **One trader screen.** Their hubs, spreads between hubs net of transport cost, storage, flows, outages, weather, regasification. | The user's own data entitlements, confirmed by them with each vendor (rule 18) |
| 5 | **Pre-filled orders** into the execution tool. | See section 7 |
| Throughout | Install and self-support (section 3, items 2 and 3). | |

Managers' market reports and the map stay as a separate area and get no new work until
steps 1 to 3 are in use.

## 5. Targets and operating requirements

Adopted from an outside review the owner commissioned, where they fit a desk this size:

- A price change is on screen within 200 ms of arriving; a new deal changes position and profit
  and loss within one second.
- An AI call that has not answered in 3 seconds is abandoned and the screen carries on without it.
- The PC keeps its clock by NTP, so deals and prices order correctly.
- Two disks, mirrored or with a nightly copy, and an uninterruptible power supply.
- Charts draw on canvas, and long sessions keep a bounded history in the browser.
- Every difference between captured deals and the ETRM entry is shown; none is hidden.

Not adopted, with the reason: separate microservices, a second database or cache, binary
message formats and WebAssembly (more parts to maintain on one PC for no gain at gas-market
speeds, and against rule 5); free-form questions turned into SQL (it would bypass book and
entity isolation); an uptime percentage (one PC cannot promise it; item 7 above is the
honest statement).

## 6. Parked: kept in the code, no further work

Hot standby and restore to a chosen minute; several API processes with a shared cache; company
single sign-on; the six-role model and the dual-control approval screen; test and training
environments; the 50-user load test; LNG cargo economics; options; the strategy laboratory (removed, architecture plan
section 5); the phase 3 feed handler. The removals list in the architecture plan still applies. The phase
2 items that steps 1 to 3 need (exact money, the versioned trade copy, ETRM reconciliation,
the end-of-day close) are built as part of those steps.

## 7. Server and execution tool

- **Server:** Ubuntu LTS with Docker Engine on the one PC. The stack and the demo already run
  this way, both are free for commercial use, and it runs unattended. The helpdesk needs no
  Linux skills if install, start, stop, update and "collect diagnostics" are each one command.
  The traders keep their own Windows PCs and use the browser or the desktop client.
- **Execution tool:** believed to be Trayport autoTRADER. Trayport's public material says its
  PRO tier has a developer kit for algorithms in Python and a REST API to command it; no
  public reference for that API was found on 2026-11-27. Before step 5: get the API reference
  from the user's Trayport account, confirm their tier includes it, and have their compliance
  confirm that a pre-filled, trader-confirmed order raises no algorithmic-trading obligation.

## 8. Unknowns

1. The step 1 samples.
2. Whether the user's Trayport, ICE and EEX terms allow their data and trades to be read by
   another program. The user confirms with each vendor; nobody accepts terms on their behalf.
3. How intraday deals can be captured without a manual export.

## 9. The trader screen: defaults the owner set (2026-11-27)

The owner reviewed a mock-up of step 4 and set these. Where he said "the professional way",
the choice below is the coordinator's, recorded so it can be challenged.

- **Board:** contracts down, hubs across (NBP, TTF, ZTP, THE, PVB). Rows: within-day,
  day-ahead, weekend, balance of month, three months, two quarters, two seasons, next calendar
  year. Bid and offer always visible, with last and change on the day.
- **Spreads:** between hubs (TTF-NBP, ZTP-NBP, TTF-ZTP, TTF-THE, PVB-TTF); across time at each
  hub (day-ahead against within-day, prompt against front month, month to month, summer
  against winter); regasification against the hub. A spread with an NBP leg is quoted in pence
  per therm, the other leg converted with the rate shown on demand.
- **Transport cost in a hub spread:** the published short-term capacity price plus the flow
  charge when the desk holds no capacity on the route (the default, and the screen says so);
  the flow charge alone when it has entered booked capacity for that route.
- **Position:** therms per day at NBP, MW at the continental hubs; physical, financial and net;
  the same rows as the board.
- **Fundamentals:** storage (GB, NL, DE, BE, ES, EU total); Norwegian supply into GB and the
  continent; the two GB-continent interconnectors with direction; LNG send-out by country;
  France-Spain and Algeria-Spain pipelines; outages at fields, terminals and storage;
  temperature and wind for GB, north-west Europe and Iberia. GB in mcm/d, the continent in
  GWh/d.
- **Theme:** light by default, dark available.
- **Language:** the trader screens are English. Chinese is for the managers' emailed reports.
- **Look:** the mock-up is the visual target for the trader screen and for the other screens
  the desk uses (blotter, end of day, position and profit and loss, limits). Parked pages are
  not restyled. The owner holds the mock-up and the design-system reference as private pages.
- **Counterparty guarantees** are shown beside exposure, not subtracted from it, until the
  risk function says otherwise.

## 10. Bringing back something that was removed

The branch `archive/full-platform-2026-11-27` and the release `v1.0.0-beta.1` hold the product
before any removal. Each removal is one commit (or one merge) on `main`, named in
`docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md`; restoring a feature starts from
reverting that commit and refitting it to the code as it then stands. Keep the archive branch
when tidying branches. Parked features (section 6) are still in the code and need no restore.

## 11. What is published is fetched, not typed (owner, 2026-11-28)

The desk is two people and cannot spend time watching websites. If something they need is
publicly published, the product gets it from where it is published, when it is published, in
the right form, and tells them; nobody types it in. This extends `AGENTS.md` rule 19 and is
bounded by rule 18: publicly viewable is not the same as free to collect. Each publication's
terms are read and recorded in `docs/legal/DATA_SOURCE_TERMS.md` ("Watched publications,
checked 2026-11-28") before anything is fetched; nobody accepts terms or signs up on the
owner's behalf.

One mechanism (`domain/publications/registry.py`, `application/publication_watch.py`), run by
the scheduler: per publication, its publisher, exact location, terms entry, check interval,
change detection by the document's digest, a parser into a typed record, and what happens on a
change (record updated with the previous one kept and a line in the events list; a document the
parser cannot read is held as "source changed on <date>, needs a person to confirm" and the
desk is told once; unreachable or not permitted is stated, never silent). The desk sees it on
Desk → Board → Calendar and in the events list; administrators see every publication's state in
Admin → Data sources → Watched publications.

| Publication | State on 2026-11-28 |
|---|---|
| ENTSOG CAM auction calendar (yearly, quarterly, monthly; firm and interruptible; offer-level days) | **Fetched** daily; replaces the rule-derived dates |
| EEX trading calendar | Hand-maintained (terms forbid storing), check reminder with the link |
| ICE Endex and ICE Futures Europe trading schedules | Hand-maintained (terms forbid robots and storing), check reminder with the link |
| PRISMA, GSA, RBP auction schedules | Link only (no public reuse terms; offers behind accounts); dates follow ENTSOG's calendar |
| LNG slot announcements: Zeebrugge, Dunkerque, Isle of Grain, Gate, DET (Wilhelmshaven, Brunsbüttel, Stade), Mukran, Spain | Link only (terms forbid reuse, or could not be read) |
| Storage offers: Uniper, Loenhout, Spain | Link only |
| Reference prices: THE imbalance prices, National Gas SMP, MIBGAS, EEX NGP | Link only (THE would need one written consent; its API is open) |

E-mail-only announcements are not read; a desk-owned mailbox is proposed in
`docs/integration/DESK_MAILBOX_DESIGN.md` (depends on the office's IT policy).
