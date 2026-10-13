"""SDK test isolation from the deployment token the suite configures globally.

``tests/conftest.py`` sets ``EUROGAS_NEXUS_PUBLIC_API_TOKEN`` for the whole run so
that API tests present a credential. The SDK now reads that same canonical name
(and falls back to the older ``EUROGAS_NEXUS_API_TOKEN``), so without this fixture
every SDK call in the suite would carry an ``Authorization`` header and the
transport fakes -- which predate that behaviour -- would reject the unexpected
keyword.

Clearing the names here keeps each SDK test's own arrangement authoritative: a
test that exercises header behaviour sets the variable itself, and every other
test sees an unauthenticated client, which is what it asserts about.
"""

from __future__ import annotations

import pytest

TOKEN_ENV_VARS = ("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "EUROGAS_NEXUS_API_TOKEN")


@pytest.fixture(autouse=True)
def _no_ambient_deployment_token(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in TOKEN_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
