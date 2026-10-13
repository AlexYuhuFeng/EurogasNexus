"""GIE AGSI/ALSI fetch-only transport (real provider HTTP, fail-closed).

Why this module exists
----------------------
The registered ``GIE`` source had a connector shell that inherited
``MockConnector`` and returned an empty payload, while the live ingestion path
fetched exactly one page with a ``limit`` parameter. Neither was the provider's
documented interface, and an empty payload could be mistaken for "no data" rather
than "no credential".

This module owns the real, bounded, read-only transport for the two GIE products
and nothing else. It fetches, validates the provider envelope and page identity,
and returns in-memory pages. It never writes to the database, never analyses and
never substitutes synthetic data.

Provider contract (GIE API documentation v013, "7.1 AGSI / ALSI" and "6.4
Importing data"):

* endpoint ``https://agsi.gie.eu/api`` / ``https://alsi.gie.eu/api``;
* header ``x-key: <api key>``;
* query ``type=eu`` selects the Europe dataset; ``page`` starts at 1; ``size``
  defaults to 30 and accepts at most 300 entries;
* the JSON envelope carries ``last_page`` (pages available for the query),
  ``total`` (entries **on this page**, not the provider grand total),
  ``dataset`` and the ``data`` array;
* an invalid or missing key is answered with HTTP 200 and
  ``{"error": "access denied", "dataset": "storage ERROR" | "lng ERROR"}`` --
  a 200 is therefore *not* evidence of a working credential.

AGSI and ALSI are kept as separate product identities: each page is tagged with
its product, each product has its own record signature fields, and a response
that carries the other product's fields is refused as a product mismatch.

Credential handling
-------------------
``resolve_gie_api_key`` applies a deterministic precedence: ``GIE_API_KEY``,
then the ``GIE_API_KEY_FILE`` secret file, then an injected encrypted
credential-store lookup. The key value is held in a dataclass whose ``repr`` is
suppressed, is sent only in the ``x-key`` header to the two official hosts, and
is never included in an exception message, URL or log line.

Credential boundary
-------------------
Before any credential-bearing request the endpoint is validated: HTTPS, the
product's own official host (AGSI can never reach the ALSI host and vice versa),
the standard 443 port, no userinfo and the documented ``/api`` path. Redirects
are disabled per request regardless of the injected client's default, so a
provider 3xx is refused instead of being followed to a foreign host that would
then receive the ``x-key`` header.

Provider text is untrusted
--------------------------
Error bodies can echo the submitted credential. ``error``, ``message`` and
``dataset`` text is inspected in memory only, to classify the failure; exception
messages carry a stable taxonomy and never the raw provider text, and decode
failures are reported without chaining the original exception.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

__all__ = [
    "GIE_ALLOWED_HOSTS",
    "GIE_API_KEY_ENV",
    "GIE_API_KEY_FILE_ENV",
    "GIE_CONNECTION_TEST_PAGE_SIZE",
    "GIE_ENDPOINT_PATH",
    "GIE_HARD_MAX_PAGES",
    "GIE_HTTPS_PORT",
    "GIE_MAX_PAGE_SIZE",
    "GIE_PRODUCT_HOSTS",
    "GIE_SOURCE_ID",
    "GieApiKey",
    "GieAuthenticationError",
    "GieConnectivityCheck",
    "GieCredentialDisabledError",
    "GieCredentialFileError",
    "GieCredentialMissingError",
    "GieCredentialStateUnreadableError",
    "GieCredentialStatus",
    "GieEmptyResponseError",
    "GieEndpointRefusedError",
    "GieFetchResult",
    "GieHttpError",
    "GieMalformedResponseError",
    "GiePage",
    "GiePaginationError",
    "GieProduct",
    "GieProductMismatchError",
    "GieProviderError",
    "GieRateLimitedError",
    "GieRedirectRefusedError",
    "GieSourceDisabledError",
    "GieTimeoutError",
    "GieTransportError",
    "GieTruncationError",
    "fetch_gie_page",
    "fetch_gie_product",
    "gie_source_operation_enabled",
    "resolve_gie_api_key",
    "resolve_gie_credential_status",
    "resolve_gie_runtime_api_key",
    "resolve_gie_runtime_credential_status",
    "stored_gie_credential_status",
    "stored_gie_credential_value",
    "test_gie_connection",
]

#: Endpoints named by the provider documentation. Only these two hosts may ever
#: receive the credential.
DEFAULT_AGSI_ENDPOINT = "https://agsi.gie.eu/api"
DEFAULT_ALSI_ENDPOINT = "https://alsi.gie.eu/api"
GIE_ALLOWED_HOSTS = frozenset({"agsi.gie.eu", "alsi.gie.eu"})

#: Documented endpoint path and the standard HTTPS port for the two hosts.
GIE_ENDPOINT_PATH = "/api"
GIE_HTTPS_PORT = 443

#: Per-product official host. The credential is refused before send unless the
#: endpoint is the product's own host, so AGSI can never reach ALSI and vice versa.
GIE_PRODUCT_HOSTS = {"AGSI": "agsi.gie.eu", "ALSI": "alsi.gie.eu"}

#: ``size`` maximum stated by the provider documentation.
GIE_MAX_PAGE_SIZE = 300
#: Bounded connection-test page size: one page per product is the operator probe.
GIE_CONNECTION_TEST_PAGE_SIZE = 30
#: Absolute page ceiling for one ingest call, independent of the operator budget.
GIE_HARD_MAX_PAGES = 50
_GIE_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_GIE_MAX_RETRY_DELAY_SECONDS = 30.0
_GIE_DEFAULT_ATTEMPTS = 3

GIE_API_KEY_ENV = "GIE_API_KEY"
GIE_API_KEY_FILE_ENV = "GIE_API_KEY_FILE"
#: A key file larger than this is refused rather than read (misconfiguration).
GIE_MAX_KEY_FILE_BYTES = 4096
#: Registry id of the single GIE source whose runtime operation controls both products.
GIE_SOURCE_ID = "src-gie"


class GieTransportError(RuntimeError):
    """A GIE transport failure with a stable machine-readable ``code``.

    The message never contains the API key: callers pass only provider error
    text, HTTP status or configuration paths.
    """

    code = "gie_transport_error"

    def __init__(
        self,
        message: str,
        *,
        product: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.product = product
        self.status_code = status_code


class GieCredentialMissingError(GieTransportError):
    """No GIE credential is configured for a required fetch."""

    code = "gie_credential_missing"


class GieCredentialFileError(GieTransportError):
    """A configured ``GIE_API_KEY_FILE`` could not be read as a key."""

    code = "gie_key_file_unreadable"


class GieCredentialDisabledError(GieTransportError):
    """The stored GIE credential was explicitly disabled by the operator.

    The disable is authoritative at the runtime fetch boundary too: environment
    or file precedence must never silently re-enable a credential the operator
    turned off.
    """

    code = "gie_credential_disabled"


class GieSourceDisabledError(GieTransportError):
    """The GIE source runtime operation was explicitly disabled by the operator."""

    code = "gie_source_disabled"


class GieCredentialStateUnreadableError(GieTransportError):
    """The operator credential/source state could not be read, so it is not a permit.

    An absent state row (no override configured) is not an error; a failed read
    is. Fail closed rather than treating an unreadable control as consent.
    """

    code = "gie_credential_state_unreadable"


class GieAuthenticationError(GieTransportError):
    """The provider refused the credential (including its HTTP 200 error body)."""

    code = "gie_access_denied"


class GieProviderError(GieTransportError):
    """The provider reported an error that is not a credential refusal."""

    code = "gie_provider_error"


class GieRateLimitedError(GieTransportError):
    """The provider kept returning 429 after the bounded retries."""

    code = "gie_rate_limited"


class GieHttpError(GieTransportError):
    """A non-success HTTP status that is not authentication or rate limiting."""

    code = "gie_http_error"


class GieEndpointRefusedError(GieTransportError):
    """The endpoint is not the product's own official HTTPS endpoint.

    Raised before any credential-bearing request so a plaintext URL, the other
    product's host, a non-standard port or a userinfo-laden URL can never see the
    ``x-key`` header.
    """

    code = "gie_endpoint_refused"


class GieRedirectRefusedError(GieTransportError):
    """The provider answered with a 3xx; redirects are never followed with a key."""

    code = "gie_redirect_refused"


class GieTimeoutError(GieTransportError):
    """The provider did not answer within the client timeout."""

    code = "gie_timeout"


class GieMalformedResponseError(GieTransportError):
    """The response was not the documented JSON envelope."""

    code = "gie_malformed_response"


class GieEmptyResponseError(GieTransportError):
    """The provider returned no data where data was required."""

    code = "gie_empty_response"


class GieProductMismatchError(GieTransportError):
    """The response does not carry the requested product's identity or fields."""

    code = "gie_product_mismatch"


