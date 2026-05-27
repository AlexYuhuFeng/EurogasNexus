"""Workflow shell tests for ingestion run lookup."""

from datetime import UTC, datetime

from eurogas_nexus.application.workflows.ingestion_runs import get_ingestion_run
from eurogas_nexus.db.repositories import IngestionRun, IngestionRunRepository


class _RepoDouble(IngestionRunRepository):
    def __init__(self, result: IngestionRun | None) -> None:
        self._result = result

    def get_by_id(self, run_id: str) -> IngestionRun | None:
        if self._result is None:
            return None
        return self._result if self._result.run_id == run_id else None


def test_get_ingestion_run_returns_research_flagged_payload() -> None:
    repo = _RepoDouble(
        IngestionRun(
            run_id="run-100",
            source_name="fixture-source",
            status="succeeded",
            started_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    result = get_ingestion_run(repo, "run-100")

    assert result.run is not None
    assert result.run.run_id == "run-100"
    assert result.research_only is True
    assert result.human_review_required is False


def test_get_ingestion_run_handles_missing_run() -> None:
    repo = _RepoDouble(None)

    result = get_ingestion_run(repo, "missing")

    assert result.run is None
    assert result.research_only is True
