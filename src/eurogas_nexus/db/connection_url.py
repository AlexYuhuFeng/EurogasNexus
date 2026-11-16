"""Turn a platform-issued PostgreSQL URI into the URL and connect arguments pg8000 needs.

Managed PostgreSQL services (Heroku-style ``DATABASE_URL``s, Aiven, most cloud
consoles) hand out a libpq URI such as
``postgresql://user:pass@host:5432/db?sslmode=require`` or the older ``postgres://``
form. The product's locked runtime driver is pg8000, and two things in such a URI do
not reach it as written:

* ``postgres://`` and ``postgresql://`` select SQLAlchemy's default psycopg2 driver,
  which is not installed;
* ``sslmode`` is a libpq option. pg8000 takes an ``ssl_context`` object instead, and
  passing ``sslmode`` through raises ``TypeError`` at the first connection.

:func:`normalize_database_url` rewrites the scheme, and :func:`pg8000_ssl_arguments`
moves ``sslmode`` out of the URL into an ``ssl_context`` with libpq's meaning:

``disable``                    no TLS (``ssl_context=False``)
``allow``, ``prefer``          TLS when the server offers it, unverified, plain otherwise
                               (pg8000's own default, so nothing is passed)
``require``                    TLS required, certificate not verified (libpq's ``require``)
``verify-ca``                  TLS, certificate chain verified, host name not checked
``verify-full``                TLS, chain and host name verified

A URL without ``sslmode`` is returned unchanged, so existing deployments behave exactly
as before.
"""

from __future__ import annotations

import os
import ssl
from collections.abc import Mapping
from typing import Any

from sqlalchemy.engine import URL, make_url

#: CA certificate for ``verify-ca``/``verify-full``: a file path or the PEM text itself.
DB_SSL_ROOT_CERT_ENV = "EUROGAS_NEXUS_DB_SSL_ROOT_CERT"
_SSL_MODES = frozenset({"disable", "allow", "prefer", "require", "verify-ca", "verify-full"})


class DatabaseUrlError(ValueError):
    """The supplied database URL cannot be used by the runtime driver."""


def normalize_database_url(raw: str) -> str:
    """Return ``raw`` with its scheme pointing at the pg8000 driver.

    ``postgres://``, ``postgresql://`` and ``postgresql+psycopg2://`` become
    ``postgresql+pg8000://``; a URL already naming pg8000 (or another backend, such as
    SQLite in tests) is returned unchanged. Query parameters, including ``sslmode``,
    are kept; :func:`pg8000_ssl_arguments` consumes them at engine creation.

    Raises:
        DatabaseUrlError: when ``raw`` is blank or names a scheme that is not a
            database URL at all.
    """

    value = (raw or "").strip()
    if not value:
        raise DatabaseUrlError("database URL is empty")
    scheme, separator, rest = value.partition("://")
    if not separator:
        raise DatabaseUrlError("database URL has no scheme (expected postgresql://...)")
    lowered = scheme.lower()
    if lowered in {"postgres", "postgresql", "postgresql+psycopg2", "postgresql+psycopg"}:
        return f"postgresql+pg8000://{rest}"
    return value


def _root_certificate(
    parsed: URL, environ: Mapping[str, str] | None
) -> tuple[str | None, str | None]:
    """Return ``(cafile, cadata)`` from ``sslrootcert`` in the URL or the CA variable."""

    raw = parsed.query.get("sslrootcert")
    from_url = (raw[-1] if isinstance(raw, tuple) else raw or "").strip()
    if from_url:
        return from_url, None
    source = os.environ if environ is None else environ
    value = (source.get(DB_SSL_ROOT_CERT_ENV) or "").strip()
    if not value:
        return None, None
    if value.startswith("-----BEGIN"):
        return None, value
    return value, None


def pg8000_ssl_arguments(
    url: str | URL, environ: Mapping[str, str] | None = None
) -> tuple[URL, dict[str, Any]]:
    """Split libpq TLS options out of a pg8000 URL into pg8000's ``ssl_context``.

    ``sslmode`` is mapped as the module docstring describes. A CA certificate, from the
    libpq ``sslrootcert`` URL parameter (a file path) or from ``EUROGAS_NEXUS_DB_SSL_ROOT_CERT``
    (a file path, or the PEM text itself), is the trust anchor for ``verify-ca`` and
    ``verify-full``; as in libpq, giving one with ``require`` (or no ``sslmode``) upgrades
    the connection to ``verify-ca``. Without one, verification uses the system trust store.

    Returns:
        The URL without the TLS parameters and the connect arguments to add (an empty dict
        when the URL carries none of them or does not use pg8000).

    Raises:
        DatabaseUrlError: for an ``sslmode`` value libpq does not define, a client
            certificate (not supported by this driver set-up), or an unreadable CA file.
    """

    parsed = make_url(url) if isinstance(url, str) else url
    if not parsed.drivername.endswith("+pg8000"):
        return parsed, {}
    for unsupported in ("sslcert", "sslkey"):
        if unsupported in parsed.query:
            raise DatabaseUrlError(
                f"{unsupported} (client certificate authentication) is not supported"
            )
    cafile, cadata = _root_certificate(parsed, environ)
    raw_mode = parsed.query.get("sslmode")
    mode = (raw_mode[-1] if isinstance(raw_mode, tuple) else raw_mode or "").strip().lower()
    if not mode and not (cafile or cadata):
        return parsed.difference_update_query(["sslrootcert"]), {}
    stripped = parsed.difference_update_query(["sslmode", "sslrootcert"])
    if mode and mode not in _SSL_MODES:
        raise DatabaseUrlError(
            f"unsupported sslmode {mode!r}; expected one of {', '.join(sorted(_SSL_MODES))}"
        )
    if mode == "disable":
        return stripped, {"ssl_context": False}
    if (cafile or cadata) and mode in {"", "allow", "prefer", "require"}:
        mode = "verify-ca"
    if mode in {"allow", "prefer"}:
        return stripped, {}
    try:
        context = ssl.create_default_context(cafile=cafile, cadata=cadata)
    except (OSError, ssl.SSLError) as exc:
        raise DatabaseUrlError(f"the database CA certificate cannot be loaded: {exc}") from exc
    if mode == "require":
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif mode == "verify-ca":
        context.check_hostname = False
    return stripped, {"ssl_context": context}
