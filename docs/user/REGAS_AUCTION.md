# Regas auctions: "bid at most X for this slot"

Desk → Cargoes → **Regas auctions** (`?workspace=market&task=auctions`). The second view of the one
LNG workspace, behind the switch at the top of Cargoes ("Cargoes in transit | Regas auctions").

When a terminal auctions a regasification slot, the desk asks a cargo owner for a price for the
cargo (fixed, or a formula on a hub index), valid for the whole auction window, and nets back:
what the gas fetches at the hub over the send-out days, less every cost of getting it there, less
the cargo. What is left is the most the slot is worth. The desk bids up to it and stops; if the
auction goes higher, the window closes and the offer lapses.

The screen computes and prepares. **It never bids, orders or nominates** (`AGENTS.md` rule 8): a
trader bids on the terminal's platform and puts hedges on in the execution tool. "Prepare hedge
orders" is shown disabled with the note "later step; a trader confirms in the execution tool".

## What the screen shows

- **The list** of auction cases, open first, each with its countdown to the auction close.
- **The answer**, recomputed whenever a price, FX rate, mark or limit changes (the session's live
  stream) and on every read:
  - **Bid at most**: the maximum bid in the auction's own quotation (per MWh of slot energy, or
    one total per slot) and as a total, with the range within the cargo's volume tolerance;
  - **Auction level**: the level the trader enters as the auction moves (who and when is kept;
    every change is in the level history and the audit trail);
  - **Headroom** = maximum bid − level, and its state: **Room to bid** (green), **At the limit**
    (amber: headroom within 2 % of the maximum bid), **Stop** (red: the level is above the
    maximum bid, or nothing is left to bid);
  - **Break-even hub price**: the average hub price over the send-out days at which the maximum
    bid equals the level. When the cargo is priced on the same hub, the price hardly moves the
    answer and the screen says so instead of quoting a meaningless price.
- **From hub revenue to the maximum bid**: the waterfall as a table.
- **What moves it**: change in the maximum bid for 1 unit up in each hub price used (1 p/th at
  NBP, 1 EUR/MWh on the continent), the ship one day late, losses one percentage point higher, and
  +1 % in the FX rate when the cargo is in another currency.
- **Price exposure**: per hub and month, the long from revenue, the short from the cargo formula,
  what the formula itself covers and the residual (MWh; money per unit move = the residual).
- **Hedges if the slot is won**: the contracts (by hub and month, Trayport names: Jan-27, BOM),
  side, volume in the desk's unit (MW, th/d at NBP) and energy, their crossing cost at half the
  bid/offer, and the month contract's last trading day. Futures only; no options.
- **Show the effect on position and limits**: a read-only what-if through the one position source
  and the limits service: position added by hub and month, each mandate's state before and after,
  and the cargo owner's credit line use before and after. Nothing is booked.
