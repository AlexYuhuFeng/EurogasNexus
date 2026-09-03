"""Ontology version and OWL/GRM parity contract tests."""

from pathlib import Path

from eurogas_nexus.domain.ontology.semantic_kernel import current_ontology_version
from eurogas_nexus.domain.ontology.vocabulary import GRM_PROCESSES, GRM_ROLES

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_VERSION = "0.5.0"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_owl_ttl_version_is_canonical() -> None:
    ttl = _read("docs/ontology/eurogas-nexus-grm.ttl")

    assert f'owl:versionInfo "{CANONICAL_VERSION}"' in ttl


def test_owl_document_version_is_canonical() -> None:
    en = _read("docs/ontology/OWL_GAS_ROLE_MODEL.md")
    cn = _read("docs/ontology/OWL_GAS_ROLE_MODEL-CN.md")

    assert f"| Version | `{CANONICAL_VERSION}` |" in en
    assert f"| 版本 | `{CANONICAL_VERSION}` |" in cn


def test_subject_architecture_version_is_canonical() -> None:
    doc = _read("docs/ontology/europe-natural-gas.md")

    assert f"- **版本**：v{CANONICAL_VERSION}。" in doc


def test_executable_ontology_version_is_canonical() -> None:
    assert current_ontology_version().label() == f"v{CANONICAL_VERSION}"


def test_grm_role_identifiers_match_owl_document() -> None:
    en = _read("docs/ontology/OWL_GAS_ROLE_MODEL.md")

    for role in GRM_ROLES:
        assert role in en


def test_grm_process_identifiers_match_owl_document() -> None:
    en = _read("docs/ontology/OWL_GAS_ROLE_MODEL.md")

    for process in GRM_PROCESSES:
        assert process in en


def test_grm_role_identifiers_match_turtle() -> None:
    ttl = _read("docs/ontology/eurogas-nexus-grm.ttl")

    for role in GRM_ROLES:
        assert f":{role} " in ttl


def test_grm_process_identifiers_match_turtle() -> None:
    ttl = _read("docs/ontology/eurogas-nexus-grm.ttl")

    for process in GRM_PROCESSES:
        assert f":{process} " in ttl
