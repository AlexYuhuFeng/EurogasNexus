"""Application workflow shell for ingestion run lookups."""

from dataclasses import dataclass

from eurogas_nexus.db.repositories import IngestionRun, IngestionRunRepository


@dataclass(frozen=True)
class IngestionRunLookupResult:
    """Workflow-safe lookup result with explicit research flags."""

    run: IngestionRun | None
    research_only: bool = True
    human_review_required: bool = False


def get_ingestion_run(
    repository: IngestionRunRepository,
    run_id: str,
) -> IngestionRunLookupResult:
    """Return ingestion run metadata via repository abstraction only."""

    run = repository.get_by_id(run_id)
    return IngestionRunLookupResult(run=run)
