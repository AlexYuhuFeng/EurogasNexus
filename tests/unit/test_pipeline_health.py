"""Pipeline health aggregation tests."""

from unittest.mock import MagicMock

from eurogas_nexus.application.pipeline_health import (
    empty_pipeline_health,
    pipeline_health,
)


def test_empty_pipeline_health_shape() -> None:
    data = empty_pipeline_health()
    assert data["sources"] == []
    assert data["quote_freshness"] == {}
    assert data["open_alerts"] == 0
    assert data["latest_opportunity_detected_at_utc"] is None


def test_pipeline_health_aggregates_empty_db() -> None:
    session = MagicMock()
    query = MagicMock()
    session.query.return_value = query
    query.order_by.return_value.limit.return_value.all.return_value = []
    query.order_by.return_value.first.return_value = None
    query.filter.return_value.all.return_value = []
    query.filter.return_value.count.return_value = 0

    data = pipeline_health(session)

    assert data["sources"] == []
    assert data["quote_freshness"] == {}
    assert data["open_alerts"] == 0
    assert data["latest_opportunity_detected_at_utc"] is None
    assert data["generated_at_utc"]
