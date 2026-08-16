"""Ontology internal-consistency tests.

These tests enforce that the typed ontology is self-consistent: unique concept
ids, resolvable relation and slot references, bilingual definitions, and a clean
allowed/forbidden action split.
"""

from eurogas_nexus.domain.ontology import (
    CONCEPTS,
    CONSTRAINTS,
    RELATIONS,
    ActionKind,
    ForbiddenAction,
)


def _concept_ids() -> set[str]:
    return {concept.concept_id for concept in CONCEPTS}


def test_concept_ids_are_unique() -> None:
    ids = [concept.concept_id for concept in CONCEPTS]
    assert len(ids) == len(set(ids))


def test_concepts_have_bilingual_definitions() -> None:
    for concept in CONCEPTS:
        assert concept.definition_en.strip()
        assert concept.definition_zh_cn.strip()


def test_relation_references_resolve_to_concepts() -> None:
    ids = _concept_ids()
    for relation in RELATIONS:
        assert relation.subject in ids, f"{relation.subject} is not a concept"
        assert relation.object in ids, f"{relation.object} is not a concept"


def test_slot_type_references_resolve() -> None:
    ids = _concept_ids()
    for concept in CONCEPTS:
        for slot in concept.slots:
            if isinstance(slot.type, str):
                assert slot.type in ids, (
                    f"{concept.concept_id}.{slot.name} references unknown concept {slot.type}"
                )


def test_allowed_and_forbidden_actions_are_disjoint() -> None:
    allowed = {action.value for action in ActionKind}
    forbidden = {action.value for action in ForbiddenAction}
    assert not (allowed & forbidden)


def test_candidate_actions_never_overlap_forbidden_actions() -> None:
    from eurogas_nexus.domain.ontology import CandidateAction

    candidate = {action.value for action in CandidateAction}
    forbidden = {action.value for action in ForbiddenAction}
    assert not (candidate & forbidden)


def test_constraints_have_callable_validators() -> None:
    for constraint in CONSTRAINTS:
        assert callable(constraint.validator)
