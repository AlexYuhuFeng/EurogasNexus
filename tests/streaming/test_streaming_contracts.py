"""Streaming boundary contract tests."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_streaming_contract_forbids_kafka_dependency_tokens() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for token in ["kafka", "confluent-kafka", "aiokafka"]:
        assert token not in pyproject


def test_streaming_contract_doc_preserves_non_authoritative_policy() -> None:
    text = (ROOT / "docs" / "contracts" / "12_STREAMING_KAFKA_CONTRACT.md").read_text(
        encoding="utf-8"
    )

    assert "Streaming must never be the runtime source of truth" in text
    assert "Kafka client libraries" in text


def test_streaming_module_imports_are_dependency_free() -> None:
    module = ROOT / "src" / "eurogas_nexus" / "streaming" / "contracts.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert not any(name.startswith("kafka") or "kafka" in name for name in imports)
