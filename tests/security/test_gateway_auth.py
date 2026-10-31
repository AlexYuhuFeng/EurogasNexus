"""Gateway (SAML, Kerberos, vendor SSO agent) assertions: trusted only with secret and peer."""

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.security.gateway_auth import (
    GatewayAuthError,
    GatewayConfig,
    gateway_principal,
)

SECRET = "s" * 40
ENV = {
    "EUROGAS_NEXUS_GATEWAY_AUTH_ENABLED": "true",
    "EUROGAS_NEXUS_GATEWAY_SECRET": SECRET,
    "EUROGAS_NEXUS_GATEWAY_TRUSTED_PROXIES": "10.20.0.0/24",
}
ROLES = {"EGN-Traders": "ANALYST", "EGN-Admins": "ADMIN"}
SCOPES = {"EGN-Traders": ["EEX", "ICE_ENDEX"]}


def _principal(headers, peer="10.20.0.5", env=ENV):
    return gateway_principal(
        headers,
        peer,
        config=GatewayConfig.from_env(env),
        groups_role_map=ROLES,
        groups_scope_map=SCOPES,
    )


def test_trusted_assertion_maps_groups_to_role_and_scopes():
    principal = _principal(
        {
            "X-Remote-User": "CORP\\jsmith",
            "X-Remote-Groups": "EGN-Traders; Everyone",
            "X-Eurogas-Gateway-Secret": SECRET,
        }
    )
    assert principal.principal_id == "sso:corp\\jsmith" and principal.name == "jsmith"
    assert principal.role == "ANALYST" and principal.data_scopes == ("EEX", "ICE_ENDEX")
    assert principal.identity_source == "GATEWAY"


def test_untrusted_assertions_are_refused_and_absent_ones_ignored():
    with pytest.raises(GatewayAuthError, match="not trusted"):
        _principal({"X-Remote-User": "eve", "X-Eurogas-Gateway-Secret": "wrong"})
    with pytest.raises(GatewayAuthError) as peer:
        _principal({"X-Remote-User": "eve", "X-Eurogas-Gateway-Secret": SECRET}, peer="8.8.8.8")
    assert peer.value.code == "gateway_peer_untrusted"
    assert _principal({"X-Eurogas-Gateway-Secret": SECRET}) is None
    disabled = {**ENV, "EUROGAS_NEXUS_GATEWAY_AUTH_ENABLED": "false"}
    assert _principal({"X-Remote-User": "eve"}, env=disabled) is None
    weak = {**ENV, "EUROGAS_NEXUS_GATEWAY_SECRET": "short"}
    with pytest.raises(GatewayAuthError, match="at least 32"):
        _principal({"X-Remote-User": "eve", "X-Eurogas-Gateway-Secret": "short"}, env=weak)


def test_api_accepts_gateway_identity_and_refuses_forgery(monkeypatch):
    for key, value in {**ENV, "EUROGAS_NEXUS_GATEWAY_TRUSTED_PROXIES": ""}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP", '{"EGN-Traders": "ANALYST"}')
    client = TestClient(create_app())
    ok = client.get(
        "/api/me",
        headers={
            "X-Remote-User": "jsmith",
            "X-Remote-Groups": "EGN-Traders",
            "X-Eurogas-Gateway-Secret": SECRET,
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["principal_id"] == "sso:jsmith"
    forged = client.get("/api/me", headers={"X-Remote-User": "admin"})
    assert forged.status_code == 401
