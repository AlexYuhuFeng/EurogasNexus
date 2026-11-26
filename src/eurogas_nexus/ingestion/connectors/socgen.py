"""Société Générale (``SOCGEN``) bank-rate connector: FX fixings and interest rates (TAR-2).

The firm's own clearing or account bank's rates are the ``contracted_bank`` tier of the
source-precedence resolver (ADR Decision 38). This connector reads them from the bank's API
for the one institution key ``SOCGEN`` and hands back raw records; the write path
(``application/bank_feeds.py``) maps them to the ``bank.fx_rates.v1`` /
``bank.interest_rates.v1`` columns and stores them through the same import contracts a file
uses, as ``BANK:SOCGEN`` rows, so precedence, lineage and audit are unchanged.

It connects only when all of these hold, and otherwise does nothing and says "not connected"
with the reason (no network call is made):

1. the organisation setting ``financial_institutions`` holds ``SOCGEN`` with access ``api``
   and ``agreement_recorded`` true (the firm's own agreement with the bank);
2. the deployment names an endpoint configuration file (``EUROGAS_NEXUS_SOCGEN_API_CONFIG_FILE``,
   kept outside the repository; see :func:`parse_config`);
3. the firm's own secret is configured (``EUROGAS_NEXUS_SOCGEN_API_SECRET``, the file named by
   ``EUROGAS_NEXUS_SOCGEN_API_SECRET_FILE``, or the encrypted credential store under provider
   ``SOCGEN``), resolved through the one provider-credential contract.

Nothing about Société Générale's real API is built in. The base URL, the token URL, the auth
scheme, the paths and the field mapping are all configuration, to be confirmed with the bank;
no address of the bank is written here. Supported auth schemes: ``oauth2_client_credentials``
(the secret is the client secret; the client id is in the configuration file) and ``api_key``
(the secret is sent in a configured header). A client certificate (mutual TLS) may be named in
the configuration file. Only ``https`` addresses are accepted, redirects are not followed, and
no response text or secret appears in an error.

The connector fetches only: it analyses, ranks and recommends nothing, and it books, pays or
sends nothing (AGENTS.md rule 8).

TAR-2：法国兴业银行（SOCGEN）汇率与利率连接器：仅在企业已记录协议、部署方提供接口配置与
企业自有凭据时取数，否则不发起任何网络调用并报告"未连接"；接口地址、认证方式与字段映射
均为配置，须与银行确认。
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from eurogas_nexus.domain.pricing.financial_institutions import Institution
from eurogas_nexus.ingestion.connectors.base import ConnectorMetadata
from eurogas_nexus.ingestion.contracts import IngestionPayload

INSTITUTION_KEY = "SOCGEN"
SOURCE_ID = "src-bank-socgen"
SOURCE_SYSTEM = "BANK:SOCGEN"
#: The provider id the secret is resolved under (provider-credential contract, #38).
PROVIDER_ID = "SOCGEN"
CONFIG_FILE_ENV = "EUROGAS_NEXUS_SOCGEN_API_CONFIG_FILE"
SECRET_ENV = "EUROGAS_NEXUS_SOCGEN_API_SECRET"
SECRET_FILE_ENV = "EUROGAS_NEXUS_SOCGEN_API_SECRET_FILE"

#: What the institution provides -> the dataset the connector serves and the contract it feeds.
DATASETS: Mapping[str, str] = MappingProxyType(
    {"fx": "bank-fx-rates", "interest": "bank-interest-rates"}
)
CONTRACT_IDS: Mapping[str, str] = MappingProxyType(
    {"fx": "bank.fx_rates.v1", "interest": "bank.interest_rates.v1"}
)
AUTH_SCHEMES = ("oauth2_client_credentials", "api_key")
CLIENT_AUTH = ("basic", "body")
MAX_RECORDS = 5000
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
#: Contract columns that hold a number and may be scaled (a bank quoting 0.0325 for 3.25 %).
NUMERIC_COLUMNS = frozenset({"rate", "rate_pct"})
#: Configuration keys that would hold a secret: refused, the secret lives in the environment.
_SECRET_KEYS = frozenset(
    {"client_secret", "secret", "api_key", "apikey", "password", "token", "access_token",
     "private_key"}
)

SOCGEN_METADATA = ConnectorMetadata(
    source_system=SOURCE_SYSTEM,
    datasets=tuple(DATASETS.values()),
    entitlement_required=True,
    credential_fields=("secret",),
    polling_supported=True,
    request_mode_supported=True,
    freshness_expectation_minutes=1440,
    export_restricted=True,
    research_only=True,
)

# Why the connector is not connected (``ConnectionStatus.code``).
READY = "ready"
INSTITUTION_NOT_CONFIGURED = "institution_not_configured"
ACCESS_NOT_API = "access_not_api"
AGREEMENT_NOT_RECORDED = "agreement_not_recorded"
ENDPOINT_NOT_CONFIGURED = "endpoint_not_configured"
ENDPOINT_CONFIG_INVALID = "endpoint_config_invalid"
CREDENTIAL_MISSING = "credential_missing"
NOT_PROVIDED = "not_provided"


class SocGenError(RuntimeError):
    """A refusal or failure of the connector, with a stable code; never carries a secret."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class SocGenNotConnected(SocGenError):
    """The connector is not connected; nothing was fetched."""


