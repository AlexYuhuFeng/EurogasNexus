"""Object storage for backups' companions: archived history, raw pages and their manifests.

Decision record ``2026-11-26-standby-backup-object-storage-retention`` makes S3-compatible
object storage part of the supported topology. The product writes to it in two places: the
retention job (archived ticks and rows, offloaded raw source pages, their manifests) and the
drills. pgBackRest writes its own backups and write-ahead log there directly.

Two backends behind one small interface:

- ``s3://bucket/prefix`` - any S3-compatible store: the firm's own, a cloud bucket or a
  provider. Requests are signed with AWS Signature Version 4 over ``httpx`` (already a runtime
  dependency), so no SDK is added for the five calls the product makes. Path-style addressing
  by default when an endpoint is configured (what on-premises stores expect), virtual-host
  style for AWS itself.
- ``file:///absolute/path`` - a directory, for the single-machine demo and for tests. It is
  not a backup target: a directory on the database host goes down with the host.

Configuration (environment; secrets never printed, :meth:`ObjectStore.describe` is safe):

``EUROGAS_NEXUS_OBJECT_STORE_URL``          ``s3://bucket[/prefix]`` or ``file:///path``
``EUROGAS_NEXUS_OBJECT_STORE_ENDPOINT``     ``https://host:port`` (omit for AWS)
``EUROGAS_NEXUS_OBJECT_STORE_REGION``       default ``us-east-1``
``EUROGAS_NEXUS_OBJECT_STORE_ACCESS_KEY_ID`` / ``..._SECRET_ACCESS_KEY``
                                            (``AWS_ACCESS_KEY_ID``/``AWS_SECRET_ACCESS_KEY``
                                            are read when these are unset)
``EUROGAS_NEXUS_OBJECT_STORE_CA_FILE``      a private CA bundle for an on-premises store
``EUROGAS_NEXUS_OBJECT_STORE_URI_STYLE``    ``path`` or ``host``
"""

from __future__ import annotations

import hashlib
import hmac
import os
import shutil
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlparse

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

#: A single PUT is limited to 5 GiB by the S3 protocol; archive files are cut far below it.
MAX_SINGLE_PUT_BYTES = 5 * 1024**3

_CHUNK = 1024 * 1024


class ObjectStoreError(RuntimeError):
    """A request to the object store failed; the message never carries a secret."""


class ObjectStoreNotConfigured(ObjectStoreError):
    """No object store is configured, so nothing that must be archived first may be removed."""


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    sha256: str


class ObjectStore:
    """Interface shared by both backends."""

    def put_bytes(
        self, key: str, data: bytes, *, content_type: str = "application/octet-stream"
    ) -> StoredObject:
        raise NotImplementedError

    def put_file(
        self, key: str, path: Path, *, content_type: str = "application/octet-stream"
    ) -> StoredObject:
        raise NotImplementedError

    def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    def get_to_file(self, key: str, path: Path) -> StoredObject:
        raise NotImplementedError

    def size(self, key: str) -> int | None:
        """Size in bytes, or ``None`` when the object does not exist."""
        raise NotImplementedError

    def describe(self) -> str:
        """Where the store is, without credentials."""
        raise NotImplementedError

    def verify(self, key: str, *, sha256: str, size: int) -> bool:
        """Read the object back and compare its digest and size (archive before delete)."""

        with tempfile.TemporaryDirectory(prefix="nexus-verify-") as tmp:
            stored = self.get_to_file(key, Path(tmp) / "object")
        return stored.sha256 == sha256 and stored.size == size


def _file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _clean_key(key: str) -> str:
    cleaned = key.strip().lstrip("/")
    parts = cleaned.split("/")
    if not cleaned or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("object keys are relative paths without empty, '.' or '..' parts")
    return cleaned


