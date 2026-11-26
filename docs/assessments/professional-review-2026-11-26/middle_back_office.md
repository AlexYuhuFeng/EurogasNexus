# Eurogas Nexus: review by middle office, back office and control functions

Reviewed 2026-11-26. Code: `/home/user/EurogasNexus-merge`. Live demo walked as test_risk, test_ops,
test_finance, test_compliance and test_manager in a browser (screens and page text in
`scratchpad/mbo/`), plus direct reads of the same API calls the client makes. The demo returned many
502s while five sessions ran at once. Key pages were re-walked one session at a time and loaded cleanly.

## 1. Verdict

Risk and scheduling staff would adopt parts of it as a second-line analytics and control layer next to
Endur, Allegro or Aligne. The parts they would use are the counterparty credit and mandate board, the
deal hedge-band check and the gas-day trade, confirmation, nomination and TSO reconciliation. All of
these are well built: method notes on every figure, unvalued legs counted rather than shown as zero, and
maker-checker with before/after diffs. Finance and product control cannot use it at all. There is no P&L
of record: `portfolio_pnl_snapshots` is empty and shows "not yet imported". The figure labelled "day P&L
change" is the 12-month net position multiplied by the front-month close-to-close move, which no
controller would sign. There is also no end-of-day freeze, no official close and no P&L explain.
Compliance gets almost nothing. Surveillance exists only as a CLI script (`scripts/ops/surveillance_report.py`),
the audit log can only be read by ADMIN, and REVIEWER is one role shared by risk, compliance and the head of
desk. Adoption is blocked by three things: trade capture that cannot carry the trade (no index pricing, no
trader, cancelled deals deleted), no end-of-day snapshot or sign-off, and a role model too coarse for
segregation of duties.

## 2. Per persona

### 2.1 Market risk analyst

**The day:** about 07:00, check that the overnight ETRM batch and the official closes have landed.
Run or verify end-of-day VaR, stress tests and limit utilisation. Explain the P&L and VaR moves. Chase
breaches, sign the risk report by about 10:00, then work on curve validation, IPV and model reviews.

**What works:**
- The position ladder (Book → Position) shows physical against financial by hub and month in native
  units, with hedge ratio, mark method (quoted, derived or flat) and a CSV/XLSX/PDF export.
- Curve consistency warnings, e.g. "CEGH q1-27 quoted 45.428 but its months average 42.723".
- Method notes on every risk figure (`domain/risk/method_notes.py`), honestly stamped "drafted; awaiting
  risk review".
- The tenor shock scenario, with the hand-entered shocks listed in `meta.manual_inputs`.
- The four-eyes queue for credit lines, mandates, hedge bands and firm marks (`governance/four_eyes.py`).

**Gaps:**
- *Must-have:*
  - **Real VaR.** Today's figure is a hub-level historical-simulation proxy: 12-month net position times
    the front-month series, one series per hub, VaR withheld when a hub is long in one month and short in
    another. A desk needs a tenor-bucketed curve (M+1…Cal+2) with correlation, plus expected shortfall.
    Demo value: 8.79m EUR over 399 observations, computed on simulated closes.
  - **Stress scenarios** (Norwegian outage, cold snap, TTF +100 %, curve twist). Nothing matches
    "stress" in `src/`.
  - **An end-of-day official close and a snapshot of every risk figure.**
  - **History of VaR, limits and positions**, needed for back-testing, trend and the regulator.
- *Should-have:* a limit hierarchy (firm → legal entity → desk → book → trader) for VaR, stop-loss and
  tenor-bucketed volume. Mandates today only cover net per hub-month, tenor, instruments and hedge band.
  Breach workflow states (acknowledge, cure plan, escalate, close). An IPV module that compares firm marks
  with broker and exchange settlements against tolerances and computes reserves; firm marks are already
  four-eyed, but that is approval, not verification. A model inventory with validation dates.
- *Nice:* intraday what-if from a proposed trade, and greeks for swing and storage.

**Redundant:** the long hedge-band breach string. One deal printed 37 consecutive "hedged -0%, under the
approved 60%" clauses (also showing negative zero). Collapse it to a monthly table.

