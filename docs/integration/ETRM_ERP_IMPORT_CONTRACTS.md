# ETRM and ERP import contracts

The files an ETRM, a scheduling system or an ERP sends to Eurogas Nexus, version by version:
which columns each file has, which are required, what makes a row the same row when the file
is sent again, and where the rows land. The contracts are defined in code
(`src/eurogas_nexus/application/import_contracts.py`). This page describes them, and
`GET /api/imports/contracts` lists them.

Eurogas Nexus is a decision-support layer. Importing a deal records a trade the ETRM already
booked. Importing a nomination status records what the scheduler or the TSO already
confirmed. Importing an invoice records a reference the ERP already holds. Nothing is booked,
nominated, posted or paid from here, and the ETRM and the ERP stay the books of record.

## How a file is checked and stored

| Step | What happens |
|---|---|
| Format | CSV, UTF-8 (a byte-order mark is accepted), one header row, comma-separated. Column names are case-insensitive. Extra columns are ignored, and blank lines are skipped. |
| Whole-file checks | The file is refused as a whole (`column_missing`, `column_forbidden`, `file_empty`, `file_too_large`) when a required column is missing, when it carries bank details or tax or government identifiers (`iban`, `bic`, `swift`, `bank_account`, `account_number`, `routing_number`, `sort_code`, `vat_id`, `vat_number`, `tax_id`, `tax_number`, `ein`, `national_id`, `passport`), or when it holds more than 200,000 rows. |
| Row checks | Every row is checked on its own. A refused row is reported with its line number (the header is line 1), a reason code and a message. A row whose key repeats an earlier row in the same file is refused as `duplicate_key`. |
| Refused rows | By default (`reject_file`), one refused row refuses the file and nothing is stored. With `skip_rows` the accepted rows are stored and the refused ones reported. |
| Re-import | Rows are keyed by the source's own id. A row equal to what is stored is counted `unchanged` and not written, so sending the same file twice changes nothing and publishes no event. |
| Report | `rows`, `accepted`, `refused` (line, reason code, message, key), `created`, `updated`, `unchanged`, `removed`, the file's SHA-256, `file_refused` and `committed`. |

How to send a file:

- **Check it (no write).** Send it with
  `POST /api/imports/{contract_id}/validate?system=<system>[&on_error=skip_rows]` and a
  `text/csv` body of up to 8 MB. This needs an analyst role or above. The answer is the
  report: what storing the file would create, update, leave unchanged or remove.
- **Store it (operator).** Run
  `python scripts/ops/import_contract_file.py --contract <id> --system <system> --file <path>`.
  Without `--commit` this is a dry run. With `--commit` the rows are stored and the import is
  audited (`data.import`). Add `--skip-bad-rows` to store the accepted rows when some are
  refused, and `--list` to print the contracts.
- **The sending system** (`--system`, `system=`) names where the file came from, for example
  `Endur` or `SAP`. It becomes part of the key of deals and ERP references, so two systems
  never overwrite each other's rows.

Integration middleware (MuleSoft, Boomi, an in-house job) checks a file with the validate
call and drops it where the operator's scheduled job runs the script. Use a service identity
key with the least role it needs (see [ERP_ETRM_INTEGRATION.md](ERP_ETRM_INTEGRATION.md)).

## Contracts

A contract's id ends in its version (`.v1`). A change that would make an accepted file mean
something else, or refuse a file that was accepted, becomes a new version, and the old version
stays accepted for a deprecation period announced in the release notes. Optional columns may be
added within a version.

### `etrm.deals.v1`: gas trades

Lands in the books, as the trades that positions, P&L and risk read. The key is
(system, `trade_id`). A re-sent deal replaces its earlier version, and a deal whose `status` is
`CANCELLED`, `CANCELED`, `DELETED` or `VOID` is removed. The checks are those of the existing
importer (`ingestion/etrm_trades.py`).

| Column | Required | Content |
|---|---|---|
| `trade_id` | yes | The ETRM's deal number |
| `book_id` | yes | Book the deal is in. It must exist here (`book_unknown`) |
| `hub` | yes | Delivery hub (TTF, THE, NBP, PEG, PSV, ZTP...) (`market_unknown`) |
| `side` | yes | `BUY` or `SELL` (`B`, `S`) (`side_invalid`) |
| `delivery_start`, `delivery_end` | yes | First and last gas day, `YYYY-MM-DD`, inclusive (`date_invalid`, `period_reversed`) |
| `quantity` | yes | Positive. The sign is the side (`quantity_not_positive`) |
| `quantity_unit` | yes | `MWh` (total), `MWh/d`, `MW`, `th/d` |
| `price`, `price_unit` | yes | The price and its quote (`EUR/MWh`, `GBp/th`), in the hub's currency |
| `trade_time` | no | ISO 8601. Defaults to the start of delivery |
| `status` | no | See above |
| `counterparty` | no | The counterparty's short name |