@dataclass(frozen=True)
class FeedConfig:
    """One feed (FX or interest rates) of the bank's API, as configured.

    ``fields`` maps a contract column to the response field holding it (a dotted path; a
    column not named reads the field of the same name). ``values`` maps a contract column's
    bank values to the contract's (``{"rate_type": {"MID": "mid"}}``), ``scale`` multiplies a
    numeric column. ``params`` are query parameters; ``{from}`` and ``{to}`` in a value are
    replaced by the look-back window's first and last dates (YYYY-MM-DD). ``records`` is the
    dotted path to the list of records in the response ("" when the response is the list).
    ``published_at`` (FX only, optional) is the local time and time zone the bank publishes
    its fixing at, used when a record carries no publication time.
    """

    path: str
    records: str = ""
    params: Mapping[str, str] = field(default_factory=dict)
    fields: Mapping[str, str] = field(default_factory=dict)
    values: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    scale: Mapping[str, float] = field(default_factory=dict)
    published_at: tuple[time, str] | None = None


@dataclass(frozen=True)
class AuthConfig:
    scheme: str
    token_url: str | None = None
    client_id: str | None = None
    scope: str | None = None
    client_auth: str = "basic"
    header: str = "Authorization"
    prefix: str = ""


@dataclass(frozen=True)
class ApiConfig:
    """The deployment's endpoint configuration for the bank's API (no secret in it)."""

    base_url: str
    auth: AuthConfig
    feeds: Mapping[str, FeedConfig]
    lookback_days: int = 5
    timeout_seconds: float = 30.0
    client_cert_file: str | None = None
    client_key_file: str | None = None
    ca_bundle_file: str | None = None


@dataclass(frozen=True)
class ConnectionStatus:
    """Whether the connector would fetch, and if not why; computed without a network call."""

    connected: bool
    code: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "connector": INSTITUTION_KEY,
            "source_id": SOURCE_ID,
            "source_system": SOURCE_SYSTEM,
            "connected": self.connected,
            "state": "ready" if self.connected else "not connected",
            "code": self.code,
            "message": self.message,
        }


# --------------------------------------------------------------------------- configuration


def _https(value: Any, name: str) -> str:
    text = str(value or "").strip()
    parts = urlsplit(text)
    if parts.scheme != "https" or not parts.hostname:
        raise SocGenError(ENDPOINT_CONFIG_INVALID, f"{name} must be an https address")
    if parts.username or parts.password:
        raise SocGenError(ENDPOINT_CONFIG_INVALID, f"{name} must not carry a user or password")
    if parts.query or parts.fragment:
        raise SocGenError(ENDPOINT_CONFIG_INVALID, f"{name} must not carry a query or fragment")
    return text.rstrip("/")


def _relative_path(value: Any, name: str) -> str:
    text = str(value or "").strip()
    parts = urlsplit(text)
    if (
        not text
        or parts.scheme
        or parts.netloc
        or text.startswith("//")
        or ".." in text.split("/")
        or parts.query
        or parts.fragment
    ):
        raise SocGenError(
            ENDPOINT_CONFIG_INVALID, f"{name} must be a path under the base address"
        )
    return "/" + text.lstrip("/")


