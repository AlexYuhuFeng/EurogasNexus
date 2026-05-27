"""Data-quality contract unit tests."""

from eurogas_nexus.data_quality import QualityCheck, QualityCheckResult


class _QualityCheckDouble(QualityCheck):
    def evaluate(self, dataset_id: str) -> QualityCheckResult:
        return QualityCheckResult(
            check_name="row-count-positive",
            passed=dataset_id == "dataset-ok",
            details=f"checked {dataset_id}",
        )


def test_quality_check_contract_is_deterministic_for_same_input() -> None:
    check = _QualityCheckDouble()

    first = check.evaluate("dataset-ok")
    second = check.evaluate("dataset-ok")

    assert first == second
    assert first.research_only is True


def test_quality_check_contract_reports_without_mutation_claims() -> None:
    check = _QualityCheckDouble()
    result = check.evaluate("dataset-bad")

    assert result.passed is False
    assert "checked dataset-bad" in result.details