### `etrm.physical_positions.v1`: the physical schedule per gas day

Lands in `gas_day_schedule_lines`, which the gas-day view and the hub balance read. These are
the lines that no trade or contract row carries: storage injections and withdrawals, customer
offtake, imports and exports on held capacity. The key is `line_id`, which must be unique
across the systems that send it. Financial positions are not imported. They are derived from
the deals, so the platform holds one truth for them.

| Column | Required | Content |
|---|---|---|
| `line_id` | yes | The scheduling system's line id |
| `gas_day` | yes | `YYYY-MM-DD` |
| `hub` | yes | The hub the line balances at |
| `direction` | yes | `in` (gas the firm takes at the hub) or `out` (gas it delivers) |
| `kind` | yes | `in`: `supply`, `upstream`, `lng_send_out`, `storage_withdrawal`, `import`, `purchase`. `out`: `sale`, `customer_offtake`, `storage_injection`, `export` (`kind_unknown`, `kind_direction_mismatch`) |
| `label` | yes | Facility, customer, point or capacity, as the desk names it |
| `quantity_mwh` | yes | MWh for the gas day, zero or more (`quantity_negative`) |
| `book_id`, `point`, `counterparty`, `contract_id` | no | As named in the ETRM |

### `etrm.nominations.v1`: nomination statuses

Lands in `gas_day_nomination_events`, which is append-only. The gas-day checklist reads the
newest status of each step, and a row is labelled `origin` `import` and recorded by
`import:<system>`. The key is a digest of (system, gas day, line, step, status, recorded time,
quantity), so the same status sent again is recorded once. Recording a status sends nothing to
a TSO.

| Column | Required | Content |
|---|---|---|
| `gas_day` | yes | `YYYY-MM-DD` |
| `line_ref` | yes | `contract:<id>`, `schedule:<line_id>`, `lng:<slot_id>`, `trade:<id>` (the ETRM deal number) or `counterparty:<name>` (a nomination netted per counterparty) (`line_ref_invalid`) |
| `hub` | yes | The line's hub |
| `step` | yes | `nomination`, `renomination`, `lng_unloading`, `lng_send_out`, `lng_inventory`, or `trade_confirmation` (the counterparty's confirmation of a deal, on its `trade:` line) (`step_unknown`) |
| `status` | yes | `to_send`, `sent`, `confirmed`, `renominated`, `mismatch_queried`, `done` (`status_unknown`) |
| `recorded_at` | yes | When it was recorded, ISO 8601, not later than now (`time_in_future`) |
| `quantity_mwh`, `book_id`, `agent`, `note` | no | The note holds at most 500 characters |
| `counterparty`, `direction`, `point`, `shipper_code`, `counterparty_shipper_code`, `counterparty_quantity_mwh` | no | SCHED-1's matching fields: whom the line is nominated against, `in` or `out` (`direction_invalid`), the interconnection point (blank for the hub's virtual trading point), the firm's and the counterparty's shipper codes, and the counterparty's own nominated MWh as the TSO's matching reports it (zero or more, `quantity_negative`) |

The SCHED-1 columns are optional within v1 (added 2026-11-25): a file without them is read as
before and keeps its event ids, because they enter the key only when given. With them, the
gas day's reconciliation (`GET /api/desk/gas-day/{gas_day}/reconciliation`) can tell a
counterparty, direction or shipper-code break from a quantity gap, and a lesser-rule cut from
a TSO's mismatch. The TSO's answer is a `confirmed` (matched; `quantity_mwh` is the matched
quantity) or `mismatch_queried` row for the same line and gas day.

### `etrm.cargo_schedule.v1`: the firm's LNG cargoes

Lands in `lng_cargoes`. A new or changed cargo of a book publishes `cargo.changed`, so the
cargo plan and each role's prompts follow (LNG-2). The key is `cargo_id`. A blank cell keeps
the stored value, so a file never takes a cargo out of its book by leaving `book_id` empty. The
checks are those of the existing importer (`ingestion/lng_positions.py`). Positions and tracks
come from the vessel feed, not from this contract.

