"""Outbound HTTP settings for connectors that must not trust the whole environment.

Several official-source connectors build their HTTP client with ``trust_env=False`` on
purpose: a stray ``.netrc`` credential or an environment-wide setting must never reach an
official download. That also dropped the two settings a trading house's network cannot
work without, the corporate proxy and the corporate CA bundle (TLS inspection), so on a
typical customer network those connectors could not connect at all.

:func:`client_options` gives those clients exactly those two settings and nothing else:

* the proxy from ``HTTPS_PROXY`` (or ``https_proxy``), unless the target host matches
  ``NO_PROXY``;
* the CA bundle from ``SSL_CERT_FILE`` (or ``REQUESTS_CA_BUNDLE``), else the system
  default certifi bundle.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit


def _first(environ, *names: str) -> str:
    for name in names:
        value = (environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _bypassed(host: str, no_proxy: str) -> bool:
    for entry in (item.strip().lower() for item in no_proxy.split(",") if item.strip()):
        if entry == "*":
            return True
        entry = entry.lstrip(".")
        if host == entry or host.endswith("." + entry):
            return True
    return False


def client_options(url: str, environ=None) -> dict[str, Any]:
    """``proxy`` and ``verify`` keyword arguments for an ``httpx.Client`` reaching ``url``."""

    env = os.environ if environ is None else environ
    options: dict[str, Any] = {}
    proxy = _first(env, "HTTPS_PROXY", "https_proxy")
    host = (urlsplit(url).hostname or "").lower()
    if proxy and not _bypassed(host, _first(env, "NO_PROXY", "no_proxy")):
        options["proxy"] = proxy
    bundle = _first(env, "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")
    if bundle and os.path.exists(bundle):
        options["verify"] = bundle
    return options
