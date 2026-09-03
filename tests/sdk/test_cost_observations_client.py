"""SDK cost-observation client tests."""


from eurogas_nexus_sdk.cost_observations import (
    CostResolutionDTO,
    fetch_cost_observations,
    resolve_cost_observation,
)


def test_fetch_cost_observations_parses_rows(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [
                    {
                        "observation_id": "cost-1",
                        "scope_type": "ROUTE",
                        "scope_id": "TTF-NBP",
                        "observation_type": "TSO_PUBLISHED",
                        "value": 1.25,
                        "currency": "EUR",
                        "unit": "MWh",
                        "effective_from_utc": "2026-01-01T00:00:00+00:00",
                        "source_system": "TSO_TARIFFS",
                        "source_reference": "test",
                        "entitlement_scope": [],
                        "status": "ACTIVE",
                        "manual_review_required": True,
                    }
                ],
                "meta": {},
            }

    monkeypatch.setattr(
        "eurogas_nexus_sdk.cost_observations._http.get",
        lambda *a, **k: Response(),
    )

    rows = fetch_cost_observations("http://localhost:8000", scope_type="ROUTE")

    assert len(rows) == 1
    assert rows[0].scope_id == "TTF-NBP"


def test_resolve_cost_observation_parses_resolution(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": {
                    "scope_type": "ROUTE",
                    "scope_id": "TTF-NBP",
                    "as_of_utc": "2026-06-01T00:00:00+00:00",
                    "selected": None,
                    "alternatives": [],
                    "fallback_used": True,
                    "entitlement_scopes": [],
                },
                "meta": {},
            }

    monkeypatch.setattr(
        "eurogas_nexus_sdk.cost_observations._http.get",
        lambda *a, **k: Response(),
    )

    result = resolve_cost_observation(
        "http://localhost:8000",
        scope_type="ROUTE",
        scope_id="TTF-NBP",
        as_of="2026-06-01T00:00:00+00:00",
    )

    assert result.fallback_used is True
    assert isinstance(result, CostResolutionDTO)