def _no_secret(value: Any, where: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).strip().lower() in _SECRET_KEYS:
                raise SocGenError(
                    ENDPOINT_CONFIG_INVALID,
                    f"{where}: {key!r} is a secret; it is read from {SECRET_ENV} or "
                    f"{SECRET_FILE_ENV}, never from the configuration file",
                )
            _no_secret(item, where)
    elif isinstance(value, list):
        for item in value:
            _no_secret(item, where)


def _string_map(value: Any, name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or any(
        not isinstance(item, (str, int, float)) or isinstance(item, bool)
        for item in value.values()
    ):
        raise SocGenError(ENDPOINT_CONFIG_INVALID, f"{name} must map names to text")
    return {str(key): str(item) for key, item in value.items()}


def _feed(kind: str, value: Any) -> FeedConfig:
    from eurogas_nexus.application.import_contracts import CONTRACTS

    where = f"feeds.{kind}"
    if not isinstance(value, Mapping):
        raise SocGenError(ENDPOINT_CONFIG_INVALID, f"{where} must be an object")
    columns = {column.name for column in CONTRACTS[CONTRACT_IDS[kind]].columns}
    fields = _string_map(value.get("fields"), f"{where}.fields")
    unknown = sorted(set(fields) - columns)
    if unknown:
        raise SocGenError(
            ENDPOINT_CONFIG_INVALID,
            f"{where}.fields: {unknown[0]!r} is not a column of {CONTRACT_IDS[kind]}",
        )
    raw_values = value.get("values") or {}
    if not isinstance(raw_values, Mapping):
        raise SocGenError(ENDPOINT_CONFIG_INVALID, f"{where}.values must be an object")
    values = {
        str(column): {key.upper(): item for key, item in _string_map(
            mapping, f"{where}.values.{column}").items()}
        for column, mapping in raw_values.items()
    }
    if set(values) - columns:
        raise SocGenError(ENDPOINT_CONFIG_INVALID, f"{where}.values names an unknown column")
    raw_scale = value.get("scale") or {}
    if not isinstance(raw_scale, Mapping):
        raise SocGenError(ENDPOINT_CONFIG_INVALID, f"{where}.scale must be an object")
    scale: dict[str, float] = {}
    for column, factor in raw_scale.items():
        if column not in NUMERIC_COLUMNS & columns:
            raise SocGenError(ENDPOINT_CONFIG_INVALID, f"{where}.scale: {column!r} is not numeric")
        if not isinstance(factor, (int, float)) or isinstance(factor, bool) or factor <= 0:
            raise SocGenError(ENDPOINT_CONFIG_INVALID, f"{where}.scale.{column} must be positive")
        scale[str(column)] = float(factor)
    published = None
    if value.get("published_at") is not None:
        if kind != "fx":
            raise SocGenError(ENDPOINT_CONFIG_INVALID, f"{where}.published_at is for FX only")
        spec = value["published_at"]
        try:
            clock = time.fromisoformat(str(spec["time"]))
            zone = str(spec["timezone"])
            ZoneInfo(zone)
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
            raise SocGenError(
                ENDPOINT_CONFIG_INVALID,
                f"{where}.published_at is {{\"time\": \"HH:MM\", \"timezone\": \"Area/City\"}}",
            ) from None
        published = (clock, zone)
    records = str(value.get("records") or "")
    return FeedConfig(
        path=_relative_path(value.get("path"), f"{where}.path"),
        records=records,
        params=_string_map(value.get("params"), f"{where}.params"),
        fields=fields,
        values=values,
        scale=scale,
        published_at=published,
    )


def parse_config(value: Any) -> ApiConfig:
    """The endpoint configuration, checked. Its shape (JSON)::

        {"base_url": "https://<the bank's API host, to confirm with the bank>",
         "auth": {"scheme": "oauth2_client_credentials",
                  "token_url": "https://<to confirm>", "client_id": "<the firm's client id>",
                  "scope": "<optional>", "client_auth": "basic"},
         "feeds": {"fx": {"path": "<to confirm>", "records": "data", "params": {...},
                          "fields": {"base_currency": "<field>", ...},
                          "values": {"rate_type": {"MID": "mid"}},
                          "published_at": {"time": "HH:MM", "timezone": "Europe/Paris"}},
                   "interest": {"path": "<to confirm>", "fields": {...},
                                "scale": {"rate_pct": 100}}},
         "lookback_days": 5, "timeout_seconds": 30,
         "client_cert_file": "<optional path>", "client_key_file": "<optional path>",
         "ca_bundle_file": "<optional path>"}

    With ``"scheme": "api_key"`` the auth object names ``header`` (default ``Authorization``)
    and an optional ``prefix``. A key that would hold a secret is refused anywhere in it.

    Raises:
        SocGenError: ``endpoint_config_invalid`` with what to fix.
    """

    if not isinstance(value, Mapping):
        raise SocGenError(ENDPOINT_CONFIG_INVALID, "the configuration must be a JSON object")
    _no_secret(value, "configuration")
    auth_raw = value.get("auth")
    if not isinstance(auth_raw, Mapping):
        raise SocGenError(ENDPOINT_CONFIG_INVALID, "auth must be an object")
    scheme = str(auth_raw.get("scheme") or "")
    if scheme not in AUTH_SCHEMES:
        raise SocGenError(
            ENDPOINT_CONFIG_INVALID, f"auth.scheme is one of {', '.join(AUTH_SCHEMES)}"
        )
    if scheme == "oauth2_client_credentials":
        client_id = str(auth_raw.get("client_id") or "").strip()
        if not client_id:
            raise SocGenError(ENDPOINT_CONFIG_INVALID, "auth.client_id is required")
        client_auth = str(auth_raw.get("client_auth") or "basic")
        if client_auth not in CLIENT_AUTH:
            raise SocGenError(ENDPOINT_CONFIG_INVALID, "auth.client_auth is basic or body")
        auth = AuthConfig(
            scheme=scheme,
            token_url=_https(auth_raw.get("token_url"), "auth.token_url"),
            client_id=client_id,
            scope=(str(auth_raw.get("scope")).strip() or None) if auth_raw.get("scope") else None,
            client_auth=client_auth,
        )
    else:
        header = str(auth_raw.get("header") or "Authorization").strip()
        if not header or any(ch in header for ch in ":\r\n "):
            raise SocGenError(ENDPOINT_CONFIG_INVALID, "auth.header must be a header name")
        auth = AuthConfig(scheme=scheme, header=header, prefix=str(auth_raw.get("prefix") or ""))
    feeds_raw = value.get("feeds")
    if not isinstance(feeds_raw, Mapping) or not feeds_raw:
        raise SocGenError(ENDPOINT_CONFIG_INVALID, "feeds must configure fx and/or interest")
    unknown = sorted(set(feeds_raw) - set(DATASETS))
    if unknown:
        raise SocGenError(ENDPOINT_CONFIG_INVALID, f"feeds: {unknown[0]!r} is not fx or interest")
    lookback = value.get("lookback_days", 5)
    if not isinstance(lookback, int) or isinstance(lookback, bool) or not 1 <= lookback <= 31:
        raise SocGenError(ENDPOINT_CONFIG_INVALID, "lookback_days is 1 to 31")
    timeout = value.get("timeout_seconds", 30)
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not 1 <= timeout <= 120
    ):
        raise SocGenError(ENDPOINT_CONFIG_INVALID, "timeout_seconds is 1 to 120")
    files = {}
    for name in ("client_cert_file", "client_key_file", "ca_bundle_file"):
        item = value.get(name)
        files[name] = str(item).strip() if item else None
    if files["client_key_file"] and not files["client_cert_file"]:
        raise SocGenError(ENDPOINT_CONFIG_INVALID, "client_key_file needs client_cert_file")
    return ApiConfig(
        base_url=_https(value.get("base_url"), "base_url"),
        auth=auth,
        feeds=MappingProxyType({kind: _feed(kind, item) for kind, item in feeds_raw.items()}),
        lookback_days=lookback,
        timeout_seconds=float(timeout),
        **files,
    )


