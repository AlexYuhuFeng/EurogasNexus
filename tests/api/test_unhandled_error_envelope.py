"""Unhandled-failure envelope tests (Architecture V2 Wave 8, system faults).

The product error taxonomy requires every failure to expose a stable code, a family, a
severity, a recoverability, a suggested action and a correlation id. HTTP failures did;
an *unexpected* exception did not - it left the framework's bare 500, which a V2 client
cannot explain and an operator cannot match to a log line.

These tests pin both halves of the bargain: the client gets an explainable, value-free
envelope, and the failure itself is not hidden - the framework still re-raises it so
logging and monitoring keep seeing the real thing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.error_handlers import UNHANDLED_ERROR_CODE, _unhandled_detail

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


class _Boom(Exception):
    """A fault whose message must never reach a client."""

    def __init__(self) -> None:
        super().__init__("TTF day-ahead closed at 31.4 EUR/MWh for counterparty Example Energy")


@pytest.fixture()
def failing_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    def _explode(*_args, **_kwargs):
        raise _Boom()

    # A route's own dependency fails: nothing about the fault is the caller's doing.
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.analysis._load_snapshot",
        _explode,
    )
    return TestClient(create_app(), raise_server_exceptions=False)


def test_an_unexpected_failure_carries_the_product_envelope(failing_client: TestClient) -> None:
    response = failing_client.post(
        "/api/analysis/query",
        json={"question": "Summarize current TTF context", "task": "DB_INQUIRY"},
    )

    assert response.status_code == 500
    body = response.json()

    # The envelope explains the failure in the taxonomy's vocabulary.
    assert body["error"] == UNHANDLED_ERROR_CODE
    assert body["family"] == "SYSTEM"
    assert body["severity"] == "critical"
    assert body["recoverability"]
    assert body["message_key"]
    assert body["action_key"]

    # A correlation id is always present and is echoed so an operator can find the log.
    assert body["correlation_id"]
    assert response.headers["X-Request-Id"] == body["correlation_id"]

    # FastAPI's own user-facing text stays in `detail`, so clients that read it are
    # unaffected by the envelope.
    assert body["detail"] == "Internal Server Error"


def test_the_fault_s_own_text_never_reaches_the_client(failing_client: TestClient) -> None:
    response = failing_client.post(
        "/api/analysis/query",
        json={"question": "Summarize current TTF context", "task": "DB_INQUIRY"},
    )

    rendered = response.text
    # Neither the exception's message nor its payload may leak: a fault's text can carry
    # commercial values, and an unentitled caller must not read them out of a 500.
    assert "31.4" not in rendered
    assert "Example Energy" not in rendered
    assert "Traceback" not in rendered
    # D1 identifies this caller: the suite's client presents the deployment token, which is the
    # documented SDK/CLI credential and resolves to the operator service principal - exactly what
    # the release profile has always done with it. So the fault's *class* is visible (it is what
    # matches the response to a server log line) and its text is not. That is the identified-caller
    # contract; the next test pins the business caller, who sees no technical detail at all.
    assert response.json()["operator_detail"] == "_Boom"
    assert "31.4" not in response.json()["operator_detail"]


def test_a_business_identity_sees_no_technical_detail_at_all() -> None:
    """The other half of the rule: an identified *business* caller learns nothing technical.

    The principal is resolved by the app-wide identity dependency (owner decision D1 installs it in
    every profile), and an identity already attached is never replaced - so a harness that installs
    one is really exercising what that identity receives.
    """

    from eurogas_nexus.security.identity import AuthenticatedPrincipal

    def _explode(*_args, **_kwargs):
        raise _Boom()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.analysis._load_snapshot",
        _explode,
    )
    app = create_app()
    business = AuthenticatedPrincipal(
        principal_id="fixture-analyst",
        name="fixture-analyst",
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=("*",),
        roles=("ANALYST",),
        auth_method="identity_key",
    )

    @app.middleware("http")
    async def _inject_business_identity(request, call_next):  # type: ignore[no-untyped-def]
        request.state.identity = business
        return await call_next(request)

    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/analysis/query",
            json={"question": "Summarize current TTF context", "task": "DB_INQUIRY"},
        )
    finally:
        monkeypatch.undo()

    assert response.status_code == 500
    assert "operator_detail" not in response.json()
    assert "_Boom" not in response.text


def test_an_operator_identity_learns_the_fault_class_but_not_its_payload() -> None:
    # The gating is a pure decision, exercised directly: the class name is what makes a
    # fault matchable to a server log line, and the message stays out of it either way.
    assert _unhandled_detail(_Boom(), operator=False) is None
    assert _unhandled_detail(_Boom(), operator=True) == "_Boom"


def test_a_handled_failure_is_unaffected_by_the_system_fault_handler() -> None:
    # The unexpected-failure handler must not swallow the taxonomy's own codes: a route
    # that raises a declared HTTPException still answers with that code and family.
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/analysis-snapshots/snap-does-not-exist")

    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "runtime_db_not_configured"
    assert body["family"] == "CONFIGURATION"
    assert body["error"] != UNHANDLED_ERROR_CODE
    assert body["correlation_id"] or response.headers.get("X-Request-Id")
