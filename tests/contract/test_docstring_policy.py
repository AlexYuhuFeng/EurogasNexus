"""Contract test: public API of core domain modules must carry docstrings.

Google-style docstrings (Summary + Args/Returns/Raises) are the documented
standard in ``docs/engineering/CODING_STANDARDS.md``. Full pydocstyle D-rule
enforcement is intentionally NOT enabled repo-wide (existing baseline makes
that uncontrolled churn); this targeted test guards the modules that other
teams most often read and copy, so the convention cannot silently regress in
exactly the places that set the example.

说明：本测试只检查"有 docstring"，不检查格式细节（Args/Returns 段落由
人工 review 把关）；私有成员与 __init__（语义由类 docstring 承载，
Google 惯例）豁免，其余 public 方法必须检查。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "eurogas_nexus"

# 契约覆盖的核心模块清单：新增"示范级"模块时应同步加入。
CHECKED_MODULES = [
    # 第一轮：核心领域模块
    "domain/market/gas_day.py",
    "domain/monitoring/freshness.py",
    "domain/constraints/access.py",
    "domain/ontology/semantic_kernel.py",
    "domain/route_cost/resource_pool.py",
    # 第二轮：API 依赖与次级领域模块
    "api/dependencies/entitlement.py",
    "api/dependencies/public_auth.py",
    "api/dependencies/route_permission.py",
    "api/dependencies/sandbox.py",
    "domain/ingestion/source_registry.py",
    "domain/ingestion/certification.py",
    "domain/constraints/risk.py",
    "domain/constraints/route_economics.py",
    "domain/identity/principal.py",
    "domain/ontology/actions.py",
    "domain/ontology/relations.py",
    "domain/ontology/constraints.py",
    "domain/route_cost/enums.py",
    "domain/route_cost/capacity_requirement.py",
    "domain/route_cost/tariff_models.py",
    "domain/route_cost/tariff_selection.py",
    "domain/market_positioning.py",
    # 第三轮：analysis 拆分后的包模块
    "domain/analysis/contracts.py",
    "domain/analysis/builders.py",
    "domain/analysis/glossary_context.py",
    "domain/analysis/glossary_profile.py",
    "domain/analysis/glossary_entities.py",
    # 第四轮：剩余领域模块
    "domain/glossary.py",
    "domain/ontology/concepts.py",
    "domain/ontology/vocabulary.py",
    "domain/ontology/grm_turtle.py",
    "domain/ontology/bindings.py",
    "domain/ontology/__init__.py",
    "domain/route_cost/uk_public_tariffs.py",
    "domain/route_cost/route_optimizer.py",
    "domain/route_cost/european_public_tariffs.py",
    "domain/route_cost/lng_regas.py",
    "domain/route_cost/route_cost_service.py",
    "domain/route_cost/live_markets.py",
    "domain/route_cost/schemas.py",
    "domain/market_intelligence/normalized_view.py",
    "domain/market_intelligence/opportunity_engine.py",
    "domain/strategy_lab/evaluation.py",
    "domain/market_positioning_import.py",
    # 第五轮：API 路由模块
    "api/routes/internal/source_certification.py",
    "api/routes/public/analysis.py",
    "api/routes/public/contracts.py",
    "api/routes/public/cost_observations.py",
    "api/routes/public/credentials.py",
    "api/routes/public/glossary.py",
    "api/routes/public/health.py",
    "api/routes/public/lng.py",
    "api/routes/public/market.py",
    "api/routes/public/monitoring.py",
    "api/routes/public/physical.py",
    "api/routes/public/portfolio.py",
    "api/routes/public/research.py",
    "api/routes/public/review.py",
    "api/routes/public/route_cost.py",
    "api/routes/public/storage.py",
    "api/routes/public/weather.py",
    # 第六轮：security / db / workflows / optimization / sdk / mcp / cli
    "security/credentials.py",
    "security/permissions.py",
    "db/models/glossary.py",
    "db/models/observation.py",
    "db/models/route_cost.py",
    "db/repositories/certification.py",
    "db/repositories/market_intelligence.py",
    "db/repositories/monitoring.py",
    "db/repositories/reference_network.py",
    "db/repositories/review.py",
    "db/repositories/route_cost.py",
    "ingestion/connectors/base.py",
    "domain/observations/market.py",
    "data_quality/contracts.py",
    "runtime_store/contracts.py",
    "optimization/_validation.py",
    "optimization/models.py",
    "optimization/network_flow.py",
    "optimization/nomination.py",
    "optimization/service.py",
    "optimization/storage.py",
    "domain/research/allocation.py",
    "domain/research/backtest.py",
    "domain/research/feasibility.py",
    "domain/research/models.py",
    "domain/research/monitoring.py",
    "domain/research/netback.py",
    "domain/research/nowcast.py",
    "domain/research/route_cost.py",
    "domain/research/shadow_run.py",
    "mcp/server.py",
    "cli/commands.py",
    "cli/main.py",
]


def _public_definitions(tree: ast.Module) -> list[tuple[str, int]]:
    """Collect (name, lineno) of public top-level functions and classes.

    只收集公开（非下划线开头）的顶层函数与类；类只检查其 public 方法
    与 __init__，属性与方法名以下划线开头的视为私有并豁免。
    """

    found: list[tuple[str, int]] = []
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("_")
        ):
            found.append((node.name, node.lineno))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            found.append((node.name, node.lineno))
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if member.name.startswith("_") or member.name == "__init__":
                        continue
                    found.append((f"{node.name}.{member.name}", member.lineno))
    return found


@pytest.mark.parametrize("module_rel", CHECKED_MODULES)
def test_public_api_has_docstrings(module_rel: str) -> None:
    """Every public function/class/method in the checked module has a docstring."""

    module_path = _SRC_ROOT / module_rel
    assert module_path.is_file(), f"Checked module not found: {module_path}"

    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    missing = [
        (name, lineno)
        for name, lineno in _public_definitions(tree)
        if not _has_docstring(_definition_node(tree, name))
    ]
    assert not missing, (
        f"{module_rel}: public API without docstring (see CODING_STANDARDS.md): "
        + ", ".join(f"{name} (line {lineno})" for name, lineno in missing)
    )


def _has_docstring(node: ast.AST) -> bool:
    """Whether the AST node carries a non-empty docstring."""

    doc = ast.get_docstring(node)
    return doc not in (None, "")


def _definition_node(tree: ast.Module, dotted_name: str) -> ast.AST:
    """Resolve ``Class.method`` or top-level name to its AST node."""

    if "." in dotted_name:
        class_name, method_name = dotted_name.split(".", 1)
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for member in node.body:
                    if (
                        isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and member.name == method_name
                    ):
                        return member
                break
        raise AssertionError(f"Method not found in AST: {dotted_name}")
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == dotted_name
        ):
            return node
    raise AssertionError(f"Definition not found in AST: {dotted_name}")