class GiePaginationError(GieTransportError):
    """The page sequence is not consistent (repeated page or changed last_page)."""

    code = "gie_pagination_error"


class GieTruncationError(GieTransportError):
    """An empty page arrived before the provider's advertised last page."""

    code = "gie_truncated_response"


@dataclass(frozen=True)
class GieProduct:
    """One GIE product identity (AGSI storage or ALSI LNG)."""

    product: str
    endpoint_url: str
    dataset: str
    error_token: str
    signature_fields: tuple[str, ...]
    selector: tuple[tuple[str, str], ...] = (("type", "eu"),)

    @classmethod
    def agsi(cls, endpoint_url: str = DEFAULT_AGSI_ENDPOINT) -> GieProduct:
        """Return the AGSI (storage) product identity."""

        return cls(
            product="AGSI",
            endpoint_url=endpoint_url,
            dataset="EU",
            error_token="storage",
            signature_fields=("gasInStorage", "workingGasVolume"),
        )

    @classmethod
    def alsi(cls, endpoint_url: str = DEFAULT_ALSI_ENDPOINT) -> GieProduct:
        """Return the ALSI (LNG) product identity."""

        return cls(
            product="ALSI",
            endpoint_url=endpoint_url,
            dataset="EU",
            error_token="lng",
            signature_fields=("inventory", "dtmi", "sendOut"),
        )

    @property
    def host(self) -> str:
        """Hostname of the endpoint (validated against the allow-list on use)."""

        return urlsplit(self.endpoint_url).hostname or ""


@dataclass(frozen=True)
class GieApiKey:
    """A resolved GIE credential.

    ``value`` is excluded from ``repr`` so an accidental log of the object cannot
    disclose it.
    """

    value: str = field(repr=False)
    source: str

    def redacted(self) -> str:
        """Return a short masked preview, never the key itself."""

        if len(self.value) <= 4:
            return "*" * len(self.value)
        return f"{self.value[:2]}***{self.value[-2:]}"


@dataclass(frozen=True)
class GieConnectivityCheck:
    """One product's bounded connection-test outcome (aggregate metadata only).

    Carries the HTTP status, provider envelope size and normalized row count --
    never a raw provider record or payload body. ``error_code`` stays ``None`` on
    a fully successful bounded page.
    """

    product: str
    ok: bool
    error_code: str | None
    http_status: int | None
    record_count: int
    normalized_rows: int
    provider_last_page: int | None
    page_size: int | None
    complete: bool | None
    response_date: str | None
    bounded_partial: bool


@dataclass(frozen=True)
class GiePage:
    """One validated provider page.

    ``received_at_utc`` is captured after the HTTP response has arrived (the
    response body is fully read by the non-streaming client), so it is the real
    receipt instant rather than the pre-request wall clock.
    """

    product: str
    page: int
    size: int
    last_page: int
    total_on_page: int
    dataset: str
    gas_day: str | None
    records: tuple[dict[str, Any], ...]
    received_at_utc: datetime
    status_code: int
    response_date: str | None
    raw_payload: dict[str, Any] = field(repr=False)

    @property
    def source_reference(self) -> str:
        """Stable per-page lineage reference (no credential content)."""

        return f"gie-{self.product.lower()}-api:page={self.page};size={self.size}"


@dataclass(frozen=True)
class GieFetchResult:
    """Result of a bounded product fetch.

    ``complete`` is True only when every provider page up to ``last_page`` was
    read. A ``False`` value is an honest bounded partial result, never a claim of
    full history. The bounds are reported separately so a floored budget cannot
    be mistaken for the requested one: ``records`` is the retained subset,
    ``record_capacity`` is the largest number of records the fetched pages could
    hold, and ``budget_records`` is the operator's requested budget (or the
    capacity when no explicit record budget was given).

    An unchanged ``last_page`` between pages is **not** treated as proof of a
    single provider snapshot: the provider exposes no revision or snapshot
    token, so only overlapping natural keys and a changed ``last_page`` are
    detectable here.
    """

    product: str
    pages: tuple[GiePage, ...]
    records: tuple[dict[str, Any], ...]
    provider_last_page: int
    complete: bool
    stop_reason: str
    budget_records: int
    page_size: int
    pages_allowed: int
    record_capacity: int
    partial_reason: str | None

    @property
    def source_reference(self) -> str:
        """Honest aggregate lineage reference (page count + completeness)."""

        if self.complete:
            suffix = "complete=true"
        else:
            suffix = f"complete=false;stop={self.stop_reason}"
        return (
            f"gie-{self.product.lower()}-api:pages="
            f"{len(self.pages)}/{self.provider_last_page};{suffix}"
        )


