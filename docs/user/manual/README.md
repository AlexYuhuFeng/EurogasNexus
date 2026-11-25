# Illustrated workflow reference

For current task instructions, start with the [Client guide](../../guides/README.md) or
[Chinese client guide](../../guides/README-CN.md). This reference provides screenshot-based
examples of contract entry, risk controls and administration using illustrative test records.
The role guides describe current navigation and operating conventions.

| Role | Manual | Short guide |
|---|---|---|
| Trader | [TRADER.md](TRADER.md) | [guides/TRADER.md](../../guides/TRADER.md) |
| Risk and middle office | [RISK.md](RISK.md) | [guides/RISK_AND_FINANCE.md](../../guides/RISK_AND_FINANCE.md) |
| IT desk (operator) | [IT_DESK.md](IT_DESK.md) | [guides/ADMIN_AND_OPERATIONS.md](../../guides/ADMIN_AND_OPERATIONS.md) |
| Administrator | [ADMIN.md](ADMIN.md) | [guides/ADMIN_AND_OPERATIONS.md](../../guides/ADMIN_AND_OPERATIONS.md) |

Roles and what each may change: [ROLES_AND_RESPONSIBILITIES.md](../../product/ROLES_AND_RESPONSIBILITIES.md).
The product supports decisions; it does not execute trades, enter orders, nominate or
settle. Every screen that could be read that way says so.

## Workflow reference by role

What each role does in a working week, where it is done, and where it is described. "Steps"
means the manual walks through it with screenshots; "Guide" means the short role guide
covers it.

### Trader