class FilesystemObjectStore(ObjectStore):
    """A directory as an object store (demo machine and tests only)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / _clean_key(key)

    def put_bytes(self, key, data, *, content_type="application/octet-stream"):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".partial")
        partial.write_bytes(data)
        partial.replace(path)
        digest = hashlib.sha256(data).hexdigest()
        return StoredObject(key=_clean_key(key), size=len(data), sha256=digest)

    def put_file(self, key, path, *, content_type="application/octet-stream"):
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".partial")
        shutil.copyfile(path, partial)
        partial.replace(target)
        digest, size = _file_digest(target)
        return StoredObject(key=_clean_key(key), size=size, sha256=digest)

    def get_bytes(self, key):
        path = self._path(key)
        if not path.is_file():
            raise ObjectStoreError(f"object not found: {_clean_key(key)}")
        return path.read_bytes()

    def get_to_file(self, key, path):
        source = self._path(key)
        if not source.is_file():
            raise ObjectStoreError(f"object not found: {_clean_key(key)}")
        shutil.copyfile(source, path)
        digest, size = _file_digest(Path(path))
        return StoredObject(key=_clean_key(key), size=size, sha256=digest)

    def size(self, key):
        path = self._path(key)
        return path.stat().st_size if path.is_file() else None

    def describe(self):
        return f"file://{self.root}"


# --- AWS Signature Version 4 -------------------------------------------------------------


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret_key: str, date_stamp: str, region: str, service: str = "s3") -> bytes:
    k_date = _hmac(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    return _hmac(k_service, "aws4_request")


def canonical_uri(path: str) -> str:
    """Each segment URI-encoded once (S3 does not double-encode), slashes kept."""

    return "/".join(quote(segment, safe="-_.~") for segment in path.split("/")) or "/"


def canonical_query(query: Mapping[str, str]) -> str:
    return "&".join(
        f"{quote(name, safe='-_.~')}={quote(value, safe='-_.~')}"
        for name, value in sorted(query.items())
    )


def sign_v4(
    *,
    method: str,
    host: str,
    path: str,
    query: Mapping[str, str],
    headers: Mapping[str, str],
    payload_sha256: str,
    access_key: str,
    secret_key: str,
    region: str,
    now: datetime,
    service: str = "s3",
) -> dict[str, str]:
    """Return the request headers with ``Authorization`` added (pure function, testable).

    ``headers`` must not contain ``host``, ``x-amz-date`` or ``x-amz-content-sha256``; they are
    set here. Every header passed is signed.
    """

    amz_date = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    date_stamp = amz_date[:8]
    signed: dict[str, str] = {
        name.lower(): " ".join(str(value).split()) for name, value in headers.items()
    }
    signed["host"] = host
    signed["x-amz-date"] = amz_date
    signed["x-amz-content-sha256"] = payload_sha256
    names = sorted(signed)
    canonical_headers = "".join(f"{name}:{signed[name]}\n" for name in names)
    signed_headers = ";".join(names)
    request = "\n".join(
        [
            method.upper(),
            canonical_uri(path),
            canonical_query(query),
            canonical_headers,
            signed_headers,
            payload_sha256,
        ]
    )
    scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(
        signing_key(secret_key, date_stamp, region, service),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    result = {name: value for name, value in signed.items() if name != "host"}
    result["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return result


class S3ObjectStore(ObjectStore):
    """Any S3-compatible store, signed with Signature Version 4."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        endpoint: str | None,
        region: str,
        access_key: str,
        secret_key: str,
        ca_file: str | None = None,
        uri_style: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not bucket:
            raise ValueError("an S3 object store needs a bucket")
        if not access_key or not secret_key:
            raise ObjectStoreNotConfigured("the object store's access key and secret are not set")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.region = region
        self._access_key = access_key
        self._secret_key = secret_key
        self.uri_style = uri_style or ("path" if endpoint else "host")
        if self.uri_style not in {"path", "host"}:
            raise ValueError("uri style must be 'path' or 'host'")
        if endpoint:
            parsed = urlparse(endpoint)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname:
                raise ValueError("the object store endpoint must be an http(s) URL")
            self.scheme = parsed.scheme
            self.endpoint_host = parsed.netloc
        else:
            self.scheme = "https"
            self.endpoint_host = (
                "s3.amazonaws.com" if region == "us-east-1" else f"s3.{region}.amazonaws.com"
            )
        self._tls_verify: str | bool = ca_file or True
        self.timeout_seconds = timeout_seconds

    # Addressing -------------------------------------------------------------------------

    def _full_key(self, key: str) -> str:
        cleaned = _clean_key(key)
        return f"{self.prefix}/{cleaned}" if self.prefix else cleaned

    def _host_and_path(self, object_key: str | None) -> tuple[str, str]:
        if self.uri_style == "host":
            host = f"{self.bucket}.{self.endpoint_host}"
            path = "/" + (object_key or "")
        else:
            host = self.endpoint_host
            path = f"/{self.bucket}" + (f"/{object_key}" if object_key else "")
        return host, path

    def _request(
        self,
        method: str,
        object_key: str | None,
        *,
        content=None,
        payload_sha256: str = EMPTY_SHA256,
        extra_headers: Mapping[str, str] | None = None,
        query: Mapping[str, str] | None = None,
        stream_to: Path | None = None,
    ):
        import httpx

        host, path = self._host_and_path(object_key)
        query = dict(query or {})
        headers = sign_v4(
            method=method,
            host=host,
            path=path,
            query=query,
            headers=dict(extra_headers or {}),
            payload_sha256=payload_sha256,
            access_key=self._access_key,
            secret_key=self._secret_key,
            region=self.region,
            now=datetime.now(UTC),
        )
        url = f"{self.scheme}://{host}{canonical_uri(path)}"
        if query:
            url += "?" + canonical_query(query)
        try:
            with httpx.Client(verify=self._tls_verify, timeout=self.timeout_seconds) as client:
                if stream_to is None:
                    return client.request(method, url, headers=headers, content=content)
                with client.stream(method, url, headers=headers) as response:
                    if response.status_code != 200:
                        response.read()
                        return response
                    with Path(stream_to).open("wb") as handle:
                        for chunk in response.iter_bytes(_CHUNK):
                            handle.write(chunk)
                    return response
        except httpx.HTTPError as exc:
            raise ObjectStoreError(
                f"object store request failed ({method} {self.describe()}): "
                f"{exc.__class__.__name__}"
            ) from None

    @staticmethod
    def _raise_for(response, action: str, key: str) -> None:
        if response.status_code >= 300:
            code = ""
            try:
                body = response.text
                start = body.find("<Code>")
                if start >= 0:
                    code = body[start + 6 : body.find("</Code>", start)]
            except Exception:  # noqa: BLE001 - the status is enough
                pass
            raise ObjectStoreError(
                f"object store {action} of {key} failed: HTTP {response.status_code} {code}".strip()
            )

    # Interface --------------------------------------------------------------------------

    def ensure_bucket(self) -> bool:
        """Create the bucket when it does not exist (drills and first setup). True if created."""

        response = self._request("HEAD", None)
        if response.status_code == 200:
            return False
        response = self._request("PUT", None)
        self._raise_for(response, "bucket creation", self.bucket)
        return True

    def put_bytes(self, key, data, *, content_type="application/octet-stream"):
        full = self._full_key(key)
        digest = hashlib.sha256(data).hexdigest()
        response = self._request(
            "PUT",
            full,
            content=data,
            payload_sha256=digest,
            extra_headers={"content-type": content_type, "content-length": str(len(data))},
        )
        self._raise_for(response, "upload", full)
        return StoredObject(key=_clean_key(key), size=len(data), sha256=digest)

    def put_file(self, key, path, *, content_type="application/octet-stream"):
        full = self._full_key(key)
        digest, size = _file_digest(Path(path))
        if size > MAX_SINGLE_PUT_BYTES:
            raise ObjectStoreError("archive file exceeds a single upload (5 GiB); cut it smaller")

        def _body() -> Iterator[bytes]:
            with Path(path).open("rb") as handle:
                while chunk := handle.read(_CHUNK):
                    yield chunk

        response = self._request(
            "PUT",
            full,
            content=_body(),
            payload_sha256=digest,
            extra_headers={"content-type": content_type, "content-length": str(size)},
        )
        self._raise_for(response, "upload", full)
        return StoredObject(key=_clean_key(key), size=size, sha256=digest)

    def get_bytes(self, key):
        full = self._full_key(key)
        response = self._request("GET", full)
        self._raise_for(response, "download", full)
        return response.content

    def get_to_file(self, key, path):
        full = self._full_key(key)
        response = self._request("GET", full, stream_to=Path(path))
        self._raise_for(response, "download", full)
        digest, size = _file_digest(Path(path))
        return StoredObject(key=_clean_key(key), size=size, sha256=digest)

    def size(self, key):
        full = self._full_key(key)
        response = self._request("HEAD", full)
        if response.status_code == 404:
            return None
        self._raise_for(response, "inspection", full)
        return int(response.headers.get("content-length", "0"))

    def describe(self):
        location = f"s3://{self.bucket}" + (f"/{self.prefix}" if self.prefix else "")
        return f"{location} at {self.scheme}://{self.endpoint_host}"


