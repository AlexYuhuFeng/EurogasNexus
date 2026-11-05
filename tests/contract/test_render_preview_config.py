"""Keep the optional Render deployment on tested main and current toolchains."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_render_tracks_main_and_waits_for_ci():
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    service = blueprint["services"][0]
    assert service["branch"] == "main"
    assert service["autoDeployTrigger"] == "checksPass"
    assert service["plan"] == "free"
    assert blueprint["databases"][0]["plan"] == "free"


def test_render_toolchains_do_not_drift_from_repository():
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    variables = {row["key"]: row for row in blueprint["services"][0]["envVars"]}
    assert variables["PYTHON_VERSION"]["value"] == (ROOT / ".python-version").read_text().strip()
    assert variables["NODE_VERSION"]["value"] == (ROOT / ".nvmrc").read_text().strip()
