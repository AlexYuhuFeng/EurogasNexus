"""AI controls at run time (GOV-1, AI controls stage 2): switch, provenance, tool allowlists.

Every model call in the product goes through :func:`governed_model` (a call bound to one
registered use) or, where a route calls the provider itself, :func:`provenance` and
:func:`ai_use_enabled`. What that gives, per call:

* **A switch per AI use.** The organisation setting ``ai_features`` (``PUT
  /api/settings/organisation``, administrators, audited as a governed write) turns a use off;
  an off use makes no provider call and the reader gets the deterministic rule text with basis
  ``rule`` (H5). No setting means on. A store that is configured but cannot be read means off.
* **Provenance on the audit row.** The use, its prompt version and prompt fingerprint, the
  model id the installation is configured with, whether that model was evaluated for this
  prompt version, and SHA-256 hashes of the input messages and of the output. Hashes, never
  the text, so an audit row holds no commercial content.
* **Tool allowlists.** A capability call made on behalf of an AI use is refused unless the
  register allows it for the use and for one of the caller's roles
  (``domain/ai/register.tool_refusal``); the refusal is audited.

AI 运行时管控：每项 AI 功能的开关、审计行上的提示词版本/模型/输入输出哈希、按角色的工具白名单。
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from collections.abc import Callable
from typing import Any

from eurogas_nexus.domain.ai.register import (
    AI_FEATURES_SETTING,
    AI_USES,
    AiUse,
    ai_use,
    tool_refusal,
)

#: Most input/output hash pairs kept on one audit row (a report may call several times).
MAX_HASHED_CALLS = 20


def sha256_text(value: Any) -> str:
    """SHA-256 of a text, or of a JSON-serialised value."""

    text = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, default=str
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_part(ref: str) -> str:
    """The text a prompt reference stands for: a function's source, or a constant's repr."""

    module_name, _, attribute = ref.partition(":")
    module = importlib.import_module(f"eurogas_nexus.{module_name}")
    value = getattr(module, attribute)
    if inspect.isfunction(value) or inspect.isclass(value):
        return inspect.getsource(value)
    return repr(value)


def prompt_fingerprint(use: str | AiUse) -> str:
    """SHA-256 over the use's prompt parts and tools: any change to either changes it."""

    item = use if isinstance(use, AiUse) else ai_use(use)
    parts = [f"{ref}\n{prompt_part(ref)}" for ref in item.prompt_refs]
    parts.append("tools:" + ",".join(item.tools))
    return sha256_text("\n\n".join(parts))


def configured_model_id() -> str:
    """The model id the installation is configured to call (``EUROGAS_NEXUS_LLM_MODEL``)."""

    from eurogas_nexus.llm.provider import LlmEndpointError, configured_endpoint

    try:
        return configured_endpoint().model
    except LlmEndpointError:
        return "unconfigured"


def evaluation_record(use: str) -> dict[str, Any] | None:
    """What the evaluation gate recorded for this use, or ``None``."""

    from eurogas_nexus.domain.ai.evaluation_record import EVALUATION_RECORD

    return EVALUATION_RECORD.get(use)


def model_evaluated(use: str, model_id: str) -> bool:
    """Whether this model was evaluated for the use's current prompt version."""

    record = evaluation_record(use)
    if record is None:
        return False
    return record.get("prompt_version") == ai_use(use).prompt_version and model_id in (
        record.get("model_ids") or []
    )


# --------------------------------------------------------------------------------- switch


def ai_switches(session: Any | None = None) -> dict[str, bool]:
    """Every registered use with whether it is on; missing settings mean on.

    Raises:
        Exception: the store could not be read (callers treat that as off).
    """

    stored: dict[str, Any] = {}
    if session is not None:
        stored = _stored_switches(session)
    else:
        from eurogas_nexus.db.session import get_session_factory, resolve_database_url

        if resolve_database_url() is not None:
            with get_session_factory()() as own:
                stored = _stored_switches(own)
    return {item.use: stored.get(item.use, True) is not False for item in AI_USES}


def _stored_switches(session: Any) -> dict[str, Any]:
    from eurogas_nexus.db.models import OrganisationSettingRecord

    row = session.get(OrganisationSettingRecord, AI_FEATURES_SETTING)
    value = row.value_json if row is not None else None
    return dict(value) if isinstance(value, dict) else {}