def object_store_from_environment(environ: Mapping[str, str] | None = None) -> ObjectStore:
    """Build the configured store; raises :class:`ObjectStoreNotConfigured` when none is set."""

    env = os.environ if environ is None else environ
    raw = (env.get("EUROGAS_NEXUS_OBJECT_STORE_URL") or "").strip()
    if not raw:
        raise ObjectStoreNotConfigured("EUROGAS_NEXUS_OBJECT_STORE_URL is not set")
    parsed = urlparse(raw)
    if parsed.scheme == "file":
        if not parsed.path.startswith("/"):
            raise ValueError("a file object store needs an absolute path (file:///...)")
        return FilesystemObjectStore(Path(parsed.path))
    if parsed.scheme == "s3":
        return S3ObjectStore(
            bucket=parsed.netloc,
            prefix=parsed.path,
            endpoint=(env.get("EUROGAS_NEXUS_OBJECT_STORE_ENDPOINT") or "").strip() or None,
            region=(env.get("EUROGAS_NEXUS_OBJECT_STORE_REGION") or "us-east-1").strip(),
            access_key=(
                env.get("EUROGAS_NEXUS_OBJECT_STORE_ACCESS_KEY_ID")
                or env.get("AWS_ACCESS_KEY_ID")
                or ""
            ).strip(),
            secret_key=(
                env.get("EUROGAS_NEXUS_OBJECT_STORE_SECRET_ACCESS_KEY")
                or env.get("AWS_SECRET_ACCESS_KEY")
                or ""
            ).strip(),
            ca_file=(env.get("EUROGAS_NEXUS_OBJECT_STORE_CA_FILE") or "").strip() or None,
            uri_style=(env.get("EUROGAS_NEXUS_OBJECT_STORE_URI_STYLE") or "").strip() or None,
        )
    raise ValueError("the object store URL must start with s3:// or file://")
