"""AI controls at run time (GOV-1, AI controls stage 2): switch, provenance, tool allowlists.

Every model call in the product goes through :func:`governed_model` (a call bound to one
registered use) or, where a route calls the provider itself, :func:`provenance` and
:func:`ai_use_enabled`. What that gives, per call:

* **One switch for all AI, and a switch per AI use.** The organisation setting ``ai_enabled``
  (``false``) turns every AI feature off at once (small-desk plan section 3 item 6); the
  setting ``ai_features`` turns one use off (``PUT /api/settings/organisation``,
  administrators, audited as a governed write). An off use makes no provider call and the
  reader gets the deterministic rule text with basis ``rule`` (H5). No setting means on. A
  store that is configured but cannot be read means off. The provider adapter checks the
  master switch again before it opens any connection (``llm/deepseek.py``).
* **What may be sent** (``ai_data_sharing``): counterparty names and deal-level data are not
  sent unless an administrator switched that category on (:func:`ai_sharing`). Names are
  replaced by aliases on the way out and restored in the reply (:class:`GovernedModel`).
* **A hard time limit per call**: ``interactive`` uses 3 s by default, ``draft`` uses longer
  (:func:`call_budget`, ``llm/provider.call_timeout_seconds``).
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
    AI_ENABLED_SETTING,
    AI_FEATURES_SETTING,
    AI_SHARING_CATEGORIES,
    AI_SHARING_SETTING,
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


def _stored(session: Any | None, key: str) -> Any:
    """One organisation setting's stored value, or ``None`` (no store, or not set).

    Raises:
        Exception: the store is configured but could not be read.
    """

    from eurogas_nexus.db.models import OrganisationSettingRecord

    if session is not None:
        row = session.get(OrganisationSettingRecord, key)
        return row.value_json if row is not None else None
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        return None
    with get_session_factory()() as own:
        row = own.get(OrganisationSettingRecord, key)
        return row.value_json if row is not None else None


def ai_enabled(session: Any | None = None) -> bool:
    """The administrator's one switch for all AI (``ai_enabled``); not set means on.

    Fails closed: a store that is configured and cannot be read means off.
    """

    try:
        return _stored(session, AI_ENABLED_SETTING) is not False
    except Exception:  # noqa: BLE001 - a store that cannot be read switches AI off, not on
        return False


def ai_sharing(session: Any | None = None) -> dict[str, bool]:
    """Which data categories the administrator allows to be sent; every one off by default."""

    try:
        stored = _stored(session, AI_SHARING_SETTING)
    except Exception:  # noqa: BLE001 - unreadable means nothing extra is sent
        stored = None
    stored = stored if isinstance(stored, dict) else {}
    return {name: stored.get(name) is True for name in AI_SHARING_CATEGORIES}


def ai_switches(session: Any | None = None) -> dict[str, bool]:
    """Every registered use with whether it is on; missing settings mean on.

    Every use is off while the administrator's master switch (``ai_enabled``) is off.

    Raises:
        Exception: the store could not be read (callers treat that as off).
    """

    if _stored(session, AI_ENABLED_SETTING) is False:
        return {item.use: False for item in AI_USES}
    stored = _stored(session, AI_FEATURES_SETTING)
    stored = dict(stored) if isinstance(stored, dict) else {}
    return {item.use: stored.get(item.use, True) is not False for item in AI_USES}


def call_budget(use: str, budget: dict[str, Any]) -> dict[str, Any]:
    """A use's call budget with its hard time limit (``interactive`` or ``draft`` timing)."""

    from eurogas_nexus.llm.provider import call_timeout_seconds

    return {**budget, "timeout_seconds": call_timeout_seconds(ai_use(use).timing)}


def provider_key(loader: Callable[[str], str | None] | None = None) -> str | None:
    """The key a model call sends: the stored one; ``""`` for a keyless self-hosted model.

    ``None`` means no call can be made (a key is needed and none is stored).
    """

    from eurogas_nexus.llm.provider import key_required

    if loader is None:
        from eurogas_nexus.security.provider_keys import load_provider_api_key

        loader = load_provider_api_key
    key = loader("DEEPSEEK") or loader("LLM")
    if key:
        return key
    return None if key_required() else ""