def load_config(environ: Mapping[str, str] | None = None) -> ApiConfig | None:
    """The configuration the deployment names, or ``None`` when it names none.

    Raises:
        SocGenError: ``endpoint_config_invalid`` when the named file cannot be read or is
            not a valid configuration.
    """

    env = os.environ if environ is None else environ
    path = str(env.get(CONFIG_FILE_ENV) or "").strip()
    if not path:
        return None
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        raise SocGenError(
            ENDPOINT_CONFIG_INVALID, f"the file named by {CONFIG_FILE_ENV} cannot be read"
        ) from None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise SocGenError(
            ENDPOINT_CONFIG_INVALID, f"the file named by {CONFIG_FILE_ENV} is not JSON"
        ) from None
    return parse_config(value)


def resolve_secret(environ: Mapping[str, str] | None = None) -> str | None:
    """The firm's secret through the provider-credential contract (environment, key file,
    encrypted store; an administrator's disable blocks it), or ``None``."""

    from eurogas_nexus.security.provider_credentials import (
        CredentialFileError,
        resolve_provider_credential,
    )

    try:
        resolved = resolve_provider_credential(PROVIDER_ID, environ)
    except CredentialFileError:
        return None
    return None if resolved is None else resolved.value


# --------------------------------------------------------------------------- status


