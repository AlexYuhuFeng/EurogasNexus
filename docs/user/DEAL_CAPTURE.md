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

## 2. Read the blotter

One row per deal: time, hub, period, buy/sell, price in its quoted unit (p/th for NBP, EUR/MWh
for continental hubs), volume as traded (MW, th/d, MWh/d; the MWh over the period on hover),
trader, counterparty (or *Cleared* with the exchange), the exchange reference and **where it came
from** (file and line, or by hand and by whom). Filter by trader, hub and venue. Rows a file could
not read are listed above the deals with the reason; mark one as dealt with (for example after
entering it by hand). Totals by hub and delivery period follow, with the average buy and sell
prices.

## 3. The ETRM entry sheet

*ETRM entry sheet (XLSX)* or *(CSV)*: the day's live deals in the column order, headers and
formats of the ETRM's entry template, ready to paste or load.

## 4. Check against the ETRM and close the day

Load the ETRM's own export of the day (the columns of `scripts/ops/import_etrm_trades.py`, plus
the column that carries the exchange reference if the ETRM has one). Every difference is listed:
a deal captured but not in the ETRM, an ETRM trade not captured, and for each pair a different
buy/sell, hub, period, volume, price or counterparty. Pairs are found by the exchange reference,
else by terms (said on the row). Write a short note against each difference; *Close the day* is
offered once every difference has one, and the close is recorded with your name in the audit
trail. A day can be closed again (for example after a late correction); the earlier close is kept.

## 5. The daily pack

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
simulated, deals not valued) says so in a box at the top.

P&L here is the desk's estimate: each captured deal at the position ladder's price for its hub
and month, (price − deal price) × MWh, the day being the change since the previous close.
Currencies are never added together. The ETRM's P&L is the official figure.

## 6. Changing a file layout (no programming)

The layouts are text files with notes in them:

| File | What it describes |
|---|---|
| `eex_trades.toml` | the EEX trade export |
| `ice_deal_report.toml` | the ICE deal report export |
| `desk_csv.toml` | a generic one-deal-per-row CSV: copy it for a new layout |
| `etrm_entry_sheet.toml` | the ETRM entry sheet's columns, and the ETRM export's reference column |

The built-in copies ship in `src/eurogas_nexus/reference_data/deal_formats/`. To change one,
copy it into the folder named by `EUROGAS_NEXUS_DEAL_FORMATS_DIR`, keep its file name (for the
sheet) or its `name = "..."` line (for a layout), and edit the copy in a text editor: on the left
the field, on the right the column header(s) in the export. Then check it against a real file:

    python scripts/ops/check_deal_format.py --format ice_deal_report --file export.csv

It lists every row it cannot read and why, and stores nothing. The EEX and ICE layouts are from
public documentation and are **not yet checked against the desk's own files**.