@dataclass(frozen=True)
class GieCredentialStatus:
    """Secret-safe GIE credential status derived from the shared resolver.

    This is the single shape every surface (credential API, source status,
    connection test) derives from, so runtime resolution and reported status can
    never disagree. It carries **no** secret value, no fingerprint fragment and
    no filesystem path -- only booleans, a stable source kind and stable
    diagnostic codes.
    """

    configured: bool
    source_kind: str
    blocked: bool
    diagnostics: tuple[str, ...] = ()
    support_flags: tuple[str, ...] = ()

    @property
    def operator_disabled(self) -> bool:
        """Whether the operator disabled the stored credential this status keeps blocked."""

        return self.blocked and self.source_kind == "operator_disabled"


def resolve_gie_api_key(
    environ: Mapping[str, str] | None = None,
    *,
    credential_lookup: Callable[[], str | None] | None = None,
) -> GieApiKey | None:
    """Resolve the GIE credential with deterministic precedence.

    Order: ``GIE_API_KEY``, then ``GIE_API_KEY_FILE`` (a secret file outside the
    repository), then the injected encrypted credential store. A configured but
    unreadable/blank key file is an explicit error, not a silent fall-through to
    a different credential source.

    Args:
        environ: Environment mapping; defaults to ``os.environ``.
        credential_lookup: Optional callable returning the decrypted key from the
            credential store.

    Returns:
        The resolved key and its source, or ``None`` when none is configured.

    Raises:
        GieCredentialFileError: When ``GIE_API_KEY_FILE`` is set but cannot be
            read as a non-empty key.
    """

    env = os.environ if environ is None else environ

    raw_env_key = str(env.get(GIE_API_KEY_ENV) or "").strip()
    if raw_env_key:
        return GieApiKey(value=raw_env_key, source="env")

    key_file = str(env.get(GIE_API_KEY_FILE_ENV) or "").strip()
    if key_file:
        return GieApiKey(value=_read_gie_key_file(key_file), source="file")

    if credential_lookup is not None:
        stored = str(credential_lookup() or "").strip()
        if stored:
            return GieApiKey(value=stored, source="credential_store")

    return None


def resolve_gie_credential_status(
    environ: Mapping[str, str] | None = None,
    *,
    credential_lookup: Callable[[], str | None] | None = None,
    stored_credential_status: Callable[[], str | None] | None = None,
    source_operation_enabled: Callable[[], bool | None] | None = None,
) -> GieCredentialStatus:
    """Derive the secret-safe GIE credential status from the same resolution order.

    Resolution matches :func:`resolve_gie_api_key` exactly (``GIE_API_KEY``, then
    ``GIE_API_KEY_FILE``, then the encrypted store), so the reported status can
    never disagree with the credential a live fetch would use. The returned
    object contains only a configured boolean, a stable source kind, stable
    diagnostic codes and support flags -- never the key, a fragment of it, or the
    external path.

    Operator-disabled precedence: a stored credential the operator marked
    ``disabled`` is authoritative -- it must not silently become enabled through
    environment/file precedence, so a disabled stored status is reported blocked
    even when ``GIE_API_KEY``/``GIE_API_KEY_FILE`` is also set. A source runtime
    state the operator disabled blocks the status regardless of any credential
    source. With no operator disable, the documented precedence holds and an
    external env/file credential is reported configured -- that is the path for an
    owner-managed key that stays outside the repository.

    Absent vs unreadable state: a callback that returns ``None`` means the state
    row is absent, which is **no override** and keeps the documented precedence.
    A callback that raises means the state could not be read; that is **not** a
    confirmed permit, so the status is blocked with the stable
    ``credential_state_unreadable`` / ``source_operation_state_unreadable``
    diagnostic instead of quietly permitting the credential.

    Args:
        environ: Environment mapping; defaults to ``os.environ``.
        credential_lookup: Callable returning the decrypted stored key.
        stored_credential_status: Callable returning the stored credential's
            status (``configured``/``disabled``) or ``None`` when absent. It may
            raise when the store cannot be read.
        source_operation_enabled: Callable returning the source operation's
            operator-controlled enabled flag, or ``None`` when no runtime state
            row exists. It may raise when the state cannot be read.

    Returns:
        A :class:`GieCredentialStatus`; the status never raises for a
        misconfigured key file -- that is reported as a stable diagnostic code.
    """

    env = os.environ if environ is None else environ
    diagnostics: list[str] = []
    support_flags = ["connection_test", "agsi", "alsi"]

    env_key_present = bool(str(env.get(GIE_API_KEY_ENV) or "").strip())
    key_file = str(env.get(GIE_API_KEY_FILE_ENV) or "").strip()

    stored_status: str = ""
    stored_state_unreadable = False
    if stored_credential_status is not None:
        try:
            stored_status = str(stored_credential_status() or "").strip()
        except Exception:  # noqa: BLE001 - an unreadable state is not a permit
            stored_state_unreadable = True
    stored_disabled = stored_status == "disabled"

    source_operation_state: bool | None = None
    source_state_unreadable = False
    if source_operation_enabled is not None:
        try:
            source_operation_state = source_operation_enabled()
        except Exception:  # noqa: BLE001 - an unreadable state is not a permit
            source_state_unreadable = True

    def blocked(source_kind: str, code: str) -> GieCredentialStatus:
        return GieCredentialStatus(
            configured=False,
            source_kind=source_kind,
            blocked=True,
            diagnostics=(*diagnostics, code),
            support_flags=tuple(support_flags),
        )

    # Explicit operator disables are authoritative and are decided before any
    # environment/file precedence. An unreadable operator state, by contrast, is
    # not a confirmed permit and must also fail closed -- but it is reported with
    # its own diagnostic so it is never mistaken for an explicit disable.
    if source_operation_state is False:
        return blocked("operator_disabled", "source_operation_disabled")
    if stored_disabled:
        return blocked("operator_disabled", "credential_disabled")
    if source_state_unreadable:
        return blocked("state_unreadable", "source_operation_state_unreadable")
    if stored_state_unreadable:
        return blocked("state_unreadable", "credential_state_unreadable")

    if env_key_present:
        return GieCredentialStatus(
            configured=True,
            source_kind="env",
            blocked=False,
            diagnostics=tuple(diagnostics),
            support_flags=tuple(support_flags),
        )

    if key_file:
        try:
            _read_gie_key_file(key_file)
        except GieTransportError as exc:
            diagnostics.append(exc.code)
            return GieCredentialStatus(
                configured=False,
                source_kind="file_unreadable",
                blocked=True,
                diagnostics=tuple(diagnostics),
                support_flags=tuple(support_flags),
            )
        return GieCredentialStatus(
            configured=True,
            source_kind="file",
            blocked=False,
            diagnostics=tuple(diagnostics),
            support_flags=tuple(support_flags),
        )

    if credential_lookup is not None:
        try:
            stored = str(credential_lookup() or "").strip()
        except Exception:  # noqa: BLE001 - a status probe must never raise
            stored = ""
        if stored:
            return GieCredentialStatus(
                configured=True,
                source_kind="credential_store",
                blocked=False,
                diagnostics=tuple(diagnostics),
                support_flags=tuple(support_flags),
            )

    diagnostics.append("credential_missing")
    return GieCredentialStatus(
        configured=False,
        source_kind="missing",
        blocked=False,
        diagnostics=tuple(diagnostics),
        support_flags=tuple(support_flags),
    )