def connection_status(
    institution: Institution | None,
    *,
    environ: Mapping[str, str] | None = None,
    config: ApiConfig | None = None,
    secret_lookup: Callable[[], str | None] | None = None,
) -> ConnectionStatus:
    """Whether the connector would fetch for ``institution``; never calls the network."""

    if institution is None or institution.key != INSTITUTION_KEY:
        return ConnectionStatus(
            False, INSTITUTION_NOT_CONFIGURED,
            f"{INSTITUTION_KEY} is not configured in financial_institutions",
        )
    if institution.access != "api":
        return ConnectionStatus(
            False, ACCESS_NOT_API,
            f"{INSTITUTION_KEY} is configured with access {institution.access!r}; its rates "
            "come in through the file import",
        )
    if not institution.agreement_recorded:
        return ConnectionStatus(
            False, AGREEMENT_NOT_RECORDED,
            "a live feed needs the firm's own agreement with the bank (agreement_recorded)",
        )
    if config is None:
        try:
            config = load_config(environ)
        except SocGenError as exc:
            return ConnectionStatus(False, exc.code, exc.message)
    if config is None:
        return ConnectionStatus(
            False, ENDPOINT_NOT_CONFIGURED,
            f"no endpoint configuration: set {CONFIG_FILE_ENV} to the file agreed with the bank",
        )
    secret = (secret_lookup or (lambda: resolve_secret(environ)))()
    if not secret:
        return ConnectionStatus(
            False, CREDENTIAL_MISSING,
            f"the firm's own credential is not configured ({SECRET_ENV}, {SECRET_FILE_ENV} or "
            f"the credential store, provider {PROVIDER_ID})",
        )
    return ConnectionStatus(True, READY, "configured; it fetches when run")


# --------------------------------------------------------------------------- connector


def _dig(record: Any, path: str) -> Any:
    value = record
    for part in [item for item in path.split(".") if item]:
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


