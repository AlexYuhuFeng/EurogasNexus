"""The shipped alert rules read metrics the product exports and point at a written response.

An alert on a metric name nobody exports never fires, and an alert without a runbook leaves
the person paged guessing. ``promtool`` (when installed) also checks the expressions and runs
the rule unit tests beside the rules.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "deploy" / "monitoring" / "prometheus" / "eurogas-nexus-alerts.yml"
RULE_TESTS = RULES.with_name("eurogas-nexus-alerts.test.yml")
RUNBOOK = ROOT / "docs" / "operations" / "ALERT_RESPONSES.md"
METRIC_SOURCES = (
    ROOT / "src" / "eurogas_nexus" / "application" / "process_metrics.py",
    ROOT / "src" / "eurogas_nexus" / "application" / "dataops_observability.py",
    ROOT / "src" / "eurogas_nexus" / "api" / "middleware" / "metrics_endpoint.py",
)


def _rules() -> list[dict]:
    document = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return [rule for group in document["groups"] for rule in group["rules"]]


def _exported_names() -> set[str]:
    names: set[str] = set()
    for path in METRIC_SOURCES:
        text = path.read_text(encoding="utf-8")
        names.update(re.findall(r'"(eurogas_[a-z0-9_]+)"', text))
        # Families written as literal exposition text ("# TYPE <name> gauge").
        names.update(re.findall(r"# TYPE (eurogas_[a-z0-9_]+)", text))
    # prometheus_client suffixes: counters _total, histograms _bucket/_sum/_count.
    names |= {f"{name}_total" for name in names}
    names |= {f"{name}{suffix}" for name in names for suffix in ("_bucket", "_sum", "_count")}
    return names


def test_every_rule_is_complete() -> None:
    rules = _rules()
    assert len(rules) >= 10
    for rule in rules:
        assert rule["alert"].startswith("Eurogas"), rule
        assert rule["labels"]["severity"] in {"critical", "warning"}, rule["alert"]
        for key in ("summary", "description", "runbook_url"):
            assert rule["annotations"].get(key), (rule["alert"], key)


def test_every_metric_in_an_expression_is_exported() -> None:
    exported = _exported_names()
    for rule in _rules():
        used = set(re.findall(r"\beurogas_[a-z0-9_]+", rule["expr"]))
        missing = used - exported
        assert not missing, f"{rule['alert']} reads metrics nobody exports: {missing}"


def test_every_alert_has_a_runbook_section() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    anchors = {
        re.sub(r"[^a-z0-9 -]", "", heading.strip().lower()).replace(" ", "-")
        for heading in re.findall(r"^#{2,3} (.+)$", text, flags=re.MULTILINE)
    }
    for rule in _rules():
        anchor = rule["annotations"]["runbook_url"].split("#", 1)[1]
        assert anchor == rule["alert"].lower()
        assert anchor in anchors, f"ALERT_RESPONSES.md has no section for {rule['alert']}"


def test_the_stopped_scheduler_alert_is_unit_tested() -> None:
    """Phase 1 exit criterion: an alert fires on a stopped scheduler."""

    tests = yaml.safe_load(RULE_TESTS.read_text(encoding="utf-8"))
    tested = {
        case["alertname"]
        for test in tests["tests"]
        for case in test.get("alert_rule_test", [])
        if case.get("exp_alerts")
    }
    assert "EurogasSchedulerHeartbeatMissing" in tested


@pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool not installed")
def test_promtool_accepts_the_rules_and_their_unit_tests() -> None:
    subprocess.run(["promtool", "check", "rules", str(RULES)], check=True)  # noqa: S603,S607
    subprocess.run(  # noqa: S603
        ["promtool", "test", "rules", RULE_TESTS.name],  # noqa: S607
        check=True,
        cwd=RULE_TESTS.parent,
    )
