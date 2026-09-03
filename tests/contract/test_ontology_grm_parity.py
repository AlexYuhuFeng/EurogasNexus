"""Mechanical parity between the executable ontology and the published OWL/Turtle.

The executable ontology (``src/eurogas_nexus/domain/ontology/``) is the
semantic source of truth. The published Turtle file is only allowed to carry
extra human-facing annotations (labels, definitions, provenance); every class,
property, and structural statement it makes must be reproducible from the
executable vocabulary via ``scripts/ontology/generate_grm_ttl.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import DCTERMS, OWL, RDF, RDFS, SKOS, Graph, Namespace, URIRef

from eurogas_nexus.domain.ontology.grm_turtle import ONTOLOGY_IRI, render_grm_ttl
from eurogas_nexus.domain.ontology.semantic_kernel import current_ontology_version
from eurogas_nexus.domain.ontology.vocabulary import (
    GRM_BOUNDARY_CLASSES,
    GRM_COMMODITY_TAXONOMY,
    GRM_INTERACTION_PROPERTIES,
    GRM_PROCESSES,
    GRM_ROLES,
)

EX = Namespace("https://eurogas-nexus.eu/ontology/grm#")
ROOT = Path(__file__).resolve().parents[2]
PUBLISHED_TTL = ROOT / "docs" / "ontology" / "eurogas-nexus-grm.ttl"

_ANNOTATION_PREDICATES = {
    DCTERMS.description,
    DCTERMS.source,
    DCTERMS.title,
    RDFS.label,
    SKOS.definition,
    SKOS.prefLabel,
}


def _parse_ttl(text: str) -> Graph:
    graph = Graph()
    graph.parse(data=text, format="turtle")
    return graph


def _local_subjects(graph: Graph, rdf_type: URIRef) -> set[str]:
    return {
        str(subject).split("#", maxsplit=1)[-1] for subject in graph.subjects(RDF.type, rdf_type)
    }


def _structural_triples(graph: Graph) -> set[tuple[str, str, str]]:
    return {
        (str(subject), str(predicate), str(obj))
        for subject, predicate, obj in graph
        if predicate not in _ANNOTATION_PREDICATES
    }


@pytest.fixture()
def published_graph() -> Graph:
    return _parse_ttl(PUBLISHED_TTL.read_text(encoding="utf-8"))


@pytest.fixture()
def generated_graph() -> Graph:
    return _parse_ttl(render_grm_ttl())


def test_generated_inventory_matches_executable_vocabulary() -> None:
    graph = _parse_ttl(render_grm_ttl())

    expected_classes = (
        set(GRM_ROLES)
        | set(GRM_PROCESSES)
        | set(GRM_BOUNDARY_CLASSES)
        | set(GRM_COMMODITY_TAXONOMY)
        | {"MarketParty", "GasMarketRole", "GasBusinessProcess"}
    )
    expected_object_properties = set(GRM_INTERACTION_PROPERTIES) | {
        "playsRole",
        "participatesIn",
        "concerns",
    }

    assert _local_subjects(graph, OWL.Class) == expected_classes
    assert _local_subjects(graph, OWL.ObjectProperty) == expected_object_properties
    assert _local_subjects(graph, OWL.DatatypeProperty) == {"hasHumanReviewRequirement"}


def test_published_ttl_contains_every_generated_structural_statement(
    published_graph: Graph, generated_graph: Graph
) -> None:
    generated = _structural_triples(generated_graph)
    published = _structural_triples(published_graph)

    missing = generated - published
    assert not missing, f"Published OWL is missing generated statements: {missing}"


def test_published_ttl_inventory_matches_executable_vocabulary(
    published_graph: Graph, generated_graph: Graph
) -> None:
    # New OWL classes or properties must first exist in the executable
    # vocabulary; this gate rejects hand-edits that drift from the code.
    assert _local_subjects(published_graph, OWL.Class) == _local_subjects(
        generated_graph, OWL.Class
    )
    assert _local_subjects(published_graph, OWL.ObjectProperty) == _local_subjects(
        generated_graph, OWL.ObjectProperty
    )
    assert _local_subjects(published_graph, OWL.DatatypeProperty) == _local_subjects(
        generated_graph, OWL.DatatypeProperty
    )


def test_generated_ontology_version_is_executable_version(generated_graph: Graph) -> None:
    version = current_ontology_version().label().lstrip("v")

    declared_versions = [
        str(value) for value in generated_graph.objects(URIRef(ONTOLOGY_IRI), OWL.versionInfo)
    ]
    assert declared_versions == [version]
