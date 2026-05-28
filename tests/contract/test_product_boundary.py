"""Product boundary tests for the V1.0 bootstrap shell."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


EXPECTED_DIRECTORIES = [
    ".agent/plans",
    "apps/api",
    "apps/worker",
    "apps/scheduler",
    "src/eurogas_nexus/core",
    "src/eurogas_nexus/db",
    "src/eurogas_nexus/runtime_store",
    "src/eurogas_nexus/api/routes/v1",
    "src/eurogas_nexus/domain/market",
    "src/eurogas_nexus/application/workflows",
    "src/eurogas_nexus/infrastructure/connectors",
    "src/eurogas_nexus/ingestion/normalization",
    "src/eurogas_nexus/data_quality",
    "src/eurogas_nexus/streaming",
    "src/eurogas_nexus/auth_runtime",
    "src/eurogas_nexus/audit",
    "src/eurogas_nexus/governance",
    "src/eurogas_nexus/sdk",
    "src/eurogas_nexus/cli",
    "clients/web",
    "clients/desktop",
    "packages/python-sdk",
    "release/v1",
    "dist/releases",
    "infra/deployment",
    "docs/contracts",
    "tests/release",
    "scripts/release",
    "data/test_fixtures",
    "alembic",
]

FORBIDDEN_DEPENDENCY_TOKENS = [
    "redis",
    "celery",
    "kafka",
    "confluent-kafka",
    "react",
    "tauri",
    "electron",
]


def test_expected_product_directories_exist() -> None:
    missing = [path for path in EXPECTED_DIRECTORIES if not (ROOT / path).is_dir()]

    assert missing == []


def test_pyproject_excludes_deferred_heavy_dependencies() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    forbidden = [token for token in FORBIDDEN_DEPENDENCY_TOKENS if token in pyproject]

    assert forbidden == []


def test_api_import_does_not_load_database_layer() -> None:
    # Remove modules that prior tests may have loaded so the check is
    # meaningful.
    for module_name in list(sys.modules):
        if module_name == "eurogas_nexus.db" or module_name.startswith("eurogas_nexus.db."):
            sys.modules.pop(module_name, None)
        if module_name == "sqlalchemy" or module_name.startswith("sqlalchemy."):
            sys.modules.pop(module_name, None)

    from apps.api.main import app

    assert any(route.path == "/v1/health" for route in app.routes)
    assert "eurogas_nexus.db" not in sys.modules
    assert "sqlalchemy" not in sys.modules


def test_agent_instructions_capture_research_only_boundary() -> None:
    instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "research-only" in instructions
    assert "PostgreSQL is the runtime source of truth" in instructions
    assert "SDK and CLI code must call the backend API" in instructions
    assert ".agent/plans/" in instructions
