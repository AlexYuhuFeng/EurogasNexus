"""Platform PostgreSQL URIs become the pg8000 URL and TLS context the runtime needs.

Shapes covered: a compose-internal URI, an external managed service such as Aiven
(``postgres://...:PORT/defaultdb?sslmode=require``), URL-encoded passwords, and every libpq
``sslmode``. No real host or password appears here; the values are placeholders.
"""

from __future__ import annotations

import ssl
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from eurogas_nexus.db.connection_url import (
    DB_SSL_ROOT_CERT_ENV,
    DatabaseUrlError,
    normalize_database_url,
    pg8000_ssl_arguments,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@db.example:5432/app", "postgresql+pg8000://u:p@db.example:5432/app"),
        ("postgresql://u:p@db.example/app", "postgresql+pg8000://u:p@db.example/app"),
        ("postgresql+psycopg2://u:p@h/app", "postgresql+pg8000://u:p@h/app"),
        ("POSTGRES://u:p@h/app", "postgresql+pg8000://u:p@h/app"),
        ("postgresql+pg8000://u:p@h/app", "postgresql+pg8000://u:p@h/app"),
        ("sqlite+pysqlite:///:memory:", "sqlite+pysqlite:///:memory:"),
        (
            "  postgres://avnadmin:p@demo-pg.example.com:24865/defaultdb?sslmode=require  ",
            "postgresql+pg8000://avnadmin:p@demo-pg.example.com:24865/defaultdb?sslmode=require",
        ),
    ],
)
def test_scheme_is_mapped_to_pg8000_and_everything_else_is_kept(raw, expected):
    assert normalize_database_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "db.example:5432/app"])
def test_blank_or_schemeless_urls_are_refused(raw):
    with pytest.raises(DatabaseUrlError):
        normalize_database_url(raw)


def test_external_service_uri_keeps_port_database_and_encoded_password():
    url = normalize_database_url(
        "postgres://avnadmin:p%40ss%2Fw%3Ard@demo-pg.example.com:24865/defaultdb?sslmode=require"
    )
    parsed, args = pg8000_ssl_arguments(url, environ={})
    assert parsed.drivername == "postgresql+pg8000"
    assert parsed.host == "demo-pg.example.com"
    assert parsed.port == 24865
    assert parsed.database == "defaultdb"
    assert parsed.username == "avnadmin"
    assert parsed.password == "p@ss/w:rd"  # decoded once, as the driver must receive it
    assert "sslmode" not in parsed.query
    context = args["ssl_context"]
    assert context.verify_mode == ssl.CERT_NONE and context.check_hostname is False


def test_a_url_without_tls_options_is_unchanged():
    raw = "postgresql+pg8000://u:p@h:5432/app"
    parsed, args = pg8000_ssl_arguments(raw, environ={})
    assert args == {}
    assert parsed == make_url(raw)


def test_disable_turns_tls_off_and_prefer_keeps_the_driver_default():
    _, disabled = pg8000_ssl_arguments("postgresql+pg8000://u:p@h/app?sslmode=disable", {})
    assert disabled == {"ssl_context": False}
    for mode in ("allow", "prefer"):
        parsed, args = pg8000_ssl_arguments(f"postgresql+pg8000://u:p@h/app?sslmode={mode}", {})
        assert args == {} and "sslmode" not in parsed.query


def test_verify_modes_check_the_certificate():
    _, full = pg8000_ssl_arguments("postgresql+pg8000://u:p@h/app?sslmode=verify-full", {})
    assert full["ssl_context"].verify_mode == ssl.CERT_REQUIRED
    assert full["ssl_context"].check_hostname is True
    _, ca = pg8000_ssl_arguments("postgresql+pg8000://u:p@h/app?sslmode=verify-ca", {})
    assert ca["ssl_context"].verify_mode == ssl.CERT_REQUIRED
    assert ca["ssl_context"].check_hostname is False


def _self_signed_ca(tmp_path: Path) -> Path:
    """A throwaway CA certificate, generated here so no key material is committed."""

    from datetime import UTC, datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test project CA")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    path = tmp_path / "ca.pem"
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return path


def test_project_ca_from_the_environment_as_a_path_or_as_pem_text(tmp_path):
    ca = _self_signed_ca(tmp_path)
    url = "postgresql+pg8000://u:p@h:24865/defaultdb?sslmode=verify-full"
    for value in (str(ca), ca.read_text()):
        _, args = pg8000_ssl_arguments(url, environ={DB_SSL_ROOT_CERT_ENV: value})
        context = args["ssl_context"]
        assert context.check_hostname is True
        assert any("test project CA" in str(item) for item in context.get_ca_certs())


def test_a_ca_with_require_upgrades_to_verify_ca_as_libpq_does(tmp_path):
    ca = _self_signed_ca(tmp_path)
    parsed, args = pg8000_ssl_arguments(
        f"postgresql+pg8000://u:p@h/app?sslmode=require&sslrootcert={ca}", environ={}
    )
    assert "sslrootcert" not in parsed.query and "sslmode" not in parsed.query
    assert args["ssl_context"].verify_mode == ssl.CERT_REQUIRED
    assert args["ssl_context"].check_hostname is False


def test_unknown_modes_client_certificates_and_unreadable_cas_are_refused(tmp_path):
    with pytest.raises(DatabaseUrlError, match="unsupported sslmode"):
        pg8000_ssl_arguments("postgresql+pg8000://u:p@h/app?sslmode=sometimes", {})
    with pytest.raises(DatabaseUrlError, match="client certificate"):
        pg8000_ssl_arguments("postgresql+pg8000://u:p@h/app?sslcert=/c.pem", {})
    with pytest.raises(DatabaseUrlError, match="CA certificate"):
        pg8000_ssl_arguments(
            "postgresql+pg8000://u:p@h/app?sslmode=verify-full",
            {DB_SSL_ROOT_CERT_ENV: str(tmp_path / "missing.pem")},
        )


def test_the_engine_receives_the_tls_context_and_a_clean_url(monkeypatch):
    from eurogas_nexus.db.session import get_engine

    monkeypatch.delenv(DB_SSL_ROOT_CERT_ENV, raising=False)
    engine = get_engine(
        normalize_database_url("postgres://u:secret@h:24865/defaultdb?sslmode=require")
    )
    try:
        assert "sslmode" not in engine.url.query
        assert engine.url.port == 24865
        assert "secret" not in repr(engine.url)  # credentials stay masked in logs
    finally:
        engine.dispose()


def test_cached_engines_are_disposed_on_shutdown(monkeypatch, tmp_path):
    from eurogas_nexus.db import session as session_module

    url = f"sqlite+pysqlite:///{(tmp_path / 'a.sqlite').as_posix()}"
    session_module.get_session_factory(database_url=url)
    assert session_module.dispose_cached_engines() >= 1
    assert session_module.dispose_cached_engines() == 0
