"""Opt-in single-origin serving of the built web client (hosted test/demo server).

The client may answer browser paths, never an ``/api`` path: an unknown API path keeps its
JSON 404, an unauthenticated read its 401, a wrong method its 405. Unset, nothing changes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.web_client import WEB_CLIENT_DIR_ENV, resolve_web_client_dir
from eurogas_nexus.core.config import Settings

INDEX = "<!doctype html><title>client</title>"


@pytest.fixture
def build_dir(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    (tmp_path / "assets" / "app-1a2b.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("outside", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(build_dir, monkeypatch):
    monkeypatch.setenv(WEB_CLIENT_DIR_ENV, str(build_dir))
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "test-token-not-a-real-credential")
    return TestClient(create_app(Settings(api_profile="release")))


def test_client_routes_fall_back_to_index_and_files_are_served(client):
    for path in ("/", "/desk/today", "/?workspace=market&task=overview"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text == INDEX
        assert response.headers["cache-control"] == "no-cache"
    asset = client.get("/assets/app-1a2b.js")
    assert asset.status_code == 200
    assert "immutable" in asset.headers["cache-control"]
    assert client.get("/favicon.svg").status_code == 200


def test_the_bundled_interface_font_is_served_as_a_font(client, build_dir):
    (build_dir / "assets" / "inter-latin-1a2b.woff2").write_bytes(b"wOF2-not-a-real-font")
    font = client.get("/assets/inter-latin-1a2b.woff2")
    assert font.status_code == 200
    assert font.headers["content-type"] == "font/woff2"
    assert "immutable" in font.headers["cache-control"]


def test_the_client_never_answers_for_the_api(client):
    unknown = client.get("/api/does-not-exist")
    assert unknown.status_code == 404
    assert unknown.headers["content-type"].startswith("application/json")
    assert client.get("/api").status_code == 404
    assert client.get("/api/").headers["content-type"].startswith("application/json")
    me = client.get("/api/me")
    assert me.status_code == 401  # authentication still applies
    assert INDEX not in me.text
    assert client.get("/api/health").json()["profile"] == "release"


def test_missing_files_traversal_and_writes_are_refused(client):
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/missing.png").status_code == 404
    assert client.get("/../secret.txt").status_code in {404, 200}
    assert "outside" not in client.get("/../secret.txt").text
    assert "outside" not in client.get("/%2e%2e/secret.txt").text
    assert client.post("/desk/today").status_code == 405
    # No directory listing: a directory is a client route.
    assert client.get("/assets/").text == INDEX


def test_security_headers_on_pages_and_api_answers(client):
    for path in ("/", "/api/health"):
        headers = client.get(path).headers
        assert "frame-ancestors 'none'" in headers["content-security-policy"]
        assert "script-src 'self'" in headers["content-security-policy"]
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "strict-transport-security" not in headers
    https = client.get("/", headers={"X-Forwarded-Proto": "https"}).headers
    assert https["strict-transport-security"].startswith("max-age=")


def test_unset_means_no_pages_and_no_extra_headers(monkeypatch):
    monkeypatch.delenv(WEB_CLIENT_DIR_ENV, raising=False)
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "test-token-not-a-real-credential")
    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.get("/")
    assert response.status_code == 404
    assert "content-security-policy" not in response.headers


def test_a_configured_directory_without_a_build_refuses_to_start(tmp_path):
    with pytest.raises(RuntimeError, match="index.html"):
        resolve_web_client_dir({WEB_CLIENT_DIR_ENV: str(tmp_path)})
    assert resolve_web_client_dir({}) is None
