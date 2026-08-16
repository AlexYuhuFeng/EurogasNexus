"""Ontology → PostgreSQL table binding consistency tests (seed ↔ binding)."""

from eurogas_nexus.db.registry import list_required_tables
from eurogas_nexus.domain.ontology import CONCEPT_TABLE_BINDINGS, CONCEPTS


def test_bindings_reference_defined_concepts() -> None:
    concept_ids = {concept.concept_id for concept in CONCEPTS}
    for concept_id in CONCEPT_TABLE_BINDINGS:
        assert concept_id in concept_ids, f"{concept_id} is not a defined concept"


def test_bindings_reference_required_tables() -> None:
    required = set(list_required_tables())
    for concept_id, table in CONCEPT_TABLE_BINDINGS.items():
        assert table in required, f"{concept_id} -> {table} is not a required table"
