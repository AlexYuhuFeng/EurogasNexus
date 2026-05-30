"""Monitoring alert generation tests."""

from eurogas_nexus.workflows.monitoring import (
    MonitoringInput,
    MonitoringThreshold,
    generate_alerts,
)


def test_generates_alert_when_threshold_exceeded() -> None:
    result = generate_alerts(MonitoringInput(
        entity_id="node-ttf", entity_name="TTF",
        observations={"price": 50.0},
        thresholds=[
            MonitoringThreshold(field="price", operator="gt", value=45.0,
                               message_template="Price {value} > {threshold}"),
        ],
    ))
    assert result.total_alerts == 1
    assert result.alerts[0].alert_type == "threshold_price"


def test_no_alert_when_threshold_not_exceeded() -> None:
    result = generate_alerts(MonitoringInput(
        entity_id="node-ttf", entity_name="TTF",
        observations={"price": 40.0},
        thresholds=[
            MonitoringThreshold(field="price", operator="gt", value=45.0),
        ],
    ))
    assert result.total_alerts == 0


def test_multiple_thresholds() -> None:
    result = generate_alerts(MonitoringInput(
        entity_id="e1", entity_name="Test",
        observations={"price": 50.0, "flow": 30.0},
        thresholds=[
            MonitoringThreshold(field="price", operator="gt", value=45.0),
            MonitoringThreshold(field="flow", operator="lt", value=100.0),
        ],
    ))
    assert result.total_alerts == 2


def test_missing_field_warns() -> None:
    result = generate_alerts(MonitoringInput(
        entity_id="e1", entity_name="Test",
        observations={},
        thresholds=[MonitoringThreshold(field="price", operator="gt", value=10.0)],
    ))
    assert len(result.warnings) >= 1
    assert result.total_alerts == 0


def test_research_metadata() -> None:
    result = generate_alerts(MonitoringInput(
        entity_id="e1", entity_name="T", observations={"a": 1.0},
    ))
    assert result.research_only is True
