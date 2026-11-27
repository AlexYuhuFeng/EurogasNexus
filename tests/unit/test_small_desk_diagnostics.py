"""`nexus diagnostics` never carries a secret: no password, key, token, password hash or
connection string with a password reaches the archive, and it is not written if one would."""

from __future__ import annotations

import base64
import os
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy" / "small-desk"))

from nexusctl import diagnostics, redact  # noqa: E402
from nexusctl.settings import FIXED_STACK_VALUES, Settings, generate_secrets, write_env  # noqa: E402
from nexusctl.stack import Result  # noqa: E402
from nexusctl.status import Finding  # noqa: E402

NOW = datetime(2026, 11, 27, 9, 30, tzinfo=UTC)
PEM = (
    "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7\n"
    "-----END PRIVATE KEY-----"
)
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6MTk5OTk5OTk5OX0.c2lnbmF0dXJlLXZhbHVl"
FERNET = "gAAAAABnQ" + "x7Kp2" * 12 + "=="
SCRYPT_SALT = base64.b64encode(os.urandom(16)).decode()
SCRYPT_DIGEST = base64.b64encode(os.urandom(32)).decode()
OTHER_PASSWORD = "Winter2026!Desk"  # an unknown password, in a URL
PROVIDER_KEY = "Xq7Lm2Np9Rs4Tv6Wy8Za1Bc3De5Fg7Hj"


def leaky_log(secrets: dict[str, str]) -> str:
    """Every way a secret has turned up in a log somewhere."""

    app = secrets["EUROGAS_NEXUS_APP_DB_PASSWORD"]
    return "\n".join(
        [
            f"connecting to postgresql+pg8000://eurogas_app:{app}@postgres:5432/eurogas",
            f"retry postgresql://ops:{OTHER_PASSWORD}@db.internal/eurogas",
            f'{{"level": "error", "message": "bad token", "token": "{JWT}"}}',
            f"Authorization: Bearer {secrets['EUROGAS_NEXUS_PUBLIC_API_TOKEN']}",
            f"EUROGAS_NEXUS_SECRET_KEY={secrets['EUROGAS_NEXUS_SECRET_KEY']}",
            f"the key was {secrets['EUROGAS_NEXUS_SECRET_KEY']} (dumped by a bad library)",
            f"POSTGRES_PASSWORD: {secrets['POSTGRES_PASSWORD']}",
            f'{{"salt_b64": "{SCRYPT_SALT}", "digest_b64": "{SCRYPT_DIGEST}", "kdf": "scrypt"}}',
            "$scrypt$ln=15,r=8,p=1$c2FsdHNhbHQ$ZGlnZXN0ZGlnZXN0ZGlnZXN0",
            f"stored credential {FERNET}",
            PEM,
            f"provider answered 401 for api_key={PROVIDER_KEY}",
            f"GIE key {PROVIDER_KEY} rejected",
            "one-time password (shown once): nufs-8ptz-jnjv-fcnp",
            "ERROR scheduler: ENTSOG read timed out after 30 s",
            "image eurogas-nexus-api@sha256:" + "ab" * 32,
        ]
    )


@pytest.fixture()
def installation(tmp_path):
    settings = Settings(root=tmp_path / "opt", data_dir=tmp_path / "ssd",
                        backup_dir=tmp_path / "hdd", server_names=["desk-server"])
    settings.root.mkdir()
    secrets = {**FIXED_STACK_VALUES, **generate_secrets()}
    write_env(settings.env_path, secrets)
    settings.save()
    settings.log_path.parent.mkdir(parents=True)
    settings.log_path.write_text(leaky_log(secrets))
    return settings, secrets


class FakeStack:
    def __init__(self, text: str) -> None:
        self.text = text

    def compose(self, args, **kwargs):
        return Result(0, self.text if args[0] == "logs" else "", "")


class FakeRunner:
    def __init__(self, text: str) -> None:
        self.text = text

    def run(self, argv, **kwargs):
        return Result(0, f"{' '.join(argv)}\n{self.text}\n", "")


