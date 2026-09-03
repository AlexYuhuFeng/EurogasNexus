"""Cost-observation resolver unit tests."""

from __future__ import annotations

from eurogas_nexus.domain.economics.cost_observation import CostObservation
from eurogas_nexus.domain.economics.resolver import resolve_cost_observations


def _observation(
    *,
    observation_id: str,
    observation_type: str,
    value: float,
    effective_from: str = "2026-01-01T00:00:00+00:00",
    effective_to: str | None = None,
    entitlement_scope: tuple[str, ...] = (),
    status: str = "ACTIVE",
) -> CostObservation:
    return CostObservation(
        observation_id=observation_id,
        scope_type="ROUTE",
        scope_id="TTF-NBP",
        observation_type=observation_type,
        value=value,
        currency="EUR",
        unit="MWh",
        effective_from_utc=effective_from,
        effective_to_utc=effective_to,
        source_system="TEST",
        source_reference="test",
        entitlement_scope=entitlement_scope,
        status=status,
    )


def test_prefers_long_term_contract_over_published_tariff() -> None:
    result = resolve_cost_observations(
        [
            _observation(observation_id="tso", observation_type="TSO_PUBLISHED", value=1.1),
            _observation(
                observation_id="contract",
                observation_type="LONG_TERM_CONTRACT",
                value=0.9,
                entitlement_scope=("EEX",),
            ),
        ],
        scope_type="ROUTE",
        scope_id="TTF-NBP",
        as_of_utc="2026-06-01T00:00:00+00:00",
        entitled_scopes={"EEX"},
    )

    assert result.selected is not None
    assert result.selected.observation_id == "contract"
    assert result.fallback_used is False
    assert len(result.alternatives) == 1
    assert result.alternatives[0].observation_id == "tso"


def test_operator_value_requires_matching_entitlement() -> None:
    result = resolve_cost_observations(
        [
            _observation(observation_id="tso", observation_type="TSO_PUBLISHED", value=1.1),
            _observation(
                observation_id="contract",
                observation_type="LONG_TERM_CONTRACT",
                value=0.9,
                entitlement_scope=("EEX",),
            ),
        ],
        scope_type="ROUTE",
        scope_id="TTF-NBP",
        as_of_utc="2026-06-01T00:00:00+00:00",
        entitled_scopes={"ICIS"},
    )

    assert result.selected is not None
    assert result.selected.observation_id == "tso"
    assert result.fallback_used is True


def test_auction_bid_outranks_contract() -> None:
    result = resolve_cost_observations(
        [
            _observation(
                observation_id="contract",
                observation_type="LONG_TERM_CONTRACT",
                value=0.9,
            ),
            _observation(observation_id="auction", observation_type="AUCTION_BID", value=0.7),
            _observation(observation_id="tso", observation_type="TSO_PUBLISHED", value=1.1),
        ],
        scope_type="ROUTE",
        scope_id="TTF-NBP",
        as_of_utc="2026-06-01T00:00:00+00:00",
    )

    assert result.selected is not None
    assert result.selected.observation_id == "auction"


def test_effective_window_filters_outside_values() -> None:
    result = resolve_cost_observations(
        [
            _observation(
                observation_id="expired",
                observation_type="TSO_PUBLISHED",
                value=1.0,
                effective_to="2026-05-31T23:59:59+00:00",
            ),
            _observation(observation_id="current", observation_type="TSO_PUBLISHED", value=1.4),
        ],
        scope_type="ROUTE",
        scope_id="TTF-NBP",
        as_of_utc="2026-06-01T00:00:00+00:00",
    )

    assert result.selected is not None
    assert result.selected.observation_id == "current"


def test_no_candidate_returns_empty_resolution() -> None:
    result = resolve_cost_observations(
        [],
        scope_type="ROUTE",
        scope_id="TTF-NBP",
        as_of_utc="2026-06-01T00:00:00+00:00",
    )

    assert result.selected is None
    assert result.alternatives == ()
    assert result.fallback_used is True

def test_cost_observation_freshness(monkeypatch) -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from eurogas_nexus.db.repositories import cost_observation as repo

    row = SimpleNamespace(
        created_at_utc=datetime(2026, 6, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(repo, "list_cost_observations", lambda *a, **k: [row])

    result = repo.cost_observation_freshness(
        object(),
        scope_type="ROUTE",
        scope_id="TTF-NBP",
        now_utc=datetime(2026, 6, 2, tzinfo=UTC),
        expectation_minutes=1440,
    )

    assert result["status"] == "live"
    assert result["age_minutes"] == 1440.0
