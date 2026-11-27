"""Which language model the installation talks to, and how.

Every supported provider is reached through the OpenAI-compatible chat-completions API:
DeepSeek, OpenAI and Azure OpenAI, Mistral, Alibaba Qwen, and self-hosted servers such as
vLLM or Ollama. There is no default provider (security review M10): an installation names its
endpoint in ``EUROGAS_NEXUS_LLM_BASE_URL``, and until it does no prompt leaves the server.
The endpoint is installation configuration, so the
China installation can use an in-country model and a European one an EU-hosted or
on-premises model, without code changes (docs/architecture/GLOBAL_DEPLOYMENT.md).

The base URL must be HTTPS. Plain HTTP is accepted only for a model served on the same
host or private network (``localhost``, loopback or RFC 1918 addresses), which is how an
on-premises model is usually deployed. A model on the firm's own network may run without a
key (vLLM and Ollama need none by default): :func:`key_required` says whether one is needed.

Every call has a hard time limit (:func:`call_timeout_seconds`): interactive uses wait at most
``EUROGAS_NEXUS_AI_TIMEOUT_SECONDS`` (default 3 s, small-desk plan section 5), drafts that a
person reads later (the market report editor, the alert enrichment worker) at most
``EUROGAS_NEXUS_AI_DRAFT_TIMEOUT_SECONDS`` (default 240 s). After it the caller carries on
without the model's text.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_PROVIDER_NAME = "CONFIGURED"
#: Kept for the setup guidance that names DeepSeek as one choice; never used implicitly.
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


#: Interactive calls: the reader is waiting on a page (small-desk plan section 5: 3 s).
DEFAULT_INTERACTIVE_TIMEOUT_SECONDS = 3.0
#: Drafts a person reads later (a market report, a background alert note).
DEFAULT_DRAFT_TIMEOUT_SECONDS = 240.0
INTERACTIVE_TIMEOUT_ENV = "EUROGAS_NEXUS_AI_TIMEOUT_SECONDS"
DRAFT_TIMEOUT_ENV = "EUROGAS_NEXUS_AI_DRAFT_TIMEOUT_SECONDS"
#: The bounds a configured value must sit in; outside them the default applies.
_TIMEOUT_BOUNDS = {"interactive": (0.5, 60.0), "draft": (1.0, 900.0)}


def call_timeout_seconds(timing: str = "interactive",
                         environ: Mapping[str, str] | None = None) -> float:
    """The hard time limit of one model call of this timing (``interactive`` or ``draft``)."""

    env = os.environ if environ is None else environ
    if timing == "draft":
        raw, default = env.get("EUROGAS_NEXUS_AI_DRAFT_TIMEOUT_SECONDS"), (
            DEFAULT_DRAFT_TIMEOUT_SECONDS
        )
    else:
        timing = "interactive"
        raw = env.get("EUROGAS_NEXUS_AI_TIMEOUT_SECONDS")
        default = DEFAULT_INTERACTIVE_TIMEOUT_SECONDS
    low, high = _TIMEOUT_BOUNDS[timing]
    try:
        value = float(str(raw or "").strip())
    except ValueError:
        return default
    return value if low <= value <= high else default


class LlmEndpointError(ValueError):
    """An endpoint configuration the installation must not use."""


@dataclass(frozen=True)
class LlmEndpoint:
    provider_name: str
    base_url: str
    model: str


def _private_host(host: str) -> bool:
    if host in {"localhost"} or host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def validate_base_url(base_url: str) -> str:
    """Return the normalised base URL or raise for an unsafe one."""

    parts = urlsplit(base_url.strip())
    if parts.scheme not in {"https", "http"} or not parts.hostname:
        raise LlmEndpointError("LLM base URL must be an http(s) URL with a host")
    if parts.username or parts.password:
        raise LlmEndpointError("LLM base URL must not carry credentials")
    if parts.scheme == "http" and not _private_host(parts.hostname):
        raise LlmEndpointError("plain HTTP is allowed only for a model on a private network")
    return base_url.strip().rstrip("/")


def private_endpoint(base_url: str) -> bool:
    """Whether the endpoint is a model on the firm's own network (on-premises)."""

    host = urlsplit(base_url.strip()).hostname or ""
    return _private_host(host)


def key_required(environ: Mapping[str, str] | None = None) -> bool:
    """Whether a call needs an API key: yes, unless the model is on the firm's own network.

    A self-hosted endpoint (``private_endpoint``) is called without an ``Authorization``
    header when no key is stored; one that does need a key answers 401 and the caller carries
    on without the model, as for any failed call.
    """

    try:
        endpoint = configured_endpoint(environ)
    except LlmEndpointError:
        return True
    return not private_endpoint(endpoint.base_url)


def configured_endpoint(environ: Mapping[str, str] | None = None) -> LlmEndpoint:
    """The installation's endpoint from ``EUROGAS_NEXUS_LLM_*``.

    Raises:
        LlmEndpointError: no endpoint is configured (there is no default provider), or the
            configured one is unsafe.
    """

    env = os.environ if environ is None else environ
    base_url = str(env.get("EUROGAS_NEXUS_LLM_BASE_URL") or "").strip()
    if not base_url:
        raise LlmEndpointError(
            "no model provider is configured: set EUROGAS_NEXUS_LLM_BASE_URL to the endpoint "
            "this installation has chosen"
        )
    model = str(env.get("EUROGAS_NEXUS_LLM_MODEL") or "").strip() or DEFAULT_MODEL
    name = str(env.get("EUROGAS_NEXUS_LLM_PROVIDER_NAME") or "").strip() or DEFAULT_PROVIDER_NAME
    return LlmEndpoint(
        provider_name=name.upper()[:32],
        base_url=validate_base_url(base_url),
        model=model[:128],
    )
