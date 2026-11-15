"""Every reader of the observation tables withholds unresolved identifiers (one rule).

``application/identity_resolution.identity_clause`` is the rule; this test fails when a
module queries a flow, capacity, storage, LNG or power table without it, so a new reader
cannot serve a quarantined row by forgetting. Modules that write, count or report on the
stored rows (not serve them) are listed with the reason.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "eurogas_nexus"

MODELS = (
    "FlowObservationRecord",
    "CapacityObservationRecord",
    "StorageObservationRecord",
    "LngObservationRecord",
    "PowerObservationRecord",
)

#: Modules that touch the tables without serving rows as known entities.
NOT_READERS = {
    "application/identity_resolution.py": "the rule itself and the quarantine report",
    "application/data_quality_report.py": "counts every stored row per dataset",
    "application/dataops_runtime.py": "last-received times per source",
    "api/routes/public/sources.py": "stored row counts per source (Source Center)",
    "db/repositories/data_platform.py": "stored row counts and provenance per table",
    "db/repositories/power.py": "upserts power rows",
    "db/repositories/public_ingestion_upsert.py": "upserts public-source rows",
    "db/repositories/entsog_observation_persistence.py": "upserts ENTSOG rows",
    "db/repositories/capacity_ranges.py": "ingest-time range re-split bookkeeping",
    "ingestion/entsog_ingestion.py": "ingest",
    "ingestion/entsog_native_observations.py": "ingest",
    "ingestion/public_sources.py": "ingest",
    "db/registry.py": "table registry",
}

QUERY = re.compile(r"session\.(query|execute|scalars)\(|\bselect\(")


def test_every_reader_of_the_observation_tables_applies_the_identity_clause():
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        if relative.startswith("db/models/") or relative in NOT_READERS:
            continue
        text = path.read_text(encoding="utf-8")
        if not any(model in text for model in MODELS) or not QUERY.search(text):
            continue
        if "identity_clause(" not in text:
            offenders.append(relative)
    assert offenders == [], (
        "These modules query observation tables without identity_clause (WITHHOLDING_RULE): "
        f"{offenders}"
    )


def test_the_listed_non_readers_exist():
    missing = [name for name in NOT_READERS if not (SRC / name).exists()]
    assert missing == []
