# Role-first redesign: design basis

Status: Accepted; decisions D1–D6 taken as recommended, D5's authority changes deferred to a security-reviewed change. Basis: branch `integrate` at `62eaaf3`, read from source and docs only. I did not run the application, so every "default view" statement rests on the code and on `docs/product/UI_INFORMATION_AUDIT.md`; each slimming package starts with a browser check.

Suggested location: `docs/product/ROLE_FIRST_REDESIGN.md`.

## 0. What the code says today

| Finding | Evidence | Consequence |
|---|---|---|
| Four modes, 17 tasks, permission-filtered; persona grants nothing. | `clients/web/src/app/navigation/modeNavigation.ts` (`PRODUCT_MODES`, `modeTaskVisible`) | Keep the modes. The redesign changes composition, not navigation. |
| Five roles carry authority; ten job functions pick the home screen only. | `src/eurogas_nexus/security/authorization.py` (`ROLE_PERMISSIONS`), `security/capabilities.py` (`FunctionalAssignment`, `ASSIGNMENT_HOME`), `docs/product/ROLES_AND_RESPONSIBILITIES.md` | A role-tuned default composition has a place to hang: the job function. |
| There is no originator and no operations/scheduling job function. | `FunctionalAssignment` enum; demo identities in `scripts/demo/start_public_demo.py` (`TESTERS`) | Two of the nine roles in this brief have no persona today (decision D4). |
| The trader's declared home is Prices (`market`, `curves`), while Today is the first Desk task and calls itself "the first screen". | `ASSIGNMENT_HOME`; `TodayScreen.tsx` header; `UX_REFERENCE.md` rule 8 | The landing is ambiguous (decision D1). |
| The strip shows every open alert to every user, with no category or role filter. That includes `data_source` / `ingestion_failed` alerts. | `app/model/tickerItems.ts` (`buildTickerItems` filters only `status === "open"`), `components/ShellTicker.tsx`, alert categories in `application/monitoring_service.py` | Pipeline health reaches the trader's board. This is the clearest case of the owner's complaint. |
| The strip is a scrolling marquee and is absent only when there are no items at all. | `components/BreakingTicker.tsx` | A standing breach or a partial derate keeps it open all day. |
| Trader pages carry pipeline and provenance furniture by default: the projection context strip, the source-approval notice, the endpoint-failure banner, and board-read retry notices. | `MarketCockpit.tsx` (`MarketContextStrip`, `SourceApprovalNotice`), `AppShell.tsx` (`describeEndpointFailures`), `CapacityWorkspace.tsx` (`CapacityBoardStateNotice`) | Move to the status chip, Inspector or Admin. |
| Catalogues built to give an unused endpoint a consumer sit on working pages. | `ReferenceNetworkCatalogue` (Network), `DataProductCatalogue` and `ResearchCapabilityCatalogue` (Research → Data), `CapacityContractBook`, `NativeCapacityContextPanel` | None serves a daily job on that page. |
| The alert centre prints the category enum with underscores replaced. | `AlertCenter.tsx` line 122 | Raw enum in visible copy. |
| Acknowledging an alert has an ANALYST floor; risk, desk head and compliance are REVIEWER (rank below ANALYST). | `security/permissions.py` (comment on `/api/monitoring/alerts/{alert_id}/acknowledge`), `ROLE_RANK` in `security/identity.py` | Risk cannot acknowledge a limit breach (decision D5). |
| `/api/audit` is ADMIN only. | `security/permissions.py` | Compliance cannot answer an audit request alone (decision D5). |
| Finance is documented as ANALYST but the demo identity is VIEWER. | `ROLES_AND_RESPONSIBILITIES.md` vs `TESTERS` | Clarify under D4. |
| No licensed news feed exists in the code. | No news connector under `src/eurogas_nexus` | "Market-impact news" on the strip must stay sourced events (REMIT UMMs, the firm's alerts) until a customer-entitled feed is connected. |
| The width class, pointer, and three-viewport browser sweep already exist. | `app/shell/useShellLayout.ts`, `docs/product/ADAPTIVE_CLIENT.md`, `scripts/uat/browser_workflow_smoke.mjs` (1440, 1920, 390) | Device work extends existing machinery. |

## 1–2. Roles, jobs and the minimal information for each

Conventions for the tables:
- "Minimal" lists the numbers or states with the comparison that gives each meaning.
- "Ends with" is the single primary action.
- "Add on demand" is ranked; the first is the most useful.
- Units follow `UX_REFERENCE.md` rules 7 and 9: EUR/MWh continental, p/th NBP, MW and th/d for volume, GWh/d for flows, TWh and % for storage.

**Never in the default view of any job below** (destination in brackets):
- Provenance ids, observation ids, input fingerprints, correlation ids (Inspector).
- Method notes and "how to read this" text (the existing `MethodNote` / `PanelHelp` popovers).
- Projection slice tables and per-source quote matrices (Inspector, "Source" link).
- Pipeline, ingestion and store state (top-bar status chip → Admin).
- Raw enums and codes (tooltip or Inspector).
- Full ISO timestamps (relative or short form; exact on hover or tap, see section 6).
- Engine, dataset or commit identity (Inspector on the run).

### R1 Front-office trader (prompt and curve)
Job function `TRADER`, role ANALYST. Assumption: one or two home hubs (TTF, NBP or THE) and a book in the ETRM.

| ID | Job | Decision · when | Minimal | Ends with | Add on demand |
|---|---|---|---|---|---|
| T1 | When I open before the market, I need what changed overnight and whether it touches my book, so that I know my first trades. | Trade or wait. Daily, 06:30–08:00 local. | DA and front-month at home hubs vs prior close; net position today and front month (MW, signed) vs yesterday; tightest limit headroom (% used); unplanned outages since yesterday at my hubs (GWh/d); storage fill vs last year (%). | Open Prices, or draft the morning brief. | 1 Hub spreads vs TTF. 2 Supply call. 3 Full outage list. |
| T2 | When the market is open, I need the curve at my hubs against the hubs I spread, so that I can spot a level worth acting on at my execution screen. | Which product and side. Continuous. | Hub × tenor board (bid, offer, change on day); spread vs TTF; simulated mark where applicable. | Nothing in-product; the trade happens on Trayport or the exchange. | 1 Forward curve chart. 2 Converter. 3 Product delivery windows. 4 Quotes by source. |
| T3 | When an unplanned outage is published, I need its size, duration and location against my position, so that I can decide whether to cover. | Cover, re-route or hold. Event-driven, minutes matter. | Asset and zone; unavailable GWh/d vs technical; start and expected end; my net position at the affected hub for those days; price move since publication. | Open the outage on Network, or "Report". | 1 Other outages in the zone. 2 Flows at adjacent points. 3 Outage-response replay. |
| T4 | When the gas day is running, I need my residual by day at each hub, so that I close out before cash-out. | How much to buy or sell within-day and day-ahead. Several times daily; hard before day end. | Per gas day: expected supply, traded, residual (MWh, signed) and the cost of leaving it open vs the DA price. | Sell-down split (how much DA, how much within-day). | 1 Delivery performance of the contracts behind supply. 2 Nomination window clock. |
| T5 | When I want to add risk, I need my position and headroom, so that I stay inside the mandate. | Size of the next trade. Before each sizeable trade. | Net by delivery period (physical + financial); mandate utilisation %; counterparty line headroom for the intended counterparty. | None (read). | 1 Hedge band per deal. 2 Book breakdown. |
| T6 | When the day ends, I need the day's P&L change and open items, so that I can hand over. | What to flag. Daily, about 17:00–18:00. | Day P&L change by hub; position at close; open alerts; tomorrow's outages. | End-of-day report draft. | 1 P&L snapshot history. |
| T7 | When I look at a location spread (for example TTF–THE or NBP–TTF), I need the spread net of transport, so that I know if moving gas pays. | Use capacity or not. Weekly to daily. | Spread (EUR/MWh) vs route cost (tariff, fuel); capacity available on the route; indicative netback. | Send the route to Evaluate. | 1 Tariff publication status. 2 Capacity billing calculator. |

### R2 Originator / structurer (deals, LNG)
No job function exists; today this person is ANALYST with `TRADER` (decision D4). Assumption: works on a few deals a week, not minute by minute.

| ID | Job | Decision · when | Minimal | Ends with | Add on demand |
|---|---|---|---|---|---|
| O1 | When a cargo is offered, I need our maximum DES price per terminal, so that I can bid. | Bid ceiling. Per tender, often within hours. | Per terminal: forward mark for the arrival month, less regas, entry, fuel, port, boil-off and charter = max DES in USD/MMBtu and % of hub; range if arrival slips. | Save the bid evaluation to a decision case. | 1 Slot availability. 2 Terminal tariff source. 3 LNG economics sandbox. |
| O2 | When I structure a supply contract, I need its delivered cost and margin against the curve, so that I can price it. | Offer price and terms. Per deal. | Volume profile; price formula vs forward mark; route cost; margin (EUR/MWh and total); credit headroom for the counterparty. | Run the scenario. | 1 Sensitivity. 2 Payment-term cash timing. 3 Financing rate helper. |
| O3 | When terms are agreed, I need to record the contract, so that the book and risk see it. | None (data entry). Per deal. | The contract form; the required fields first. | Save the contract. | 1 Read a confirmation PDF into a draft. 2 Revision history. |
| O4 | When several resources and sales compete, I need the allocation that maximises margin within constraints, so that I can propose a plan. | Which supply to which sale. Weekly, monthly. | Allocated and unallocated volume; net margin; binding constraints, each stated as a reason. | Open a decision case for review. | 1 Per-allocation route detail. 2 Map paths. |
| O5 | When a deal needs approval, I need its case to be complete, so that the reviewer can decide. | Submit or fix. Per deal. | Case objective, due time, evidence present or missing, blockers. | Submit for review. | 1 Decision pack. |
| O6 | When I compare routes for a deal, I need each route's all-in cost, so that I pick the cheapest feasible one. | Route. Per deal. | Per route: tariff, fuel and loss, capacity state; total EUR/MWh vs the spread it serves. | Choose the route in the scenario. | 1 Tariff publications. 2 Capacity billing. |

### R3 Analyst (fundamentals and research)
Job functions `HQ_BUSINESS_ANALYST` and `QUANT_RESEARCHER`, role ANALYST.

| ID | Job | Decision · when | Minimal | Ends with | Add on demand |
|---|---|---|---|---|---|
| A1 | When the morning data lands, I need storage, flows, LNG send-out and the supply call against expectation, so that I can brief the desk. | View for the day. Daily, by 08:00. | Storage fill % vs last year and vs target trajectory; NW Europe supply call (GWh/d) vs the 7-day average; Norway and LNG send-out vs yesterday; gas-for-power burn and clean spark vs clean dark. | Draft the morning brief. | 1 14-day balance forecast. 2 Per-zone gas for power. 3 Weather evidence. |
| A2 | When a fundamentals surprise occurs, I need its size against normal, so that I can quantify the price effect. | Bullish or bearish and how much. Event-driven. | The series, its latest value, the deviation from the comparison period, the affected hub. | Generate a situation report. | 1 Spread lab on the affected spread. |
| A3 | When I test a spread idea, I need its level, z-score and whether a rule on it would have paid, so that I can decide to pursue it. | Pursue or drop. Weekly. | Spread history; current level vs mean (z-score); rule result (indicative P&L, drawdown, sample size). | Save as a strategy draft. | 1 Backtest. 2 Compare runs. 3 Shadow monitor. |
| A4 | When I write the weekly or monthly report, I need the standard sections assembled from current data, so that I only edit. | What to publish. Weekly, monthly. | Report catalogue; the plan; the generated report. | Generate, then print or download. | 1 Stored reports. |
| A5 | When I need a dataset for a model, I need to define and build it point-in-time, so that the research is reproducible. | Build or fix the specification. Occasional. | Specification form; validation result; build result. | Build the dataset. | 1 Lineage. 2 Feature and target registry. 3 Data product catalogue. |
| A6 | When a strategy is in shadow, I need its drift against the backtest, so that I can retire or keep it. | Keep, pause or retire. Weekly. | Shadow P&L vs backtest expectation; open shadow alerts; data staleness on its inputs. | Pause, resume or retire the monitor. | 1 Run detail (price basis, per-contract contribution). |

### R4 Risk manager
Job function `RISK_MANAGER`, role REVIEWER (per `docs/user/manual/RISK.md`).

| ID | Job | Decision · when | Minimal | Ends with | Add on demand |
|---|---|---|---|---|---|
| K1 | When I start the day, I need every limit against its line, so that I chase breaches first. | Whom to call. Daily. | Credit: exposure vs approved line per counterparty (% used), breaches first. Mandates: open position vs mandate per trader. Counts of breach and watch vs yesterday. | Open the breach. | 1 Why (drivers). 2 History of the utilisation. |
| K2 | When a breach occurs, I need its size, cause and owner, so that I can escalate or approve a temporary excess. | Escalate, accept or instruct reduction. Event-driven. | Limit, utilisation, excess amount, the trades or contracts driving it, since when. | Acknowledge with a note (see D5), or change the line. | 1 Position ladder for the book. |
| K3 | When a deal is submitted, I need its evidence and downside, so that I can accept, reject or reopen. | Decision on the case. Per deal; due time matters. | Objective; result (margin, volume); warnings and blockers; evidence freshness as one word; who opened it. | Record the decision (four-eyes). | 1 Decision pack. 2 Run assessments. |
| K4 | When a committee approves a hedge band, I need to record it and see cover against it, so that hedging stays within approval. | Band per deal. Per committee. | Per contract: approved band (min–max %) vs measured cover by month. | Save the band. | 1 Book-level hedge ratio. |
| K5 | When I set or review a credit line or mandate, I need the current use and recent peaks, so that the line fits. | Line size. Monthly or on request. | Current exposure, the line, peak use (assumption: history is not stored today; see gaps). | Save the line. | — |
| K6 | When I report weekly or monthly, I need positions, P&L and limit use for the period, so that I can sign off the risk report. | Report content. Weekly, month-end. | Net position by period and hub; MTM and VaR where validated; breaches in the period. | Export (Excel or PDF). | 1 P&L snapshots. |

### R5 Middle office / operations (deliveries, reconciliation)
No job function exists (decision D4). Assumption: schedulers nominate in the TSO or shipper system; this product informs and never nominates.

| ID | Job | Decision · when | Minimal | Ends with | Add on demand |
|---|---|---|---|---|---|
| M1 | When the gas day is planned, I need each contract's expected delivery against nominated, so that I spot shortfalls. | Chase the supplier or inform the trader. Daily, D-1 and within day. | Per contract: contracted, delivered and shortfall (MWh), and the delivery rate vs its norm. | Flag to the trader (Report or brief). | 1 Daily balance at the hub. |
| M2 | When a nomination window approaches, I need the deadline and what is still open, so that nothing is missed. | Prioritise. Several times daily. | Next windows with the time to close (in my time zone); quantities still unplanned. Information only. | None in-product. | 1 Nomination assessment. |
| M3 | When storage is in play, I need inventory, injection and withdrawal limits and the plan, so that the schedule is feasible. | Feasible or not. Daily to weekly. | Inventory vs capacity; today's limit; planned injection or withdrawal vs limit. | None (planning view). | 1 Dispatch assessment. |
| M4 | When ETRM trades are imported, I need books and assignments to be right, so that positions roll up correctly. | Reassign. On import; month-end. | Books by entity; unassigned contracts or trades (count). | Assign to a book. | — |
| M5 | When month-end comes, I need delivered against contracted per contract, so that reconciliation and invoices can start. | Sign off volumes. Monthly. | Per contract for the month: contracted, delivered, variance. | Export. | 1 Tolerances and make-up terms on the contract. |
| M6 | When an outage affects a delivery point, I need the contracts routed through it, so that I can warn counterparties. | Whom to inform. Event-driven. | Outage; contracts at that point; volume at risk per day. | Open the contracts. | 1 Outage-response replay. |

### R6 Finance
Job function `FINANCE_SETTLEMENT`; role VIEWER in the demo. Assumption: reads only; invoices live in the ERP.

| ID | Job | Decision · when | Minimal | Ends with | Add on demand |
|---|---|---|---|---|---|
| F1 | When I forecast cash, I need payments due by date and currency, so that treasury can fund. | Funding. Weekly. | Per contract: next payment date, amount estimate, currency; payment lag. | Export. | 1 FX fix used. 2 Financing rate. |
| F2 | When month-end closes, I need delivered volumes and P&L snapshots, so that accruals are right. | Accrual amounts. Monthly. | Delivered volume per contract; MTM at close; P&L snapshot of the last day. | Export. | — |
| F3 | When a counterparty's credit is discussed, I need exposure against the line, so that I can support the decision. | None (input). Occasional. | Exposure vs line, per counterparty. | None. | — |
| F4 | When an auditor asks, I need the contract terms and their revisions, so that I can evidence a figure. | None. Occasional. | Contract, payment terms as declared, revision list. | Export or print. | — |
| F5 | When tariffs change, I need the new tariff and its date, so that budgets are updated. | Budget. Yearly, and around NC TAR publications. | TSO, gas year, indicative or final, due date. | None. | — |

### R7 Compliance
Job function `LEGAL_COMPLIANCE`, role REVIEWER.

| ID | Job | Decision · when | Minimal | Ends with | Add on demand |
|---|---|---|---|---|---|
| C1 | When an audit or regulator request arrives, I need the decision record for a deal with its evidence, so that I can answer. | None (retrieve). Occasional, deadline-bound. | Case, decision, who and when, evidence list. | Export the decision pack. | 1 Audit log extract (not available to this role today, D5). |
| C2 | When I check four-eyes, I need cases where the opener and decider are recorded, so that I can attest. | Attest. Quarterly. | Decided cases: opener, decider, date. | Export. | — |
| C3 | When data licences are reviewed, I need who holds which licensed scope, so that vendor reports are right. | Report. Quarterly, per vendor. | Licence, holders (count and names). ADMIN only today. | Export. | — |
| C4 | When a REMIT-relevant event touches our assets, I need to know it was seen, so that I can show awareness. | None. Event-driven. | Outage, when published, who acknowledged. | None. | — |
| C5 | When a contract is retired, I need the reason and the trail, so that the record is complete. | None. Occasional. | Retired contracts with reason, who, when. | None. | — |

### R8 Desk head / manager
Job functions `MANAGEMENT` and `REVIEWER_MANAGEMENT`, role REVIEWER.

| ID | Job | Decision · when | Minimal | Ends with | Add on demand |
|---|---|---|---|---|---|
| H1 | When I look in, morning and evening, I need the desk's P&L change, position and limit state, so that I know if I must intervene. | Intervene or not. Twice daily, often on a phone. | Day P&L change (total, by hub); net position front month; breaches (count, worst); decisions waiting for me (count, nearest due). | Open the waiting decision. | 1 Position ladder. 2 Brief. |
| H2 | When a deal waits for me, I need its summary, so that I can decide quickly. | Accept, reject, reopen. Per deal. | Same as K3. | Record the decision. | Same as K3. |
| H3 | When something breaks (outage, breach), I need to know before the phone rings. | Whom to call. Event-driven. | The strip item with size and effect on the book. | Open it. | — |
| H4 | When I report up weekly or monthly, I need the market and book summary, so that I only edit. | Content. Weekly, monthly. | Stored reports; the desk brief. | Generate or download. | — |
| H5 | When access is reviewed quarterly, I need who can see my desk's data, so that I can confirm. | Confirm or revoke. Quarterly. | Users with commercial roles and scopes for my desk. No screen for this role today (gap). | Sign off. | — |

### R9 Platform admin / data operations
`PLATFORM_ADMINISTRATOR` (ADMIN) and `DATA_OPERATOR` (OPERATOR). ADMIN alone sees no commercial data.

| ID | Job | Decision · when | Minimal | Ends with | Add on demand |
|---|---|---|---|---|---|
| P1 | When I start, I need the sources that need me, so that the desk has data. | Which to fix first. Daily. | Sources needing attention: name, one state word, since when, next action. | Run, retry, or fix the credential. | 1 Run history. 2 Health detail. |
| P2 | When a source is onboarded, I need its terms approved, key stored and first run validated, so that it goes live. | Approve and connect. Occasional. | Provider, terms summary, approval state, key state, last validation. | Approve, save the key, test the connection. | 1 Certification. |
| P3 | When a user reports a problem, I need the report with its diagnostics, so that I can resolve it. | Fix or route. Event-driven. | Inbox: who, page, words, failing reads. | Reply or close. | 1 Diagnostics bundle. |
| P4 | When someone joins or leaves, I need to grant or remove roles, scopes and job functions, so that access matches the mandate. | Grant. Occasional. | User, roles, scopes, job functions, office. | Save access. | 1 API keys. 2 SSO. |
| P5 | When I check the platform, I need readiness and job state, so that I catch failures early. | Intervene. Daily. | Readiness gates as one line; failed jobs (count, newest). | Open the failed job. | 1 Governance. 2 Quote freshness. |
| P6 | When an auditor asks, I need the audit trail for a period, so that I can export it. | None. Occasional. | Audit rows filtered by actor, action, period. | Export. | — |
| P7 | When notifications are set up, I need each channel's categories and last delivery, so that alerts reach people. | Routing. Occasional. | Channel, categories, minimum severity, last delivery state. | Save, test. | — |

## 3. Map of jobs to the current product

Verdicts: **Keep**, **Slim** (what leaves the default view), **Merge**, **Move** (Admin or Inspector), **Remove**. "Fold" means behind a one-line disclosure, as `UI_INFORMATION_AUDIT.md` already does.

### 3.1 Shell

| Element (file) | Jobs · roles | Verdict | Reason and change |
|---|---|---|---|
| Top bar, modes, account menu (`WorkspaceTopBar.tsx`, `HeaderPreferencesMenu.tsx`) | All | Keep | Already priority-driven (`ADAPTIVE_CLIENT.md`). |
| Answer bar and command palette (`AnswerBar.tsx`, `CommandPalette.tsx`) | T2, T5, look-ups for all | Keep | It is the sanctioned route to anything folded or moved. |
| Alert centre (`AlertCenter.tsx`) | T1, T3, K1, K2, H3 | Slim | Replace the category enum with a translated word; filter by the role audience of section 5; closed alerts counted, not listed. |
| Breaking ticker (`BreakingTicker.tsx`, `ShellTicker.tsx`, `tickerItems.ts`) | T3, K2, M2, H3 | Rebuild as the situational strip | Section 5. |
| Data-status chip (`TopBarStatus.tsx`) | Trust check for all | Keep; absorbs more | It becomes the only place a commercial user sees data health. |
| Endpoint-failure banner (`AppShell.tsx`) | P-jobs | Move | For commercial users, one word on the status chip ("Some data unavailable") with the detail in its panel. The banner stays for ADMIN and OPERATOR. |
| Inspector (`InspectorPanel.tsx`) | Provenance on demand | Keep; absorbs more | Destination for ids, sources, exact times, method. |
| Copilot (`CopilotPanel.tsx`, hosted by the palette) | A2, look-ups | Keep | Not a page. |
| Desk brief dialog (`DeskBriefDialog.tsx`) | T1, T6, A1, H4 | Keep | Core phone job (read a brief). |
| Report a problem (`ReportProblemDialog.tsx`) | All → P3 | Keep | In the account menu on phone. |
| Trading context controls (`TradingContextControls.tsx`) | T-jobs | Keep | One chip. |
| Sign-in, restricted surface, shortcuts dialog | — | Keep | — |

### 3.2 Desk

| Element | Jobs · roles | Verdict | Reason and change |
|---|---|---|---|
| **Today** (`TodayScreen.tsx`, `GET /api/desk/today`) | T1, T6, A1, H1, K1 | Keep; make it role-composed | It is the only one-read, server-assembled page; the row order and set should follow the role (section 4). |
| Today · key figures row | T1, H1 | Keep | — |
| Today · what changed (alerts, outages) | T1, T3 | Slim | At most 3 each, role-filtered; "n more" links. No data-source alerts for commercial roles. |
| Today · our book vs market | T1, T6, H1 | Keep | Hidden without `portfolio.read`. |
| Today · fundamentals (storage chart, `NweBalancePanel`, `GasForPowerPanel`) | A1; secondary for T1 | Slim for trader | Trader: two figures (storage vs last year, supply call); charts fold. Analyst: open and first. |
| `TodayFreshness` | Trust | Slim | One word; the list on demand (already a popover). |
| Market context strip (`MarketContextStrip.tsx`, `ProjectionContextStrip.tsx`) | None directly | Move to the status chip and Inspector | Slice freshness is plumbing. Keep one coloured word on the page only when a slice the page shows is degraded. |
| Source-approval notice (`PublicSourceApprovals.tsx` → `SourceApprovalNotice`) | P2 | Move to Admin | A trader cannot approve. For commercial users the affected panel's empty state says "Waiting for administrator approval of <source>". |
| **Prices** · hub board and ladder (`MarketTerminal.tsx`, `MarketLadder.tsx`) | T2, T7 | Keep | The core screen. |
| Prices · intraday decision feed (`IntradayDecisionFeed.tsx`) | T2 | Keep | Already one line when empty. |
| Prices · quotes by source, `ReferenceIndexEvidence.tsx` | Evidence | Move to Inspector | Reached from a price's "Source" link; no longer a fold on the board. |
| Prices · `PriceCharts.tsx` | T2, T7 | Keep | Desktop beside or under the board; folded on phone. |
| Prices · `TraderDeskPanel.tsx` (product strip, converter, storage trajectory) | Look-ups | Slim | The converter duplicates the answer bar (rule 12): remove it here. Product strip folds. Storage trajectory moves to Today fundamentals (one number, one place). |
| **Network** · map (`GasNetworkMap.tsx`, `MapFinder.tsx`) | T3, M6, O4 | Keep | — |
| Network · panel tabs Outages / Capacity / Flows / Our book (`NetworkInfoPanel.tsx`, `MapBookPanel.tsx`, `MapDetailPanel.tsx`) | T3, T7, M6 | Keep | The right shape already. |
| Network · operating board (`CapacityWorkspace.tsx`) | T7 | Slim | Board only. `CapacityBoardStateNotice` becomes a one-line empty state; retry stays as one button. |
| Network · `NativeCapacityContextPanel.tsx` (query by ENTSOG point id) | A-research at most | Move to Research → Data | An expert query by identifier. |
| Network · `CapacityContractBook.tsx` | T7, O6 | Merge into Deals → Routes | Booked capacity belongs with route cost. |
| Network · `ReferenceNetworkCatalogue.tsx` | None daily | Move to Admin → Connectors (Infrastructure) | A register, not a desk reading. |
| Network · `ResourcePoolPathOverlay.tsx`, decision rail, `CommercialWarningList` | O4 | Slim | Shown only when a pool result exists for the current context. |
| Network · replay bar | Look-back | Keep, folded under History | "History is not an action". |

### 3.3 Deals

| Element | Jobs · roles | Verdict | Reason and change |
|---|---|---|---|
| Evaluate · `ScenarioWorkspace.tsx` | O2, O4, T7 | Keep | The work itself. |
| Evaluate · `DayBoardPanel.tsx` (drawn on every decision task) | M2, O5 | Slim | One line (next deadline) on Evaluate and Optimise; the full board only on Review and Nominations. |
| Evaluate · `DeskReplayPanel.tsx` | T3 follow-up, M6 | Slim | Folded; opened from an outage ("Replay response"). The input fingerprint goes to the Inspector. |
| Evaluate · `DecisionActionStatus.tsx` | Feedback | Slim | State word and reason; the correlation id under "Details". |
| Optimise · `OptimizeWorkspace` in `DecisionWorkspace.tsx` | O4 | Keep; optimise as a view of Evaluate | Evaluate and Optimise are two steps of one job. Recommend one task "Evaluate" with a Scenario / Optimise switch (the deep link `task=optimize` is kept). |
| Routes · `RouteCostWhatIfPanel.tsx` | T7, O6 | Keep | — |
| Routes · `CapacityBillingPanel.tsx` | O6 occasional | Keep folded | Already folded. |
| Routes · `LngCargoBidPanel.tsx` | O1 | Keep; first for an originator | — |
| Routes · `TariffPublicationsPanel.tsx` | F5, T7 | Slim | Only overdue or changed rows by default; "all publications" folds. |
| Contracts · `ContractWorkbench.tsx`, `ContractChainStrip.tsx`, `ContractPaymentTerms.tsx`, `ContractLifecycleControls.tsx` | O3, F4, C5 | Slim | Required fields first; optional groups folded; the read-only summary is the default for roles without `portfolio.write`. |
| Contracts · `FinancingRateHelper.tsx` | O2, F1 | Keep folded | — |
| Contracts · `LngEconomicsPanel.tsx` (1,189 lines, a text-in, text-out sandbox) | O1 research | Move to Research | It is a research sandbox (`/api/research/lng-economics-only`), not contract entry. |
| Review · `DecisionCasePanel.tsx`, `DecisionPackPanel.tsx` | K3, H2, O5, C1 | Keep | Phone-capable (approve). |
| Review · `ReviewContextStrip.tsx` | Trust | Slim | One evidence-state word on the case; slices in the Inspector. |
| Review · `ReviewWorkspace.tsx` (already folded "supporting tools") | K3 depth | Keep folded | — |

### 3.4 Book

| Element | Jobs · roles | Verdict | Reason and change |
|---|---|---|---|
| Position · `PositionLadderPanel.tsx` | T5, K6, H1 | Keep | — |
| Position · `PortfolioOverview` (scenario strip, resource register, warnings) | O4 residue | Slim | The scenario strip and register belong to Deals; here keep warnings as one line with a link. |
| Position · `PortfolioContextStrip.tsx`, scope fold | Trust | Move | As the market strip. |
| Limits · `RiskLimitsPanel.tsx` | T5, K1, K2, K5, F3 | Keep | Maintenance controls only with the permission (`canMaintainRisk`), and behind "Edit". |
| Limits · `DealHedgeApprovalsPanel.tsx` | K4 | Keep; folded for non-risk roles | — |
| Limits · `TradingBooksPanel.tsx` | M4 | Slim | Shown open for operations; folded for others. "Add a book" is already folded. |
| Limits · `MarketPositioningWorkspace.tsx` (screen-order observations, P&L snapshots) | T6, F2, K6 | Slim | P&L snapshots stay. Screen-order observations fold (recorded observations are history). |
| Delivery · `DeliveryPerformancePanel.tsx` | M1, M5 | Keep | First for operations. |
| Delivery · `DailyBalancePanel.tsx` | T4 | Keep | First for the trader. |
| Delivery · `SellDownPanel.tsx` | T4 | Keep; folded until a residual exists | A form. |
| Nominations · `NominationWindowPanel.tsx` | M2 | Keep | The task needs `scenario.create`, yet the windows read is READ. Show the deadlines read-only on Delivery for roles without it. |
| Storage · `StorageDispatchPanel.tsx` | M3 | Merge into one "Planning" task with Nominations | Both are planning views of the same optimisation run; a switch inside the task (links `task=nomination` and `task=dispatch` kept). |

### 3.5 Research

| Element | Jobs · roles | Verdict | Reason and change |
|---|---|---|---|
| Strategies · Spread (`SpreadLabWorkspace.tsx`) | A3, T7 | Keep; the default task | — |
| Strategies · Design, Backtest, Compare (`StrategyDesignWorkspace.tsx`, `StrategyBacktestWorkspace.tsx`, `StrategyCompareWorkspace.tsx`) | A3 | Keep | Desktop only (section 6). |
| Strategies · Shadow (`StrategyShadowShell.tsx`, `StrategyShadowRunDetail.tsx`, `StrategyShadowRunSections.tsx`) | A6 | Slim | Default: status, drift, alerts. Engine, dataset and commit go to the Inspector. |
| Strategies · navigator, identity header, sharing | A3 | Keep | — |
| Reports (`ReportsWorkspace.tsx`) | A4, H4, T1 | Keep | The plan view is already folded. Reading is a phone job. |
| Data · datasets, features, targets (`ResearchDataWorkspace.tsx`) | A5 | Keep | Desktop only. |
| Data · products (`DataProductCatalogue.tsx`, `ResearchCapabilityCatalogue.tsx`) | None daily | Merge into the Manual as reference; the capability catalogue to Admin | Declarations, not work. |
| Assistant (`AgentsWorkspace.tsx`: capabilities, research, runs; `AgentArtifactChain.tsx`, `AgentReviewGate.tsx`) | A2 depth | Slim | Default view: research run and results. The capabilities catalogue moves to Admin. Replay sits behind a run. |

### 3.6 Utilities and Admin

| Element | Jobs · roles | Verdict | Reason and change |
|---|---|---|---|
| Settings · personal preferences (`PreferencesPanels.tsx`) | All | Keep | Adds the strip thresholds and the time-zone choice. |
| Settings · About/release, backend API, service access, backend boundary (`SettingsCenter.tsx`) | P-jobs | Move to Admin → Runtime | Developer and deployment facts. Personal Settings keeps the version as one line. The workstation section stays for the Tauri client only. |
| Settings · `NotificationChannelsPanel.tsx` | P7 | Move to Admin | Administrators only already. |
| Manual (`ManualWorkspace.tsx`), Glossary (`GlossaryWiki.tsx`) | Look-ups | Keep | The glossary is also in the answer bar. |
| Connectors (`SourceCenter.tsx`: attention, catalog, access, infrastructure; `PublicSourceApprovals`, `WeatherForecastEvidence.tsx`) | P1, P2 | Keep | Admin is the right home; receives the items moved above. |
| Runtime (`RuntimeWorkspace.tsx`: delivery, readiness, governance, support; `JobTimeline.tsx`, `DiagnosticsPanel.tsx`, `SupportInboxPanel.tsx`) | P3, P5 | Keep | — |
| Access (`AccessCenter.tsx`: users, API keys, catalogue, audit, SSO; `LicenceRegisterPanel.tsx`) | P4, P6, C3 | Keep | — |

### 3.7 Jobs no current screen serves well

| Gap | Job | Proposal (no new page) |
|---|---|---|
| G1 | H1 desk head summary | A role composition of Today: P&L, position, limits, decisions waiting. Needs a "decisions waiting" figure in the Today read. |
| G2 | K1 risk morning | Today composed as limits first; today it shows only the tightest limit (`_tightest_limit` in `application/desk_today.py`). |
| G3 | T3 "price move beyond a range" | No such alert type exists (`monitoring_service.py` raises opportunity, ingestion, outage, credit, mandate). Needs a threshold alert; backend work. |
| G4 | M2 deadlines for a read-only role | Read-only deadline line on Book → Delivery from `/api/optimization/nomination-windows` (READ). |
| G5 | M1 delivery shortfall as an alert | Shortfalls are a table only; no alert category. Backend work for a strip item. |
| G6 | K5, K6 limit history | No utilisation history is evident. Assumption to verify; backend work. |
| G7 | F1 cash calendar | Payment terms exist per contract only; no cross-contract view. A "Cash" view inside Book → Position. Backend read needed. |
| G8 | F2, M5 month-end reconciliation | A month filter and export on Delivery performance. |
| G9 | C1, C2 audit for compliance | Decision D5. |
| G10 | H5 access review by the desk head | A quarterly access report as a stored report (Research → Reports catalogue section). |
| G11 | Acknowledge on phone for REVIEWER | Decision D5. |
| G12 | T1 "my hubs" | The strip and Today need the user's focus hubs. Derive from book positions plus the context hub; a personal preference overrides. |

## 4. Target information architecture

### 4.1 Mechanism: one product, role-tuned defaults

1. **Authority stays where it is.** `modeTaskVisible` and the backend decide what a user may open. Nothing below adds or removes a permission.
2. **A composition registry** (new, client side, `app/experience/roleComposition.ts`) maps the first declared job function to:
   - the landing (mirrors `ASSIGNMENT_HOME` on the server);
   - the ordered shortlist of at most four tasks;
   - per page, each panel's default state: `open`, `folded` or `hidden`;
   - the Today row order;
   - the strip audience (section 5).
3. **Visibility is the registry AND the permission.** A panel the role may not read is absent whatever the registry says. A registry entry for a task the user cannot open is dropped. This must be a unit test, like `WORK_MODE_GRANTS_AUTHORITY`.
4. **Nothing becomes unreachable.** Tasks outside the shortlist sit under "More" in the task row and in the palette (decision D6). A folded panel opens with one click, and the choice is remembered per user (personal preference tier, already server-stored through `app/preferences/remotePreferences.ts`).
5. **Several job functions:** the first declared one sets the defaults (current rule). The account menu offers "View as: Trader / Risk" among the user's own declared functions. This is presentation only.
6. **No job function declared:** defaults derive from permissions (ANALYST → trader composition; REVIEWER → reviewer composition; VIEWER → read-only desk head composition).

### 4.2 Per role: landing and at most four places

| Role | Landing | Place 2 | Place 3 | Place 4 | Under "More" |
|---|---|---|---|---|---|
| Trader | Desk → Today (D1) | Desk → Prices | Book → Delivery (balance) | Book → Limits | Network, Routes, Position, Research |
| Originator | Deals → Evaluate | Deals → Routes (cargo bid first) | Deals → Contracts | Deals → Review (own cases) | Desk, Book |
| Analyst | Desk → Today (fundamentals first) | Research → Strategies | Research → Reports | Desk → Network | Data, Assistant, Prices |
| Risk manager | Book → Limits | Deals → Review | Book → Position | Desk → Today (limits first) | Delivery, Reports |
| Operations | Book → Delivery | Book → Planning (nominations, storage) | Desk → Network (outages) | Deals → Contracts (read) | Limits (books), Today |
| Finance | Book → Position (cash view, G7) | Book → Delivery (month view) | Deals → Contracts (read) | Book → Limits (credit, read) | Routes (tariffs) |
| Compliance | Deals → Review (decided cases) | Deals → Contracts (read, retired) | Research → Reports | — | Limits |
| Desk head | Desk → Today (summary) | Deals → Review | Book → Limits | Book → Position | Reports, Prices |
| Platform admin, data ops | Admin → Connectors (attention) | Admin → Runtime | Admin → Access | Settings | — |

Net task changes within the four modes (17 → 15, deep links kept through the existing redirect table):
- Evaluate and Optimise become one task with a switch.
- Nominations and Storage become one "Planning" task with a switch.

### 4.3 What the shell provides everywhere

| Region | Content | Rule |
|---|---|---|
| Top bar | Modes, answer bar, context chip, alerts bell, status chip, account | Unchanged. |
| Situational strip | Section 5 | At most one line; hidden when nothing qualifies. |
| Answer bar | Calculator, look-ups, ask, navigation | The route to anything folded. |
| Alerts bell | The role's open alerts; closed ones counted | Same audience filter as the strip. |
| Status chip | One word on data health; detail in its panel | The only data-health element a commercial user sees by default. |
| Inspector | Source, exact time, method, ids for the selected object | Destination of everything moved "on demand". |

### 4.4 What the administrator sees separately

Admin is not a mode and is not offered to identities without an administration capability (`compositionSeesAdministration`).

| Admin area | Contains | Receives from this redesign |
|---|---|---|
| Connectors | Attention, catalogue, credentials, infrastructure, public-source approvals | Source-approval notice; reference-network catalogue; data-source alerts. |
| Runtime | Delivery, readiness, governance, support inbox, jobs, diagnostics | About/release; backend API and boundary; endpoint-failure detail; agent capability catalogue; research capability catalogue. |
| Access | Users, API keys, role catalogue, audit, SSO, licences | Notification channels. |

## 5. The situational strip

Replaces the "Breaking" bar. Built on `tickerItems.ts`, `ShellTicker.tsx` and `BreakingTicker.tsx`.

### 5.1 States

| State | When | Appearance |
|---|---|---|
| Hidden | Nothing qualifies as urgent and the role has no quiet content | Zero height. The bell carries the count. |
| Quiet | No urgent item; the role has one useful standing fact | One static line in muted text, no colour, no motion. |
| Urgent | At least one qualifying item | One static line: severity mark, the top item, "+n more". Coloured edge. No marquee (decision D3). |
| Expanded | The user opens it | A list of at most 7 items over the page (popover on desktop, sheet on phone), each with its link and actions. Escape closes. |

A new urgent item is announced once to screen readers and flashes once (existing behaviour). A standing state never re-announces.

### 5.2 What qualifies, per role

Thresholds are personal preferences with organisation defaults (existing three-tier settings in `domain/settings/preferences.py`). The numbers below are proposed defaults and are assumptions for the owner to confirm.

| Role | Urgent | Quiet line |
|---|---|---|
| Trader | Unplanned outage ≥ 50 GWh/d, or ≥ 50 % of the asset (existing rule), in a zone where the user has position or at a focus hub. Breach of the user's own mandate or of a line they trade against. DA or front-month move ≥ 5 % vs prior close at a focus hub (needs G3). | Booked trades today from the ETRM import, read-only (decision D2); otherwise the next nomination window. |
| Originator | A decision on the user's case (accepted, rejected, reopened). Outage at a terminal or route in an open evaluation. | Cases awaiting review (count, nearest due). |
| Analyst | Fundamentals surprise: storage daily change, supply call, or LNG send-out outside a set band vs the 7-day average (needs a rule; today only outages qualify). Large unplanned outage anywhere in NW Europe. Shadow-strategy alert. | Next scheduled data arrival (assumption: derivable from the source schedule). |
| Risk manager | Any limit breach. A credit event (line exceeded or new watch). A decision case past its due time. | Counts: breach, watch, cases waiting. |
| Operations | Delivery shortfall above tolerance (needs G5). Outage at a delivery point of an active contract. Nomination window closing within 60 minutes, as information only. | The next window and its time to close. |
| Finance | None by default. | None (hidden). |
| Compliance | None by default. | Decided cases this week (count). |
| Desk head | Any breach. Unplanned outage touching the book. A case waiting for them past half its time. | Day P&L change and the breach count. |
| Admin, data ops | A source failing or held back. Failed jobs. A new problem report. | Sources needing attention (count). |

Data-source and ingestion alerts appear only for the last row.

### 5.3 Ranking, dismissal, links, audit

| Aspect | Rule |
|---|---|
| Ranking | 1 Severity (critical before warning). 2 Touches the user's own book or mandate. 3 Size relative to threshold. 4 Newest. At most 7 items; the rest are counted. |
| Breaking vs standing | An item is urgent for `BREAKING_WINDOW_MS` (6 h, existing) after it becomes true or materially changes. After that it is standing: listed in the bell, not on the strip. |
| Dismiss | "Hide" removes the item from this user's strip only. Stored per user. It does not change the alert. It reappears if the item materially changes (size or status). |
| Acknowledge | For alerts, the existing governed write (`/api/monitoring/alerts/{alert_id}/acknowledge`), which records who and when. Offered only with the permission (D5). |
| Link | Each item opens the object where the job continues: an outage on Network with the outage selected; a limit on Book → Limits; a case on Deals → Review; a window on Book → Planning. Never the alert centre as a detour. |
| Why and Report | The existing `WhyButton` and `ReportLink` in the expanded list. |
| Audit | Acknowledgement is already recorded server side. Hide is a preference, not an audited act. If the firm wants "seen by" evidence for REMIT events (job C4), record first display per user. That is backend work and optional. |

### 5.4 Data each item needs

| Field | Purpose |
|---|---|
| `id`, `kind` (outage, limit, credit, price move, delivery, deadline, decision, fundamentals, booked trade, source) | Identity and icon |
| `severity`, `urgentUntil` | State |
| `headline` (translated sentence built from fields, never free text from a feed) | Display |
| `magnitude`, `unit`, `comparison` (for example "310 GWh/d of 420") | The number that makes it meaningful |
| `affects` (hub, zone, book ids, contract ids) | Role and book matching |
| `occurredAt`, `source` (name; evidence reference kept for the Inspector) | Relative time on the strip; exact time and source on demand |
| `target` (page, task, object parameter) | The link |
| `audience` (which rule matched) | Tests and the "why am I seeing this" line |
| `simulated` | The `sim` mark, as on the board |

### 5.5 What must never appear

- Any control that places, amends or cancels an order, nominates or settles. Booked trades are a read-only report of the ETRM import.
- Anything without a named source. No model-written headline; the AI may explain an item ("Why"), never originate one.
- Market news text, unless it comes from a feed the customer is licensed for and has connected. None exists today.
- A simulated figure without its mark.
- Pipeline or platform state for commercial roles.
- Book-level figures for a user who cannot see every book behind them (existing rule in `application/alert_scope.py`).

## 6. Device strategy

Width classes are the existing ones (`compact` < 720 px, `medium` 720–1199, `wide` ≥ 1200; `app/shell/useShellLayout.ts`). Role decides what comes first; the device decides how much.

| Device | Purpose | Composition |
|---|---|---|
| Desktop (wide) | The full working day | Multi-panel: main board, side panel, Inspector as a side pane. All tasks. |
| Tablet (medium) | Meetings, review, reading | Two panes where they fit; Inspector as a sheet. Forms usable; set-up of optimiser and strategy design allowed with a fine pointer only. |
| Phone (compact) | Monitor, be alerted, look up a number, read, approve or acknowledge, ask | One column; one landing view of at most five elements; everything else through the answer bar or the menu. |

### 6.1 Phone jobs

| Makes sense on a phone | Does not: read-only summary plus "Continue on desktop" |
|---|---|
| Today for the role; the strip; alerts; acknowledge | Contract entry and editing (`ContractWorkbench`) |
| Look up a price, position, limit or outage (answer bar) | Scenario and optimiser set-up (`ScenarioWorkspace`, optimise) |
| Read the brief or a stored report | Strategy design, backtest, compare |
| Record a decision on a case | Dataset specification and build |
| Outage list and detail (the map becomes optional) | Route cost what-if, capacity billing, LNG economics sandbox |
| Ask a question | Admin: credentials, access changes, SSO |

"Continue on desktop" shows the object's summary (name, state, key result) and a share or copy-link control. Continuity already works through URLs.

### 6.2 Phone landing per role (at most five elements)

| Role | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Trader | Strip | Home-hub prices (DA, front month, change) | Net position today and front month | Tightest limit | What changed (3 items) |
| Originator | Strip | My cases (state, due) | Latest evaluation result | Home-hub forward mark | — |
| Analyst | Strip | Storage vs last year | Supply call | Brief or report (read) | What changed |
| Risk manager | Strip | Breaches (list) | Cases waiting | Watch count | — |
| Operations | Strip | Next windows | Shortfalls today | Outages at delivery points | — |
| Finance | Next payments (when G7 exists) | P&L snapshot | — | — | — |
| Compliance | Decided cases (recent) | Reports | — | — | — |
| Desk head | Strip | Day P&L change | Breaches | Cases waiting | Net position |
| Admin, data ops | Strip | Sources needing attention | Failed jobs | Problem reports | — |

### 6.3 Hidden versus summarised on small screens

1. A table shows the identifying column and one value; the rest is the row's detail sheet (existing content rule 1).
2. A chart shows its headline number and a sparkline; the full chart opens on tap.
3. A panel that is `folded` on desktop for the role is `hidden` on the phone, reachable by the answer bar.
4. A form that is a desktop job is replaced by its read-only summary.
5. The map is not the default on a phone: the outage list is, with "Show on map".
6. No horizontal page scroll; numeric tables scroll inside their own box.

### 6.4 Timestamps

| Case | Default | On demand (hover, focus, tap → Inspector) |
|---|---|---|
| Age of a figure, under 24 h | Relative: "12 min ago" (existing `ageText` in `app/model/todayModel.ts`) | Exact time, user's zone, zone abbreviation |
| Older | Short day: "Mon 16 Nov" (existing `shortDay`) | Exact |
| Gas day | "GD 17 Nov" | Start and end in market time |
| Deadline | Time to go ("closes in 42 min") plus clock time in the user's zone | Market time zone |
| Event window (outage) | "until Thu 19 Nov" (existing `timeWindow`) | Exact start and end |
| Fresh figure | No time at all | Exact |
| Stale or degraded figure | The age shown and coloured | Exact |

The user's zone is the office zone (`OFFICE_TIME_ZONES` in `security/capabilities.py`), overridable as a personal preference. ISO strings and "UTC" never appear in default views of commercial pages. Admin pages may show exact times.

## 7. Information rules (testable)

| # | Rule | Check |
|---|---|---|
| I1 | Every number has its unit in the cell or the column header. | Browser: every `[data-figure]` has a non-empty `data-unit`. |
| I2 | As-of, source and method are on demand, not inline. A fresh figure shows no time. | Browser: on commercial pages no visible text matches an ISO date-time or `UTC` (regex `\d{4}-\d{2}-\d{2}T`). |
| I3 | No internal ids or raw enums in visible text. | Browser: no visible text matches a UUID, `[A-Z]+_[A-Z_]+`, or `[a-z]+_[a-z_]+` outside `code` in Admin. Allow-list for product names. |
| I4 | One primary action per view. | Browser: at most one `.button-primary` (or `data-primary-action`) visible per task. |
| I5 | An empty state is one line: why, and where to fix it. | Browser: every `[data-empty-state]` is at most 2 lines high and contains a reason; a link when a fix exists. |
| I6 | A simulated figure carries the mark; a simulated board carries the banner. | Existing hooks `data-state="simulated"`, `data-simulated-board`. |
| I7 | Freshness is one word on the status chip; a degraded figure is marked at the figure. | Browser: no `.projection-context` slice table in the default view of a commercial page. |
| I8 | Pipeline and platform state never appear on commercial pages for commercial roles. | Browser as `demo.trader`: no source-approval notice, no endpoint banner, no data-source item in the strip or bell. |
| I9 | One number, one place per page (`UX_REFERENCE.md` rule 1). | Review checklist; automated for storage fill and net position by `data-figure` key uniqueness. |
| I10 | Density per device. Proposed targets: phone landing ≤ 5 elements and ≤ 2 screen heights; desktop default view of a task ≤ 1.5 viewport heights at 1440×900; ≤ 7 open panels. | Browser: count `[data-panel][data-default="open"]`; measure `scrollHeight`. Extend `scripts/uat/geometry_budget.json`. |
| I11 | Role composition never widens access. | Unit: for every job function and every role, the composed tasks are a subset of `visibleModes(user)`. |
| I12 | Anything folded or moved is reachable in at most two actions (palette or disclosure). | Unit over the registry and palette commands. |
| I13 | The strip is hidden when nothing qualifies; at most one line otherwise; no motion. | Browser: `[data-shell-region="ticker"]` absent or ≤ one line high; no CSS animation. |
| I14 | Touch targets are 44 px on coarse pointers; nothing overlaps. | Existing sweep. |

## 8. Implementation plan

Shared conflict points that set the parallelism:
- `clients/web/src/i18n/en.json` and `zh.json`: every package adds keys. Use a per-package key prefix and append in one block; `scripts/uat/check_i18n_parity.py` runs in each package.
- `scripts/uat/browser_workflow_smoke.mjs`: only WP-01 and WP-19 edit it; other packages add checks through data hooks that WP-01 defines.
- `app/experience/roleComposition.ts`: created by WP-02; later packages only add entries for their own page keys.

| WP | Scope | Files | Depends on | Acceptance (automatable unless stated) |
|---|---|---|---|---|
| **WP-01** Information-rule gates | Add the hooks and checks I1–I5, I7, I10, I13 as warnings first, with per-page baselines. Add role sign-ins (`demo.trader`, `demo.risk`, `demo.manager`, `demo.ops`, `demo.admin`) and an 820×1180 viewport to the sweep. | `scripts/uat/browser_workflow_smoke.mjs`, `scripts/uat/geometry_budget.json`, `clients/web/tests/browserSmokeGates.test.ts` | — | The sweep reports rule counts per page and role without failing; baselines committed. |
| **WP-02** Role composition registry | The registry and resolver (section 4.1): landing, shortlist, panel defaults, Today row order, strip audience; fallbacks; "View as" among declared functions. | New `clients/web/src/app/experience/roleComposition.ts` and test; `app/experience/index.ts` | — | Unit tests for I11 and I12; every `FunctionalAssignment` has an entry; an unknown function falls back by permission. |
| **WP-03** Time and figure formatting | One module for relative, short and exact times in the user's zone; a `Figure` wrapper that carries `data-figure`, `data-unit` and the exact time in its title. Move `ageText`, `shortDay`, `timeWindow` there and re-export. | New `clients/web/src/app/format/time.ts`; `app/model/todayModel.ts`; `components/ui/KeyFigure.tsx` | — | Unit tests per row of section 6.4, including a zone change and DST. |
| **WP-04** Strip model | `SituationItem`, qualification per audience, ranking, urgent window, hide list, link targets. Client side over existing reads (alerts, grouped outages, Today limits, nomination windows). Data-source alerts only for the admin audience. | `app/model/tickerItems.ts` (becomes the situation model), `clients/web/tests/breakingTicker.test.ts` | WP-02 | Unit: each row of 5.2 that needs no backend work; ranking; an unsourced item is rejected; book-scoped items are dropped without the book. |
| **WP-05** Strip component | States hidden, quiet, urgent, expanded; no marquee; popover or sheet; hide, acknowledge, Why, Report; announce once. | `components/BreakingTicker.tsx`, `components/ShellTicker.tsx`, strip CSS, `app/shell/AppShell.tsx` (mount only) | WP-04 | I13. As `demo.trader` with no qualifying item the region is absent. Keyboard: open, move, Escape. axe clean. 390 px: one line. |
| **WP-06** Strip thresholds as preferences | Preference keys for the thresholds and focus hubs; organisation defaults; the Settings controls. | `src/eurogas_nexus/domain/settings/preferences.py`, `components/PreferencesPanels.tsx`, `app/preferences/*` | WP-04 | Backend unit: unknown keys refused. UI: changing a threshold changes which fixture outage qualifies. |
| **WP-07** Today by role | Row order and set from the registry; trader fundamentals slimmed; "what changed" capped and role-filtered; desk-head and risk compositions with what the read already returns. Server home for the trader per D1. | `components/TodayScreen.tsx`, `components/today.css`, `app/hooks/useDeskToday.ts`, `security/capabilities.py` (`ASSIGNMENT_HOME`) | WP-02, WP-03 | Per demo identity: the first row matches section 4.2; `demo.finance` sees no absent-permission rows; I10 at 390 px. |
| **WP-08** Plumbing off the desk | Context strips to one conditional word; source-approval notice to Admin with a role-aware empty state; endpoint banner limited to admin roles; status chip absorbs the rest. | `components/MarketCockpit.tsx`, `MarketContextStrip.tsx`, `PortfolioContextStrip.tsx`, `ReviewContextStrip.tsx`, `ProjectionContextStrip.tsx`, `PublicSourceApprovals.tsx`, `TopBarStatus.tsx`, `app/shell/AppShell.tsx` (banner only) | — | I7 and I8 as `demo.trader`. As `demo.admin` the notice and banner still appear. A degraded slice still colours a word on the page. |
| **WP-09** Prices slimming | Evidence folds to the Inspector; converter removed; product strip folded; storage trajectory to Today. | `components/MarketTerminal.tsx`, `TraderDeskPanel.tsx`, `ReferenceIndexEvidence.tsx`, `app/model/inspectorDetail.ts` | WP-03 | The board, charts and feed are the only open panels; "Source" on a price opens the Inspector with the per-source quotes; existing `data-market-board` tests pass. |
| **WP-10** Network slimming | Reference catalogue and native point query leave; capacity book to Routes; pool overlay only with a result; board notice to one line. | `components/NetworkWorkspace.tsx`, `NetworkInfoPanel.tsx`, `CapacityWorkspace.tsx`; mounts added in `SourceCenter.tsx` and `ResearchDataWorkspace.tsx` | — | The Network default view is the map plus one panel; moved components render at their new home; `nativeCapacityInteraction.mjs` updated to the new address. |
| **WP-11** Book: Position and Limits | Overview residue to a link line; maintenance behind "Edit"; role defaults for hedge bands, books and screen-order observations; alert-centre category words. | `components/PortfolioWorkspace.tsx` (overview and exposure branches), `RiskLimitsPanel.tsx`, `DealHedgeApprovalsPanel.tsx`, `TradingBooksPanel.tsx`, `MarketPositioningWorkspace.tsx`, `AlertCenter.tsx` | WP-02 | As `demo.trader`: the ladder and limits are open and the rest folded. As `demo.risk`: limits and bands open. I4. |
| **WP-12** Book: Delivery and Planning | Role order on Delivery; sell-down folded until a residual; read-only deadline line (G4); month filter and export (G8); Nominations and Storage as one Planning task with a switch and redirects. | `components/PortfolioWorkspace.tsx` (delivery branch), `DeliveryPerformancePanel.tsx`, `DailyBalancePanel.tsx`, `SellDownPanel.tsx`, `decision/NominationWindowPanel.tsx`, `decision/StorageDispatchPanel.tsx`, `app/navigation/modeNavigation.ts` | WP-02 | Old links `task=nomination` and `task=dispatch` land on the right switch state. A VIEWER sees deadlines on Delivery. |
| **WP-13** Deals: Evaluate, Routes, Review | Evaluate and Optimise as one task with a switch; day board to one line off Review; replay folded; action status slimmed; tariff panel to exceptions; capacity book received; review strip to one word. | `components/DecisionWorkspace.tsx`, `ScenarioWorkspace.tsx`, `decision/DayBoardPanel.tsx`, `decision/DeskReplayPanel.tsx`, `decision/DecisionActionStatus.tsx`, `PortfolioWorkspace.tsx` (routes branch), `TariffPublicationsPanel.tsx`, `app/navigation/modeNavigation.ts` | WP-12 merges first (both edit `modeNavigation.ts` and `PortfolioWorkspace.tsx`) | `task=optimize` still opens the optimiser. Review on 390 px: a decision can be recorded. I4. |
| **WP-14** Deals: Contracts | Required fields first; optional groups folded; read-only summary for roles without write; LNG sandbox moved to Research. | `components/ContractWorkbench.tsx`, `ContractChainStrip.tsx`, `LngEconomicsPanel.tsx` (mount only), `ResearchDataWorkspace.tsx` or `StrategyLabWorkspace.tsx` (new mount) | — | `demo.finance` sees no editable field. The contract save flow tests pass. Form height at 1440 falls below the WP-01 baseline. |
| **WP-15** Research slimming | Shadow default view; catalogues out of Data; Assistant default to research; capability catalogues to Admin. | `components/strategy/StrategyShadow*.tsx`, `ResearchDataWorkspace.tsx`, `AgentsWorkspace.tsx`, `RuntimeWorkspace.tsx` (new mounts), `ManualWorkspace.tsx` | WP-10 and WP-14 merge first (shared `ResearchDataWorkspace.tsx`) | The Data default view shows datasets only. Engine and commit are absent from the shadow default view and present in the Inspector. |
| **WP-16** Settings and Admin split | Release, backend and boundary facts and notification channels to Admin; personal Settings keeps preferences and one version line. | `components/SettingsCenter.tsx`, `RuntimeWorkspace.tsx`, `AccessCenter.tsx`, `NotificationChannelsPanel.tsx` | WP-15 merges first (shared `RuntimeWorkspace.tsx`) | As `demo.trader`, Settings shows preferences only. `controlPlaneSeparation.test.ts` passes. |
| **WP-17** Task-row shortlist | Shortlist first, "More" for the rest, palette unchanged; landing from the registry when no URL or preference. | `app/navigation/useModeHeader.ts`, `components/ui/WorkspaceTabs.tsx`, `app/hooks/useWorkspaceNavigation.ts` | WP-02; D6 | Per demo identity the task row shows at most four tasks plus "More"; every hidden task opens from "More" and the palette; URLs unchanged. |
| **WP-18** Phone views | Phone landing per role (6.2); the "Continue on desktop" wrapper for the jobs in 6.1; outage list before map; chart-to-sparkline rule. | New `components/ui/DesktopTaskNotice.tsx`; `TodayScreen.tsx` (compact branch), `NetworkWorkspace.tsx` (compact branch); wrappers in `ContractWorkbench.tsx`, `ScenarioWorkspace.tsx`, `strategy/StrategyDesignWorkspace.tsx`, `ResearchDataWorkspace.tsx` | WP-07, WP-10, WP-14, WP-15 | 390×844 per identity: at most 5 landing elements; no horizontal scroll; desktop jobs show the summary and a link; a decision and an acknowledgement can be completed. |
| **WP-19** Gates on, documents | Turn the WP-01 warnings into failures at the new baselines. Update `UX_REFERENCE.md` (rule 8 per D1), `ROLES_AND_RESPONSIBILITIES.md`, `ADAPTIVE_CLIENT.md`, the role manuals under `docs/user/manual/` and their screenshots. | Those files; `scripts/uat/browser_workflow_smoke.mjs` | All | The sweep is green in EN and ZH, light and dark, at four viewports, for five identities. |
| **WP-20** Backend additions (each separate, optional for the first release) | (a) Price-move alert (G3). (b) Delivery-shortfall alert (G5). (c) Today figures: decisions waiting, top limits (G1, G2). (d) Cash calendar read (G7). (e) Job functions `ORIGINATOR` and `OPERATIONS` (D4). (f) Acknowledge and audit permissions (D5). | `application/monitoring_service.py`, `application/desk_today.py`, `security/capabilities.py`, `security/authorization.py`, `security/permissions.py` | Owner decisions; (f) needs a security review | Per item: deterministic unit tests, a role access test, and the strip or Today row that consumes it. |

### Order and parallelism

| Wave | Packages | Run in parallel? |
|---|---|---|
| 1 | WP-01, WP-02, WP-03, WP-08 | Yes, no shared files. |
| 2 | WP-04 → WP-05 → WP-06 (one implementer, serial); WP-07; WP-09; WP-10; WP-14 | Yes across the five tracks. |
| 3 | WP-11; WP-12 → WP-13 (serial, shared files); WP-15 → WP-16 (serial) | Yes across the three tracks. |
| 4 | WP-17; WP-18 | Serial with each other only where `TodayScreen.tsx` is touched; otherwise parallel. |
| 5 | WP-19 | Alone. |
| Any time after wave 1 | WP-20 items | Parallel with client work; each lands behind its consumer. |

`PortfolioWorkspace.tsx` is edited by WP-11, WP-12 and WP-13 in separate task branches of one file. Either run them serially or first split the file into one component per task (a small preparatory change) so they can run in parallel.

### Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| D1 | Trader landing: Today or Prices. `UX_REFERENCE.md` rule 8 and `ASSIGNMENT_HOME` say Prices; the navigation puts Today first. | Today, with home-hub prices as its first row, on every device. Amend rule 8 to "prices are the first thing on the landing view". Prices stays one click away, and a saved personal view still wins. |
| D2 | "Trade execution" on the strip, given rule 8 of `AGENTS.md` (no execution). | Read-only "booked today" from the ETRM import, as the trader's quiet line. No entry control anywhere. I did not verify that imported trades carry a booking time; if they do not, show a count only. |
| D3 | Marquee or static strip. | Static: one item plus a count, expanding to a list. A scrolling bar cannot be read on a phone and never rests. |
| D4 | Add job functions for originator and operations; settle finance's role. | Add both as composition-only assignments. Finance stays VIEWER (reads only) and the roles document is corrected. |
| D5 | Let REVIEWER acknowledge alerts, and give compliance a read of the audit trail. | Yes to acknowledgement for limit alerts (risk owns them). For audit, a scoped read of decision and contract events rather than the whole log. Both change authority, so they need a security review and are outside the presentation work. |
| D6 | Tasks outside a role's shortlist: under "More", or removed from the row entirely. | "More". The owner's aim is a calmer default, and hiding permitted tasks would make persona behave like authority. |