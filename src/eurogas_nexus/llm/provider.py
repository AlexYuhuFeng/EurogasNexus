"""Which language model the installation talks to, and how.

Every supported provider is reached through the OpenAI-compatible chat-completions API:
DeepSeek (the default), OpenAI and Azure OpenAI, Mistral, Alibaba Qwen, and self-hosted
servers such as vLLM or Ollama. The endpoint is installation configuration, so the
China installation can use an in-country model and a European one an EU-hosted or
on-premises model, without code changes (docs/architecture/GLOBAL_DEPLOYMENT.md).

The base URL must be HTTPS. Plain HTTP is accepted only for a model served on the same
host or private network (``localhost``, loopback or RFC 1918 addresses), which is how an
on-premises model is usually deployed.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_PROVIDER_NAME = "DEEPSEEK"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


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


def configured_endpoint(environ: Mapping[str, str] | None = None) -> LlmEndpoint:
    """The installation's endpoint from ``EUROGAS_NEXUS_LLM_*``; DeepSeek when unset."""

    env = os.environ if environ is None else environ
    base_url = str(env.get("EUROGAS_NEXUS_LLM_BASE_URL") or "").strip() or DEFAULT_BASE_URL
    model = str(env.get("EUROGAS_NEXUS_LLM_MODEL") or "").strip() or DEFAULT_MODEL
    name = str(env.get("EUROGAS_NEXUS_LLM_PROVIDER_NAME") or "").strip() or DEFAULT_PROVIDER_NAME
    return LlmEndpoint(
        provider_name=name.upper()[:32],
        base_url=validate_base_url(base_url),
        model=model[:128],
    )
