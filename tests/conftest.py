"""Shared test fixtures.

- The public API token env var is configured for the whole session so release
  profile tests exercise the authenticated path; individual tests may override
  it locally.
- ``tmp_path`` is replaced with a sandbox-safe implementation: this environment
  denies enumeration of directories created with mode 0o700 (the mode pytest's
  own temp machinery uses), so fixtures are created with default permissions
  under a pre-existing enumerable workspace directory.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

import pytest

_TMP_ROOT = Path(os.environ.get("EUROGAS_NEXUS_TEST_TMP_ROOT", ".tmp_work")).resolve()


@pytest.fixture(scope="session", autouse=True)
def _public_api_token_env() -> None:
    os.environ.setdefault("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "test-public-api-token")


@pytest.fixture(autouse=True)
def _development_clients_present_the_deployment_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Make the suite act as a caller, because every profile now identifies its callers.

    Owner decision **D1** installs authentication in every route profile: a request that presents
    nothing is refused with 401 instead of silently resolving to the compatibility principal. Every
    test that exercises *business* behaviour would therefore answer 401 for a reason it is not
    testing, which is what made the first attempt at this change look far larger than it is.

    Those tests were already acting as the compatibility principal - the development profile used to
    attach it to any request - so the faithful harness is the documented SDK/CLI caller: the
    deployment token, presented as a header. Nothing about the principal, its data scopes or the
    row filtering they produce changes; only the credential the request carries does.

    Scope, deliberately narrow:

    * **development and internal profiles only.** Release clients in the suite are built to test the
      gate itself, and they present their own credentials (or assert the refusal of none), so
      injecting here would rewrite the tests that define the posture.
    * **never over an explicit credential.** A client built with an identity header, an OIDC token,
      a session cookie, its own API key or the internal token is left exactly as it is.
    * **opt out per test** with ``monkeypatch.setenv("EUROGAS_NEXUS_TEST_ANONYMOUS", "1")`` before
      building the client, for the tests that assert what an anonymous caller gets.
    """

    from starlette.testclient import TestClient

    original_init = TestClient.__init__

    def patched_init(self, app, *args, **kwargs):  # type: ignore[no-untyped-def]
        headers = dict(kwargs.get("headers") or {})
        profile = getattr(getattr(app, "state", None), "route_profile", None)
        anonymous_requested = os.environ.get("EUROGAS_NEXUS_TEST_ANONYMOUS", "") == "1"
        credential_present = any(
            key.lower()
            in {
                "authorization",
                "x-eurogas-api-key",
                "x-eurogas-identity",
                "x-eurogas-oidc-access-token",
                "x-eurogas-internal-token",
            }
            for key in headers
        )
        if (
            getattr(profile, "name", "") in {"development", "internal"}
            and not anonymous_requested
            and not credential_present
            and os.environ.get("EUROGAS_NEXUS_PUBLIC_API_TOKEN")
        ):
            headers.setdefault(
                "X-Eurogas-Api-Key", os.environ["EUROGAS_NEXUS_PUBLIC_API_TOKEN"]
            )
            kwargs["headers"] = headers
        original_init(self, app, *args, **kwargs)

    monkeypatch.setattr(TestClient, "__init__", patched_init)


@pytest.fixture(scope="session", autouse=True)
def _pythonpath_for_subprocesses() -> None:
    """Make ``src`` importable by scripts spawned as subprocesses."""

    root = Path(__file__).resolve().parent.parent
    src = str(root / "src")
    parts = [part for part in os.environ.get("PYTHONPATH", "").split(os.pathsep) if part]
    if src not in parts:
        parts.insert(0, src)
    os.environ["PYTHONPATH"] = os.pathsep.join(parts)


@pytest.fixture(autouse=True)
def _no_ambient_runtime_store(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the non-integration suites independent of the machine's deployment config.

    Most suites assert what the platform does *with the store they configure themselves* -
    a SQLite fixture, or no store at all - and a developer who runs them on a workstation
    that happens to have `RUNTIME_STORE_DATABASE_URL` set (a live deployment, a container)
    would otherwise see roughly twenty failures that say nothing about the change under
    test: a route that should answer `runtime_db_not_configured` answers from the live
    store instead, and a degradation test asserts a warning the live run does not produce.

    `tests/integration` is the one place a live store is meant to be exercised, so this
    fixture leaves it alone - and it removes the variables through `monkeypatch`, so the
    ambient value is restored for the tests that do want it. A test that configures its own
    store is unaffected: its `monkeypatch.setenv` runs after this fixture.
    """

    if "integration" in Path(str(request.path)).parts:
        return
    for name in (
        "RUNTIME_STORE_DATABASE_URL",
        "DATABASE_URL",
        "EUROGAS_NEXUS_DB_DSN",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def tmp_path() -> Path:
    """Return a writable per-test directory (sandbox-safe, default mode)."""

    _TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = _TMP_ROOT / f"t-{uuid.uuid4().hex[:12]}"
    path.mkdir()
    yield path
    shutil.rmtree(path, ignore_errors=True)
