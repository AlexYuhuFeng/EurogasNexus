# Deal capture and the end of the day

Book → **Blotter**. The day's deals come in from the exchange exports and by hand, go out as the
ETRM entry sheet, are checked against the ETRM at the end of the day, and reach managers and the
remote risk function as the daily pack (PDF and XLSX, English and Chinese). The ETRM stays the
official record: everything here is the desk's own copy, labelled *desk estimate, before ETRM
close* until the day is closed. Nothing here places, sends or pre-fills an order (AGENTS.md rule 8).

## 1. Bring the day's deals in

- **Upload**: choose the book, leave *File layout* on *Recognise from the headers* (or name the
  layout), and pick the file. The result says how many deals were new, corrected, cancelled,
  already held, and how many rows could not be read.
- **Watched folder**: with `EUROGAS_NEXUS_DEAL_DROP_DIR` set, drop the file in
  `<folder>/<book id>/` (or `<folder>/<book id>/<layout name>/`). The monitoring worker imports
  it and moves it to `imported/` or `refused/` beside a `.result.txt` note.
- **By hand** (broker and bilateral deals): *Enter a deal by hand*. The deal is marked as entered
  by hand on the blotter, in the ETRM sheet's *Source* column and in the packs, with the fields
  that were typed.

Exporting the same day again is safe: a deal is recognised by its venue and venue trade id, so a
repeat adds nothing; a changed deal becomes a new version (the earlier one is kept, see
*N versions* on the row) and a cancelled deal stays on the blotter marked *cancelled*.

## 2. The deals in the position, during the day

A captured deal is in the desk's position the moment it is stored: the position ladder, Today,
credit exposure, mandate usage, the limit alerts, the reports and the daily pack all read one
position source, so no two of them can disagree. A screen that is open changes within a second
of a new, corrected or cancelled deal (it re-reads on the deal at once, whatever the price tape
is doing). While a deal's day is not closed every figure built from it says *desk estimate,
before ETRM close*; a deal with no price is listed as not valued, never counted as zero.

**One deal is counted once.** When the ETRM extract is loaded into the book
(`scripts/ops/import_etrm_trades.py`) before the day is closed, each ETRM trade is matched with
the captured deal it is, by the same rule as the end-of-day check:

1. a pair recorded when a day was closed;
2. else the exchange's trade id: the ETRM column the layout file names (`reference_column` in
   `etrm_entry_sheet.toml`) equals the deal's trade id;
3. else, for an ETRM trade without that column, the same hub, buy or sell, and delivery period
   (the closest volume and price among several).

Until the day is closed the captured deal counts (a correction or a cancellation shows at once);
once it is closed the ETRM trade counts (the official record). The order in which deals are
captured, the extract is loaded and the day is closed does not matter.

**Physical or financial.** The position shows physical, financial and net. Each captured deal is
classified, in order, by a choice made by hand on the blotter (*In position as*; recorded as
entered by hand, with who and when, audited), by the deal itself when it says physical, then by
the rule file `reference_data/desk/position_kinds.toml`: options and swaps financial; exchange
spot and prompt products (delivering within three gas days) physical; exchange futures financial
until their first delivery day, physical from then on; bilateral and broker forwards physical
(title transfer at the hub); anything else financial. To change the rule, copy the file into the
folder named by `EUROGAS_NEXUS_DEAL_FORMATS_DIR` and edit it. The ETRM entry sheet's physical
column follows the same classification.

**Units.** The ladder's *Captured deals in it* rows give each hub and month in the desk's unit,
therms per day at NBP and MW at the continental hubs, with the MWh on hover, in exact decimals
from the deal to the row.

## 3. Read the blotter

One row per deal: time, hub, period, buy/sell, price in its quoted unit (p/th for NBP, EUR/MWh
for continental hubs), volume as traded (MW, th/d, MWh/d; the MWh over the period on hover),
trader, counterparty (or *Cleared* with the exchange), the exchange reference and **where it came
from** (file and line, or by hand and by whom). Filter by trader, hub and venue. Rows a file could
not read are listed above the deals with the reason; mark one as dealt with (for example after
entering it by hand). Totals by hub and delivery period follow, with the average buy and sell
prices.

## 4. The ETRM entry sheet

*ETRM entry sheet (XLSX)* or *(CSV)*: the day's live deals in the column order, headers and
formats of the ETRM's entry template, ready to paste or load.

## 5. Check against the ETRM and close the day

Load the ETRM's own export of the day (the columns of `scripts/ops/import_etrm_trades.py`, plus
the column that carries the exchange reference if the ETRM has one). Every difference is listed:
a deal captured but not in the ETRM, an ETRM trade not captured, and for each pair a different
buy/sell, hub, period, volume, price or counterparty. Pairs are found by the exchange reference,
else by terms (said on the row). Write a short note against each difference; *Close the day* is
offered once every difference has one, and the close is recorded with your name in the audit
trail. A day can be closed again (for example after a late correction); the earlier close is kept.

## 6. The daily pack

- **Management summary**: P&L for the day, month and year to date; volume traded by hub and
  period; open position by hub and month; limit usage; prices held for the next month.
- **Risk pack**: P&L by trader and hub; exposure per counterparty against its limit and its
  guarantee with the guarantee's expiry; mandate checks (options, tenor, volume); the end-of-day
  check with each acknowledgement; rows not read; deals not valued.

Download either in English or Chinese, PDF or XLSX, to send by hand. *Send* queues them for
e-mail to the recipient lists an administrator keeps under Settings → Notifications (*Daily
management summary*, *Daily risk pack*; recipients must be registered people allowed to read
every book's limits). *Send on a schedule* sends them by itself on weekdays at the chosen time.
A pack that fails a check (no deals on a trading day, rows not read, the day not closed, prices
simulated, deals not valued) says so in a box at the top. A trading day is a weekday on which at
least one of the desk's exchanges is open, from `reference_data/desk/trading_calendars.toml`:
the exchange holidays, **maintained by hand** from each exchange's published calendar (its source
is named in the file; `checked = false` until someone has compared it). Add the next year before
it starts; for a year the file does not cover, the pack says so.

P&L here is the desk's estimate: each captured deal at the position ladder's price for its hub
and month, (price − deal price) × MWh, the day being the change since the previous close.
Currencies are never added together. The ETRM's P&L is the official figure.

## 7. Changing a file layout (no programming)

The layouts are text files with notes in them:

| File | What it describes |
|---|---|
| `eex_trades.toml` | the EEX trade export |
| `ice_deal_report.toml` | the ICE deal report export |
| `desk_csv.toml` | a generic one-deal-per-row CSV: copy it for a new layout |
| `etrm_entry_sheet.toml` | the ETRM entry sheet's columns, and the ETRM export's reference column |
| `position_kinds.toml` | which deals count as physical or financial (folder `reference_data/desk`) |
| `trading_calendars.toml` | the exchanges' non-trading weekdays (folder `reference_data/desk`) |

The built-in copies ship in `src/eurogas_nexus/reference_data/deal_formats/`. To change one,
copy it into the folder named by `EUROGAS_NEXUS_DEAL_FORMATS_DIR`, keep its file name (for the
sheet) or its `name = "..."` line (for a layout), and edit the copy in a text editor: on the left
the field, on the right the column header(s) in the export. Then check it against a real file:

    python scripts/ops/check_deal_format.py --format ice_deal_report --file export.csv

It lists every row it cannot read and why, and stores nothing. The EEX and ICE layouts are from
public documentation and are **not yet checked against the desk's own files**.
