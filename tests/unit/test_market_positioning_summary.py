"""Unit tests for ``summarize_portfolio`` unknown-versus-zero semantics.

Audit item ``UX01-EXPOSURE-001`` (``docs/ux/UI_DEBT_REGISTER.md``): ``GBP 0``
summary metrics must not coexist with unavailable placeholder rows, because a
missing measurement then reads as a measured zero. These tests pin the domain
boundary between the two:

* no valuation evidence  -> ``None`` aggregates (unknown), warning + lineage kept;
* valuation evidence totalling zero -> ``0.0`` (a real measurement).
"""

from eurogas_nexus.domain.market_positioning import (
    WARNING_VALUATION_EVIDENCE_MISSING,
    PortfolioPnlSnapshot,
    ScreenOrderObservation,
    summarize_portfolio,
)


def _snapshot(
    *,
    snapshot_id: str = "pnl-1",
    portfolio_id: str = "portfolio-demo",
    valuation_time_utc: str = "2026-06-01T08:30:00+00:00",
    realized_pnl_gbp: float = 1200.0,
    unrealized_pnl_gbp: float = 4200.0,
    indicative_pnl_gbp: float = 5400.0,
    cash_value_gbp: float = 1800.0,
    warnings: list[str] | None = None,
) -> PortfolioPnlSnapshot:
    return PortfolioPnlSnapshot(
        pnl_snapshot_id=snapshot_id,
        portfolio_id=portfolio_id,
        resource_id="ttf-bbl-portfolio",
        strategy_id="sap-icis-ocm",
        valuation_time_utc=valuation_time_utc,
        realized_pnl_gbp=realized_pnl_gbp,
        unrealized_pnl_gbp=unrealized_pnl_gbp,
        indicative_pnl_gbp=indicative_pnl_gbp,
        cash_value_gbp=cash_value_gbp,
        market_value_gbp=142000.0,
        quantity_mwh=10000.0,
        valuation_basis="live-bid-mark",
        source_system="fixture-runtime",
        source_reference="fixture:pnl",
        warnings=warnings or [],
    )


def _order(*, order_id: str, status: str) -> ScreenOrderObservation:
    return ScreenOrderObservation(
        order_observation_id=order_id,
        provider_id="ICE_OCM",
        venue="ICE OCM",
        account_label="demo-screen",
        external_order_id=order_id,
        side="SELL",
        order_type="LIMIT",
        hub="NBP",
        product="Within-day",
        contract_code="NBP-WD-20260601",
        delivery_start_utc="2026-06-01T06:00:00+00:00",
        delivery_end_utc="2026-06-02T06:00:00+00:00",
        price=28.4,
        currency="GBP",
        unit="GBP/MWh",
        quantity_mwh=5000.0,
        filled_quantity_mwh=2500.0,
        remaining_quantity_mwh=2500.0,
        status=status,
        observed_at_utc="2026-06-01T08:30:00+00:00",
        source_system="fixture-runtime",
        source_reference="fixture:order",
    )


def test_empty_inputs_report_unknown_not_zero_with_lineage_intact() -> None:
    summary = summarize_portfolio([], [])

    assert summary.total_realized_pnl_gbp is None
    assert summary.total_unrealized_pnl_gbp is None
    assert summary.total_indicative_pnl_gbp is None
    assert summary.total_cash_value_gbp is None
    assert summary.latest_valuation_time_utc is None
    assert summary.portfolio_id == "unknown-portfolio"
    assert WARNING_VALUATION_EVIDENCE_MISSING in summary.warnings
    assert summary.open_order_count == 0
    assert summary.filled_order_count == 0
    assert summary.research_only is True
    assert summary.human_review_required is True
    dumped = summary.model_dump(mode="json")
    assert dumped["total_indicative_pnl_gbp"] is None
    assert dumped["total_cash_value_gbp"] is None


def test_orders_without_valuation_evidence_keep_counts_but_unknown_totals() -> None:
    summary = summarize_portfolio(
        [_order(order_id="ord-open", status="PARTIALLY_FILLED")],
        [],
    )

    assert summary.open_order_count == 1
    assert summary.filled_order_count == 0
    assert summary.total_indicative_pnl_gbp is None
    assert summary.total_cash_value_gbp is None


def test_populated_inputs_totals_are_unchanged() -> None:
    summary = summarize_portfolio(
        [_order(order_id="ord-open", status="WORKING")],
        [_snapshot(warnings=["fixture valuation"])],
    )

    assert summary.portfolio_id == "portfolio-demo"
    assert summary.latest_valuation_time_utc == "2026-06-01T08:30:00+00:00"
    assert summary.total_realized_pnl_gbp == 1200.0
    assert summary.total_unrealized_pnl_gbp == 4200.0
    assert summary.total_indicative_pnl_gbp == 5400.0
    assert summary.total_cash_value_gbp == 1800.0
    assert summary.open_order_count == 1
    assert WARNING_VALUATION_EVIDENCE_MISSING not in summary.warnings
    assert summary.warnings == ["fixture valuation"]


def test_populated_inputs_aggregate_multiple_snapshots() -> None:
    summary = summarize_portfolio(
        [],
        [
            _snapshot(snapshot_id="pnl-1", valuation_time_utc="2026-06-01T08:30:00+00:00"),
            _snapshot(
                snapshot_id="pnl-2",
                valuation_time_utc="2026-06-01T09:30:00+00:00",
                realized_pnl_gbp=100.0,
                unrealized_pnl_gbp=200.0,
                indicative_pnl_gbp=300.0,
                cash_value_gbp=400.0,
            ),
        ],
    )

    assert summary.total_realized_pnl_gbp == 1300.0
    assert summary.total_unrealized_pnl_gbp == 4400.0
    assert summary.total_indicative_pnl_gbp == 5700.0
    assert summary.total_cash_value_gbp == 2200.0
    assert summary.latest_valuation_time_utc == "2026-06-01T09:30:00+00:00"


def test_measured_zero_total_stays_zero_and_is_not_treated_as_unknown() -> None:
    """A real snapshot whose true total is 0.0 is evidence, so it stays 0.0."""

    summary = summarize_portfolio(
        [],
        [
            _snapshot(
                realized_pnl_gbp=0.0,
                unrealized_pnl_gbp=0.0,
                indicative_pnl_gbp=0.0,
                cash_value_gbp=0.0,
            )
        ],
    )

    assert summary.total_realized_pnl_gbp == 0.0
    assert summary.total_unrealized_pnl_gbp == 0.0
    assert summary.total_indicative_pnl_gbp == 0.0
    assert summary.total_cash_value_gbp == 0.0
    assert summary.total_indicative_pnl_gbp is not None
    assert summary.latest_valuation_time_utc == "2026-06-01T08:30:00+00:00"
    assert summary.portfolio_id == "portfolio-demo"
    assert summary.warnings == []