| Column | Required | Content |
|---|---|---|
| `cargo_id`, `vessel_name`, `status`, `load_port` | yes | `status`: `loading`, `laden`, `discharging`, `delivered`, `ballast` (`status_invalid`) |
| `eta`, `eta_basis`, `eta_confidence` | no | ISO 8601. The basis is one of `master_notice`, `ais_declared`, `feed_estimate`, `schedule`, `manual`. The confidence is `high`, `medium` or `low` |
| `vessel_imo`, `load_country`, `departed_at`, `destination_terminal`, `destination_country`, `volume_m3`, `energy_gwh`, `book_id` | no | `book_id` must exist here |

### `etrm.capacity_bookings.v1`: capacity the firm holds (TAR-2)

Lands in `capacity_bookings` (migration 0088, ADR Decision 38). The key is the sending system
and `booking_id`. A booking's contracted cost prices what it covers before any public tariff:
in route pricing, contract costs, the capacity optimiser, LNG-3 and `GET /api/capacity/cost`.
A row with `status` `RELEASED`, `CANCELLED`, `CANCELED` or `VOID` ends the booking: it is
stamped released and stays readable as of the instants it was held. A booking without a price
is held, and the cost it covers is then not given (never zero). Nothing is booked, bid or
released at a TSO or terminal from here.

| Column | Required | Content |
|---|---|---|
| `booking_id`, `kind`, `facility`, `first_gas_day`, `last_gas_day`, `quantity`, `quantity_unit`, `acquired_via` | yes | `kind`: `entry`, `exit`, `lng_slot`, `regas`, `send_out`, `storage` (`kind_unknown`). `facility`: the ENTSOG point key, terminal id or storage id as the registers name it. `quantity_unit`: `MWh/d`, `kWh/h`, `kWh/d`, `MWh` or `slot` (only, and always, for `lng_slot`: `unit_unknown`). `acquired_via`: `auction`, `long_term`, `allocation`, `secondary`, `fcfs`, `bilateral` (`acquired_via_unknown`). The last day is inclusive (`period_reversed`); the quantity is positive (`quantity_not_positive`) |
| `price`, `price_unit`, `currency` | no | The contracted price in a tariff unit (`EUR/(kWh/h)/y`, `p/kWh/d`, `EUR/MWh`, ...) or `<CCY>/slot` for slots; the currency defaults to the unit's |
| `operator`, `facility_name`, `product`, `firmness`, `book_id`, `counterparty`, `status` | no | `firmness` `FIRM` (default) or `INTERRUPTIBLE` (`firmness_invalid`); a blank `book_id` holds the capacity at firm level |

### `bank.fx_rates.v1` and `bank.interest_rates.v1`: the firm's own bank (TAR-2)

The firm's clearing or account bank's FX and interest rates, from the bank's own export or typed
by hand. The sending system (`--system`) is the institution's key in the organisation setting
`financial_institutions` (administrators, audited; no credential is accepted there), and the
rows land in `fx_observations` and `interest_rate_observations` with source `BANK:<key>`. They
are the `contracted_bank` tier of the source-precedence resolver, used before a licensed
fixing (WM/Reuters, BFIX) and the ECB unless the firm sets another order; rows of a key that is
not configured are stored but not used. A re-sent rate replaces the earlier one. No bank is
connected live: a feed needs the firm's own agreement and credentials, and stays outside this
product.

| Contract | Column | Required | Content |
|---|---|---|---|
| `bank.fx_rates.v1` | `base_currency`, `quote_currency`, `rate`, `value_date` | yes | ISO 4217 codes (`pair_invalid` when the same); `rate` positive, quote currency per unit of base; `value_date` YYYY-MM-DD |
| | `rate_type`, `published_at`, `rate_id` | no | `mid` (default), `buy` or `sell` (`rate_type_unknown`); when the bank published it (default: the end of the value date); the bank's own reference |
| `bank.interest_rates.v1` | `rate_id`, `currency`, `rate_pct`, `value_date` | yes | The bank's name for the rate, up to 9 characters (`EUR-ON`, `USD-1M`); percent a year, -5 to 50 |
| | `day_count` | no | `ACT/360` (default) or `ACT/365F` |

### `erp.counterparties.v1`: counterparties

Lands in `erp_references` (kind `counterparty`). It is a reference that lets a trade, a credit
line or an invoice be matched to the ERP's own number. The key is (system, `erp_id`).