def ai_use_enabled(use: str, session: Any | None = None) -> bool:
    """Whether the organisation has this AI use switched on (fails closed on a read error)."""

    ai_use(use)  # an unregistered use is a programming error, not "off"
    try:
        return ai_switches(session)[use]
    except Exception:  # noqa: BLE001 - a store that cannot be read switches AI off, not on
        return False


# ----------------------------------------------------------------------------- provenance


def provenance(
    use: str,
    *,
    messages: Any,
    output: str | None,
    status: str,
    model_id: str | None = None,
) -> dict[str, Any]:
    """The audit facts of one model call: versions and hashes, never the text."""

    item = ai_use(use)
    model = model_id or configured_model_id()
    return {
        "use": use,
        "prompt_version": item.prompt_version,
        "prompt_fingerprint": prompt_fingerprint(item)[:16],
        "model_id": model,
        "model_evaluated": model_evaluated(use, model),
        "input_sha256": sha256_text(messages),
        "output_sha256": sha256_text(output) if output is not None else None,
        "status": status,
    }


def provenance_summary(calls: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One audit summary for the calls a request made: shared versions, per-call hashes."""

    if not calls:
        return None
    first = calls[0]
    return {
        "ai": {
            "use": first["use"],
            "prompt_version": first["prompt_version"],
            "prompt_fingerprint": first["prompt_fingerprint"],
            "model_id": first["model_id"],
            "model_evaluated": first["model_evaluated"],
            "calls": len(calls),
            "hashes": [
                {
                    "input_sha256": call["input_sha256"],
                    "output_sha256": call["output_sha256"],
                    "status": call["status"],
                }
                for call in calls[:MAX_HASHED_CALLS]
            ],
        }
    }


class GovernedModel:
    """A model call bound to one registered AI use that records each call's provenance.

    ``call`` takes the messages and returns ``(content, status)``; this object is what the
    application code receives as its ``model`` and calls with the messages only.
    """

    def __init__(self, use: str, call: Callable[[list[dict[str, str]]], tuple[str | None, str]]):
        ai_use(use)
        self.use = use
        self._call = call
        self.calls: list[dict[str, Any]] = []

    def __call__(self, messages: list[dict[str, str]]) -> str | None:
        content, status = self._call(messages)
        self.calls.append(provenance(self.use, messages=messages, output=content, status=status))
        return content

    def audit_summary(self) -> dict[str, Any] | None:
        return provenance_summary(self.calls)


def governed_model(use: str, *, api_key: str, budget: dict[str, Any]) -> GovernedModel:
    """The provider call for one registered use, bounded by its call budget."""

    from eurogas_nexus.llm import invoke_deepseek

    def call(messages: list[dict[str, str]]) -> tuple[str | None, str]:
        result = invoke_deepseek(api_key=api_key, messages=messages, **budget)
        return (result.content if result.status == "success" else None), result.status

    return GovernedModel(use, call)


# --------------------------------------------------------------------------------- tools


def ai_tool_refusal(use: str, roles: list[str] | tuple[str, ...], capability_id: str) -> str:
    """Why a model acting for this use and these roles may not call the capability, or ``""``.

    The switch is part of the answer: a use that is off may call nothing.
    """

    refusal = tool_refusal(use, roles, capability_id)
    if refusal:
        return refusal
    if not ai_use_enabled(use):
        return f"AI use {use!r} is switched off in organisation settings"
    return ""


def record_ai_tool_refusal(
    *, use: str, principal_id: str, capability_id: str, reason: str, request_id: str | None
) -> None:
    """Audit a refused model tool call (best-effort: the refusal itself never depends on it)."""

    from eurogas_nexus.application.audit_service import record_audit_event

    record_audit_event(
        event_type="governance.ai_tools",
        action="ai.tool.refused",
        resource=f"capability:{capability_id}"[:128],
        principal=principal_id[:64],
        outcome="denied",
        severity="warning",
        detail=f"use={use}; {reason}"[:900],
        source_system="agent-runtime",
        request_id=request_id,
    )


__all__ = [
    "GovernedModel",
    "ai_switches",
    "ai_tool_refusal",
    "ai_use_enabled",
    "configured_model_id",
    "evaluation_record",
    "governed_model",
    "model_evaluated",
    "prompt_fingerprint",
    "provenance",
    "provenance_summary",
    "record_ai_tool_refusal",
    "sha256_text",
]