def _default_session_factory() -> Callable[[], Any]:
    """Return the process-wide runtime session factory (raises when unconfigured)."""

    from eurogas_nexus.db.session import get_session_factory

    return get_session_factory()


def _operator_state_store_configured() -> bool:
    """Whether a runtime database exists to hold the operator credential/state rows."""

    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def stored_gie_credential_status(
    session_factory: Callable[[], Any] | None = None,
) -> str | None:
    """Return the stored GIE credential status, or ``None`` when no row exists.

    With no configured runtime store there is no override to read, which is the
    same fact as an absent row. A read failure against a configured store
    deliberately propagates: an unreadable operator state is not the same fact as
    "no stored credential", and callers must not treat it as a confirmed permit.
    """

    from eurogas_nexus.db.models import ProviderCredentialRecord

    if session_factory is None and not _operator_state_store_configured():
        return None
    factory = session_factory or _default_session_factory()
    with factory() as session:
        row = session.get(ProviderCredentialRecord, "GIE")
        return row.status if row is not None else None


def stored_gie_credential_value(
    session_factory: Callable[[], Any] | None = None,
) -> str | None:
    """Return the decrypted stored GIE key in memory only, or ``None``.

    The value is never logged, returned to a client or persisted by this helper.
    A store that cannot be read yields ``None`` (no stored key); that can only
    fail closed, never grant access.
    """

    from eurogas_nexus.db.models import ProviderCredentialRecord
    from eurogas_nexus.security.credentials import (
        credential_store_configured,
        decrypt_credential_payload,
    )

    if not credential_store_configured():
        return None
    try:
        factory = session_factory or _default_session_factory()
        with factory() as session:
            row = session.get(ProviderCredentialRecord, "GIE")
            if row is None:
                return None
            payload = decrypt_credential_payload(row.encrypted_payload)
            return str(payload.get("api_key") or "").strip() or None
    except Exception:  # noqa: BLE001 - an unreadable store is not a credential
        return None


def gie_source_operation_enabled(
    session_factory: Callable[[], Any] | None = None,
) -> bool | None:
    """Return the GIE source runtime enabled flag, or ``None`` when absent.

    ``None`` means no runtime-state row exists, i.e. no operator override; a
    missing runtime store is the same absence. A read failure against a
    configured store propagates so the caller never mistakes an unreadable
    control for consent.
    """

    from eurogas_nexus.db.models import SourceRuntimeStateRecord

    if session_factory is None and not _operator_state_store_configured():
        return None
    factory = session_factory or _default_session_factory()
    with factory() as session:
        row = (
            session.query(SourceRuntimeStateRecord)
            .filter(SourceRuntimeStateRecord.source_id == GIE_SOURCE_ID)
            .one_or_none()
        )
        return bool(row.enabled) if row is not None else None


def resolve_gie_runtime_credential_status(
    environ: Mapping[str, str] | None = None,
    *,
    session_factory: Callable[[], Any] | None = None,
) -> GieCredentialStatus:
    """Resolve the secret-safe GIE status through the one DB-backed path.

    Every surface (runtime fetch, credential API, source registry) derives its
    reported status here, so an operator-disabled stored credential or an
    explicitly disabled source runtime state can never be bypassed by
    environment/file precedence, and the reported status can never disagree with
    the credential a live fetch would use.
    """

    return resolve_gie_credential_status(
        environ,
        credential_lookup=lambda: stored_gie_credential_value(session_factory),
        stored_credential_status=lambda: stored_gie_credential_status(session_factory),
        source_operation_enabled=lambda: gie_source_operation_enabled(session_factory),
    )


def resolve_gie_runtime_api_key(
    environ: Mapping[str, str] | None = None,
    *,
    session_factory: Callable[[], Any] | None = None,
) -> GieApiKey | None:
    """Resolve the runtime GIE key, refusing an operator-disabled credential/source.

    This is the credential-fetch boundary: the operator disable is enforced here,
    not only on the reported status surface, so environment/file precedence cannot
    turn a disabled stored credential or a disabled source operation back on.

    Raises:
        GieCredentialDisabledError: The stored credential is operator-disabled.
        GieSourceDisabledError: The source runtime operation is operator-disabled.
        GieCredentialStateUnreadableError: The operator state could not be read.
        GieCredentialFileError: ``GIE_API_KEY_FILE`` is configured but unreadable.
    """

    status = resolve_gie_runtime_credential_status(
        environ, session_factory=session_factory
    )
    if status.blocked:
        raise _blocked_gie_credential_error(status)
    return resolve_gie_api_key(
        environ,
        credential_lookup=lambda: stored_gie_credential_value(session_factory),
    )


