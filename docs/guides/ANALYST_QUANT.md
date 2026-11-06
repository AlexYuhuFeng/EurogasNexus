# Analyst and quant guide

[简体中文](ANALYST_QUANT-CN.md) · [Client guide](README.md)

**Outcome:** an analysis that another authorised colleague can reproduce from the same
data, version and assumptions.

## Explore a spread

1. Open **Strategy Lab → Spread**.
2. Select the series and weights. Check each leg's hub, tenor, source, unit and available history.
3. Put legs on a common currency and energy basis before combining them.
4. Inspect the spread history and statistics over the chosen period.
5. For a rule backtest, record the rule, sample dates and cost assumptions alongside the result.

**Check the result:** the input series and periods explain the observations used.
A short or missing series can change the sample; resolve that difference before comparing runs.
See the [Spread workflow](../user/STRATEGY_LAB.md).

## Develop a saved strategy

1. In **Design**, create or select the strategy and complete its draft inputs.
2. Resolve validation blockers, then freeze the version to retain the specification.
3. In **Backtest**, choose the period and evaluation policies and start the run.
4. Inspect returns, drawdown, attribution, warnings and data coverage.
5. In **Compare**, select compatible saved runs and review the compatibility assessment.
6. Use **Shadow** to evaluate a frozen version against its stated baseline and incoming data.

**Check the result:** the strategy version and run identifiers are recorded with the input
period and costs. Create a new draft when changing a frozen specification.

## Build a research dataset

1. Open **Research → Research Data → Datasets**.
2. Select registered targets, features, entities and the observation window.
3. Set the relevant resampling and history options, then validate the specification.
4. Build a snapshot after validation succeeds.
5. Inspect coverage, temporal integrity and training-readiness results before exporting.

Retain the snapshot identifier, specification, observation types and availability cutoffs
with your notebook or model run. Separate forecast vintages from actual observations and
record the treatment of missing values.

Technical references: [Point-in-time datasets](../research/POINT_IN_TIME_DATASETS.md),
[Features](../research/FEATURE_REGISTRY.md), [Targets](../research/TARGET_REGISTRY.md)
and [ML readiness](../research/ML_READINESS.md).

## Use the Python SDK

Use the SDK distributed with your installation and its documented authentication method.
Start with the [SDK readme](../../packages/python-sdk/README.md) and
[function catalogue](../api/DATA_SCIENCE_FUNCTIONS.md). Keep the API address, SDK version,
request parameters and returned evidence metadata with a reproducible example.
Copy working examples from the matching SDK release rather than inferring method names
from UI labels.

## Share the work

Attach the saved run or snapshot reference, your business question, assumptions and
material sensitivities to the decision case or desk research record. Confirm the
permitted recipients and export use for the underlying data.