- **Inputs and where each came from**: every cost line with its value, total and source
  (tariff register, published tariff, computed, desk default, or "entered by hand by <who> on
  <date>" with the operator's tariff link); every send-out day's price in the hub's own unit with
  its source and time; the defaults the answer stands on.
- **Snapshots**: "Save snapshot" keeps the answer a trader acted on (inputs, each price with its
  time and source, the result, and the valuation snapshot it was read through), so after the
  window the desk and the remote risk function see what the limit was at each point and why.
- **Close the case**: won, lost or lapsed, with a note. A won case records what the slot and its
  hedges would become in the position (the regas slot, the hedge legs, the cargo purchase); it is
  not booked: booking is a later step a person confirms.
- **Case report**: one PDF and one XLSX, English or Chinese, for the emailed risk pack.

## The formula in plain words

    energy unloaded    E      = slot quantity x the stated factor (MWh)
    energy sent out           = E x (1 - losses %)
    revenue                   = for each send-out day: energy sent out that day x that day's hub price
    cargo                     = E x the cargo price (fixed, or slope x index + constant), in the hub's currency
    cost lines                = regas fee + berthing + storage + entry x sent out + hedging
                                + financing + margin x sent out + late-ship buffer + other
    maximum bid (total)       = revenue - cost lines - cargo
    maximum bid (quoted)      = total / E (per MWh), or the total (per slot)
    headroom                  = quoted maximum bid - auction level

The day's hub price is the one price the whole product uses for that day: the contract that covers
it (day-ahead, balance of month, the month). Revenue is valued at that price; crossing the
bid/offer when hedging is the hedging cost line, so the two together are what the desk can sell at.
Financing is the cargo payment x (benchmark rate + the desk's spread) x days tied up / 365.

## Worked example

A TTF slot at Gate of 1,000 GWh (factor 1,000 MWh per GWh), sent out evenly over 10 to 13 January
2027; day prices 30.00, 30.40, 30.80 and 31.20 EUR/MWh. Losses 1 %. Regas fee 450,000 EUR; berthing
120,000 EUR; entry 0.50 and margin 0.25 EUR/MWh sent out; hedging at half a bid/offer of
0.025 EUR/MWh; late-ship buffer 50,000 EUR; financing 4.0 % (2.5 % benchmark + 1.5 pp) for 30 days.
The cargo owner offers a fixed 28.00 EUR/MWh. The auction stands at 0.60 EUR/MWh.

| Step | EUR | EUR/MWh unloaded |
|---|---:|---:|
| Hub value of the slot's energy (250,000 MWh a day x the four prices) | 30,600,000.00 | 30.6000 |
| Fuel and boil-off losses (1 %) | −306,000.00 | −0.3060 |
| Terminal regas fee | −450,000.00 | −0.4500 |
| Berthing and port | −120,000.00 | −0.1200 |
| Send-out and grid entry (990,000 MWh x 0.50) | −495,000.00 | −0.4950 |
| Hedging (sell 990,000 MWh Jan-27 x 0.025) | −24,750.00 | −0.0248 |
| Financing (28,000,000 x 4 % x 30/365) | −92,054.79 | −0.0921 |
| Desk margin (990,000 x 0.25) | −247,500.00 | −0.2475 |
| Late-ship buffer | −50,000.00 | −0.0500 |
| Cargo under the offer (1,000,000 x 28.00) | −28,000,000.00 | −28.0000 |
| **Maximum bid for the slot** | **814,695.21** | **0.8147** |

Headroom 0.8147 − 0.60 = 0.2147 EUR/MWh: **Room to bid**. At 0.80 it reads **At the limit**
(0.0147 is within 2 % of 0.8147); at 0.82 it reads **Stop**.

What moves it: TTF up 1 EUR/MWh +990,000 EUR (+0.99/MWh); one day late +293,931.51 EUR (the days
slide to 11-14 January, all at higher prices, less one more day of money); losses one point higher
−298,250 EUR. Break-even TTF at 0.60: 30.3831 EUR/MWh on average over the send-out days.

The same slot with a **formula** cargo, 1.0 x TTF (average of the send-out days) − 2.50: the index
is 30.60, the cargo 28.10 EUR/MWh. The formula is short 1,000,000 MWh of TTF in January while the
revenue is long 990,000 MWh: the formula covers 990,000 MWh and the residual is a 10,000 MWh short
(the energy lost to fuel is paid for but not sold). The hedge is to **buy** 10,000 MWh Jan-27, and
a 1 EUR/MWh TTF move changes the maximum bid by only −13,288 EUR, so no break-even price is quoted.

These figures are the hand-worked examples in `tests/unit/test_regas_auction.py`.

## Where inputs come from, and when they are missing

- Hub prices, FX for the delivery month and the overnight benchmark come through the valuation
  reader every screen uses: licensed prices only through the firm's entitlement, public data,
  else the firm's own marks. Bid/offer for the hedging line comes from executable quotes when held.
- Terminal figures (regas fee, gas in kind, entry tariff) come from the firm's terms, the reviewed
  tariff register and the published tariffs the product holds. Most terminal sites may not be
  stored (`docs/legal/DATA_SOURCE_TERMS.md`): the desk enters the figure from the operator's
  published tariff with its link, and the answer says "entered by hand by <who> on <date>".
- **A missing input is never zero.** The answer says "Not computed: inputs missing", lists what is
  missing ("TTF price: 4 days with no licensed or public price", a cost line, the benchmark rate)
  and offers to enter each by hand. Whatever is entered by hand is listed under the answer and in
  the report.
- **Simulated prices** (the demo desk) give an answer labelled "Illustration, not a bid level"
  with the `sim` mark beside the figure; it never reads Room, At the limit or Stop.

## Deadlines

The auction close and the cargo offer's expiry raise the existing alerts (to the trader, book
scoped) 120 minutes ahead (warning) and 30 minutes ahead (critical), and appear in Desk → Board's
events list and calendar. A case whose offer lapses before the auction closes says so.

## The desk's own definitions

`src/eurogas_nexus/reference_data/desk/regas_auction.toml` holds, in plain text the desk can edit:
how the auction quotes (per MWh or per slot), the auction formats, the "at the limit" band, the
offer kinds, pricing periods and price units, the default volume tolerance, the cost lines (label,
basis, where each comes from, defaults), the financing days, day count and spread, and the alert
lead times. A copy with the same name in the folder named by `EUROGAS_NEXUS_DEAL_FORMATS_DIR`
replaces it; no code change. Every default an answer uses is stated on the screen.

## Assumptions to confirm with the traders

The traders have been asked, and have not yet answered. Until they do, the defaults below stand
and are stated on the screen:

1. Which terminals (the picker offers every terminal the firm's terms, the tariff register or the
   published tariffs name; another can be entered by hand).
2. How each auction runs (rising rounds, sealed bid, first come first served). The calculation is
   the same; only the level history differs.
3. How the auction is quoted: per MWh of slot energy by default.
4. How cargo owners price: fixed (EUR, GBP or USD per MWh, USD/MMBtu, p/th) or a formula on one
   hub's index, over the send-out days (each day weighted the same) or one month.
5. Which costs they include: the ten default lines; the desk margin defaults to 0.25 EUR/MWh sent
   out, hedging to half a bid/offer of 0.05 per MWh when no quotes are held, storage, late-ship
   buffer and other to zero.
6. Financing: 30 days tied up, the benchmark plus 1.5 pp, ACT/365, on the cargo payment.
7. "At the limit" means headroom within 2 % of the maximum bid.
8. Send-out even over the slot's days unless edited; an LNG slot in m3 at 6.5 MWh per m3 unless
   the operator's factor is entered.
9. Whether they hedge during the window or only after winning: the hedges are shown either way,
   nothing is placed.
