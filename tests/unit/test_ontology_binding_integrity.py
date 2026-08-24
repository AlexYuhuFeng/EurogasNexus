"""Ontology concept <-> table binding integrity tests (slot-level).

This is the machine-checkable counterpart of the audit finding that
"~13/20 DB bindings have slot/field/enum/meaning inconsistencies": every slot
of every bound concept must resolve to a real column on the bound table, and
slot maps must stay exhaustive — drift now fails the build.
"""

from __future__ import annotations

from eurogas_nexus.db.base import Base
from eurogas_nexus.domain.ontology.bindings import (
    CONCEPT_SLOT_COLUMN_MAPS,
    CONCEPT_TABLE_BINDINGS,
)
from eurogas_nexus.domain.ontology.concepts import CONCEPTS


def _model_by_table(table_name: str):
    import eurogas_nexus.db.models  # noqa: F401  (register mappers)

    for mapper in Base.registry.mappers:
        if mapper.class_.__table__.name == table_name:
            return mapper.class_
    return None


def test_every_bound_table_has_a_sqlalchemy_model() -> None:
    for concept_id, table_name in CONCEPT_TABLE_BINDINGS.items():
        assert _model_by_table(table_name) is not None, (
            f"{concept_id} binds to {table_name!r} but no SQLAlchemy model exists"
        )


def test_every_bound_concept_has_an_exhaustive_slot_map() -> None:
    for concept in CONCEPTS:
        if concept.concept_id not in CONCEPT_TABLE_BINDINGS:
            continue
        slot_map = CONCEPT_SLOT_COLUMN_MAPS.get(concept.concept_id)
        assert slot_map is not None, (
            f"{concept.concept_id} is bound to a table but has no slot map"
        )
        slot_names = {slot.name for slot in concept.slots}
        assert set(slot_map) == slot_names, (
            f"{concept.concept_id} slot map drift: "
            f"missing={sorted(slot_names - set(slot_map))} "
            f"extra={sorted(set(slot_map) - slot_names)}"
        )


def test_slot_map_targets_resolve_to_real_columns() -> None:
    for concept_id, table_name in CONCEPT_TABLE_BINDINGS.items():
        model = _model_by_table(table_name)
        columns = set(model.__table__.columns.keys())
        slot_map = CONCEPT_SLOT_COLUMN_MAPS[concept_id]
        for slot, target in slot_map.items():
            if not target:
                continue
            base_column = target.split(".")[0]
            assert base_column in columns, (
                f"{concept_id}.{slot} maps to {target!r} which is not a column "
                f"of {table_name}"
            )


def test_slot_maps_have_no_stale_entries() -> None:
    for concept_id in CONCEPT_SLOT_COLUMN_MAPS:
        assert concept_id in CONCEPT_TABLE_BINDINGS, (
            f"stale slot map for unbound concept {concept_id}"
        )


def test_flow_observation_kind_is_column_backed() -> None:
    """The audit-flagged FlowObservation.kind must exist as a column."""

    model = _model_by_table("flow_observations")
    assert "kind" in model.__table__.columns


def test_capacity_profile_product_and_scope_are_column_backed() -> None:
    """The audit-flagged CapacityProfile product/scope must exist as columns."""

    model = _model_by_table("capacity_profiles")
    assert "capacity_product" in model.__table__.columns
    assert "capacity_scope" in model.__table__.columns
