"""Glossary concept-id mapping and hub supersession tests (Gate 2)."""

from eurogas_nexus.domain.glossary import TERM_CONCEPT_IDS, baseline_glossary_terms
from eurogas_nexus.domain.ontology.vocabulary import MARKET_HUB_SUPERSESSIONS


def test_every_baseline_term_has_an_explicit_concept_id_decision() -> None:
    terms = baseline_glossary_terms()
    assert len(terms) >= 29
    for term in terms:
        assert term.term_id in TERM_CONCEPT_IDS, (
            f"glossary term {term.term_id!r} lacks an explicit concept_id decision"
        )


def test_hub_terms_annotate_the_virtual_hub_concept() -> None:
    by_id = {term.term_id: term for term in baseline_glossary_terms()}
    for term_id in ("hub-ttf", "hub-nbp", "hub-the", "hub-peg"):
        assert by_id[term_id].concept_id == "VirtualHub"


def test_capacity_terms_annotate_capacity_profile() -> None:
    by_id = {term.term_id: term for term in baseline_glossary_terms()}
    for term_id in (
        "concept-entry-capacity",
        "concept-exit-capacity",
        "concept-firm-capacity",
        "concept-interruptible-capacity",
    ):
        assert by_id[term_id].concept_id == "CapacityProfile"


def test_localized_includes_concept_id() -> None:
    by_id = {term.term_id: term for term in baseline_glossary_terms()}
    localized = by_id["hub-ttf"].localized("en")
    assert localized["concept_id"] == "VirtualHub"


def test_hub_supersessions_record_the_market_area_consolidation() -> None:
    # THE replaced the historical NCG and GASPOOL market areas.
    assert MARKET_HUB_SUPERSESSIONS == {"NCG": "THE", "GASPOOL": "THE"}


def test_reference_market_hub_model_has_effective_period_columns() -> None:
    from eurogas_nexus.db.models import ReferenceMarketHub

    columns = set(ReferenceMarketHub.__table__.columns.keys())
    for column in (
        "market_area",
        "valid_from_utc",
        "valid_to_utc",
        "superseded_by_hub_id",
    ):
        assert column in columns
