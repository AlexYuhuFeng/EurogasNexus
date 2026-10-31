# Customer acceptance review: role by role (2026-10-31)

Written as the buyer: a European gas trading house running NBP, TTF and continental hub
books, bilateral upstream supply, regas capacity and spot LNG, with exchange hedges, a
middle office, credit, compliance and IT. Each role was walked through its day in the
running application (seeded walkthrough data, browser-driven); the gaps found were
implemented in the same change where they could be, and the rest are listed with an owner.

## 1. What ships to the customer, and what does not

| Item | Ships? | Why |
|---|---|---|
| Application (API, web, desktop installer, Python SDK), migrations, docs | Yes | The product |
| Backup **tooling** (`scripts/ops/backup_runtime.py`, `backup_restore_drill.py`, runbooks) | Yes | The customer runs backups of their own database; the product gives the tools and the drill |
| Backup **storage**, encryption keys, encryption at rest (database volume, backup target) | No: deployment-side | These belong to the customer's infrastructure (their KMS/HSM, their storage, their PostgreSQL or cloud database settings). The deployment guide states the requirement; we do not hold their keys. Deferred by the owner for product-side work |
| Simulated price sources (`*_Sim`) | Code ships, **disabled** | Off in trial and release environments (`simulated_sources_allowed()`); a simulated price is never a mark, a VaR input or a bid price. They exist for demos and tests only |
| Licensed market data (ICE Endex, EEX, Trayport, Argus/ICIS, Kpler) | No | Arrives only through the customer's own entitlement and credentials (connectors, imports, licence register) |
| Public data connectors (ENTSOG, GIE, ECB, BoE, NY Fed, ENTSO-E, EIA, National Gas, ECMWF) | Yes (connector code) | The customer supplies their own keys where needed (GIE, ENTSO-E, EIA) |
| Seed/demo data, walkthrough data | No | Never in a release bundle |
| Code signing | Customer's choice | Not a 1.0.0 requirement (owner decision); a buyer signs with their own certificate if their policy requires it |

## 2. External security review and live source certification

* **Security review.** An internal, adversarial review runs on every release
  (`scripts/security/run_security_acceptance.py`, permission matrix, CSRF, isolation,
  secret scanning, Trivy, cargo-audit). It is not a substitute for an **independent**
  penetration test, which the buyer's security team or a CREST/OSCP firm commissions
  against their own deployment (gate G15). Nobody inside the vendor can sign that gate.
* **Live source certification (G16).** Certification proves each connector against the
  live provider with the customer's credentials, in the customer's network. From the
  development sandbox every provider host was refused by the sandbox network policy
  (ENTSOG, ECB, GIE, EIA, ENTSO-E, BoE, NY Fed on 2026-10-31), so no live run was
  possible here and none is claimed. In the customer's environment the operator runs
  `/api/internal/sources/certification` per source after entering their own keys; licensed
  feeds are certified only under the customer's licence.
* **UAT (G18)** is the customer's own sign-off with their users and data.

## 3. Role walkthroughs: would they accept it?

### Trader: hub gas, upstream bilateral, LNG, hedging

| Daily task | Before this review | Now |
|---|---|---|
| Morning: positions by hub and month, hedge ratio, MtM, VaR | Position ladder (physical + financial, curve marks, VaR) | Same, exportable to Excel and PDF |
| Bilateral supply: did the seller deliver what we nominated? | **Missing**: no nomination or allocation data at all | **Delivery against nominations** (Portfolio → Resources): per contract the net and absolute deviation, short/long days beyond the nomination tolerance, imbalance volume, delivery volatility (CV), 7-day trend against DCQ, days outside swing, TSO/point; a gas-day strip per contract. Loaded daily from the TSO (Gassco, National Gas, GTS) or ETRM allocation file |
| "What do we bid for this cargo?" | Netback research engine only (explicit inputs, no terminal comparison) | **LNG cargo bid** (Portfolio → Routes): for each terminal the firm has terms for, the max DES bid from the hub forward for the arrival month less regas, entry, fuel retention, port costs, boil-off and charter; breakeven, the range if arrival slips a month, USD/MMBtu, % of hub, ranked in one currency, by-country ranges and spot alongside |
| Hedging with futures | Screen trades as financial legs; hedge ratio | Same; mandate usage now shows if the hedge pushes the trader over size or tenor |
| New bilateral contract arrives as a signed PDF | Re-keyed by hand (JSON/text import only) | **PDF intake**: upload the PDF, every recognised term (reference, counterparty, delivery point → hub, period → gas year, DCQ converted from kWh/h, MW, th/d or GJ/d, price converted from p/th or USD/MMBtu, index formula, tolerances, law) arrives in the draft with its page and the words it came from; nothing saved until a person checks and saves |
| TSO registration / capacity at the entry point | Entry/exit capacity on the contract; TSO access read path | TSO now shown per contract on the delivery view; booking and nomination stay in the TSO portals (product boundary: no nomination) |