class SocGenConnector:
    """Fetch-only connector for the ``SOCGEN`` institution's FX and interest-rate feeds.

    Args:
        institution: The configured ``SOCGEN`` institution (``None`` when not configured).
        environ: Environment for the configuration file and the secret (default
            ``os.environ``; the encrypted credential store is read only then).
        client: An ``httpx.Client`` to use (tests pass one over ``httpx.MockTransport``).
            A client made here is closed after each fetch.
        config: An endpoint configuration to use instead of the file.
        secret_lookup: Returns the secret instead of the credential contract (tests).
        now: The instant the look-back window ends at (default: now).
    """

    def __init__(
        self,
        institution: Institution | None,
        *,
        environ: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        config: ApiConfig | None = None,
        secret_lookup: Callable[[], str | None] | None = None,
        now: datetime | None = None,
    ) -> None:
        self._institution = institution
        self._environ = environ
        self._client = client
        self._config = config
        self._secret_lookup = secret_lookup or (lambda: resolve_secret(environ))
        self._now = now
        self._token: str | None = None

    @property
    def metadata(self) -> ConnectorMetadata:
        """Capabilities metadata of the connector."""

        return SOCGEN_METADATA

    def status(self) -> ConnectionStatus:
        """Whether the connector would fetch; never calls the network."""

        return connection_status(
            self._institution, environ=self._environ, config=self._config,
            secret_lookup=self._secret_lookup,
        )

    def feed(self, dataset: str) -> FeedConfig:
        """The configured feed of ``dataset``.

        Raises:
            ValueError: ``dataset`` is not one the connector serves.
            SocGenNotConnected: not connected, or the feed is not provided or configured.
        """

        kind = next((key for key, name in DATASETS.items() if name == dataset), None)
        if kind is None:
            raise ValueError(
                f"the SOCGEN connector serves {', '.join(DATASETS.values())}, not {dataset!r}"
            )
        state = self.status()
        if not state.connected:
            raise SocGenNotConnected(state.code, state.message)
        assert self._institution is not None
        config = self._loaded()
        if kind not in self._institution.provides or kind not in config.feeds:
            raise SocGenNotConnected(
                NOT_PROVIDED, f"{dataset} is not provided by {INSTITUTION_KEY} or not configured"
            )
        return config.feeds[kind]

    def fetch(self, dataset: str) -> IngestionPayload:
        """Fetch one dataset's raw records from the bank's API.

        Raises:
            ValueError: ``dataset`` is not one the connector serves.
            SocGenNotConnected: not connected; no network call was made.
            SocGenError: the bank refused or answered something unusable.
        """

        feed = self.feed(dataset)
        config = self._loaded()
        secret = self._secret_lookup()
        if not secret:  # removed between status and fetch
            raise SocGenNotConnected(CREDENTIAL_MISSING, "the firm's own credential is gone")
        end = (self._now or datetime.now(UTC)).astimezone(UTC).date()
        start = end - timedelta(days=config.lookback_days)
        params = {
            key: value.replace("{from}", start.isoformat()).replace("{to}", end.isoformat())
            for key, value in feed.params.items()
        }
        client = self._client or self._make_client(config)
        try:
            headers = self._auth_headers(client, config, secret)
            try:
                response = client.get(
                    config.base_url + feed.path, params=params, headers=headers,
                    follow_redirects=False,
                )
            except httpx.HTTPError as exc:
                raise SocGenError(
                    "transport_failed", f"{dataset}: {exc.__class__.__name__}"
                ) from None
        finally:
            if self._client is None:
                client.close()
        received = datetime.now(UTC)
        records = self._records(dataset, response, feed)
        return IngestionPayload(
            source_name="socgen-bank-api",
            source_reference=f"socgen-api:{dataset}",
            source_system=SOURCE_SYSTEM,
            dataset=dataset,
            raw_data=records,
            retrieval_ts_utc=received.isoformat(),
            source_reference_id=(
                f"socgen-api:{dataset}:{start.isoformat()}..{end.isoformat()}:"
                f"{len(records)} records"
            ),
        )

    # ----------------------------------------------------------------- internals

    def _loaded(self) -> ApiConfig:
        if self._config is None:
            self._config = load_config(self._environ)
        if self._config is None:  # status() said otherwise; keep it safe
            raise SocGenNotConnected(ENDPOINT_NOT_CONFIGURED, "no endpoint configuration")
        return self._config

    @staticmethod
    def _make_client(config: ApiConfig) -> httpx.Client:
        cert = None
        if config.client_cert_file:
            cert = (
                (config.client_cert_file, config.client_key_file)
                if config.client_key_file
                else config.client_cert_file
            )
        return httpx.Client(
            timeout=config.timeout_seconds,
            follow_redirects=False,
            cert=cert,
            verify=config.ca_bundle_file or True,
            headers={
                "User-Agent": "EurogasNexus bank-rate-connector",
                "Accept": "application/json",
            },
        )

    def _auth_headers(self, client: httpx.Client, config: ApiConfig, secret: str) -> dict:
        auth = config.auth
        if auth.scheme == "api_key":
            return {auth.header: f"{auth.prefix}{secret}"}
        if self._token is None:
            data = {"grant_type": "client_credentials"}
            if auth.scope:
                data["scope"] = auth.scope
            basic = None
            if auth.client_auth == "basic":
                basic = httpx.BasicAuth(str(auth.client_id), secret)
            else:
                data |= {"client_id": str(auth.client_id), "client_secret": secret}
            try:
                response = client.post(
                    str(auth.token_url), data=data, auth=basic,
                    headers={"Accept": "application/json"}, follow_redirects=False,
                )
            except httpx.HTTPError as exc:
                raise SocGenError("transport_failed", f"token: {exc.__class__.__name__}") from None
            if response.status_code != 200:
                raise SocGenError(
                    "auth_refused", f"the token endpoint answered HTTP {response.status_code}"
                )
            try:
                token = response.json().get("access_token")
            except (ValueError, AttributeError):
                token = None
            if not isinstance(token, str) or not token.strip():
                raise SocGenError("auth_refused", "the token endpoint returned no access token")
            self._token = token.strip()
        return {"Authorization": f"Bearer {self._token}"}

    @staticmethod
    def _records(dataset: str, response: httpx.Response, feed: FeedConfig) -> list[dict]:
        if response.status_code in (401, 403):
            raise SocGenError("auth_refused", f"{dataset}: the bank answered HTTP "
                              f"{response.status_code}")
        if response.status_code != 200:
            raise SocGenError("bad_response", f"{dataset}: the bank answered HTTP "
                              f"{response.status_code}")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise SocGenError("bad_response", f"{dataset}: the response is larger than 8 MB")
        try:
            body = response.json()
        except ValueError:
            raise SocGenError("bad_response", f"{dataset}: the response is not JSON") from None
        records = _dig(body, feed.records) if feed.records else body
        if not isinstance(records, list) or any(not isinstance(item, Mapping) for item in records):
            raise SocGenError(
                "bad_response", f"{dataset}: no list of records at {feed.records or 'the top'}"
            )
        if len(records) > MAX_RECORDS:
            raise SocGenError("bad_response", f"{dataset}: more than {MAX_RECORDS} records")
        return [dict(item) for item in records]