| Column | Required | Content |
|---|---|---|
| `erp_id` | yes | The ERP's business partner, customer or vendor number |
| `name` | yes | Legal name |
| `counterparty_id` | no | This platform's counterparty id (credit lines), when mapped |
| `legal_entity` | no | The firm's company code facing it |
| `country` | no | ISO 3166 alpha-2 (`country_invalid`) |
| `currency` | no | ISO 4217 (`currency_invalid`) |
| `payment_terms_days` | no | A whole number of days |
| `blocked` | no | `true`/`false` (`x` reads as true) |

### `erp.invoices.v1`: invoice references

Lands in `erp_references` (kind `invoice`). The key is (system, `invoice_id`). The
counterparty must already be known from the same system's counterparty file
(`counterparty_unknown`), so send counterparties first.

| Column | Required | Content |
|---|---|---|
| `invoice_id` | yes | The ERP's document number |
| `counterparty_erp_id` | yes | The counterparty's `erp_id` |
| `direction` | yes | `receivable` or `payable` |
| `issue_date`, `due_date` | yes | `YYYY-MM-DD`. The due date is not before the issue date (`period_reversed`) |
| `amount`, `currency` | yes | Gross amount, positive (`amount_not_positive`), and its ISO 4217 code |
| `trade_ref` | no | The deal, contract or cargo invoiced, as the ETRM names it |
| `status` | no | `open` (default), `partially_paid`, `paid`, `cancelled` |
| `paid_amount` | no | Between 0 and the amount |
| `period_start`, `period_end`, `legal_entity` | no | Delivery period invoiced, and company code |

## Mapping from common systems

These contracts are vendor-neutral, and no vendor-specific connector is supplied. An ETRM or
ERP extract is mapped to them in the system's own reporting layer or in the middleware. The
notes below describe the kind of fields such systems typically hold, as general industry
knowledge. Field names, tables and extract tools differ by product version and by each firm's
configuration, so confirm every mapping with the system's administrator.

| Contract | Typically supplied by | Fields such systems typically hold |
|---|---|---|
| `etrm.deals.v1` | Allegro, Endur (Openlink), RightAngle and other ETRMs (several of these are now ION products) | A deal or trade number, trade date and time, internal portfolio or book, counterparty, buy/sell, delivery location or pipeline point, start and end dates, volume with its unit and frequency, fixed price or price index with its currency and unit, and a deal status (validated, amended, cancelled). A position is often extracted per deal leg, and a firm with legs maps each leg to one row with its own `trade_id` |
| `etrm.physical_positions.v1` | the ETRM's scheduling or logistics module, or a separate scheduling system | Daily scheduled quantities per location and path, storage injection and withdrawal by facility, and customer offtake. These are often held as nominations or schedules per gas day |
| `etrm.nominations.v1` | the ETRM's scheduling module or the nominations agent's confirmations | Nomination and renomination quantities per gas day and point, with a status that moves from submitted to confirmed or matched, and confirmation times. TSO confirmations follow the Edig@s message flow, which the scheduler typically records |
| `etrm.cargo_schedule.v1` | the ETRM's LNG or shipping module | A cargo or voyage id, vessel, load port, laycan or loading window, discharge terminal, ETA, and volume (m3) or energy |
| `etrm.capacity_bookings.v1` | the ETRM's transport or capacity module, or a download from the booking platform (PRISMA, a terminal's portal) | A capacity contract or booking number, point or terminal, direction, product, period, booked quantity (often kWh/h), auction premium or contracted price, and the platform it was bought on |
| `bank.fx_rates.v1`, `bank.interest_rates.v1` | the bank's own rate export or the treasury system | A currency pair or rate name, value date, rate and its type (mid, buy, sell), and the bank's reference |
| `erp.counterparties.v1` | SAP S/4HANA or ECC, and other ERPs | A business partner or customer/vendor number, legal name, country, company code, payment terms and a posting or payment block flag. Bank details and tax numbers are also held there, and they are deliberately not taken |
| `erp.invoices.v1` | SAP S/4HANA or ECC (accounts receivable and payable), and other ERPs | Document number, company code, customer or vendor number, document and due dates, gross amount and currency, clearing status, and a reference or assignment field that often carries the ETRM's deal number |

## Errors

Whole-file refusals answer 422 on the validate call, and print `Refused: [code] message` from
the script with exit status 2. An unknown contract answers 404 `contract_unknown`. A file larger
than 8 MB answers 413 `file_too_large` over HTTP. Send larger extracts through the script, which
takes up to 64 MB. Row-level refusals are part of the report: the validate call answers 200,
and the script prints each refusal, exits 2 when the file is refused, and exits 0 when the
rows were skipped as asked.