**Would accept** for analysis and decision support. **Worries left:** live licensed price
connectors (Trayport/ICE) depend on the customer's licence and a certified connector; the
contract price field is GBP/MWh for historical reasons, so a EUR contract price is shown
by intake but must be recorded in notes until the multi-currency price field lands.

### Analyst

Fundamentals (NWE balance, gas-for-power, storage vs target, weather demand), spread lab,
datasets for ML. All tabular reads now export to Excel and PDF as well as CSV. Accept.

### Risk, credit and legal/compliance

| Need | Before | Now |
|---|---|---|
| Monitor traders' books and positions incl. futures | Ladder by book, entity, region; portfolio isolation | Same |
| Trader authorisation | Roles only; **no mandates** | **Trader mandates**: books, hubs, max net MWh per hub-month, max tenor, physical/financial allowed, expiry. Usage and breaches (hub outside mandate, over size, beyond tenor, product not allowed) per trader |
| Credit | **Missing** | **Counterparty credit lines**: limit, collateral, rating, approval expiry. Exposure = netted replacement cost at curve marks + unpaid receivables − collateral, utilisation, watch at 75 %, breach above 100 %; unvalued deals counted, never hidden |
| Who may change limits | — | Only someone holding REVIEWER (risk); a trader's rank does not suffice; nobody sets their own mandate; every change audited |
| Market abuse / REMIT | Surveillance report, UMM import with platform terms | Same |
| Reports for committees | CSV | Excel (frozen header, filters, numbers as numbers, About sheet) and PDF (A4 landscape, page n of m, caveat) |

**Would accept** as the risk view beside the ETRM. **Worries left:** the ETRM stays the
book of record and credit system of record; limits here are a control view and early
warning, not a hard pre-trade block (the product does not execute). Credit exposure
nets per counterparty assuming an EFET master with close-out netting; a counterparty
without one should be set up as separate lines.

### Regional and global managers

Head office sees all books; regional heads see their own (portfolio isolation). The
limits panel shows breaches at the top of Exposure; positions roll up by entity, region
and business; the live map gives the portfolio by country. Accept.

### IT desk: maintain, debug, extend

Config contract with generated templates, health and readiness, structured logs, audit
trail, backup/restore drill, migration preflight, SBOMs and licence notices, signed and
attested release assets, Windows installer upgrade/uninstall verified in CI. New this
round: one new runtime dependency (pypdf, BSD-3-Clause); OCR is optional and uses a
Tesseract binary the customer installs (Apache-2.0; nothing GPL is bundled). The daily
allocation load is a script (`scripts/ops/import_contract_deliveries.py`) for their
scheduler. Accept, with their own pen test (G15).

### The LLM layer

Used where it is safe: research orchestration over governed capabilities, glossary and
copilot explanations, with policy gates, entitlement checks and no authority to change
records. Contract intake deliberately uses deterministic extraction with evidence, not an
LLM, so every term traces to a page and the same PDF always reads the same way; an LLM
pass for unusual wording is a sensible next step only behind the same review screen and
the firm's own model endpoint (contract text must not leave the firm unless their policy
allows).

### UI/UX and platforms

One design system (tokens, light/dark, reduced motion), status colours with text (never
colour alone), the same export control on every table, new panels inside existing pages
(no new page per capability). Web (current Chrome, Edge, Firefox, Safari), Windows
desktop installer, Python SDK. Bug reports and client updates: see
[`docs/guides/SUPPORT_AND_UPDATES.md`](../guides/SUPPORT_AND_UPDATES.md).

## 4. Found in the walkthrough and fixed

* The delivery strip coloured every shortfall while the table counted only those beyond
  the nomination tolerance; the strip now marks the same days the table counts.
* An expired credit line with exposure showed only as *expired*; it now counts with the
  breaches at the top of the panel.
* The LNG bid called the front-month close "spot"; it is labelled as what it is.
* With the web client on an origin the server was not told about, every write answered
  `origin_not_allowed`: correct behaviour, and the deployment guide's
  `EUROGAS_NEXUS_CORS_ORIGINS` step is what an installation must set.

## 5. Still open before acceptance

1. **G15** independent penetration test of the customer's deployment.
2. **G16** live certification of each source with the customer's credentials in their
   network.
3. **G18** customer UAT with their data and users.
4. Encryption at rest and encrypted backups configured in the customer's infrastructure
   (deferred by the owner on the product side).
5. Multi-currency contract price field (EUR/USD contracts recorded natively).
6. Daily feeds the customer wires to their scheduler: allocations (TSO/ETRM), ETRM trades,
   vessel positions (their Kpler/Spire licence).