**Organisation:** make "Risk → End of day" the risk analyst's home. It should hold the close status, a
frozen snapshot, VaR/ES with history, limit hierarchy breaches, P&L explain, and sign-off.

### 2.2 Credit risk officer

**The day:** read overnight exposure by counterparty and by group, check margin calls and collateral,
handle rating changes and line expiries, and approve or decline pre-deal credit checks.

**What works:**
- The credit board (Book → Limits & P&L): limit, replacement exposure, receivable, collateral, net
  exposure, utilisation, status (ok / watch / breach / expired / incomplete) and a **Why?** button.
- Evergreen contracts are capped at the end of the gas year.
- Provenance on each line ("set by demo-seed, not second-approved").
- Maker-checker on line changes, and breach alerts routed to the limits channel.

**Gaps:**
- *Must-have:*
  - **Netting-set and agreement modelling.** There are no EFET/ISDA/CSA master agreements, no
    payables netted against receivables (the method note excludes this) and no thresholds, MTA or
    independent amounts.
  - **A parent/guarantor hierarchy**, so a group's exposure can be aggregated.
  - **PFE / add-on** (excluded today).
  - **Exchange clearing exposure:** margin to ICE and EEX, initial and variation margin, and a liquidity
    view. `collateral_amount` is one float per line (`db/models/risk_controls.py`).
- *Should-have:*
  - Settlement exposure separated from MtM.
  - A rating source and its history.
  - Collateral as documents (LC expiry, issuer bank rating).
  - Credit-limit history.
  - A pre-deal check API that the ETRM or the trader can call. Read-only, which still respects rule 8.
- *Nice:* wrong-way risk flags for Norwegian producers' exposure in an outage.

**Redundant:** the "tightest credit line" tile on the trader's Today screen. Traders need headroom per
counterparty, not "−15,272,920 EUR, used 507 %" on their landing page, especially on simulated marks.

### 2.3 Gas scheduler / operations

**The day:** before the D-1 nomination deadline (about 13:00 UTC for the continent, earlier internal
cut-offs), aggregate trades into nominations per TSO and point. Send them in Edig@s (NOMINT/NOMRES) or on
portals, match with counterparties, handle renominations across the gas day, read allocations (D+1) and
close the imbalance.

**What works:**
- **SCHED-1** (`application/gas_day_reconciliation.py`, `domain/portfolio/nomination_reconciliation.py`)
  reconciles traded, confirmed, nominated and TSO-matched quantities per hub and counterparty. It names
  each break (lesser-rule cut, shipper-code mismatch, late, unit mismatch), sorts by minutes to cut-off,
  shows native units (th/d and kWh/h) and gives indicative cash-out.
- Delivery against nominations per contract, with days short and imbalance.
- The daily balance and the sell-down plan.

This is what a scheduler would actually use.

**Gaps:**
- *Must-have:*
  - **A scheduler login and home.** The demo "ops" user is a DATA_OPERATOR whose home is Sources. There
    is no SCHEDULER test account, although the role exists (`security/identity.py`), and `gas_day.record`
    is held by ANALYST, meaning traders.
  - **Per-TSO nomination windows.** The demo shows "No nomination windows configured" and falls back to
    EU network-code defaults labelled as assumptions. UNC at NBP, THE, GTS and GRTgaz each differ.
  - **Imports of allocation and imbalance prices.** Cash-out uses an approved premium, not the
    published SAP/SMP or the THE balancing price.
- *Should-have:*
  - Edig@s message status ingestion (NOMRES/ALOCAT), read-only.
  - PRISMA/RBP capacity bookings tied to the nomination; `etrm.capacity_bookings.v1` exists but is a file.
  - A within-day linepack and system-length signal.
- *Nice:* an export of nomination proposals as a draft for the scheduling system, clearly marked "not
  submitted".

**Redundant:** the Network map, Strategy Lab and Research for this person.

**Organisation:** a "Gas day" workspace with three tabs (Cut-offs and breaks → Imbalance → Allocations
D+1). Today the content is split between Book → Delivery, Deals → Review ("Nomination window") and Today.

### 2.4 Finance / product control / settlements

