# The answer bar

The search bar at the top of every page (or **Ctrl K**, **⌘K** on a Mac) answers as well as
finds. Type a sum, a conversion, a hub or a question: the answer is the first row, and the pages
and commands that match are listed under it as before.

It answers in three ways, cheapest and surest first.

## 1. Instant: as you type, no Enter

Worked out on your screen, with no data read and no AI.

| You type | The answer row shows |
|---|---|
| `(42.5-39.8)*30` | **81** |
| `200 + 15%` · `15% of 200` | **230** · **30** |
| `100 GWh to therm` | **3,412,141.63 th** |
| `500 MW in GWh/d` | **12 GWh/d** |
| `40 EUR/MWh to p/th` | **97.8271 p/th** · *ECB 16 Nov: EURGBP 0.8345* |
| `12 $/MMBtu in €/MWh` | the price, with the ECB EURUSD rate and its date |
| `10 mcm/d to GWh/d` | **110 GWh/d** · *At 11 kWh/m³ (GCV, combustion 25 °C, volume 0 °C, 101.325 kPa): assumption* |
| `10 mcm to GWh at 11.2` | **112 GWh**, at the calorific value you typed |
| `gas day` · `D+2` · `days to 1 Jan` · `front month` | the gas day and its UTC window, the day count, `Dec-26` |
| `what is TTF` · `TTF 是什么` · `define UMM` | the glossary's short definition; **Enter** opens the entry |

- The conversion factors are the product's own units authority, the same ones the server uses.
- A volume becomes energy only with a calorific value on the line: the one you typed, or the
  desk's assumed value, which the line calls an assumption.
- A price changes currency only with an **ECB reference rate the product holds**; the line names
  the rate and its date. With no rate held it says so and converts nothing.
- **Numbers:** the decimal mark is the point (`42.5`); a comma is a thousands separator only in
  groups of three (`1,000`, `12,345.6`). A decimal comma such as `3,5` is not read, so it never
  becomes a wrong figure. Full-width digits and operators from a Chinese input method are read.
- Nothing is computed while you are typing a name: `TTF`, `Dec-26`, `2026-11-16` or a lone `2026`
  give no calculator answer. Put **`=`** in front to force the calculator (`=2026`).

## 2. Looked up: a moment after you stop typing

Read from the product's own data, as the page that owns the number reads it. Each answer shows
its as-of time and source; **Enter** opens the page where the number lives.

| You type | The answer row shows | Enter opens |
|---|---|---|
| `TTF` · `NBP` · `TTF Dec-26` · `NBP DA` | the price in the hub's quotation (NBP in p/th), the day change, close date and source | Desk → Prices |
| `storage` · `storage DE` · `German storage` | fill %, TWh in store, the target status | Desk → Today |
| `LNG` · `LNG FR` · `Norway` | GWh/d and the change against a week earlier | Desk → Today |
| `outages` · `outages NBP` · `UK outages` · `outages Haldor` | active count, GWh/d offline, the largest three | Desk → Outages & capacity |
| `position` · `position NBP Dec-26` | net MWh/d (with your book permission) | Book → Position |
| `credit Rhinmark` · `Rhinmark headroom` | headroom, % used, status | Book → Limits & P&L |
| `contract Haldor` | daily quantity, delivery point, gas year | Deals → Contracts |

A simulated price carries the same **sim** mark as the hub board and is never shown as a market
price. Where no sourced price exists the row says **No sourced price** and why, as the board does.
Book answers are offered only to people allowed to read the book; the server checks again.

## 3. Asked: press Enter on the Ask row

A question that needs a summary ("what's going on with Norwegian supply this week", "why did
storage withdrawal jump", "挪威供应这周怎么样？") offers an **Ask** row. Nothing is sent until you
press **Enter** (or put **`?`** in front). The answer appears in the bar:

- **AI summary**, two to five sentences written only from the desk's own figures (prices,
  outages, storage, the NW Europe balance, and your book if you may read it), each with its date.
  It passes the same checks as every AI note in the product (no number, hub, unit or source the
  figures lack; no advice to trade or nominate; simulated data said as such) or it is not shown.
- **Figures used**, each with its as-of date, and links to the pages that hold them.
- **Open as report** takes the question to Research → Reports, which proposes a report plan.
- While it works the bar says what it is doing; **Esc** cancels.

If AI is off for your role or this installation, the Ask row says so and Enter shows the figures
and the pages instead. A definition question whose term is in the glossary goes to the glossary,
never to the AI.

## Keys

| Key | Does |
|---|---|
| ↑ ↓ | move between the answer, Ask and the results |
| Enter | open where the answer lives, run Ask, or open the selected result |
| Tab | take the answer into the field (a result to calculate on, a term, an instrument) |
| Ctrl+C / ⌘C | copy the answer's number; with Shift, copy it with its unit |
| Esc | leave an asked answer, then close the bar |
| `=` / `?` in front | force the calculator / force Ask |