| When | Workflow | Where | Described |
|---|---|---|---|
| Morning | Check prices, freshness and alerts | Desk → Today, Desk → Prices; top bar | Guide |
| Every day | See the gas day: IN, OUT and net to clear per hub; nomination status and LNG terminal steps | Desk → Today → My gas day, Gas day checklist | [Steps](TRADER.md) |
| Morning | Review the position ladder: net long/short per hub and month, hedge, marks, VaR | Book → Limits & P&L | [Steps](TRADER.md#4-monitor-the-book-position) |
| Morning | See where the mandate stands before trading | Book → Limits & P&L → Credit and mandates | [Steps](TRADER.md#4-monitor-the-book-position) |
| Every day | See each gas day's balance: supply, exchange and bilateral trades, the residual still to sell or buy, and the cash-out cost if left | Book → Delivery → Daily gas balance | [Steps](TRADER.md#5-balance-each-gas-day) |
| Day-ahead | Decide how much of tomorrow's supply to sell DA and how much to keep for WD | Book → Delivery → Tomorrow's sell-down | [Steps](TRADER.md#5-balance-each-gas-day) |
| Daily | Watch delivered against nominated volume per contract | Book → Delivery → Delivery against nominations | [Steps](TRADER.md#5-balance-each-gas-day) |
| Before each cut-off | See why trades, confirmations and nominations disagree, each break explained with the next step (operations) | Desk → Today → Reconciliation; What needs me | [Steps](TRADER.md#scheduler-why-trades-confirmations-and-nominations-disagree) |
| New deal | Find what is worth doing: evaluators and the market lane, net of tariffs | Deals → Opportunities | [Steps](TRADER.md#6-study-a-cargo-and-its-netback) |
| New deal | Enter a contract by hand: choose its kind, then its terms | Deals → Contracts → New contract | [Steps](TRADER.md#1-enter-a-new-contract) |
| New deal | Read a signed contract PDF into a new contract and check each term | Deals → Contracts → Import PDF | [Steps](TRADER.md#2-read-a-contract-pdf-into-a-new-contract) |
| Change | Edit a stored contract (the edit token prevents overwriting a colleague's change) | Deals → Contracts → open the contract → Edit | Guide |
| End of deal | Retire a terminated contract with a reason; reinstate it if the termination is withdrawn | Deals → Contracts → open the contract → Retire…; Retired contracts | [Steps](TRADER.md#3-retire-and-reinstate-a-contract) |
| Research | Spreads, a strategy described in words, cargo netbacks, storage, LNG and flows | Research → Spreads, Cargo & netback, Fundamentals | [Steps](TRADER.md#6-study-a-cargo-and-its-netback) |
| Yearly | Track each TSO's indicative and final tariffs for the next gas year | Administration → Data Sources → Infrastructure → Tariff publications | [Steps](TRADER.md#7-track-tso-tariff-publications) |
| When a leg is unpriced | Enter a TSO's published tariff ENTSOG lacks; a second person reviews it | Administration → Data Sources → Access & certification | [Steps](TRADER.md#7-track-tso-tariff-publications) |
| Reporting | Export the ladder, credit and mandate tables to Excel, PDF or CSV | Export buttons on each table | [Steps](TRADER.md#4-monitor-the-book-position) |
| Research | Write a market report from the catalogue's sections | Research → Reports | Guide |
| Start and end of day | Draft the morning brief or end-of-day report | Desk → Today → Desk brief, or Ctrl K | [Steps](TRADER.md#8-draft-the-morning-brief-or-end-of-day-report) |
| Any time | Look up a term, its unit, formula and where it appears | Help & Settings → Glossary | [Steps](TRADER.md#9-look-up-a-term) |
| Any time | Report a problem to the IT desk with diagnostics attached | Top bar "?" | [Steps](TRADER.md#10-report-a-problem) |

### Risk and middle office

| When | Workflow | Where | Described |
|---|---|---|---|
| Daily | Read counterparty exposure against limits: replacement, receivable, collateral, expiry | Book → Limits & P&L → Credit and mandates | [Steps](RISK.md#1-read-the-credit-and-mandate-board) |
| Daily | Read each trader's mandate use: size, tenor, hubs, hedge ratio against the band, instruments | same | [Steps](RISK.md#1-read-the-credit-and-mandate-board) |
| On change | Set or change a counterparty credit line | Credit line… | [Steps](RISK.md#2-set-a-counterparty-credit-line) |
| On change | Set a trader mandate, including a legal hedge cap (e.g. 80 %) and allowed instruments (no options) | Mandate… | [Steps](RISK.md#3-set-a-mandate-with-a-hedge-cap) |
| Per deal | Approve a hedge band for one contract (80 % for one, 50 % for another) and watch the linked trades' cover | Book → Limits & P&L → Deal hedge approvals | [Steps](RISK.md#4-approve-a-hedge-band-for-a-deal) |
| Monthly | Review delivery performance per contract (shortfalls against tolerance) | Book → Delivery | [Steps](RISK.md#5-delivery-performance) |
| Audit | Show who changed a limit, retired a contract or resolved a report, and when | Audit trail (Admin → Access & Identity → Audit, export) | Guide |

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
| Set-up | Route email notifications (alerts, IT desk reports, limit breaches, tariff deadlines, source outages) | Help & Settings → Settings → Notifications | [Steps](ADMIN.md#1-route-email-notifications) |
| Set-up | Users, roles, job functions and data scopes; SSO | Admin → Access & Identity | [Steps](ADMIN.md#2-people-and-access) |
| Set-up | Market-data licences and the customer's own credentials | Admin → Data Sources | Guide |

## Screenshot context

The screenshots were taken on 2026-11-01 to 2026-11-07, before the four-mode navigation
(Desk, Deals, Book, Research) and the current brand mark. The top bar in them is the old
one. The pictures of the earlier contract draft workbench (`tr-02` to `tr-12`, `tr-20`)
and of the removed LNG cargo bid (`tr-17`) are no longer referenced, because those screens
are gone; the text describes the current screens.

The screenshots show reference walkthrough records, rather than client positions or current
market observations. Use the interface labels and release supplied for your installation.
Earlier walkthrough findings are preserved in the
[engineering documentation review](../../engineering/DOCUMENTATION_DELIVERY_REVIEW.md#earlier-walkthrough-record).
