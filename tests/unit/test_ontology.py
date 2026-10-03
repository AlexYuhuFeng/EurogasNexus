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


def test_contract_payment_terms_concepts_are_declared_without_invented_tables() -> None:
    """S2a payment terms are a declared-rule ontology, not a datastore.

    The typed model lives in ``domain/route_cost/payment_terms.py``; the
    concepts intentionally have no table binding because no persistence slice
    has been reviewed or implemented. The item's money-flow direction is the
    reviewed vocabulary slot, never inferred from the cash-flow category.
    """

    from eurogas_nexus.domain.ontology import CONCEPT_TABLE_BINDINGS
    from eurogas_nexus.domain.ontology.vocabulary import PaymentFlowDirection

    ids = _concept_ids()
    assert {"ContractPaymentTerms", "PaymentScheduleItem"} <= ids
    assert "ContractPaymentTerms" not in CONCEPT_TABLE_BINDINGS
    assert "PaymentScheduleItem" not in CONCEPT_TABLE_BINDINGS

    item_concept = next(
        concept for concept in CONCEPTS if concept.concept_id == "PaymentScheduleItem"
    )
    slots = {slot.name: slot for slot in item_concept.slots}
    assert slots["flow_direction"].type is PaymentFlowDirection
    assert {member.value for member in PaymentFlowDirection} == {"INFLOW", "OUTFLOW"}


def test_contract_payment_terms_relations_are_declared() -> None:
    triples = {
        (relation.subject, relation.predicate, relation.object)
        for relation in RELATIONS
    }

    assert ("UpstreamResourceContract", "declares", "ContractPaymentTerms") in triples
    assert ("ContractPaymentTerms", "contains", "PaymentScheduleItem") in triples
