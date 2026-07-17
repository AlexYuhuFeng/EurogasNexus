"""Product boundary tests for the V1.0 bootstrap shell."""

import subprocess
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
    "src/eurogas_nexus/api/routes/public",
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
    script = (
        "from apps.api.main import app; import sys; "
        "from fastapi.testclient import TestClient; "
        "print(TestClient(app).get('/api/health').status_code == 200); "
        "print('eurogas_nexus.db' in sys.modules); "
        "print('sqlalchemy' in sys.modules)"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == ["True", "False", "False"]


def test_agent_instructions_capture_decision_support_boundary() -> None:
    instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "market-intelligence, optimization, and" in instructions
    assert "human_review_required" in instructions
    assert "`meta.research_only` remains only" in instructions
    assert "Do not reintroduce `/v1` or `/api/v1` aliases" in instructions
    assert "PostgreSQL is the runtime source of truth" in instructions
    assert "SDK and CLI code must call the backend API" in instructions
    assert ".agent/plans/" in instructions