# --------------------------------------------------------------------------- mapping


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return repr(value)
    return str(value).strip()


def contract_rows(kind: str, records: list[Mapping[str, Any]], feed: FeedConfig) -> list[dict]:
    """The records as rows of the kind's import contract (column -> text).

    Nothing is checked here beyond the mapping: the contract's own parser checks every row
    and refuses one with its reason code, exactly as for a file.
    """

    from eurogas_nexus.application.import_contracts import CONTRACTS

    columns = [column.name for column in CONTRACTS[CONTRACT_IDS[kind]].columns]
    rows = []
    for record in records:
        row: dict[str, str] = {}
        for column in columns:
            text = _cell(_dig(record, feed.fields.get(column, column)))
            mapped = feed.values.get(column)
            if mapped and text.upper() in mapped:
                text = mapped[text.upper()]
            if text and column in feed.scale:
                try:
                    text = repr(round(float(text.replace(",", "")) * feed.scale[column], 10))
                except ValueError:
                    pass  # left as sent: the contract refuses it as number_invalid
            row[column] = text
        if kind == "fx" and not row.get("published_at") and feed.published_at:
            row["published_at"] = _published_at(row.get("value_date", ""), feed.published_at)
        rows.append(row)
    return rows


def _published_at(value_date: str, spec: tuple[time, str]) -> str:
    try:
        day = date.fromisoformat(value_date.strip()[:10])
    except ValueError:
        return ""  # the contract refuses the row's value_date itself
    clock, zone = spec
    return datetime.combine(day, clock, ZoneInfo(zone)).astimezone(UTC).isoformat()


def contract_csv(kind: str, rows: list[Mapping[str, str]]) -> str:
    """The contract file text for ``rows`` (header of every contract column)."""

    import csv
    import io

    from eurogas_nexus.application.import_contracts import CONTRACTS

    columns = [column.name for column in CONTRACTS[CONTRACT_IDS[kind]].columns]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(column, "") for column in columns])
    return buffer.getvalue()


__all__ = [
    "AUTH_SCHEMES",
    "CONFIG_FILE_ENV",
    "CONTRACT_IDS",
    "DATASETS",
    "INSTITUTION_KEY",
    "PROVIDER_ID",
    "SECRET_ENV",
    "SECRET_FILE_ENV",
    "SOCGEN_METADATA",
    "SOURCE_ID",
    "SOURCE_SYSTEM",
    "ApiConfig",
    "AuthConfig",
    "ConnectionStatus",
    "FeedConfig",
    "SocGenConnector",
    "SocGenError",
    "SocGenNotConnected",
    "connection_status",
    "contract_csv",
    "contract_rows",
    "load_config",
    "parse_config",
    "resolve_secret",
]
