"""Turtle rendering for the executable Harmonised Gas Role Model (GRM).

The executable ontology in :mod:`eurogas_nexus.domain.ontology.vocabulary` is
the semantic source of truth. This module renders its classes and properties
into Turtle syntax so the published OWL artifact stays reproducible and can be
checked mechanically by ``tests/contract/test_ontology_grm_parity.py``.
"""

from __future__ import annotations

from eurogas_nexus.domain.ontology.semantic_kernel import current_ontology_version
from eurogas_nexus.domain.ontology.vocabulary import (
    GRM_BOUNDARY_CLASSES,
    GRM_COMMODITY_TAXONOMY,
    GRM_INTERACTION_PROPERTIES,
    GRM_INTERACTION_SUBPROPERTIES,
    GRM_PROCESSES,
    GRM_ROLES,
)

ONTOLOGY_IRI = "https://eurogas-nexus.eu/ontology/grm"
VERSION = current_ontology_version().label().lstrip("v")


def _section(title: str) -> str:
    return f"# {'-' * 75}\n# {title}\n# {'-' * 75}\n"


def render_grm_ttl() -> str:
    """Render the generated GRM Turtle document from the executable vocabulary."""

    lines = [
        "# Generated from src/eurogas_nexus/domain/ontology/vocabulary.py",
        "# by scripts/ontology/generate_grm_ttl.py. Do not edit by hand.",
        "# The executable ontology is the semantic source of truth.",
        "@prefix : <https://eurogas-nexus.eu/ontology/grm#> .",
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "@prefix dcterms: <http://purl.org/dc/terms/> .",
        "@prefix saref: <https://saref.etsi.org/core/> .",
        "",
        f"<{ONTOLOGY_IRI}> a owl:Ontology ;",
        '    dcterms:title "Eurogas Nexus Harmonised Gas Role Model ontology"@en ;',
        '    dcterms:creator "Eurogas Nexus ontology working group" ;',
        f'    owl:versionInfo "{VERSION}" ;',
        "    owl:imports <https://saref.etsi.org/core/> .",
        "",
        _section("GRM role model"),
        ":MarketParty a owl:Class .",
        ":GasMarketRole a owl:Class .",
        ":playsRole a owl:ObjectProperty ;",
        "    rdfs:domain :MarketParty ;",
        "    rdfs:range :GasMarketRole .",
        "",
    ]

    for role in GRM_ROLES:
        lines.extend(
            [
                f":{role} a owl:Class ;",
                "    rdfs:subClassOf :GasMarketRole .",
                "",
            ]
        )

    lines.extend(
        [
            _section("GRM business-process view"),
            ":GasBusinessProcess a owl:Class .",
            ":participatesIn a owl:ObjectProperty ;",
            "    rdfs:domain :GasMarketRole ;",
            "    rdfs:range :GasBusinessProcess .",
            ":concerns a owl:ObjectProperty ;",
            "    rdfs:domain :GasBusinessProcess ;",
            "    rdfs:range saref:Commodity .",
            "",
        ]
    )

    for process in GRM_PROCESSES:
        lines.extend(
            [
                f":{process} a owl:Class ;",
                "    rdfs:subClassOf :GasBusinessProcess .",
                "",
            ]
        )

    lines.extend([_section("GRM commodity view (SAREF alignment)")])
    for commodity, parents in GRM_COMMODITY_TAXONOMY.items():
        lines.extend(
            [
                f":{commodity} a owl:Class ;",
                f"    rdfs:subClassOf {', '.join(parents)} .",
                "",
            ]
        )

    lines.extend([_section("GRM interaction properties")])
    for prop, (domain, range_) in GRM_INTERACTION_PROPERTIES.items():
        lines.extend([f":{prop} a owl:ObjectProperty ;"])
        if parent := GRM_INTERACTION_SUBPROPERTIES.get(prop):
            lines.append(f"    rdfs:subPropertyOf :{parent} ;")
        lines.extend(
            [
                f"    rdfs:domain :{domain} ;",
                f"    rdfs:range :{range_} .",
                "",
            ]
        )

    lines.extend([_section("Decision-support boundary")])
    for cls in GRM_BOUNDARY_CLASSES:
        lines.extend(
            [
                f":{cls} a owl:Class ;",
                "    rdfs:subClassOf saref:Commodity .",
                "",
            ]
        )
    lines.extend(
        [
            ":hasHumanReviewRequirement a owl:DatatypeProperty ;",
            "    rdfs:domain :DecisionSupportOutput ;",
            "    rdfs:range xsd:boolean .",
            "",
        ]
    )

    return "\n".join(lines)
