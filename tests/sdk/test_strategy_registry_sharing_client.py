"""SDK contract for owner-controlled strategy sharing."""

import httpx
import pytest
from eurogas_nexus_sdk import strategy_registry


def _strategy(**sharing):
    return {
        "strategy_id": "strategy-1",
        "name": "Research",
        "description": "",
        "lifecycle_status": "ACTIVE",
        "created_by": "owner",
        "created_at_utc": "2026-10-22T00:00:00Z",
        "updated_at_utc": "2026-10-22T00:00:00Z",
        **sharing,
    }


@pytest.mark.parametrize(
    "visibility,group_ids", [("PRIVATE", None), ("PUBLIC", []), ("GROUPS", ["desk-1"])]
)
def test_update_sharing_serializes_scope_and_preserves_server_authority(
    monkeypatch, visibility, group_ids
):
    def fake_patch(url, *, json, timeout):
        assert url == "https://example.test/api/strategies/strategy%2F1%3F/sharing"
        assert json == {"visibility": visibility, "group_ids": group_ids or []}
        assert timeout == 15
        return httpx.Response(
            200,
            request=httpx.Request("PATCH", url),
            json={
                "data": _strategy(
                    owner_principal_id="owner",
                    visibility=visibility,
                    shared_group_ids=group_ids or [],
                    can_manage=False,
                )
            },
        )

    monkeypatch.setattr(httpx, "patch", fake_patch)
    result = strategy_registry.update_strategy_sharing(
        "https://example.test/", "strategy/1?", visibility=visibility, group_ids=group_ids
    )
    assert result.owner_principal_id == "owner"
    assert result.visibility == visibility
    assert result.shared_group_ids == (group_ids or [])
    assert result.can_manage is False


@pytest.mark.parametrize("status", [403, 404, 422])
def test_update_sharing_propagates_server_refusal(monkeypatch, status):
    def fake_patch(url, **kwargs):
        return httpx.Response(status, request=httpx.Request("PATCH", url))

    monkeypatch.setattr(httpx, "patch", fake_patch)
    with pytest.raises(httpx.HTTPStatusError) as error:
        strategy_registry.update_strategy_sharing(
            "https://example.test", "strategy-1", visibility="PUBLIC"
        )
    assert error.value.response.status_code == status


def test_legacy_strategy_payload_defaults_to_private_without_management_authority():
    first = strategy_registry.StrategyDTO(**_strategy())
    second = strategy_registry.StrategyDTO(**_strategy())
    assert first.visibility == "PRIVATE"
    assert first.owner_principal_id is None
    assert first.can_manage is False
    first.shared_group_ids.append("desk-1")
    assert second.shared_group_ids == []


def test_list_my_groups_parses_eligible_groups_and_sends_identity(monkeypatch):
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "deployment-token")
    monkeypatch.setenv("EUROGAS_NEXUS_IDENTITY_BEARER", "owner-identity")

    def fake_get(url, *, timeout, headers):
        assert url == "https://example.test/nexus/api/me/groups"
        assert timeout == 15
        assert headers["Authorization"] == "Bearer deployment-token"
        assert headers["X-Eurogas-Identity"] == "owner-identity"
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"data": [{"group_id": "desk/alpha", "name": "Research 参数"}]},
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    groups = strategy_registry.list_my_groups("https://example.test/nexus/")
    assert len(groups) == 1
    assert isinstance(groups[0], strategy_registry.StrategySharingGroupDTO)
    assert groups[0].group_id == "desk/alpha"
    assert groups[0].name == "Research 参数"


def test_list_my_groups_preserves_empty_membership(monkeypatch):
    def fake_get(url, **kwargs):
        return httpx.Response(200, request=httpx.Request("GET", url), json={"data": []})

    monkeypatch.setattr(httpx, "get", fake_get)
    assert strategy_registry.list_my_groups("https://example.test") == []


def test_list_my_groups_propagates_forbidden_instead_of_returning_no_groups(monkeypatch):
    def fake_get(url, **kwargs):
        return httpx.Response(403, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(httpx.HTTPStatusError) as error:
        strategy_registry.list_my_groups("https://example.test/")
    assert error.value.response.status_code == 403
