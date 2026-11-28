"""CODEX-1: the capability runtime controls the Codex agentisation review found missing.

The review (``research/agentic-decision-architecture``, ``AGENTISATION_ARCHITECTURE_REVIEW.md``)
found that the runtime skipped completion metadata on an early refusal, never set the output
hash, did not check a result against its declared output schema, did not report a handler
that overran its declared timeout, reported every result as ``VERIFIED`` and took a
confirmation from whoever sent the flag. Each test pins one of those.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from eurogas_nexus.application.agents import runtime as runtime_module
from eurogas_nexus.application.agents.registry import CapabilityRegistry
from eurogas_nexus.application.agents.runtime import (
    CapabilityRuntime,
    declared_timeout_seconds,
    output_problem,
)
from eurogas_nexus.domain.agents.contracts import (
    ActionPolicy,
    AgentInvocationContext,
    CapabilityDefinition,
    CapabilityDomain,
    CapabilityFailureCode,
    CapabilityResult,
    DeterminismClass,
    SideEffectClass,
)


def _definition(capability_id: str, **overrides: Any) -> CapabilityDefinition:
    fields: dict[str, Any] = {
        "capability_id": capability_id,
        "name": capability_id,
        "domain": CapabilityDomain.MARKET,
        "description": "test capability",
        "input_schema": {"type": "object", "properties": {"x": {"type": "number"}}},
        "output_schema": {"type": "object", "required": ["value"]},
        "determinism_class": DeterminismClass.DETERMINISTIC,
    }
    fields.update(overrides)
    return CapabilityDefinition(**fields)


def _runtime(definition: CapabilityDefinition, data: Any = None, *, sleep: float = 0.0):
    def handler(arguments: dict, context: AgentInvocationContext) -> CapabilityResult:
        if sleep:
            time.sleep(sleep)
        return CapabilityResult.success(
            capability=definition.capability_id,
            capability_version=definition.capability_version,
            data={"value": arguments.get("x", 1)} if data is None else data,
        )

    registry = CapabilityRegistry()
    registry.register(definition, handler)
    return CapabilityRuntime(registry)


def _person(**overrides: Any) -> AgentInvocationContext:
    fields: dict[str, Any] = {
        "principal_id": "user:analyst-1",
        "principal_type": "USER",
        "role": "ANALYST",
        "roles": ["ANALYST"],
        "data_scopes": ["*"],
        "agent_run_id": "run-1",
    }
    fields.update(overrides)
    return AgentInvocationContext(**fields)


@pytest.fixture
def audit_rows(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def record(**fields: Any) -> str:
        rows.append(fields)
        return f"evt-{len(rows)}"

    monkeypatch.setattr(
        "eurogas_nexus.application.audit_service.record_audit_event", record
    )
    return rows


def test_a_refusal_is_traced_like_a_run() -> None:
    runtime = _runtime(_definition("test.read", required_permissions=["review.record"]))
    viewer = _person(role="VIEWER", roles=["VIEWER"])

    unknown = runtime.invoke("test.missing", {"x": 1}, viewer)
    denied = runtime.invoke("test.read", {"x": 1}, viewer)

    for result, capability in ((unknown, "test.missing"), (denied, "test.read")):
        assert result.status == "BLOCKED"
        metadata = result.execution_metadata
        assert metadata.capability_id == capability
        assert metadata.principal_id == "user:analyst-1"
        assert metadata.agent_run_id == "run-1"
        assert metadata.input_hash and metadata.completed_at_utc is not None
        assert metadata.duration_ms is not None
        assert metadata.output_hash is None
    assert unknown.execution_metadata.capability_version == "unknown"
    assert denied.execution_metadata.capability_version == "v1"
    assert denied.failure.code == CapabilityFailureCode.PERMISSION_DENIED


def test_a_success_carries_a_reproducible_output_hash() -> None:
    runtime = _runtime(_definition("test.read"))

    first = runtime.invoke("test.read", {"x": 2}, _person())
    second = runtime.invoke("test.read", {"x": 2}, _person())
    other = runtime.invoke("test.read", {"x": 3}, _person())

    assert first.status == "SUCCESS"
    assert first.execution_metadata.output_hash == second.execution_metadata.output_hash
    assert first.execution_metadata.input_hash == second.execution_metadata.input_hash
    assert other.execution_metadata.output_hash != first.execution_metadata.output_hash


def test_a_result_that_breaks_its_declared_shape_is_refused() -> None:
    wrong_type = _runtime(_definition("test.read"), data=[1, 2, 3])
    missing_field = _runtime(_definition("test.read"), data={"other": 1})

    for runtime, fragment in ((wrong_type, "expected object"), (missing_field, "value")):
        result = runtime.invoke("test.read", {"x": 1}, _person())
        assert result.status == "BLOCKED"
        assert result.failure.code == CapabilityFailureCode.INTERNAL_ERROR
        assert "output_schema" in result.failure.detail and fragment in result.failure.detail
        assert result.data is None


def test_a_handler_that_returns_no_result_envelope_is_refused() -> None:
    registry = CapabilityRegistry()
    registry.register(_definition("test.read"), lambda arguments, context: {"value": 1})

    result = CapabilityRuntime(registry).invoke("test.read", {}, _person())

    assert result.status == "BLOCKED"
    assert "did not return a CapabilityResult" in result.failure.detail


def test_output_problem_follows_the_declared_subset() -> None:
    assert output_problem({"value": 1}, {"type": "object", "required": ["value"]}) == ""
    assert output_problem({}, {}) == ""
    assert "expected number" in output_problem(True, {"type": "number"})
    assert "expected array" in output_problem({"a": 1}, {"type": "array"})
    assert "unsupported" in output_problem(1, {"type": "tuple"})


def test_an_overrun_of_the_declared_timeout_is_reported() -> None:
    runtime = _runtime(_definition("test.read", timeout_policy="1ms"), sleep=0.02)

    result = runtime.invoke("test.read", {"x": 1}, _person())

    assert result.status == "SUCCESS"
    assert any(item.startswith("TIMEOUT_OVERRUN") for item in result.warnings)
    on_time = _runtime(_definition("test.read")).invoke("test.read", {"x": 1}, _person())
    assert not any(item.startswith("TIMEOUT_OVERRUN") for item in on_time.warnings)


def test_declared_timeouts_parse() -> None:
    assert declared_timeout_seconds("30s") == 30
    assert declared_timeout_seconds("120s") == 120
    assert declared_timeout_seconds("2m") == 120
    assert declared_timeout_seconds("250ms") == 0.25
    assert declared_timeout_seconds("none") is None


def test_a_result_states_no_quality_it_did_not_check() -> None:
    result = _runtime(_definition("test.read")).invoke("test.read", {"x": 1}, _person())

    assert result.quality_state == "NOT_ASSESSED"


@pytest.mark.parametrize(
    ("context", "fragment"),
    [
        (_person(human_confirmation=False), "Human confirmation is required"),
        (_person(human_confirmation=True, ai_use="mcp_tools"), "cannot confirm"),
        (
            _person(
                principal_id="service:public-api",
                principal_type="SERVICE",
                human_confirmation=True,
            ),
            "signed-in person",
        ),
    ],
)
def test_only_a_persons_own_confirmation_counts(context, fragment, audit_rows) -> None:
    # An id the mcp_tools allowlist names, so the register's list (which runs first) lets
    # the use reach it: the refusal below is the runtime's own rule.
    runtime = _runtime(
        _definition(
            "review.get",
            action_policy=ActionPolicy.HUMAN_CONFIRMATION,
            side_effect_class=SideEffectClass.RESEARCH_OBJECT_WRITE,
        )
    )

    result = runtime.invoke("review.get", {"x": 1}, context)

    assert result.status == "BLOCKED"
    assert result.failure.code == CapabilityFailureCode.HUMAN_CONFIRMATION_REQUIRED
    assert fragment in result.failure.detail
    actions = [row["action"] for row in audit_rows]
    if context.human_confirmation:
        assert actions == ["agent.capability.confirmation_refused"]
        assert audit_rows[0]["outcome"] == "denied"
    else:
        # A writing capability's call is audited even when it is refused for want of a
        # confirmation; nobody claimed to confirm, so nothing was refused as a confirmation.
        assert actions == ["agent.capability.invoked"]
        assert audit_rows[0]["outcome"] == "blocked"


def test_a_persons_confirmation_runs_and_is_audited_with_the_version(audit_rows) -> None:
    runtime = _runtime(
        _definition(
            "test.write",
            action_policy=ActionPolicy.HUMAN_CONFIRMATION,
            side_effect_class=SideEffectClass.RESEARCH_OBJECT_WRITE,
            capability_version="v3",
        )
    )

    result = runtime.invoke(
        "test.write",
        {"x": 1},
        _person(human_confirmation=True, confirmation_note="checked the spec"),
    )

    assert result.status == "SUCCESS"
    (row,) = audit_rows
    assert row["action"] == "agent.capability.confirmed"
    assert row["principal"] == "user:analyst-1"
    assert row["resource"] == "capability:test.write@v3"
    assert row["outcome"] == "success"
    assert f"input_hash={result.execution_metadata.input_hash}" in row["detail"]
    assert f"output_hash={result.execution_metadata.output_hash}" in row["detail"]
    assert "note=checked the spec" in row["detail"]
    # The audit row holds hashes, never the arguments or the output.
    assert "'x'" not in row["detail"] and "value" not in row["detail"]


def test_a_read_is_not_audited_and_a_write_is(audit_rows) -> None:
    read = _runtime(_definition("test.read"))
    write = _runtime(
        _definition("test.write", side_effect_class=SideEffectClass.RESEARCH_OBJECT_WRITE)
    )

    read.invoke("test.read", {"x": 1}, _person())
    assert audit_rows == []
    write.invoke("test.write", {"x": 1}, _person())
    assert [row["action"] for row in audit_rows] == ["agent.capability.invoked"]
    assert "side_effect=RESEARCH_OBJECT_WRITE" in audit_rows[0]["detail"]


def test_a_missing_audit_store_never_changes_the_result(monkeypatch) -> None:
    def broken(**fields: Any) -> None:
        return None

    monkeypatch.setattr("eurogas_nexus.application.audit_service.record_audit_event", broken)
    runtime = _runtime(
        _definition("test.write", side_effect_class=SideEffectClass.RESEARCH_OBJECT_WRITE)
    )

    assert runtime.invoke("test.write", {"x": 1}, _person()).status == "SUCCESS"


def test_the_runtime_module_documents_the_controls() -> None:
    text = runtime_module.__doc__ or ""
    for phrase in ("refusals included", "output_schema", "signed-in person", "timeout_policy"):
        assert phrase in text
