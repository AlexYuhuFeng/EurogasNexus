# Risk, middle office and finance guide

[简体中文](RISK_AND_FINANCE-CN.md) · [Client guide](README.md)

Use this workflow to reconcile the represented position, interpret valuation and investigate
limit exceptions. Select the relevant books, valuation date and reporting currency first.

## Review exposure

1. Open the **Portfolio** exposure view and position ladder.
2. Confirm the book scope, delivery horizon, physical contracts and imported trade legs.
3. Inspect net position and hedge measures by hub and delivery month.
4. Review unvalued positions, missing FX and marking warnings before reading the totals.
5. Reconcile a sample of contracts and trades against the firm's position system.

**Result:** an exposure review with a clear population and identified exceptions.
A grouping by region or business is an analytical aggregation; access boundaries come
from the deployment's permissions and supported scoping controls.

## Understand the marks

The monthly curve uses quoted months and longer delivery products. Longer-product prices
are allocated consistently with delivery-hour weights, including daylight-saving changes.
The position view can fill uncovered months using the hub's latest daily close and labels
that marking method as flat.

Distinguish a quoted month, a derived month and a flat fallback in a valuation review.
The curve builder and the position view have different responsibilities: an uncovered
curve month and a subsequent position-mark fallback are separate steps.

The indicative VaR view measures historical price moves on the represented position.
Read the displayed horizon, confidence level, available history and warnings with the
result. Volume uncertainty, shape, basis and credit exposures require their own assessment.

See [Calculation basis](../user/DATA_STATUS_AND_PROVENANCE.md#calculation-basis) for the
marking and input conventions used in a review.

## Review credit and mandates

1. Open **Credit and mandates** in the exposure view.
2. Check counterparty mapping, approved line, collateral, approval expiry and utilisation.
3. Inspect trader mandates by book, hub, tenor and permitted instrument.
4. Review contract-level hedge approvals where applicable.
5. Record the exception, owner and follow-up through your firm's control process.

Use the authorised risk controls to change approvals. Reconcile approved changes with the
firm's limit record and retain the audit reference.
The [risk walkthrough](../user/manual/RISK.md) covers the forms and review steps.

## Check cash and financing assumptions

Inspect each contract's currency, payment dates/lags and recorded financing terms.
Check the benchmark, spread, day-count and valuation date supported by the selected
calculation. A percentage annual rate and a cash amount per day are different measures.

For resource-pool comparisons, check each allocation's contract rate or scenario-default
rate, and its day-count basis. The [portfolio workflow](../user/PORTFOLIO_WORKFLOW.md)
explains which default applies when a contract rate is absent.
[Interest-rate sources](../operations/INTEREST_RATES.md) describe available benchmark inputs.

## Retain the review

Save or export the permitted position view and its context, identify any omitted or unvalued
legs, and link the relevant decision and audit references. The firm's risk system and
finance ledger provide the reconciled records for its control and accounting processes.
