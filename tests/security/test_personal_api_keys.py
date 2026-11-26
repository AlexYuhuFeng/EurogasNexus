"""A person issues their own API keys; nobody issues a key to act as someone else.

Hands-on review QA-R-02 (standard F4): an administrator could mint a key for a risk manager
and change limits as them, with the audit naming the risk manager.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from eurogas_nexus.api.middleware.origin_csrf import csrf_for_session
from tests.security.test_local_accounts_api import (  # noqa: F401 - fixtures
    _admin,
    _audit,
    _client,
    _create_local,
    _fast_kdf_and_clean_throttles,
    _first_sign_in,
    store,
)


def _guarded(client) -> dict[str, str]:
    token = client.cookies.get("eurogas_session")
    return {
        "Origin": "https://testserver",
        "X-Forwarded-Proto": "https",
        "X-Eurogas-CSRF": csrf_for_session(token),
    }


def test_an_administrator_cannot_issue_a_key_for_another_person(store):  # noqa: F811
    engine, ids, bearers = store
    client = _client()
    refused = client.post(
        "/api/access/api-keys",
        headers=_admin(bearers["admin"]),
        json={"principal_id": ids["analyst"], "display_name": "impersonate"},
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "personal_key_self_service"
    assert any(
        row.action == "access.api_key.create" and row.outcome == "denied" for row in _audit(engine)
    )
    # Their own key stays possible.
    own = client.post(
        "/api/access/api-keys",
        headers=_admin(bearers["admin"]),
        json={"principal_id": ids["admin"], "display_name": "mine"},
    )
    assert own.status_code == 200, own.text


def test_a_person_issues_lists_and_revokes_their_own_key(store):  # noqa: F811
    engine, _ids, bearers = store
    client = _client()
    principal_id, secret = _create_local(client, bearers["admin"])
    _first_sign_in(client, "jane.trader", secret)
    headers = _guarded(client)

    created = client.post("/api/me/api-keys", headers=headers, json={"display_name": "sdk"})
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    bearer, key = data["api_key"], data["key"]
    expires = datetime.fromisoformat(key["expires_at_utc"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    assert timedelta(days=89) < expires - datetime.now(UTC) <= timedelta(days=90)

    # The key acts as its owner and cannot mint a successor.
    as_key = {"X-Eurogas-Api-Key": "test-public-api-token", "X-Eurogas-Identity": bearer}
    fresh = _client()
    assert fresh.get("/api/me", headers=as_key).json()["data"]["principal_id"] == principal_id
    minted = fresh.post("/api/me/api-keys", headers=as_key, json={})
    assert minted.status_code == 403
    assert minted.json()["detail"]["code"] == "interactive_sign_in_required"

    listed = client.get("/api/me/api-keys").json()["data"]
    assert [row["key_id"] for row in listed] == [key["key_id"]]
    assert bearer not in str(listed)

    revoked = client.post(f"/api/me/api-keys/{key['key_id']}/revoke", headers=headers)
    assert revoked.status_code == 200
    assert fresh.get("/api/me", headers=as_key).status_code in {401, 403}
    actions = {row.action for row in _audit(engine) if row.principal == principal_id}
    assert {"me.api_key.create", "me.api_key.revoke"} <= actions


def test_a_personal_key_stays_within_its_owner(store):  # noqa: F811
    _engine, ids, bearers = store
    client = _client()
    _principal_id, secret = _create_local(client, bearers["admin"])
    _first_sign_in(client, "jane.trader", secret)
    headers = _guarded(client)
    too_long = (datetime.now(UTC) + timedelta(days=400)).isoformat()
    assert client.post(
        "/api/me/api-keys", headers=headers, json={"expires_at_utc": too_long}
    ).json()["detail"]["code"] == "key_expiry_out_of_range"
    assert client.post(
        "/api/me/api-keys", headers=headers, json={"scopes": ["ICIS"]}
    ).json()["detail"]["code"] == "scope_not_held"
    # Another person's key is not found, not revoked.
    other = _client().post(
        "/api/access/api-keys",
        headers=_admin(bearers["admin"]),
        json={"principal_id": ids["admin"], "display_name": "admin-own"},
    ).json()["data"]["key"]["key_id"]
    assert client.post(f"/api/me/api-keys/{other}/revoke", headers=headers).status_code == 404