**The day:** freeze the end-of-day marks, run P&L, explain day-on-day movement (new trades, price,
volume, time decay, FX), sign off by T+1 morning. At month-end: accruals for delivered but not invoiced
gas, invoice validation against allocations, and the realised/unrealised split per legal entity.

**What works:**
- `erp.invoices.v1` and `erp.counterparties.v1` exist as references.
- The ladder rolls up by legal entity and currency at ECB rates.
- Exports carry an "about" block with warnings.

**Gaps:**
- *Must-have:*
  - **A P&L of record.** None exists: the snapshots table is empty, it is GBP-only
    (`realized_pnl_gbp`, `unrealized_pnl_gbp`) and stored as `Float`
    (`db/models/market_positioning.py`).
  - **Money in Decimal.** 224 `Float` columns against 7 `Numeric` in `db/models` (credit limits, prices,
    quantities). That is unacceptable for sign-off arithmetic.
  - **An official close per hub.** The price resolver prefers "the freshest in-date market price",
    including intraday ticks, over settlement (`application/valuation_snapshot.py`). Today labelled a
    10:20 UTC tick as the "close" behind the day P&L.
  - **Daily P&L explain**, a **sign-off workflow** and a **locked prior day**.
  - **Accruals and invoice-to-allocation checks.** Invoices are stored but never compared with
    allocated MWh × contract price.
- *Should-have:* realised P&L on delivered gas (excluded per the method note), a transport and storage
  cost accrual, and a month-end close calendar.

