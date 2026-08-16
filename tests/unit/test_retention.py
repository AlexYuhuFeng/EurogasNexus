"""Retention pruning tests."""

from unittest.mock import MagicMock

from eurogas_nexus.application.retention import (
    OBSERVATION_RETENTION_DAYS,
    OPPORTUNITY_RETENTION_DAYS,
    QUOTE_RETENTION_DAYS,
    prune_expired_rows,
)


def test_retention_defaults() -> None:
    assert QUOTE_RETENTION_DAYS == 30
    assert OBSERVATION_RETENTION_DAYS == 90
    assert OPPORTUNITY_RETENTION_DAYS == 7


def test_prune_expired_rows_deletes_across_three_tables() -> None:
    session = MagicMock()
    query = MagicMock()
    session.query.return_value = query
    query.filter.return_value = query
    query.delete.return_value = 3
    query.count.return_value = 3

    summary = prune_expired_rows(session)

    assert summary["market_quotes_deleted"] == 3
    assert summary["market_observations_deleted"] == 3
    assert summary["intraday_opportunities_deleted"] == 3
    assert summary["dry_run"] is False


def test_prune_expired_rows_dry_run_counts_instead_of_deleting() -> None:
    session = MagicMock()
    query = MagicMock()
    session.query.return_value = query
    query.filter.return_value = query
    query.count.return_value = 5

    summary = prune_expired_rows(session, dry_run=True)

    assert summary["dry_run"] is True
    assert summary["market_quotes_deleted"] == 5
    assert not query.delete.called