def _blocked_gie_credential_error(status: GieCredentialStatus) -> GieTransportError:
    """Map a blocked status to its stable, secret-safe runtime error."""

    diagnostics = set(status.diagnostics)
    if status.source_kind == "file_unreadable" or "gie_key_file_unreadable" in diagnostics:
        return GieCredentialFileError(
            "GIE_API_KEY_FILE is configured but could not be read; refusing to resolve "
            "a credential.",
            product="GIE",
        )
    if "source_operation_disabled" in diagnostics:
        return GieSourceDisabledError(
            "GIE source operation is disabled by the operator; refusing to resolve a "
            "credential.",
            product="GIE",
        )
    if "credential_disabled" in diagnostics:
        return GieCredentialDisabledError(
            "The stored GIE credential is disabled by the operator; refusing to resolve "
            "a credential.",
            product="GIE",
        )
    if (
        "source_operation_state_unreadable" in diagnostics
        or "credential_state_unreadable" in diagnostics
    ):
        return GieCredentialStateUnreadableError(
            "The GIE credential/source operator state could not be read; refusing to "
            "treat an unknown state as a permit.",
            product="GIE",
        )
    return GieCredentialMissingError(
        "GIE ingestion requires an API key; none is configured.",
        product="GIE",
    )


def fetch_gie_page(
    client: httpx.Client,
    *,
    product: GieProduct,
    api_key: str,
    page: int,
    size: int,
    sleeper: Callable[[float], None] = time.sleep,
    attempts: int = _GIE_DEFAULT_ATTEMPTS,
) -> GiePage:
    """Fetch and validate exactly one provider page.

    Args:
        client: HTTP client (a ``httpx.MockTransport`` client in tests).
        product: AGSI or ALSI identity.
        api_key: The credential value; sent only in the ``x-key`` header.
        page: 1-based page number.
        size: Entries per page, 1..300.
        sleeper: Backoff sleep function (injectable for tests).
        attempts: Bounded retry attempts for transport errors and 429/5xx.

    Returns:
        The validated page with its post-response receipt instant.

    Raises:
        GieCredentialMissingError: The key value is blank.
        GieEndpointRefusedError: The endpoint is not the product's own official
            HTTPS endpoint (checked before the credential is sent).
        GieRedirectRefusedError: The provider answered with a 3xx.
        GieAuthenticationError: 401/403, or the provider's 200 access-denied body.
        GieRateLimitedError: 429 persisted through the bounded retries.
        GieHttpError: Any other non-success status.
        GieTimeoutError: The request timed out through the bounded retries.
        GieMalformedResponseError: The envelope is not the documented shape.
        GieEmptyResponseError: The requested data set is empty.
        GieProductMismatchError: The response is another product's shape.
        GiePaginationError: The requested page is beyond the advertised last page.
        GieTruncationError: An empty page arrived before ``last_page``.
    """

    if not isinstance(api_key, str) or not api_key.strip():
        raise GieCredentialMissingError(
            f"GIE {product.product} ingestion requires an API key; none is configured.",
            product=product.product,
        )
    if page < 1:
        raise ValueError("page must be >= 1")
    if not 1 <= size <= GIE_MAX_PAGE_SIZE:
        raise ValueError(f"size must be between 1 and {GIE_MAX_PAGE_SIZE}")

    _assert_allowed_endpoint(product)
    params = {**dict(product.selector), "page": str(page), "size": str(size)}
    response = _request_with_retry(
        client,
        product,
        params=params,
        api_key=api_key,
        sleeper=sleeper,
        attempts=attempts,
    )
    # The non-streaming client has read the body by now, so this is the response
    # receipt instant. It is never backdated to the pre-request clock.
    received_at = datetime.now(UTC)
    return _parse_page(
        product,
        page=page,
        size=size,
        response=response,
        received_at=received_at,
    )


