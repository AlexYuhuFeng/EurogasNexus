"""Shadow evaluations run under the assumptions their backtest would (or did) use."""

from eurogas_nexus.application.shadow_runtime import _economic_assumptions
from eurogas_nexus.domain.backtest.contracts import BacktestEconomicAssumptions
from eurogas_nexus.domain.ontology.vocabulary import CostTreatment, MissingDataPolicy
from eurogas_nexus.domain.strategy_lab.registry import StrategyVersionDefinition


def test_a_version_with_the_registry_defaults_can_be_shadow_evaluated():
    # The registry's default missing-data policy is BLOCK_OR_PARTIAL; the engine calls it FAIL.
    definition = StrategyVersionDefinition().semantic_payload()
    assumptions = _economic_assumptions(definition)
    assert assumptions.missing_data_policy == MissingDataPolicy.FAIL


def test_no_cost_line_keeps_the_backtest_default_cost_contract():
    definition = StrategyVersionDefinition().semantic_payload()
    shadow = _economic_assumptions(definition)
    backtest = BacktestEconomicAssumptions()
    assert [c.code for c in shadow.cost_components] == [c.code for c in backtest.cost_components]
    assert any(c.treatment == CostTreatment.UNAVAILABLE for c in shadow.cost_components)


def test_a_baseline_run_replays_its_recorded_assumptions():
    recorded = BacktestEconomicAssumptions(
        missing_data_policy=MissingDataPolicy.SKIP_DECISION, require_historical_fx=False
    ).model_dump(mode="json")
    definition = {"economic_assumptions": {"missing_data_policy": "FAIL"}}
    assumptions = _economic_assumptions(definition, baseline=recorded)
    assert assumptions.missing_data_policy == MissingDataPolicy.SKIP_DECISION
    assert assumptions.require_historical_fx is False