def ai_state(*, role_denied: bool = False) -> dict[str, Any]:
    """Whether AI can be used for this caller now, why not, and what an administrator set.

    ``role_denied``: the API layer found the caller may not use AI (``ai_authority_denial``).

    ``reason``: ``on``; ``switched_off`` (the administrator's switch, or the installation's
    ``EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED``); ``not_configured`` (no endpoint);
    ``no_key``; ``role`` (the caller may not use AI). Never raises.
    """

    from eurogas_nexus.core.config import get_settings
    from eurogas_nexus.llm.provider import (
        LlmEndpointError,
        call_timeout_seconds,
        configured_endpoint,
        private_endpoint,
    )

    provider: dict[str, Any] | None = None
    reason = "on"
    try:
        endpoint = configured_endpoint()
        provider = {
            "name": endpoint.provider_name,
            "model": endpoint.model,
            "self_hosted": private_endpoint(endpoint.base_url),
        }
    except LlmEndpointError:
        reason = "not_configured"
    try:
        if not get_settings().llm_external_provider_enabled or not ai_enabled():
            reason = "switched_off"
        elif reason == "on" and provider_key() is None:
            reason = "no_key"
        elif reason == "on" and role_denied:
            reason = "role"
    except Exception:  # noqa: BLE001 - an incomplete set-up reads as unavailable, never a failure
        reason = "switched_off" if reason == "on" else reason
    return {
        "available": reason == "on",
        "reason": reason,
        "provider": provider,
        "timeouts_seconds": {
            "interactive": call_timeout_seconds("interactive"),
            "draft": call_timeout_seconds("draft"),
        },
        "sharing": ai_sharing(),
    }


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

    def __init__(
        self,
        use: str,
        call: Callable[[list[dict[str, str]]], tuple[str | None, str]],
        *,
        aliases: Any | None = None,
    ):
        ai_use(use)
        self.use = use
        self._call = call
        #: Counterparty aliases (``ai_payloads.CounterpartyAliases``) while names may not be
        #: sent; ``None`` when the administrator allows them.
        self._aliases = aliases
        self.calls: list[dict[str, Any]] = []

    def __call__(self, messages: list[dict[str, str]]) -> str | None:
        sent = self._aliases.hide_messages(messages) if self._aliases is not None else messages
        content, status = self._call(sent)
        self.calls.append(provenance(self.use, messages=sent, output=content, status=status))
        if content is not None and self._aliases is not None:
            content = self._aliases.restore(content)
        return content

    def audit_summary(self) -> dict[str, Any] | None:
        return provenance_summary(self.calls)


def governed_model(use: str, *, api_key: str | None, budget: dict[str, Any]) -> GovernedModel:
    """The provider call for one registered use, bounded by its budget and its time limit.

    Counterparty names are aliased unless the administrator allows them (``ai_sharing``).
    """

    from eurogas_nexus.llm import invoke_deepseek

    bounded = call_budget(use, budget)

    def call(messages: list[dict[str, str]]) -> tuple[str | None, str]:
        result = invoke_deepseek(api_key=api_key, messages=messages, **bounded)
        return (result.content if result.status == "success" else None), result.status

    return GovernedModel(use, call, aliases=counterparty_aliases())


def counterparty_aliases(session: Any | None = None) -> Any | None:
    """The aliases that keep counterparty names on the platform, or ``None`` when allowed."""

    if ai_sharing(session).get("counterparty_names"):
        return None
    from eurogas_nexus.application.ai_payloads import CounterpartyAliases

    # The names are read in a session of their own (cached): the caller's session may hold
    # changes a failed read must not roll back.
    return CounterpartyAliases.from_store()


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
    "ai_enabled",
    "ai_sharing",
    "ai_state",
    "ai_switches",
    "call_budget",
    "counterparty_aliases",
    "provider_key",
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
