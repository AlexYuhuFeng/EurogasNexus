# LNG terminal costs: where each figure comes from

Two things are kept apart (design C.5, CP-11):

* **the firm's terms** (`lng_terminal_terms`): what the firm pays under its own contracts,
  entered by the desk;
* **the public register** (`lng_terminal_tariff`): what each operator publishes, one row per
  figure, versioned by document (URL, SHA-256, title, date read), never overwritten, and
  reviewed by a second person before it prices anything actionable.

Pricing a cargo uses, in order: the firm's terms; the reviewed public tariff in force for the
arrival month and cargo class; a candidate public tariff (shown as *indicative*); otherwise
the terminal is left out with the reason (`needs_firm_terms`, `no_tariff_in_force`,
`cargo_class_not_offered`). `GET /api/lng/terminal-tariffs/price` answers it.

**Terms first.** The operators' sites restrict reuse (docs/legal/DATA_SOURCE_TERMS.md): an
operator's documents are read only after an administrator records the firm's permission for
that operator (`PUT /api/lng/terminal-tariffs/operators/{operator}` with the reference the firm
holds). `scripts/ops/refresh_lng_terminal_tariffs.py` then reads them, adds candidate rows for a
new document and queues one attention item ("Fluxys LNG tariff changed: review 2 values"); the
same document again changes nothing. An operator without recorded permission is skipped and
reported `needs_firm_terms`. The evidence below was read on 31 October 2026, before this terms
check; it is kept as the record of what the documents said, not as a licence to reuse them.

## Evidence as read on 31 October 2026

| Terminal | Regime | What is priced | Figure | Source |
|---|---|---|---|---|
| Zeebrugge (Fluxys LNG) | Regulated (CREG), indexed monthly with CPI | Slot: berthing, basic storage and basic send-out for one cargo (up to 140,000 m³ LNG over 10 days) | €631,714.81 per cargo for October 2026 (basis-2003 €527,803.20 × index 1.1969); gas in kind 1.30 % | Fluxys LNG price simulator, October 2026, and tariff list (CREG approvals 2019–2025), [tariff page](https://www.fluxys.com/en/natural-gas-and-biomethane/empowering-you/tariffs/tariff_fluxyslng-lng) |
| Montoir-de-Bretagne (Elengy) | Regulated (CRE, ATTM7) | Total per cargo by class; standard and SMART SPOT (booked after the 20th of the month before) | Standard cargo (1,000 GWh): €972,000 term, €752,000 SMART SPOT; Med-Max €531,000 / €421,000; Q-Flex €1,324,800 / €1,016,800; Q-Max €1,589,400 / €1,215,400 | [Elengy ATTM7 tariff brochure](https://www.elengy.com/en/our-services/pricing-conditions/our-access-tariffs), applicable from 1 April 2025 |
| Fos Cavaou (Elengy) | Regulated (CRE, ATTM7) | as above | Standard cargo €1,082,000 term, €836,000 SMART SPOT | same |
| Fos Tonkin (Elengy) | Regulated (CRE, ATTM7) | Med-Max ships only | €724,000 term, €562,000 SMART SPOT | same; regulated activity ends end-2028 |
| Brunsbüttel (DET) | Auction | Short-term storage, regas and send-out | €0.20/MMBtu average (€0.682/MWh), 1 June to 31 August 2026 | [DET auction notice](https://energy-terminal.de/en/news/news-detail/erfolgreiche-auktion-von-regasifizierungskapazitaten-am-terminal-brunsbuttel-fur-den-zeitraum-1-juni-31-august-2026) |
| Wilhelmshaven (DET) | Auction | as above | from the latest DET notice the desk passes with `--det-notice` | DET news |
| Gate (Rotterdam), Dunkerque LNG, Grain, Eemshaven, private terminals | Exempt or negotiated | Contract, open season or market call | Entered by the desk from the firm's own contract or offer | The firm's contract; Dunkerque LNG is exempt from regulated access and tariffs (CRE deliberation 2024-58); Grain sells capacity by bid on an annual capacity charge |

Elengy figures exclude gas taken off (fuel), port fees and the transmission entry tariff;
Fluxys figures exclude port dues and transmission entry. The desk keeps those, the extra
sailing days and any other cost on each terminal's terms; the refresh never overwrites them.

## Why the dates differ

* **Fluxys** publishes a new indexed tariff every month (CPI indexation formula
  0.65 + 0.35 × I/I₀ in the tariff list), so the refresh picks up a new figure monthly.
* **Elengy**'s ATTM7 tariff is in force from 1 April 2025. In deliberation 2025-41 the CRE
  chose not to update it every year (the allowed movement was widened from ±3 % to ±5 %);
  the next scheduled update is 1 April 2028. The 2025 brochure is therefore current.
* **DET** prices short-term capacity by auction; each result applies to its own period
  only, so a bid for a later period needs the matching notice.

## How a bid uses them

* A **slot or fixed charge per cargo** (Zeebrugge) is divided by the cargo's energy.
* A **total by cargo class** (Elengy) takes the smallest class that holds the cargo; a
  class the terminal does not list (a Q-Max at Fos Tonkin) means the cargo cannot be landed
  there on that tariff, and the sheet says so instead of guessing.
* An **auction price per MMBtu** (DET) is converted at 0.29307107 MWh/MMBtu.
* **Long-term capacity the firm already holds** counts only its variable cost: the fee is
  sunk whether or not this cargo lands.
