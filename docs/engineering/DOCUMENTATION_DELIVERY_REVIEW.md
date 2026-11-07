# Client documentation delivery review

[简体中文](DOCUMENTATION_DELIVERY_REVIEW-CN.md)

Reviewed: 5 November 2026. Source baseline: `cad2f8f9`, package 0.7.0.
Audience: documentation owners, product, implementation and client-service teams.

## Assessment

The existing repository contains substantial operational and product information, but its
client-facing layer does not yet form a dependable commercial handover pack. The main issue
is organisation and verified instructions, rather than a lack of files. A trading-house user
needs a short route from a task to prerequisites, actions, expected results and support.

This revision establishes that client layer. Installation acceptance, contractual support
terms and release approval remain records to complete for the actual delivery.

## Findings and corrections

| Finding | Evidence at the reviewed baseline | Correction in this revision |
| --- | --- | --- |
| Customers enter an engineering catalogue before finding daily tasks | `docs/README.md` mixes user guides, architecture programmes and historical evidence | Put the client guide first; retain the technical index for specialist reference |
| Navigation and setup instructions disagree | Quick Start says five workspaces; the navigation registry defines six; older admin guide places Sources under System | Reconcile quick start and role guides with current workspace ownership |
| Setup can imply that a running service already has usable data | Older first-use guidance has no first-record check | Add source commissioning and source-to-screen verification |
| Configuration examples lag implementation | CI at the reviewed baseline fails the generated-environment-template check after provider changes | Regenerate both shipped templates in PR #44; document the active credential contract |
| Role guides describe capabilities without a complete task/result structure | Several guides are short feature tables with fixed landing claims | Add prerequisites, steps, expected results and evidence/exception handling |
| Support claims are broader than available delivery evidence | Support guide promises browser/Python/server ranges without a versioned acceptance matrix; updates are described as uniformly manual | Use release-specific platform evidence and distinguish browser, desktop and server updates |
| Method wording can change interpretation | Risk guide describes longer products as day-weighted; current curve code uses delivery hours | Explain delivery-hour weighting, position fallback and valuation exceptions |
| Financing and currency descriptions lag implementation | Older portfolio guidance describes a shared funding rate and leaves any different-currency leg unvalued; current resource allocation uses contract rates and positions convert with ECB rates | Document per-resource rate/fallback/day-count reporting and missing-FX exceptions |
| Chinese client coverage is incomplete | Role guides have no Chinese companions | Add separately edited Chinese guides with the same operational facts |
| Customer instructions include development retrospective material | Screenshot-manual index lists earlier bugs and broad historical fix claims | Keep task navigation in the manual and retain retrospective material in engineering records |

## Documentation structure

- **Client guide:** first use, role tasks, data interpretation, support and handover.
- **Specialist references:** deployment, SSO, source operations, API and detailed methodology.
- **Engineering/release records:** architecture decisions, dated acceptance evidence,
  readiness findings and development history.

There is one entry point for client reading: `docs/guides/README.md`, with its Chinese
companion. Existing screenshot procedures remain reference material. This change does
not alter the in-app Manual implementation or certify new UI workflows.

## Industry references and design decisions

- [Bloomberg Professional support](https://professional.bloomberg.com/support/) separates
  product assistance, data issues, software updates and account support. Use clear support
  routes and release/package references.
- [LSEG Workspace learning](https://www.lseg.com/en/training/learning-centre/learning-paths/learning-paths-for-other/lseg-workspace)
  distinguishes installed, browser and mobile learning paths. Make client-specific setup
  and update instructions explicit.
- [Kpler's client guide](https://help.kpler.com/en/articles/15451019-kpler-chartering-client-guide)
  connects initial setup to useful workflows and further help.
  [Kpler's methodology collection](https://help.kpler.com/en/collections/2123463-resources-methodology)
  provides a separate place for data/method explanations. Apply that separation to task
  guides and numerical interpretation.
- [Apple China: changing settings](https://support.apple.com/zh-cn/guide/mac-help/mh15217/27/mac/27)
  demonstrates concise Chinese task titles, quoted interface labels and ordered actions.
  Use native Chinese task phrasing rather than copying English sentence structure.

These are public documentation references, not evidence that Eurogas Nexus has the same
features, support service or certification. The revised text is original; the references
inform structure and editorial choices.

## Source checks for numerical and integration claims

| Topic | Reviewed implementation/reference |
| --- | --- |
| Workspace ownership | `clients/web/src/app/navigation/productNavigation.ts` |
| Credentials and preview activation | `src/eurogas_nexus/security/provider_credentials.py`, `scripts/uat/start_mobile_preview.py` |
| Calendar and curve weighting | `src/eurogas_nexus/domain/market/gas_day.py`, `src/eurogas_nexus/domain/market/forward_curve.py` |
| Contract FX and position marks | `src/eurogas_nexus/api/positions.py` |
| Per-resource financing and cash-timing formula | `src/eurogas_nexus/domain/route_cost/resource_pool.py`, `src/eurogas_nexus/application/resource_pool.py` |
| UI default rate | `clients/web/src/app/model/scenarioInputProvenance.ts` |
| SDK/CLI example | SDK `health_client.py` and CLI `main.py`; import, URL, response-field and parser checks |

The cash-timing explanation distinguishes a contract rate from the scenario fallback and
resource-model day-count support from the default used by saved-contract composition.

## English and Chinese editorial review

Write the English factual baseline first. Edit the Chinese version around the user's task:
use direct verbs, Chinese interface labels and standard desk terminology; keep API names,
units and identifiers exact. Compare both versions for permissions, units, steps, outcomes,
source prerequisites and exception handling. Chinese readers should be able to complete
the task without opening the English document.

## Release maintenance

Before distributing the pack, record its release/build, verify navigation against that
build, validate source examples, check local links and language pairs, and test the
representative onboarding tasks. Retain screenshot capture version/date when refreshing
the illustrated walkthroughs.

The client-specific handover supplies support contacts and hours, supported device/browser
versions, source coverage, agreed recovery targets and acceptance ownership.

## Earlier walkthrough record

The following notes are preserved from the screenshot-manual index at the reviewed baseline.
They are the earlier walkthrough's retrospective account, rather than fresh acceptance
claims made by this documentation revision.



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

Since 2026-11-05 a contract's price is recorded in GBP, EUR or USD, so a contract delivered
at TTF or another euro hub is marked to market against its hub in EUR.
