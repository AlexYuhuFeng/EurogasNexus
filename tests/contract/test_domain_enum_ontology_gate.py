"""Review gate for string enums defined outside the executable ontology.

``eurogas_nexus.domain.ontology`` is the semantic source of truth for
gas-market vocabulary. A new ``StrEnum`` under ``eurogas_nexus.domain`` must
either be added to the ontology vocabulary or be explicitly reviewed and
recorded here. This gate turns "someone added an arbitrary enum string" into
a test failure instead of a silent ontology drift.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
DOMAIN_ROOT = SRC / "eurogas_nexus" / "domain"

# Reviewed non-ontology enums that are allowed to stay in domain modules.
# Adding an entry here is an ontology-review decision; prefer putting the
# vocabulary into domain/ontology/vocabulary.py instead.
_REVIEWED_DOMAIN_STR_ENUMS: set[str] = {
    "eurogas_nexus.domain.analysis.contracts:AnalysisTask",
    "eurogas_nexus.domain.ingestion.certification:CertificationStage",
    "eurogas_nexus.domain.market.gas_day:GasDayCalendar",
    "eurogas_nexus.domain.market_intelligence.opportunity_engine:AccessStatus",
    "eurogas_nexus.domain.market_intelligence.opportunity_engine:OpportunityStatus",
    "eurogas_nexus.domain.monitoring.freshness:FreshnessStatus",
    "eurogas_nexus.domain.observations.market:ObservationFreshness",
    "eurogas_nexus.domain.research.backtest:BacktestResultStatus",
    "eurogas_nexus.domain.research.feasibility:FeasibilityStatus",
    "eurogas_nexus.domain.research.models:AlertSeverity",
    "eurogas_nexus.domain.research.models:CandidateAction",
    "eurogas_nexus.domain.research.models:CostComponentType",
    "eurogas_nexus.domain.research.models:FeasibilityStatus",
    "eurogas_nexus.domain.research.models:ShadowRunStatus",
    "eurogas_nexus.domain.research.monitoring:AlertSeverity",
    "eurogas_nexus.domain.research.shadow_run:PaperAction",
    "eurogas_nexus.domain.research.shadow_run:ShadowRunStatus",
}


def _is_str_enum(node: ast.ClassDef) -> bool:
    return any("StrEnum" in ast.unparse(base) for base in node.bases)


def _defined_domain_str_enums() -> set[str]:
    found: set[str] = set()

    for path in sorted(DOMAIN_ROOT.rglob("*.py")):
        if "ontology" in path.parts:
            continue

        module = ".".join(path.relative_to(SRC).with_suffix("").parts)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and _is_str_enum(node):
                found.add(f"{module}:{node.name}")

    return found


def test_new_domain_str_enums_require_ontology_review() -> None:
    found = _defined_domain_str_enums()

    unreviewed = sorted(found - _REVIEWED_DOMAIN_STR_ENUMS)
    assert not unreviewed, (
        "New domain StrEnum definitions are outside the executable ontology. "
        "Move the vocabulary to eurogas_nexus.domain.ontology.vocabulary or "
        f"record an explicit ontology-review entry: {unreviewed}"
    )


def test_domain_str_enum_review_entries_do_not_go_stale() -> None:
    found = _defined_domain_str_enums()

    stale = sorted(_REVIEWED_DOMAIN_STR_ENUMS - found)
    assert not stale, (
        f"Reviewed enum entries no longer exist; remove them from the review allowlist: {stale}"
    )
