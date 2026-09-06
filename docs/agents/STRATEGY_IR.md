# Strategy IR (CR-15)

Source: `src/eurogas_nexus/domain/agents/strategy_ir.py`.

## Why a constrained IR exists

The LLM may draft a JSON/YAML-serializable strategy specification. It cannot
write arbitrary Python or reference execution primitives. Every nested model
uses `extra="forbid"`.

## Structure

`hypothesis`, `universe` (origin/destination/product/currency), typed
`components` (known `StrategyComponentType` families), `conditions` with
explicit feature/operator/value/unit, bounded `parameters`, `sizing`,
`risk_controls`, `economic_assumptions`, `data_requirements`,
`evaluation_windows`.

## Validation

Checks feature existence and unit compatibility, product validity, component
support, parameter ranges/defaults, risk-control consistency, and required
series availability. Only valid IR may compile.

## Compilation

`compile_strategy_ir` maps the IR into the existing CR-03
`StrategyVersionDefinition`. Backtest and Shadow consume the same immutable
domain model; no second strategy engine exists.