**Redundant:** finance's home is Exposure, which shows credit and mandates and not their job. The finance
account is read-only VIEWER and cannot even produce a report ("generating a report requires the analyst
role").

**Organisation:** "Control → P&L and close" (day P&L, explain, sign-off, month-end accrual checks).

### 2.5 Compliance / market surveillance

**The day:** review surveillance alerts (REMIT Art. 3/5, MAR), handle inside-information logs and
watch/restricted lists, check ARIS/RRM reporting completeness and rejections, run EMIR reconciliation,
track MiFID II position limits on EEX/ICE TTF (commodity derivatives), and review audit trails and
barriers.

**What works:**
- The surveillance logic is well conceived (`application/surveillance.py`): late own disclosure
  (> 1 h), activity before own disclosure, and activity before the market disclosure.
- Decision cases with evidence hashes and four-eyes.
- Audit retention of five years by default (`application/audit_retention.py`).
- Provenance of simulated rows.

**Gaps:**
- *Must-have:*
  - **A surveillance queue in the product**: alerts, disposition, case notes, escalation. Today it is
    a CLI script that writes CSV.
  - **Audit read access for compliance.** `/api/audit` is `Permission.ADMIN`; test_compliance gets 403
    `identity_role_forbidden`.
  - **A tamper-evident audit.** It is a plain table that an operator can prune
    (`prune_expired_audit_events`). There is no hash chain and no WORM export.
  - **Separation of compliance from risk.** Both are REVIEWER, so compliance can set credit lines and
    approve firm marks.
  - **An inside-information register.** The firm's own UMMs and who knew what, when.
- *Should-have:*
  - A REMIT reporting completeness check: ETRM trades against the RRM's ACK/NACK file, plus a UTI on
    `etrm.deals.v1`.
  - A MiFID II position-limit monitor for TTF futures by contract month (spot month / other months).
  - Information-barrier evidence: who viewed which book.
  - Alerts on report access to own-book data.
- *Nice:* communications linking (pass to Behavox or SMARTS).

**Redundant:** the market Today page as compliance's landing page, and research tools.

### 2.6 Head of desk / management

**The day:** read P&L versus budget, risk utilisation, open breaches, the biggest positions and
counterparties, and decide on hedging escalations.

**What works:**
- Decision cases with four-eyes.
- The position ladder by book, legal entity and region.
- Daily and weekly reports with a "include own book" option.

**Gaps:**
- *Must-have:* a one-page management pack: P&L MTD/YTD against budget, VaR use, top breaches with
  owner and age, top counterparties.
- *Should-have:*
  - Scheduled distribution of that pack. Schedules exist but show "no scheduled reports".
  - Alert triage: the demo has 69 open alerts, 7 of them critical, which is noise for a manager.

**Redundant:** archived reports listed under raw `principal-4c67e75955a9` instead of a person's name,
and AI chat panels next to sign-off figures.

**SoD issue:** the head of desk is REVIEWER, so they can approve credit lines and firm marks for their
own desk. Front office must not approve its own marks.

## 3. Cross-cutting gaps

| # | What is missing | Why a firm needs it | Evidence | Severity | Fix size |
|---|---|---|---|---|---|
| 1 | Trade capture fit for risk | Index-priced, floating, option and multi-leg deals are the gas book. Trader and legal entity drive mandates and REMIT | `etrm.deals.v1` has only a fixed `price`, no index or formula, no trader, no UTI, no legal entity, and `counterparty` is optional; CANCELLED deals are **removed** and re-sent deals **replaced** (`docs/integration/ETRM_ERP_IMPORT_CONTRACTS.md`). There is no amendment history, so yesterday cannot be reproduced | blocker | feature (new contract version, bitemporal trade table) |
| 2 | End-of-day freeze and official close | Every risk and P&L number is signed against one COB set | Price resolver prefers intraday ticks; views are "warm" for 60 s; no COB table. Today's "close" is a 10:20 UTC tick | blocker | architectural |
| 3 | P&L of record and explain | Product control signs P&L daily | `pnl-snapshots` empty; GBP-only Float; "day P&L change" = 12-month net × front-month move (+31.4m GBP on NBP in the demo) | blocker | feature + model |
| 4 | Decimal money | Reconciliation to the cent | 224 `Float` vs 7 `Numeric` columns in `db/models` | major | architectural (migration) |
| 5 | Role model | Segregation: risk, credit, compliance, finance, front office, scheduler | Six roles; REVIEWER covers risk, compliance and management (`security/identity.py`, `ROLES_AND_RESPONSIBILITIES.md`). The doc admits commercial grants lack business approval | major | feature |
| 6 | Audit integrity and access | MAR/REMIT/MiFID record keeping; regulator requests | `/api/audit` ADMIN-only (`security/permissions.py:86`); prunable table, no hash chain | major | feature |
| 7 | Surveillance in product | REMIT Art. 15 obligation to detect and report STORs | `scripts/ops/surveillance_report.py` only; no queue or disposition | major | feature |
| 8 | Risk history | Back-testing VaR, trend, audit of breaches | No exposure, VaR or limit history tables in `db/models`; only alerts | major | feature |
| 9 | Stress and limit hierarchy | Board risk appetite is expressed as VaR, stress and stop-loss limits by entity and desk | No stress code; mandates only cover hub-month volume, tenor and hedge band | major | feature |
| 10 | Two screens, two numbers | Trust | Today shows NBP 12-month net +11,908,399 MWh; the ladder for the same hub and day gives +11,188,399 (horizon definitions differ, neither says so) | major | config/feature (one definition) |
| 11 | Risk figures on simulated prices raising "breach" | Rule 17; demo alerts teach users to ignore breaches | Credit board: Rhinmark 510 % "breach"; 37 hedge-band alerts "based on simulated prices" | minor (demo) / major (if a customer runs mixed) | config |
| 12 | Report authoring for control functions | Risk and finance own the daily reports | Generating a report requires the ANALYST role; REVIEWER and VIEWER can only read archives | minor | config |
| 13 | Human-readable actors | Audit readability | Report library shows `principal-4c67e75955a9` | minor | config |

## 4. Structural limits

- **Data model is snapshot, not bitemporal.** Trades are upserted and cancelled trades deleted. Credit
  lines and mandates keep only provenance of the last change. Positions and VaR are computed on read,
  with a 60 s warm view. No question of the form "what did we report at COB on 14 November, and why
  did it differ?" can be answered. Control functions are built around that question. It needs an
  as-of/system-time model for trades, marks and limits, plus a COB run that persists every figure.
- **Compute-on-read risk.** `/api/desk/today` takes 158 statements and 4.9 s; `/api/reports/catalogue`
  takes 5.8 s (`BACKEND_AUDIT` P3). Real VaR, ES or Monte Carlo over thousands of deals × 36 tenors ×
  500 scenarios cannot run per request. It needs a batch risk run with stored results. A job runner
  exists, so no new datastore is needed. This is a run-model change.
- **Floats for money and volumes** throughout the schema.
- **Price authority.** One resolver mixes ticks, settlements, firm marks and flat fallbacks. Good for a
  trader's live view, wrong for valuation of record. The product needs two explicit price sets: live and
  official COB.
- **Integration is file-based and vendor-neutral.** No Endur, Allegro or Aligne adapter. Imports
  replace rather than version. No RRM, Edig@s or PRISMA feeds, even read-only. Reconciliation to the
  ETRM is a manual "sample" step in the guide.
- **Licensing.** Official closes (ICE Endex, EEX settlements) and broker curves for IPV are licensed.
  Under rule 18 they arrive only through the customer's entitlement. Until a customer connects them,
  every risk number is either simulated or a public reference index, and so unsignable.
- **Coarse identity scopes.** REGION and PORTFOLIO scopes are reported as unsupported
  (`experience.unsupported_scope_kinds`). Information barriers rest on book scopes. Market data and
  UMMs are shared to everyone with the source family (`COMPLIANCE_AUDIT.md` M1).

## 5. Where it sits beside the incumbent stack

- **Replaces:** the scheduler's Excel reconciliation of trades against nominations and TSO responses.
  It also replaces risk's spreadsheet credit and mandate board, which today sits outside the ETRM for
  hedge-band policies.
- **Complements:** Endur, Allegro or Aligne (book of record, settlement, P&L) and the RRM or ETRM
  (ARIS, EMIR), as a readable second line with method notes and maker-checker.
- **Duplicates pointlessly, if pursued:** its own P&L or VaR "of record" without the ETRM's trade
  fidelity. Better to import the ETRM's official P&L and VaR and do the explain, comparison and
  breach workflow here.

## 6. Top 10 changes, in priority order

1. **`etrm.deals.v2` and a bitemporal trade store.** Add index and formula pricing, trader, legal
   entity, UTI, deal version and amendment time. Keep cancelled deals as a state, never delete.
2. **A COB run.** Freeze the official close per hub (customer settlements; never ticks), then persist
   positions, MtM, VaR, credit and limit utilisation per date with a frozen manifest. The existing
   `freeze_snapshot` is the seed.
3. **P&L of record by import, plus a native P&L explain.** Import ETRM P&L in the entity currency
   (drop GBP-only fields). Explain new trades, price, volume and FX. Add product-control sign-off with
   four-eyes and lock the prior day. Rename "day P&L change" to "flat-curve price move indication" or
   remove it.
4. **Decimal for money, prices and volumes** in the risk, credit, P&L and invoice tables (expand/contract
   migration).
5. **Split roles:** MARKET_RISK, CREDIT_RISK, COMPLIANCE, PRODUCT_CONTROL, SCHEDULER and DESK_HEAD,
   mapped to the existing permissions. Front office and the desk head cannot approve marks or credit.
   Add an access-request flow approved by the business owner.
6. **Compliance workspace:** an audit read for COMPLIANCE, a hash-chained or WORM-exported audit, the
   surveillance queue with disposition, and an inside-information register.
7. **Risk engine v2:** tenor-bucketed historical VaR and ES on the curve, named stress scenarios, a
   VaR/stress/stop-loss limit hierarchy by entity, desk and book, a breach lifecycle and history.
8. **Credit v2:** netting agreements, payables netting, parent and guarantor aggregation, CSA thresholds,
   exchange margin, and a read-only pre-deal check API.
9. **Scheduler workspace:** per-TSO nomination windows, imports of published imbalance prices and
   allocations, read-only Edig@s/PRISMA status, and a SCHEDULER demo account with that home.
10. **Trust hygiene:**
    - One definition of net position across Today and the ladder.
    - No "breach" alerts from simulated marks.
    - Hedge-band text collapsed to a table.
    - People's names instead of principal ids.
    - Report authoring for REVIEWER and VIEWER on their own sections (risk and finance daily reports).
