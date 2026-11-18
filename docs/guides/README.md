# Eurogas Nexus client guide

[简体中文](README-CN.md)

Use Eurogas Nexus to inspect European gas markets, assess a physical or financial position,
compare alternatives and retain the evidence behind a decision.

## Get started

1. Follow [First sign-in and first checks](../user/QUICK_START.md).
2. Open the guide for your work below.
3. Use [Data, units and methodology](../user/DATA_STATUS_AND_PROVENANCE.md) when interpreting a figure.
4. For an access, data or application problem, follow [Support and updates](SUPPORT_AND_UPDATES.md).

| Your work | Start here | Typical result |
| --- | --- | --- |
| Trading and physical portfolio management | [Trader](TRADER.md) | A market or portfolio assessment with its price basis and assumptions |
| Research and quantitative analysis | [Analyst and quant](ANALYST_QUANT.md) | A reproducible analysis, strategy run or dataset snapshot |
| Risk, middle office and finance | [Risk and finance](RISK_AND_FINANCE.md) | An exposure review with identified exceptions |
| Desk and business management | [Management](MANAGEMENT.md) | A portfolio summary and decisions requiring attention |
| Legal and compliance | [Legal and compliance](LEGAL_COMPLIANCE.md) | A traceable decision or access record |
| Platform administration and data operations | [Administration and operations](ADMIN_AND_OPERATIONS.md) | Working access, configured sources and monitored refreshes |
| A new client installation or desk rollout | [Client onboarding](CLIENT_ONBOARDING.md) | A recorded handover with named owners and completed acceptance tasks |

## Find a workspace

The top bar has four working modes. A mode is a row of tasks; the task you open is in the
address, so a link or a refresh returns to it.

| Mode | Tasks | The question it answers |
| --- | --- | --- |
| Desk | Today, Prices, Network (map with outages, capacity and flows beside it) | What changed, and does it touch us? |
| Deals | Contracts, Review (Opportunities is coming) | What have we contracted, and has it been approved? |
| Book | Position, Limits & P&L, Delivery, Planning (Nominations and Storage plan behind one switch) | Where do we stand, and what is near a limit? |
| Research | Reports (Spreads, Fundamentals and Cargo & netback are coming) | Why is the market here, and what does history say? |

**Help & Settings** (Settings, Manual, Glossary) and **Administration** (Data Sources, Runtime,
Access & Identity) are in the account menu, not the top bar. Keyboard users reach the modes with
**Ctrl+Shift+1** to **4** (⌘ on a Mac), Help & Settings with **Ctrl+Shift+5** and Administration
with **Ctrl+Shift+6**; the top bar is one Tab stop, and the arrow keys move between modes.

Decision Center is no longer a separate area. A decision review is **Deals → Review**, with the
deals it approves; nomination and storage assessments are the two views of **Book → Planning**.
Evaluate, Optimise, Routes & netback, Strategies, Data and the Research assistant were removed
(commercial design basis 2, section I): a bookmarked link to one of them opens the nearest
surviving task (Deals → Contracts, or Research → Reports), and the search (Ctrl+K) still finds the
old names of the tasks that remain.

The available workspaces depend on your access and job profile. A job profile organises
your workspace; roles and data scopes determine the actions and information available.
See [Roles and responsibilities](../product/ROLES_AND_RESPONSIBILITIES.md).

Open **Settings** from the account menu for language, appearance and personal display
preferences. The account menu also opens Help & manual, Administration (for administrators) and
sign out. Keyboard users can open
search with **Ctrl+K**, or **⌘K** where supported; touch users can select the search control.

## Scope and document version

These instructions describe the source behaviour reviewed on 5 November 2026, package
version 0.7.0. The release supplied to your firm determines the installed capabilities,
platforms and release status. Record that release during [onboarding](CLIENT_ONBOARDING.md).

The workstation supports analysis and decision recording. Trade execution, nomination
submission and settlement processing remain in your firm's execution and operating systems.
Use the [release readiness record](../release/RELEASE_READINESS.md) for delivery approval
and the [release notes](../../CHANGELOG.md) for changes.

[Screenshot walkthroughs](../user/manual/README.md) provide examples using test records.
The [technical documentation index](../README.md) contains deployment, API and methodology
references for administrators and specialists.
