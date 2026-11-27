"""GOV-1, AI controls stage 2: the AI-use register, the switch and the tool allowlists."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from eurogas_nexus.application import ai_controls
from eurogas_nexus.application.agents.registry import register_builtin_capabilities
from eurogas_nexus.application.agents.runtime import CapabilityRuntime
from eurogas_nexus.application.ai_controls import (
    GovernedModel,
    ai_tool_refusal,
    prompt_part,
    provenance,
    provenance_summary,
)
from eurogas_nexus.domain.agents.contracts import AgentInvocationContext
from eurogas_nexus.domain.ai.register import (
    AI_USES,
    AI_USES_BY_NAME,
    LEVELS,
    NEVER_MODEL_TOOLS,
    ROLE_TOOL_ALLOWLIST,
    ai_use,
    tool_refusal,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "eurogas_nexus"

#: The only modules that may call the provider directly; each must bind a registered use.
PROVIDER_CALLERS = {
    "llm/__init__.py",
    "llm/deepseek.py",
    "application/ai_controls.py",
    "api/routes/public/analysis.py",
    "api/routes/public/monitoring.py",
    "application/monitoring_service.py",
}


def _capability_ids() -> set[str]:
    return {d.capability_id for d in register_builtin_capabilities().list_definitions()}


def _matches(capability_id: str, pattern: str) -> bool:
    return capability_id == pattern or (
        pattern.endswith("*") and capability_id.startswith(pattern[:-1])
    )


def test_every_use_is_described_completely() -> None:
    assert len({item.use for item in AI_USES}) == len(AI_USES) == len(AI_USES_BY_NAME)
    for item in AI_USES:
        assert item.title and item.owner and item.purpose, item.use
        assert item.level in LEVELS, item.use
        assert item.surfaces and item.data and item.controls, item.use
        assert item.prompt_refs and item.prompt_version, item.use
        assert (ROOT / item.evaluation_set).is_file(), item.use
        assert 0 < item.threshold <= 1, item.use
        assert re.fullmatch(r"note_cases:\w+(:ask|:alert)?|pytest:tests/\S+\.py", item.scorer)
        if item.scorer.startswith("pytest:"):
            assert (ROOT / item.scorer.partition(":")[2]).is_file(), item.use
        for ref in item.prompt_refs:
            assert prompt_part(ref), ref


def test_an_unregistered_use_cannot_be_called_or_switched() -> None:
    with pytest.raises(KeyError):
        ai_use("free_text")
    with pytest.raises(KeyError):
        GovernedModel("free_text", lambda _m: ("x", "success"))
    with pytest.raises(KeyError):
        ai_controls.ai_use_enabled("free_text")


def test_only_pinned_modules_call_the_provider_and_each_binds_a_registered_use() -> None:
    callers = {
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if re.search(r"\binvoke_deepseek\(", path.read_text(encoding="utf-8"))
    }
    assert callers <= PROVIDER_CALLERS, sorted(callers - PROVIDER_CALLERS)
    for name in ("api/routes/public/analysis.py", "api/routes/public/monitoring.py",
                 "application/monitoring_service.py"):
        text = (SRC / name).read_text(encoding="utf-8")
        assert "ai_use_enabled(" in text and "provenance(" in text, name
    bound = set()
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        bound.update(re.findall(r'(?:ai_use_enabled|governed_model|provenance)\(\s*"(\w+)"', text))
        bound.update(re.findall(r'_model_for\([^)]*use="(\w+)"', text))
    assert bound and bound <= set(AI_USES_BY_NAME), sorted(bound - set(AI_USES_BY_NAME))


def test_every_tool_pattern_names_a_real_capability() -> None:
    capabilities = _capability_ids()
    patterns = {p for item in AI_USES for p in item.tools}
    patterns |= {p for allowed in ROLE_TOOL_ALLOWLIST.values() for p in allowed}
    dead = sorted(p for p in patterns if not any(_matches(c, p) for c in capabilities))
    assert dead == []
    assert NEVER_MODEL_TOOLS <= capabilities


@pytest.mark.parametrize(
    ("use", "roles", "capability", "allowed"),
    [
        ("mcp_tools", ["ANALYST"], "market.get_curve", True),
        ("mcp_tools", ["VIEWER"], "analytics.correlation", False),  # role allowlist
        ("mcp_tools", ["ANALYST"], "dataset.build", False),  # not a tool of the use
        ("explain", ["ANALYST"], "market.get_curve", False),  # a note use calls no tool
        ("unknown", ["ANALYST"], "market.get_curve", False),
    ],
)
def test_tool_refusal(use, roles, capability, allowed) -> None:
    assert (tool_refusal(use, roles, capability) == "") is allowed


def test_never_tools_are_refused_whatever_the_role() -> None:
    for capability in NEVER_MODEL_TOOLS:
        for role in ROLE_TOOL_ALLOWLIST:
            for item in AI_USES:
                assert tool_refusal(item.use, [role], capability)


def test_a_switched_off_use_may_call_no_tool(monkeypatch) -> None:
    monkeypatch.setattr(ai_controls, "ai_use_enabled", lambda use, session=None: False)
    assert "switched off" in ai_tool_refusal("mcp_tools", ["ANALYST"], "market.get_curve")


def test_the_runtime_refuses_a_model_tool_call_outside_the_allowlist(monkeypatch) -> None:
    refused: list[dict] = []
    monkeypatch.setattr(ai_controls, "record_ai_tool_refusal", lambda **k: refused.append(k))
    runtime = CapabilityRuntime(register_builtin_capabilities())
    context = AgentInvocationContext(
        principal_id="service:mcp", role="VIEWER", roles=["VIEWER"], ai_use="mcp_tools"
    )
    result = runtime.invoke("analytics.correlation", {}, context)
    assert result.status != "success"
    assert "ai_tool_not_allowed" in result.model_dump_json()
    assert refused and refused[0]["capability_id"] == "analytics.correlation"
    # The same call made by a person directly is not judged by the model allowlist.
    direct = runtime.invoke(
        "analytics.correlation", {}, context.model_copy(update={"ai_use": None})
    )
    assert "ai_tool_not_allowed" not in direct.model_dump_json()


def test_mcp_runs_as_its_registered_use() -> None:
    from eurogas_nexus.mcp.server import _agent_context

    assert _agent_context().ai_use == "mcp_tools"


def test_provenance_holds_versions_and_hashes_never_the_text(monkeypatch) -> None:
    monkeypatch.setattr(ai_controls, "configured_model_id", lambda: "deepseek-v4-flash")
    model = GovernedModel("explain", lambda _m: ("TTF rose on Norwegian outages.", "success"))
    messages = [{"role": "user", "content": "secret desk position 40 MW"}]
    assert model(messages) == "TTF rose on Norwegian outages."
    summary = model.audit_summary()["ai"]
    assert summary["use"] == "explain"
    assert summary["prompt_version"] == ai_use("explain").prompt_version
    assert summary["model_id"] == "deepseek-v4-flash"
    assert summary["model_evaluated"] is True
    assert summary["calls"] == 1 and len(summary["hashes"][0]["input_sha256"]) == 64
    assert "secret" not in repr(summary) and "Norwegian" not in repr(summary)
    other = provenance("explain", messages=messages, output=None, status="timeout",
                       model_id="another-model")
    assert other["model_evaluated"] is False and other["output_sha256"] is None
    assert provenance_summary([]) is None