def fetch_gie_product(
    client: httpx.Client,
    *,
    product: GieProduct,
    api_key: str,
    max_records: int | None = None,
    page_size: int | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    attempts: int = _GIE_DEFAULT_ATTEMPTS,
    max_pages: int = GIE_HARD_MAX_PAGES,
) -> GieFetchResult:
    """Fetch a bounded page sequence for one product.

    The operator's record budget is honoured **without** changing the page size
    midstream (a changing ``size`` moves the provider's page offsets), so the
    budget is consumed in whole pages: ``max_records=301`` fetches one 300-record
    page and stops with ``stop_reason="operator_record_budget"`` instead of
    fetching a second page and retaining 600. The provider's own ``last_page``
    always terminates the loop earlier when it is reached.

    ``page_size`` selects the provider page size explicitly (1..300). With both
    ``page_size`` and ``max_records`` the whole-page floor of
    ``max_records // page_size`` pages is fetched, and ``page_size`` must not
    exceed ``max_records``. With only ``max_records`` the page size is
    ``min(300, max_records)``. ``max_pages`` is clamped to
    :data:`GIE_HARD_MAX_PAGES`: the documented hard ceiling is absolute and no
    caller can raise it.

    ``complete`` reports which bound stopped the fetch, so a budget-limited
    result can never be presented as full history. An unchanged ``last_page``
    is not proof of one consistent provider snapshot -- the provider returns no
    revision token -- so this function detects only overlapping natural keys
    across pages and a changed ``last_page``; a silently rewritten earlier page
    is not detectable here and that limitation is deliberate and documented.
    """

    budget: int | None = None
    if max_records is not None:
        try:
            budget = max(1, int(max_records))
        except (TypeError, ValueError) as exc:
            raise ValueError("max_records must be a positive integer") from exc
    if page_size is not None:
        try:
            explicit_size = int(page_size)
        except (TypeError, ValueError) as exc:
            raise ValueError("page_size must be a positive integer") from exc
        if not 1 <= explicit_size <= GIE_MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {GIE_MAX_PAGE_SIZE}")
    else:
        explicit_size = None

    if explicit_size is not None:
        resolved_size = explicit_size
    elif budget is not None:
        resolved_size = min(GIE_MAX_PAGE_SIZE, budget)
    else:
        resolved_size = GIE_MAX_PAGE_SIZE

    pages_cap = min(max(1, int(max_pages)), GIE_HARD_MAX_PAGES)

    if budget is None:
        pages_allowed = pages_cap
        budget_records = resolved_size * pages_allowed
    else:
        if resolved_size > budget:
            raise ValueError(
                "page_size must not exceed max_records: the record budget cannot be "
                "honoured without changing the page size midstream."
            )
        pages_allowed = min(budget // resolved_size, pages_cap)
        budget_records = budget

    pages: list[GiePage] = []
    records: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    expected_last_page: int | None = None
    complete = False
    stop_reason = "operator_record_budget"

    for index in range(1, pages_allowed + 1):
        page = fetch_gie_page(
            client,
            product=product,
            api_key=api_key,
            page=index,
            size=resolved_size,
            sleeper=sleeper,
            attempts=attempts,
        )
        if expected_last_page is None:
            expected_last_page = page.last_page
        elif page.last_page != expected_last_page:
            raise GiePaginationError(
                (
                    f"GIE {product.product} changed last_page between pages "
                    f"({expected_last_page} -> {page.last_page}); stopping rather than "
                    "mixing two provider revisions."
                ),
                product=product.product,
            )
        page_keys = [_record_key(record) for record in page.records]
        if len(set(page_keys)) != len(page_keys):
            raise GiePaginationError(
                (
                    f"GIE {product.product} page {index} repeats a natural key within the "
                    "page; refusing a page that is not a set of distinct records."
                ),
                product=product.product,
            )
        overlap = seen_keys.intersection(page_keys)
        if overlap:
            raise GiePaginationError(
                (
                    f"GIE {product.product} page {index} repeats {len(overlap)} natural "
                    "key(s) already seen on an earlier page; refusing to ingest overlapping "
                    "pages as new data."
                ),
                product=product.product,
            )
        seen_keys.update(page_keys)
        pages.append(page)
        records.extend(page.records)
        if index >= page.last_page:
            complete = True
            stop_reason = "provider_last_page"
            break

    if expected_last_page is None:  # pragma: no cover - pages_allowed is always >= 1
        raise GieEmptyResponseError(
            f"GIE {product.product} returned no pages.", product=product.product
        )

    if not complete:
        if budget is None or pages_cap < (budget // resolved_size):
            stop_reason = "operator_page_budget"
        else:
            stop_reason = "operator_record_budget"

    partial_reason: str | None = None
    if not complete:
        partial_reason = (
            "page_budget_exhausted"
            if stop_reason == "operator_page_budget"
            else "record_budget_whole_page_floor"
        )

    return GieFetchResult(
        product=product.product,
        pages=tuple(pages),
        records=tuple(records),
        provider_last_page=expected_last_page,
        complete=complete,
        stop_reason=stop_reason,
        budget_records=budget_records,
        page_size=resolved_size,
        pages_allowed=pages_allowed,
        record_capacity=resolved_size * pages_allowed,
        partial_reason=partial_reason,
    )


def test_gie_connection(
    client: httpx.Client,
    *,
    api_key: str,
    products: tuple[GieProduct, ...] = (),
    page_size: int = GIE_CONNECTION_TEST_PAGE_SIZE,
    attempts: int = _GIE_DEFAULT_ATTEMPTS,
) -> tuple[GieConnectivityCheck, ...]:
    """Run the bounded one-page connection check for each GIE product.

    Each product is probed independently through the corrected
    :func:`fetch_gie_product` transport, so a transport failure for AGSI cannot
    hide or fake ALSI's result. The bound is one page per product (the operator's
    documented bounded probe): a successful result is an honest bounded partial,
    never a claim of full history or certification.

    Returns one :class:`GieConnectivityCheck` per product, in the given order.
    The check never raises for a provider/transport failure: the failure is
    represented as ``ok=False`` with the transport's stable error code, so the
    API can report every product's outcome in one response.
    """

    resolved_products = products or (GieProduct.agsi(), GieProduct.alsi())
    checks: list[GieConnectivityCheck] = []
    for product in resolved_products:
        checks.append(
            _test_one_product(
                client,
                product=product,
                api_key=api_key,
                page_size=page_size,
                attempts=attempts,
            )
        )
    return tuple(checks)


def _test_one_product(
    client: httpx.Client,
    *,
    product: GieProduct,
    api_key: str,
    page_size: int,
    attempts: int,
) -> GieConnectivityCheck:
    try:
        result = fetch_gie_product(
            client,
            product=product,
            api_key=api_key,
            page_size=page_size,
            max_pages=1,
            attempts=attempts,
        )
    except GieTransportError as exc:
        return GieConnectivityCheck(
            product=product.product,
            ok=False,
            error_code=exc.code,
            http_status=exc.status_code,
            record_count=0,
            normalized_rows=0,
            provider_last_page=None,
            page_size=None,
            complete=None,
            response_date=None,
            bounded_partial=False,
        )
    page = result.pages[0]
    shape = _normalization_shape(
        product, result.records, received_at=page.received_at_utc
    )
    return GieConnectivityCheck(
        product=product.product,
        ok=shape.error_code is None,
        error_code=shape.error_code,
        http_status=page.status_code,
        record_count=len(result.records),
        normalized_rows=shape.normalized_rows,
        provider_last_page=result.provider_last_page,
        page_size=result.page_size,
        complete=result.complete,
        response_date=page.response_date,
        bounded_partial=not result.complete,
    )


#: Quantitative columns that must be present on every normalized row for the page
#: to count as fully conformant. These are the products' primary measurement and
#: the documented capacity/send-out figures; a provider row that loses one of them
#: has not normalized into a usable canonical observation.
_GIE_REQUIRED_QUANTITY_COLUMNS: dict[str, tuple[str, ...]] = {
    "AGSI": ("inventory_twh", "working_capacity_twh"),
    "ALSI": ("inventory_twh", "send_out_twh_d"),
}


@dataclass(frozen=True)
class _NormalizationShape:
    """Outcome of normalizing one fetched page for the connection+shape test."""

    normalized_rows: int
    error_code: str | None


def _normalization_shape(
    product: GieProduct,
    records: tuple[dict[str, Any], ...],
    *,
    received_at: datetime,
) -> _NormalizationShape:
    """Normalize a fetched page and report whether the whole page conforms.

    The connection test reuses the real normalizer on a synthetic envelope so
    "the envelope parses" and "the product's documented records normalize
    completely" are reported as different facts. The page's own receipt instant
    (:attr:`GiePage.received_at_utc`) is passed as the normalization fallback --
    never a freshly invented ``now`` -- so the connectivity probe reports the
    same availability basis a live fetch would. Nothing is written to any
    database here.

    A page conforms only when every fetched record normalizes into a canonical
    row and every required quantitative column is present. Otherwise the page
    fails with a stable shape code:

    * ``gie_normalization_failed`` -- the normalizer raised or produced no row
      for a non-empty page;
    * ``gie_normalization_incomplete`` -- some records were silently skipped
      (for example a missing code or gas day), so the page is only partly usable;
    * ``gie_malformed_quantitative`` -- a row's required quantitative column is
      absent/unparseable.

    This is a connectivity+shape check, never a temporal or certification claim.
    """

    if not records:
        return _NormalizationShape(normalized_rows=0, error_code=None)

    from eurogas_nexus.ingestion.public_sources import (
        gie_lng_observations_from_json,
        gie_storage_observations_from_json,
    )

    envelope = {
        "data": [dict(record) for record in records],
        "last_page": 1,
        "total": len(records),
        "dataset": product.dataset,
    }
    try:
        if product.product == "AGSI":
            rows = gie_storage_observations_from_json(
                envelope, observed_at_utc=received_at
            )
        else:
            rows = gie_lng_observations_from_json(envelope, observed_at_utc=received_at)
    except Exception:  # noqa: BLE001 - normalization status is reported, not raised
        return _NormalizationShape(
            normalized_rows=0, error_code="gie_normalization_failed"
        )

    if len(rows) != len(records):
        return _NormalizationShape(
            normalized_rows=len(rows), error_code="gie_normalization_incomplete"
        )

    required = _GIE_REQUIRED_QUANTITY_COLUMNS.get(product.product, ("inventory_twh",))
    if any(row.get(column) is None for row in rows for column in required):
        return _NormalizationShape(
            normalized_rows=len(rows), error_code="gie_malformed_quantitative"
        )

    return _NormalizationShape(normalized_rows=len(rows), error_code=None)


def _read_gie_key_file(path: str) -> str:
    file_path = Path(path)
    try:
        if not file_path.is_file():
            raise GieCredentialFileError(
                f"GIE_API_KEY_FILE is set but is not a readable file: {file_path}",
                product="GIE",
            )
        if file_path.stat().st_size > GIE_MAX_KEY_FILE_BYTES:
            raise GieCredentialFileError(
                f"GIE_API_KEY_FILE exceeds {GIE_MAX_KEY_FILE_BYTES} bytes: {file_path}",
                product="GIE",
            )
        raw = file_path.read_bytes()
    except GieCredentialFileError:
        raise
    except OSError as exc:
        raise GieCredentialFileError(
            f"GIE_API_KEY_FILE could not be read ({type(exc).__name__}): {file_path}",
            product="GIE",
        ) from exc
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        # ``from None`` matters: the chained traceback would expose the decoder's
        # byte detail, and the file holds the credential. The message is a stable
        # configuration error that names only the path.
        raise GieCredentialFileError(
            (
                "GIE_API_KEY_FILE is not valid UTF-8 text; refusing to use or report "
                f"its contents: {file_path}"
            ),
            product="GIE",
        ) from None
    if not value:
        raise GieCredentialFileError(
            f"GIE_API_KEY_FILE is empty: {file_path}", product="GIE"
        )
    return value


def _assert_allowed_endpoint(product: GieProduct) -> None:
    """Refuse any endpoint except HTTPS on the product's own official host.

    Runs before the credential-bearing request, so a plaintext URL, the other
    product's host, a non-standard port, userinfo, a query/fragment or a
    non-documented path can never receive the ``x-key`` header. The error text
    names only the expected host: the submitted URL is not echoed because it
    could itself embed a credential.
    """

    try:
        parsed = urlsplit(product.endpoint_url)
        port = parsed.port
    except ValueError:
        raise GieEndpointRefusedError(
            (
                f"GIE {product.product} endpoint is not a valid URL; refusing to send "
                "the credential."
            ),
            product=product.product,
        ) from None

    expected_host = GIE_PRODUCT_HOSTS.get(product.product)
    if (
        expected_host is None
        or parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != expected_host
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, GIE_HTTPS_PORT)
        or parsed.path.rstrip("/") != GIE_ENDPOINT_PATH
        or bool(parsed.query)
        or bool(parsed.fragment)
    ):
        raise GieEndpointRefusedError(
            (
                f"refusing to send the GIE credential: GIE {product.product} requires "
                f"an HTTPS {expected_host or 'official product'} endpoint on port "
                f"{GIE_HTTPS_PORT} at path {GIE_ENDPOINT_PATH}, with no userinfo, query "
                "or fragment."
            ),
            product=product.product,
        )


def _request_with_retry(
    client: httpx.Client,
    product: GieProduct,
    *,
    params: dict[str, str],
    api_key: str,
    sleeper: Callable[[float], None],
    attempts: int,
) -> httpx.Response:
    bounded_attempts = max(1, int(attempts))
    last_error: GieTransportError | None = None

    for attempt in range(bounded_attempts):
        try:
            # ``follow_redirects=False`` is forced per request, overriding the
            # injected client's default: a 3xx must never forward the x-key
            # header to a foreign destination.
            request = client.build_request(
                "GET",
                product.endpoint_url,
                params=params,
                headers={"x-key": api_key},
            )
            response = client.send(request, follow_redirects=False)
        except httpx.TimeoutException as exc:
            last_error = GieTimeoutError(
                f"GIE {product.product} timed out ({type(exc).__name__}).",
                product=product.product,
            )
        except httpx.HTTPError as exc:
            # Only the exception class is recorded: provider/library text could
            # echo request details, and the header carries the credential.
            last_error = GieHttpError(
                f"GIE {product.product} transport error ({type(exc).__name__}).",
                product=product.product,
            )
        else:
            if 300 <= response.status_code < 400:
                raise GieRedirectRefusedError(
                    (
                        f"GIE {product.product} answered HTTP {response.status_code}; "
                        "refusing to follow a redirect because the request carries the "
                        "credential."
                    ),
                    product=product.product,
                    status_code=response.status_code,
                )
            if response.status_code in _GIE_RETRY_STATUS and attempt < bounded_attempts - 1:
                sleeper(_retry_delay_seconds(response, attempt))
                continue
            return response
        if attempt < bounded_attempts - 1:
            sleeper(1.5 * (attempt + 1))

    assert last_error is not None
    raise last_error


def _retry_delay_seconds(response: httpx.Response, attempt: int) -> float:
    retry_after = str(response.headers.get("retry-after") or "").strip()
    if retry_after.isdigit():
        return min(float(retry_after), _GIE_MAX_RETRY_DELAY_SECONDS)
    if retry_after:
        try:
            from email.utils import parsedate_to_datetime

            target = parsedate_to_datetime(retry_after)
            if target is not None:
                delay = (target - datetime.now(UTC)).total_seconds()
                if delay > 0:
                    return min(delay, _GIE_MAX_RETRY_DELAY_SECONDS)
        except (TypeError, ValueError):
            pass
    return 1.5 * (attempt + 1)


def _parse_page(
    product: GieProduct,
    *,
    page: int,
    size: int,
    response: httpx.Response,
    received_at: datetime,
) -> GiePage:
    if response.status_code in (401, 403):
        raise GieAuthenticationError(
            (
                f"GIE {product.product} refused the credential with HTTP "
                f"{response.status_code}."
            ),
            product=product.product,
            status_code=response.status_code,
        )
    if response.status_code == 429:
        raise GieRateLimitedError(
            f"GIE {product.product} rate-limited the request (HTTP 429).",
            product=product.product,
            status_code=429,
        )
    if response.status_code >= 400:
        raise GieHttpError(
            f"GIE {product.product} returned HTTP {response.status_code}.",
            product=product.product,
            status_code=response.status_code,
        )

    try:
        payload = response.json()
    except ValueError:
        # Never chain the decoder: a chained traceback could quote response text.
        raise GieMalformedResponseError(
            f"GIE {product.product} response was not valid JSON.",
            product=product.product,
            status_code=response.status_code,
        ) from None
    if not isinstance(payload, dict):
        raise GieMalformedResponseError(
            f"GIE {product.product} response was not a JSON object.",
            product=product.product,
            status_code=response.status_code,
        )

    dataset_text = _dataset_text(payload.get("dataset"))
    provider_error = payload.get("error")
    provider_message = str(payload.get("message") or "").strip()
    if provider_error or dataset_text.upper().endswith("ERROR"):
        # The body is untrusted and may echo the submitted key. Its text is
        # inspected in memory only, to classify the failure; the exception keeps
        # a stable taxonomy and never interpolates the provider detail.
        classification_text = " ".join(
            part
            for part in (str(provider_error or ""), provider_message, dataset_text)
            if part
        )
        if _looks_like_access_denied(classification_text):
            raise GieAuthenticationError(
                (
                    f"GIE {product.product} refused the credential: the provider "
                    "returned an access-denied error body (provider detail withheld)."
                ),
                product=product.product,
                status_code=response.status_code,
            )
        raise GieProviderError(
            (
                f"GIE {product.product} reported a provider error; the provider detail "
                "is withheld because response bodies are untrusted."
            ),
            product=product.product,
            status_code=response.status_code,
        )

    if not dataset_text:
        raise GieEmptyResponseError(
            (
                f"GIE {product.product} returned no dataset identity; refusing an "
                "unscoped response."
            ),
            product=product.product,
            status_code=response.status_code,
        )
    if dataset_text != product.dataset:
        # The provider label is not echoed: it is untrusted response text.
        raise GieProductMismatchError(
            (
                f"GIE {product.product} response dataset identity did not match the "
                f"expected {product.dataset!r} scope; the provider label is withheld "
                "because response bodies are untrusted."
            ),
            product=product.product,
            status_code=response.status_code,
        )

    missing = [key for key in ("data", "last_page", "total") if key not in payload]
    if missing:
        raise GieMalformedResponseError(
            (
                f"GIE {product.product} response is missing documented keys: "
                + ", ".join(missing)
            ),
            product=product.product,
            status_code=response.status_code,
        )

    data = payload.get("data")
    if not isinstance(data, list):
        raise GieMalformedResponseError(
            f"GIE {product.product} 'data' is not an array.",
            product=product.product,
            status_code=response.status_code,
        )
    records = tuple(item for item in data if isinstance(item, dict))
    if len(records) != len(data):
        raise GieMalformedResponseError(
            f"GIE {product.product} 'data' contains non-object entries.",
            product=product.product,
            status_code=response.status_code,
        )

    last_page = _as_int(payload.get("last_page"))
    if last_page is None or last_page < 0:
        raise GieMalformedResponseError(
            f"GIE {product.product} 'last_page' is not a non-negative integer.",
            product=product.product,
            status_code=response.status_code,
        )
    total_on_page = _as_int(payload.get("total"))
    if total_on_page is None or total_on_page < 0:
        raise GieMalformedResponseError(
            f"GIE {product.product} 'total' is not a non-negative integer.",
            product=product.product,
            status_code=response.status_code,
        )

    # A totally empty dataset is the provider's honest "no data" answer, not an
    # out-of-range page.
    if not records and page == 1 and last_page == 0:
        raise GieEmptyResponseError(
            f"GIE {product.product} returned no records for dataset {product.dataset}.",
            product=product.product,
            status_code=response.status_code,
        )
    if records and last_page < 1:
        raise GieMalformedResponseError(
            (
                f"GIE {product.product} returned records with last_page={last_page}; a "
                "non-empty page must advertise at least one page."
            ),
            product=product.product,
            status_code=response.status_code,
        )
    if page > last_page:
        raise GiePaginationError(
            (
                f"GIE {product.product} page {page} is beyond the advertised last_page "
                f"{last_page}; refusing an out-of-range page."
            ),
            product=product.product,
            status_code=response.status_code,
        )
    if not records:
        raise GieTruncationError(
            (
                f"GIE {product.product} page {page} is empty but the provider "
                f"advertises {last_page} pages; refusing a truncated result."
            ),
            product=product.product,
            status_code=response.status_code,
        )
    if total_on_page != len(records):
        raise GieMalformedResponseError(
            (
                f"GIE {product.product} reported total={total_on_page} for "
                f"{len(records)} data entries; the documented per-page total must equal "
                "len(data)."
            ),
            product=product.product,
            status_code=response.status_code,
        )
    if len(records) > size:
        raise GieMalformedResponseError(
            (
                f"GIE {product.product} returned {len(records)} records for a requested "
                f"page size of {size}; refusing an over-sized page."
            ),
            product=product.product,
            status_code=response.status_code,
        )

    _validate_record_signature(product, records)

    return GiePage(
        product=product.product,
        page=page,
        size=size,
        last_page=last_page,
        total_on_page=total_on_page,
        dataset=dataset_text,
        gas_day=_optional_str(payload.get("gas_day")),
        records=records,
        received_at_utc=received_at,
        status_code=response.status_code,
        response_date=response.headers.get("date"),
        raw_payload=payload,
    )


def _validate_record_signature(
    product: GieProduct, records: tuple[dict[str, Any], ...]
) -> None:
    for record in records:
        if not any(field in record for field in product.signature_fields):
            raise GieProductMismatchError(
                (
                    f"GIE {product.product} record does not carry any expected field "
                    f"({', '.join(product.signature_fields)}); refusing a cross-product "
                    "response."
                ),
                product=product.product,
            )


def _record_key(record: dict[str, Any]) -> str:
    code = str(record.get("code") or "").strip()
    gas_day = str(record.get("gasDayStart") or "").strip()
    if code and gas_day:
        return f"{code}|{gas_day}"
    return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)


def _dataset_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    # The provider may wrap a nested breadcrumb in anchor tags.
    text = _strip_tags(text)
    return " ".join(text.split())


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]*>", "", text)


def _looks_like_access_denied(detail: str) -> bool:
    lowered = detail.lower()
    return "access denied" in lowered or "api key" in lowered or "unauthor" in lowered


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _optional_str(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
