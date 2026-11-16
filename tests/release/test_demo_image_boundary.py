"""The root Dockerfile is the hosted test/demo server image and stays out of customer delivery.

``docker build .`` and most tools build ``./Dockerfile`` by default, so the demo image lives
there and ``deploy/demo/compose.yaml`` runs it; the
customer runtime image is ``deploy/runtime/Dockerfile.api`` and is the only one the release
workflow builds. These checks keep the two from leaking into each other.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "Dockerfile"
CUSTOMER = ROOT / "deploy" / "runtime" / "Dockerfile.api"


def test_root_dockerfile_declares_itself_the_demo_image_and_points_to_the_customer_one():
    text = DEMO.read_text(encoding="utf-8")
    header = text.split("FROM ", 1)[0]
    assert "NOT the customer runtime" in header
    assert "deploy/runtime/Dockerfile.api" in header
    assert "docs/deployment/SELF_HOSTED_DEMO.md" in header
    assert 'CMD ["python", "scripts/demo/start_public_demo.py", "serve"]' in text
    assert "USER eurogas" in text
    # Pinned base images, as the customer image pins them.
    for line in re.findall(r"(?m)^FROM\s+(\S+)", text):
        assert "@sha256:" in line, line


def test_release_workflow_builds_only_the_customer_image():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    files = re.findall(r"(?m)^\s*file:\s*(\S+)", workflow)
    assert files and set(files) == {"deploy/runtime/Dockerfile.api"}
    parsed = yaml.safe_load(workflow)
    assert parsed  # the workflow still parses


def test_customer_image_carries_no_demo_payload_or_web_serving():
    text = CUSTOMER.read_text(encoding="utf-8")
    assert "scripts/demo" not in text
    assert "start_public_demo" not in text
    assert "EUROGAS_NEXUS_WEB_CLIENT_DIR" not in text
    assert "clients/" not in text
    policy = json.loads(
        (ROOT / "scripts/release/runtime_artifact_policy.json").read_text(encoding="utf-8")
    )
    assert not any(path.startswith("scripts/demo/") for path in policy["runtime_scripts"])
    bundle = json.loads(
        (ROOT / "scripts/release/package_deployment_bundle.policy.json").read_text(
            encoding="utf-8"
        )
    )
    sources = [entry["source"] for entry in bundle["entries"]]
    assert "Dockerfile" not in sources
    assert not any(source.startswith("scripts/demo/") for source in sources)


def test_build_context_keeps_secrets_and_local_state_out():
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for entry in (
        ".git", ".env", ".env.*", "**/.env", ".dnx*", "**/.dnx*", ".automation",
        "**/node_modules", "**/dist", "**/*.pem", "**/*.key", "data", "tests", "docs",
    ):
        assert entry in ignore, entry
    # The demo image builds the web client from source, so its sources stay in the context.
    assert "clients" not in ignore
    assert "clients/web" not in ignore
