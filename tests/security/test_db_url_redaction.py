"""Security tests for DB URL handling."""

from eurogas_nexus.db import redact_database_url


def test_redact_database_url_hides_password() -> None:
    redacted = redact_database_url(
        "postgresql+psycopg://eurogas:super-secret@db.example.test:5432/eurogas_nexus"
    )

    assert redacted is not None
    assert "super-secret" not in redacted
    assert "eurogas" in redacted
    assert "***" in redacted


def test_redact_database_url_handles_missing_url() -> None:
    assert redact_database_url(None) is None


def test_redact_database_url_handles_unparseable_secret_text() -> None:
    redacted = redact_database_url("postgresql://user:secret value@localhost/db")

    assert "secret value" not in (redacted or "")