def forbidden(secrets: dict[str, str]) -> list[str]:
    values = [value for name, value in secrets.items()
              if any(word in name for word in ("PASSWORD", "SECRET", "TOKEN"))]
    return [*values, OTHER_PASSWORD, JWT, FERNET, SCRYPT_SALT, SCRYPT_DIGEST, PROVIDER_KEY,
            "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC", "nufs-8ptz-jnjv-fcnp",
            "ZGlnZXN0ZGlnZXN0ZGlnZXN0"]


def build(settings, secrets, tmp_path):
    text = leaky_log(secrets)
    return diagnostics.build_archive(
        settings=settings,
        stack=FakeStack(text),
        runner=FakeRunner(text),
        version="1.0.0",
        facts={"probe": {"note": text}},
        findings=[Finding("backup", "fail", "No backup has succeeded yet.", "Run backup."),
                  Finding("clock", "ok", "The clock is synchronised.")],
        status_text="status\n" + text,
        destination=tmp_path / "out",
        now=NOW,
    )


def test_no_secret_reaches_the_archive(installation, tmp_path) -> None:
    settings, secrets = installation
    archive, summary = build(settings, secrets, tmp_path)
    with zipfile.ZipFile(archive) as opened:
        names = opened.namelist()
        contents = {name: opened.read(name).decode("utf-8") for name in names}
    everything = "\n".join(contents.values()) + summary.read_text()
    for value in forbidden(secrets):
        assert value not in everything, f"leaked: {value[:6]}..."
    # What stays is still useful.
    assert "postgresql+pg8000://eurogas_app:<removed>@postgres:5432/eurogas" in everything
    assert "ENTSOG read timed out" in contents["recent-errors.txt"]
    assert "sha256:" + "ab" * 32 in everything  # image digests are not secrets
    assert "EUROGAS_NEXUS_APP_DB_USER=eurogas_app" in contents["config/stack.env.names-only"]
    assert "EUROGAS_NEXUS_SECRET_KEY=<removed>" in contents["config/stack.env.names-only"]


def test_summary_comes_first_and_reads_plainly(installation, tmp_path) -> None:
    settings, secrets = installation
    archive, summary = build(settings, secrets, tmp_path)
    with zipfile.ZipFile(archive) as opened:
        assert opened.namelist()[0] == "SUMMARY.txt"
        text = opened.read("SUMMARY.txt").decode()
    assert text.startswith("EUROGAS NEXUS DIAGNOSTICS SUMMARY")
    assert "Overall     : PROBLEMS" in text
    assert "No backup has succeeded yet.  -> Run backup." in text
    assert "paste this summary into a message or an AI assistant" in text
    assert summary.read_text() == text


def test_nothing_is_written_when_a_secret_would_remain(installation, tmp_path, monkeypatch):
    settings, secrets = installation
    monkeypatch.setattr(redact.Redactor, "redact", lambda self, text: text)
    with pytest.raises(diagnostics.LeakRefused) as refused:
        build(settings, secrets, tmp_path)
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").iterdir())
    for value in forbidden(secrets):
        assert value not in str(refused.value)


@pytest.mark.parametrize(
    "line",
    [
        "DATABASE_URL=postgresql://u:p4ssw0rd-long@h/db",
        "password=hunter2hunter2",
        '"client_secret": "s3cr3t-value-123"',
        "Authorization: Basic dXNlcjpwYXNzd29yZA==",
        "x-api-key: 9f8e7d6c5b4a39281706f5e4d3c2b1a0",
        "EUROGAS_NEXUS_OBJECT_STORE_SECRET_ACCESS_KEY=AbCdEf0123456789",
        "cookie: nexus_session=Zm9vYmFyYmF6cXV4cXV1eGNvcmdlZ3JhdWx0",
    ],
)
def test_secret_shapes_are_removed_even_when_unknown(line) -> None:
    cleaned = redact.Redactor().redact(line)
    assert "<removed>" in cleaned
    assert redact.Redactor().leaks(cleaned) == []
    secret = line.replace("=", " ").replace(":", " ").split()[-1].strip('"@')
    assert secret[-8:] not in cleaned
