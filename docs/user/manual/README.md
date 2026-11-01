# User manual

Step-by-step instructions for each role, with screenshots taken by signing in as that
role and doing the work in the real client: typing contracts and limits, retiring and
reinstating, reporting a problem and resolving it. The test data is fictitious (a UK and
a Dutch book, two pipeline supply contracts, a handful of screen and ETRM trades, ninety
days of deliveries); every figure on a screenshot is what the product calculated from it.

| Role | Manual | Short guide |
|---|---|---|
| Trader | [TRADER.md](TRADER.md) | [guides/TRADER.md](../../guides/TRADER.md) |
| Risk and middle office | [RISK.md](RISK.md) | [guides/RISK_AND_FINANCE.md](../../guides/RISK_AND_FINANCE.md) |
| IT desk (operator) | [IT_DESK.md](IT_DESK.md) | [guides/ADMIN_AND_OPERATIONS.md](../../guides/ADMIN_AND_OPERATIONS.md) |
| Administrator | [ADMIN.md](ADMIN.md) | [guides/ADMIN_AND_OPERATIONS.md](../../guides/ADMIN_AND_OPERATIONS.md) |

Roles and what each may change: [ROLES_AND_RESPONSIBILITIES.md](../../product/ROLES_AND_RESPONSIBILITIES.md).
The product supports decisions; it does not execute trades, enter orders, nominate or
settle. Every screen that could be read that way says so.

## Every workflow, by role

What each role does in a working week, where it is done, and where it is described. "Steps"
means the manual walks through it with screenshots; "Guide" means the short role guide
covers it.

### Trader

