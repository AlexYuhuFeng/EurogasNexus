"""Market positioning DB model contract tests."""

from eurogas_nexus.db.registry import list_required_tables


def test_market_positioning_tables_are_registered() -> None:
    required = set(list_required_tables())

    assert "screen_order_observations" in required
    assert "portfolio_pnl_snapshots" in required


def test_market_positioning_models_are_in_metadata() -> None:
    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models import PortfolioPnlSnapshotRecord, ScreenOrderObservationRecord

    assert ScreenOrderObservationRecord.__tablename__ == "screen_order_observations"
    assert PortfolioPnlSnapshotRecord.__tablename__ == "portfolio_pnl_snapshots"
    assert "screen_order_observations" in Base.metadata.tables
    assert "portfolio_pnl_snapshots" in Base.metadata.tables
