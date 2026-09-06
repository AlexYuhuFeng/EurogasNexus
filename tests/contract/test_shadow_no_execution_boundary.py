"""No-execution boundary regression tests for the shadow runtime."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def test_shadow_runtime_has_no_execution_adapter_imports() -> None:
    runtime = (SRC / "eurogas_nexus" / "application" / "shadow_runtime.py").read_text(
        encoding="utf-8"
    )
    api = (
        SRC / "eurogas_nexus" / "api" / "routes" / "public" / "shadow.py"
    ).read_text(encoding="utf-8")

    for forbidden in [
        "place_order",
        "submit_nomination",
        "nomination_service",
        "execution_adapter",
        "order_routing",
        "trade_capture",
    ]:
        assert forbidden not in runtime.lower(), forbidden
        assert forbidden not in api.lower(), forbidden


def test_shadow_candidate_schema_uses_research_vocabulary_only() -> None:
    model = (
        SRC / "eurogas_nexus" / "db" / "models" / "shadow.py"
    ).read_text(encoding="utf-8")
    candidate = model.split("class StrategyShadowCandidateRecord")[1].split(
        "class StrategyShadowRiskCheckRecord"
    )[0]
    lowered = candidate.lower()
    for forbidden in ["order", "trade", "execution", "nomination"]:
        assert forbidden not in lowered, forbidden