| When | Workflow | Where | Described |
|---|---|---|---|
| Morning | Check prices, freshness and alerts | Market → Curves & Spreads; top bar | Guide |
| Morning | Review the position ladder: net long/short per hub and month, hedge, marks, VaR | Portfolio → Exposure | [Steps](TRADER.md#4-monitor-the-book-position) |
| Morning | See where the mandate stands before trading | Portfolio → Exposure → Credit and mandates | [Steps](TRADER.md#4-monitor-the-book-position) |
| Every day | See each gas day's balance: supply, exchange and bilateral trades, the residual still to sell or buy, and the cash-out cost if left | Portfolio → Resources → Daily gas balance | [Steps](TRADER.md#5-balance-each-gas-day) |
| Day-ahead | Decide how much of tomorrow's supply to sell DA and how much to keep for WD | Portfolio → Resources → Tomorrow's sell-down | [Steps](TRADER.md#5-balance-each-gas-day) |
| Daily | Watch delivered against nominated volume per contract | Portfolio → Resources → Delivery against nominations | [Steps](TRADER.md#5-balance-each-gas-day) |
| New deal | Enter a supply contract by hand | Portfolio → Resources → New draft | [Steps](TRADER.md#1-enter-a-new-supply-contract) |
| New deal | Read a signed confirmation PDF into a draft and check each term | Portfolio → Resources → Import | [Steps](TRADER.md#2-read-a-confirmation-pdf-into-a-draft) |
| Change | Edit a stored contract (the edit token prevents overwriting a colleague's change) | Portfolio → Resources → Library → Inspect | Guide |
| End of deal | Retire a terminated contract with a reason; reinstate it if the termination is withdrawn | Portfolio → Resources → Library | [Steps](TRADER.md#3-retire-and-reinstate-a-contract) |
| Cargo | Price the most to bid DES for an LNG cargo at each terminal | Portfolio → Routes → LNG cargo bid | [Steps](TRADER.md#6-price-an-lng-cargo-bid) |
| Capacity | Cost a route with entry/exit tariffs; compare alternatives | Portfolio → Routes | Guide |
| Yearly | Track each TSO's indicative and final tariffs for the next gas year | Portfolio → Routes → Tariff publications | [Steps](TRADER.md#7-track-tso-tariff-publications) |
| Reporting | Export the ladder, credit and mandate tables to Excel, PDF or CSV | Export buttons on each table | [Steps](TRADER.md#4-monitor-the-book-position) |
| Research | Back-test a spread or benchmark strategy | Strategy Lab | Guide |
| Any time | Look up a term, its unit, formula and where it appears | System → Glossary | [Steps](TRADER.md#8-look-up-a-term) |
| Any time | Report a problem to the IT desk with diagnostics attached | Top bar "?" | [Steps](TRADER.md#9-report-a-problem) |

### Risk and middle office

| When | Workflow | Where | Described |
|---|---|---|---|
| Daily | Read counterparty exposure against limits: replacement, receivable, collateral, expiry | Portfolio → Exposure → Credit and mandates | [Steps](RISK.md#1-read-the-credit-and-mandate-board) |
| Daily | Read each trader's mandate use: size, tenor, hubs, hedge ratio against the band, instruments | same | [Steps](RISK.md#1-read-the-credit-and-mandate-board) |
| On change | Set or change a counterparty credit line | Credit line… | [Steps](RISK.md#2-set-a-counterparty-credit-line) |
| On change | Set a trader mandate, including a legal hedge cap (e.g. 80 %) and allowed instruments (no options) | Mandate… | [Steps](RISK.md#3-set-a-mandate-with-a-hedge-cap) |
| Per deal | Approve a hedge band for one contract (80 % for one, 50 % for another) and watch the linked trades' cover | Portfolio → Exposure → Deal hedge approvals | [Steps](RISK.md#4-approve-a-hedge-band-for-a-deal) |
| Monthly | Review delivery performance per contract (shortfalls against tolerance) | Portfolio → Resources | [Steps](RISK.md#5-delivery-performance) |
| Audit | Show who changed a limit, retired a contract or resolved a report, and when | Audit trail (System, export) | Guide |

Limits are set by the risk function only (REVIEWER role); a trader cannot set their own.

### IT desk (operator)

| When | Workflow | Where | Described |
|---|---|---|---|
| Daily | Work problem reports: take, investigate with the attached diagnostics, resolve with a note | Admin → Runtime → Problem reports | [Steps](IT_DESK.md#1-work-a-problem-report) |
| Daily | Check source freshness, failures and the scheduler | Admin → Data Sources, Runtime | [Steps](IT_DESK.md#2-check-the-platform) |
| On alert | Read the emailed alert, open the source, re-run or escalate | Admin → Data Sources | Guide |
| Release | Install an update; read the release notes and the schema revision | [SUPPORT_AND_UPDATES.md](../../guides/SUPPORT_AND_UPDATES.md) | Guide |

### Administrator

| When | Workflow | Where | Described |
|---|---|---|---|
| Set-up | Route email notifications (alerts, IT desk reports, limit breaches, tariff deadlines, source outages) | System → Settings → Notifications | [Steps](ADMIN.md#1-route-email-notifications) |
| Set-up | Users, roles, job functions and data scopes; SSO | Admin → Access & Identity | [Steps](ADMIN.md#2-people-and-access) |
| Set-up | Market-data licences and the customer's own credentials | Admin → Data Sources | Guide |

## Findings from the walkthrough

Doing the work as each role found problems that tests had not; all were fixed before
these screenshots were taken:

- A new contract draft carried invented facts ("Operator draft counterparty", gas year
  2025+) that could be saved as recorded terms. They now start blank.
- Trades that add to a position showed as a negative hedge ratio (-222 %). They read
  "adds 222 %" and are flagged.
- A trader with an NBP and a TTF mandate saw an NBP-book trade reported as a breach of
  the TTF mandate.
- Filled trades showed 0 MWh (the unfilled remainder).
- Screens showed internal principal ids instead of people's names.
- The IT desk's inbox was three clicks deep under Governance.
- With six workspaces (operators, administrators) the account menu went off screen on
  1280–1680 px monitors.
- Registration forms had no layout; checkboxes rendered as text boxes; buttons nobody had
  styled fell back to the browser's grey bevel.
- Hubs, exit points, sale routes, index and law were free text, so a typo silently took a
  contract out of positions or routing. They are chosen from lists now, and the template
  no longer pre-selects a delivery hub.
- The risk officer could not see which contracts to approve a hedge band for (the
  contract library is a trader's read); the approvals list its own contracts, without
  prices.

Known gap, not yet fixed: a contract's price is recorded in GBP/MWh only, so a contract
delivered at TTF or another euro hub is shown but not marked to market, and its credit
exposure is reported as "Incomplete, not valued". Until contract currency is added, keep
euro-hub contracts' valuation in the ETRM.
