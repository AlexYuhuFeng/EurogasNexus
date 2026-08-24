"""Request-ID middleware tests."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


def test_every_response_carries_x_request_id() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    request_id = response.headers.get("x-request-id")
    assert request_id is not None
    assert len(request_id) == 16
    assert request_id.isalnum()


def test_request_ids_differ_across_requests() -> None:
    client = TestClient(create_app())

    first = client.get("/api/health").headers["x-request-id"]
    second = client.get("/api/health").headers["x-request-id"]

    assert first != second


def test_request_id_also_present_on_errors() -> None:
    client = TestClient(create_app())

    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert "x-request-id" in response.headers
