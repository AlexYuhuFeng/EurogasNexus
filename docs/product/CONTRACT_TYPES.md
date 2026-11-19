# Contract types: one book, several kinds of agreement

Status: design note and first slice (2026-11-19). Owner request: "Contracts could be of
different types, LNG MSPA, upstream tender and so on. Consider this."

## 1. What the model holds today

Every contract is one row of `upstream_resource_contracts` in one shape: *supply contract,
delivery point, gas year, MWh/d, price*. The columns and who reads them:

| Column(s) | Read by |
|---|---|
| `delivery_point_name`, `gas_year`, `delivery_quantity_mwh_per_day`, `contract_price_gbp_mwh` + `contract_price_currency` | position ladder (`application/position_inputs.py`: one physical leg per contract, hub from the identity resolver, gas-year window), credit (`limits_service.credit_inputs`: legs referenced by the credit line's `contract_ids`), mandates, hedge cover, opportunity reads (`opportunity_reads.contracts`), resource pool (`resource_pool.portfolio_resource_from_contract`), map "Our book" (`map_situation`), delivery performance (DCQ vs `contract_deliveries`) |
| `delivery_tolerance_pct`, `nomination_tolerance_pct`, `tolerance_risk_allowance_gbp_mwh` | resource pool / route optimiser (type R re-route) |
| `allowed_exit_points`, `eligible_sale_modes`, `owned_entry/exit_capacity_mwh_per_day` | resource pool sale options, held capacity, map paths |
| `settlement_frequency`, both lags, `annual_financing_rate_pct`, `financing_tranches`, `payment_terms_json` | early-cash value in the optimiser; revisions v2-v4 |
| `resource_type` (PIPELINE_IMPORT, BEACH_DELIVERY, LNG_REGAS, STORAGE, CONTRACT_POOL) | delivery mode in the pool; it is a *physical route* tag, not a contract type |
| `notes` (JSON) | counterparty, a free-text "contract type", index basis, title-transfer and beach points, governing law, document provenance, variable/regas costs |
| `book_id`, `retired_*` | book scope; lifecycle (retired rows leave every consumer) |

Around it: the governed write (`POST /api/route-cost/upstream-contracts`) with edit token and
immutable revisions (schemas v1-v4), PDF intake (`/api/contracts/intake`, OCR when Tesseract
is installed), the capacity book (`capacity_profiles`), LNG terminal terms, own cargoes and
regas slots (`lng_cargoes`, `regas_slots`, ETRM/vessel feed), and the cargo study
(`POST /api/lng/cargo-economics`), which today is fed only by hand.

What is lost: an MSPA has no volume or price of its own; a cargo is a lump of energy in a
window, priced off Henry Hub or a hub with a slope and a constant; a tender has a swing band
and floats at an index. Squeezing these into "MWh/d at a price" either invents numbers or drops
the terms that carry the value.

## 2. Taxonomy

A desk contracts in nine kinds. Each row: what it is · terms that matter · optionality · what
the product must compute · covered today / missing.

| Kind (`contract_kind`) | What it is and its terms | Optionality | The product computes | Covered / missing |
|---|---|---|---|---|
| **SUPPLY_GSA** long-term gas supply agreement | ACQ/DCQ, delivery point, period, index or fixed price, price review, take-or-pay, make-up/carry-forward | swing (min/max DCQ), make-up | position, credit, re-route, delivery vs DCQ | All of today's columns are this shape; ToP, make-up, price review missing (text for now) |
| **UPSTREAM_TENDER** producer offtake sold by tender (UKCS/Norwegian field gas) | seller, field/source, landing/entry point, tender period, DCQ with min/max, nomination basis (DA/WD), price = hub index ± differential (or fixed), offtake obligation/shortfall, field outage as force majeure, entry/lifting cost | swing inside min-max DCQ; nominated daily | position at DCQ over the tender period at the delivery hub; swing band for the evaluators; floating price (no fixed MTM) | Point, DCQ, tolerances covered; period dates, swing, index ± diff, FM, entry cost missing → **typed now** |
| **LNG_MSPA** master sale and purchase agreement | counterparty, our side, signed date, law, delivery terms allowed (FOB/DES), laytime, demurrage rate, quality range, credit support, destination/diversion rights | none on its own; it frames confirmations | nothing on its own: it is not a position | Nothing fits → **typed now**, excluded from every consumer |
| **LNG_CARGO** Confirmation Notice under an MSPA | master, FOB/DES, load port or discharge terminal, delivery window and the narrowed window, cargo size (MMBtu) ± tolerance, price formula (slope × HH/Brent/hub + constant, pricing month), boil-off, vessel | tolerance, diversion (from the master), window narrowing | DES: the cargo's energy as a physical leg at the terminal's hub over its window; FOB: no European hub leg; expected arrival on the map; cargo study prefilled | Nothing fits → **typed now** |
| **LNG_TERM_SPA** multi-year LNG SPA | ACQ, ADP, take-or-pay, downward quantity tolerance, make-up, price review, destination clause | DQT, cancellations, diversion | annual programme, ToP exposure, lifting-vs-cancel (cargo study "lifting cost") | Deferred: needs ADP rows (cargoes become confirmations under it) |
| **HUB_TRADE** EFET GA (TTF/PEG/THE appendices), NBP 2015, ZBT confirmations | master + confirmation: hub, product, volume, price | none | position and credit | Arrives from the ETRM as trades (screen orders); stays read-only, no editor |
| **TRANSPORT_CAPACITY** entry/exit bookings, PRISMA products | point, direction, firm/interruptible, product duration, booked kWh/h, tariff | use-it-or-lose-it, secondary resale | held capacity for routes (type C) | `capacity_profiles` covers it; a typed editor is deferred |
| **LNG_TERMINAL_CAPACITY** TUA, regas slots | slots, send-out, storage rights, tariffs | slot release | regas slots, terminal costs | `regas_slots` + LNG terminal terms; deferred |
| **STORAGE_CAPACITY** SBU | space, injection/withdrawal rights and ratchets | intrinsic/extrinsic | storage value | storage masters; deferred |

Out of scope: **tolling/processing** (liquefaction or regas tolling is an asset-backed
arrangement whose economics the cargo study already holds as "fee"; no customer request) and
**swaps** (financial, they arrive from the ETRM as trades, not as contracts we author).

## 3. Model

- **Discriminator on the existing row.** `contract_kind` (NOT NULL, default `SUPPLY_GSA`) and
  `contract_kind_reviewed` (false for a migrated row until a person confirms the kind).
- **Typed terms as one validated JSON block** `kind_terms`, versioned inside
  (`"schema": "upstream-tender/v1"`), validated by strict Pydantic models per kind
  (`domain/contracts/kinds.py`, `extra="forbid"`). Chosen over per-kind tables because the
  governed write, edit token, revisions, audit and book scope stay one path; kinds evolve by
  schema version, not by migration; nothing queries a term in SQL. The cost is that a term is
  checked in Python, not by a column constraint; the golden-case tests carry that.
- **`master_contract_id`** (self foreign key, `ON DELETE RESTRICT`): a confirmation names its
  master; the master must be an `LNG_MSPA`, active, and allow the delivery term.
- **`unmodelled_terms`** (text): every term the product does not model yet (price review,
  heel, make-up mechanics) is kept verbatim, so nothing typed in or read from a PDF is lost.
- **One authority for the old columns.** For a typed kind the server derives the base columns
  from the terms (`derive_base_fields`), so every consumer above keeps working unchanged:
  tender → point, DCQ, swing as tolerances, price; cargo → terminal or port, window, MWh/d
  over the window. A master stores zero volume and price and is excluded from every consumer
  (`feeds_book`). The form never asks for a column the kind does not have.
- **Revisions v5** record kind, terms, master and unmodelled text in the hashed snapshot,
  produced only when the row has any of them, so migrated rows keep their bytes and hashes.
  Edit token v4 covers the new columns.
- **Migration 0072** adds the five columns; every existing row becomes `SUPPLY_GSA`,
  unreviewed, with its terms untouched: the library shows "kind inferred, confirm". Downgrade
  drops the columns.

## 4. What each consumer reads per kind

| Consumer | SUPPLY_GSA | UPSTREAM_TENDER | LNG_MSPA | LNG_CARGO |
|---|---|---|---|---|
| Position ladder | as today | DCQ over the tender's own dates at the point's hub; index-priced → price floats (unpriced on fixed MTM, said in warnings) | not read | DES: cargo MWh spread over the window at the terminal's hub; FOB: not on a European hub (warning) |
| Credit | credit line `contract_ids` | also the terms' counterparty | — | the master's counterparty |
| Resource pool / re-route (R) | as today | point, DCQ, swing as tolerances; index cost = latest price at the point + differential (simulated if that price is) | not read | DES only, at the terminal |
| Opportunity reads (`contracts`) | as today | + kind, min/max DCQ | — | + kind |
| Delivery performance | DCQ | DCQ | — | — |
| Map "Our book" | as today | as today | — | expected cargo at its terminal with the window start as ETA, unless the vessel feed already holds it |
| Cargo study | — | — | — | "From a confirmed cargo" fills term, size, slope, constant, pricing month |

## 5. Built now and later

Built in this slice: the discriminator, typed blocks for UPSTREAM_TENDER, LNG_MSPA and
LNG_CARGO, migration 0072, revisions v5, the type-first form (cards, then only that kind's
terms grouped as parties and master · quantity · delivery · price · flexibility · credit,
pickers for counterparties, points, terminals, ports, books, masters), PDF intake proposing a
kind, the list showing kind, counterparty, period and the figure that matters (DCQ and swing;
cargo TBtu and window; master: confirmations held), the consumers in §4, one demo contract of
each new kind. SUPPLY_GSA keeps today's editor plus the kind badge and the unmodelled-terms
box.

Later, in order: LNG term SPA with ADP (confirmations hang under it as under an MSPA); take-or-pay
and make-up accounting for GSA and SPA; window-narrowing schedule as dated steps; typed editors
for transport, terminal and storage capacity over the existing registers; price review events.
