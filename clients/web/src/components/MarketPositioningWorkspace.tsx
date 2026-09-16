import type {
  PortfolioLiveSummaryDTO,
  PortfolioPnlSnapshotDTO,
  ScreenOrderObservationDTO,
} from "@/api/client";

type Translate = (key: string) => string;

/**
 * Render a summary total without inventing evidence.
 *
 * The backend reports `null` when there is no valuation evidence to aggregate
 * (empty or degraded read) and a real `0` when the measured total is genuinely
 * zero. Only the latter may be printed as `GBP 0`; the former must stay an
 * explicit unknown.
 */
function formatGbpTotal(value: number | null | undefined, t: Translate): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return t("status.unknown");
  }
  return `GBP ${Math.round(value).toLocaleString()}`;
}

interface MarketPositioningWorkspaceProps {
  portfolioSummary: PortfolioLiveSummaryDTO | null;
  screenOrders: ScreenOrderObservationDTO[];
  pnlSnapshots: PortfolioPnlSnapshotDTO[];
  formatTimestamp: (value: string | null | undefined) => string;
  t: Translate;
}

export function MarketPositioningWorkspace({
  portfolioSummary,
  screenOrders,
  pnlSnapshots,
  formatTimestamp,
  t,
}: MarketPositioningWorkspaceProps) {
  return (
    <div className="workspace-grid orders-page">
      <div className="workspace-panel span-3">
        <div className="section-heading">
          <span className="eyebrow">{t("nav.orders")}</span>
          <strong>{t("orders.title")}</strong>
        </div>
        <p className="panel-copy">{t("orders.subtitle")}</p>
        <div className="metric-grid four-column">
          <div><span>{t("portfolio.indicative_pnl")}</span><strong>{formatGbpTotal(portfolioSummary?.total_indicative_pnl_gbp, t)}</strong></div>
          <div><span>{t("portfolio.cash_value")}</span><strong>{formatGbpTotal(portfolioSummary?.total_cash_value_gbp, t)}</strong></div>
          <div><span>{t("portfolio.open_orders")}</span><strong>{portfolioSummary?.open_order_count ?? screenOrders.length}</strong></div>
          <div><span>{t("orders.filled_orders")}</span><strong>{portfolioSummary?.filled_order_count ?? "n/a"}</strong></div>
        </div>
      </div>
      <div className="workspace-panel span-3">
        <h2>{t("orders.screen_orders")}</h2>
        <div className="data-table orders-table" tabIndex={0}>
          <div className="data-table-row header six"><span>Venue</span><span>Side</span><span>Hub</span><span>Qty</span><span>Price</span><span>Status</span></div>
          {screenOrders.map((order) => (
            <div key={`orders-${order.order_observation_id}`} className="data-table-row six">
              <span>{order.venue}</span><span>{order.side}</span><span>{order.hub}</span><strong>{order.remaining_quantity_mwh.toLocaleString()} MWh</strong><span>{order.price.toFixed(2)} {order.unit}</span><span>{order.status}</span>
            </div>
          ))}
          {screenOrders.length === 0 && (
            <div className="data-table-row six"><span>n/a</span><span>n/a</span><span>n/a</span><strong>{t("status.unknown")}</strong><span>n/a</span><span>{t("data.unavailable")}</span></div>
          )}
        </div>
      </div>
      <div className="workspace-panel span-3">
        <h2>{t("orders.pnl_snapshots")}</h2>
        <div className="data-table" tabIndex={0}>
          <div className="data-table-row header six"><span>Portfolio</span><span>Valuation</span><span>Quantity</span><span>Indicative</span><span>Cash</span><span>Basis</span></div>
          {pnlSnapshots.slice(0, 8).map((snapshot) => (
            <div key={`pnl-${snapshot.pnl_snapshot_id}`} className="data-table-row six">
              <strong>{snapshot.portfolio_id}</strong>
              <span>{formatTimestamp(snapshot.valuation_time_utc)}</span>
              <span>{snapshot.quantity_mwh.toLocaleString()} MWh</span>
              <span>GBP {Math.round(snapshot.indicative_pnl_gbp).toLocaleString()}</span>
              <span>GBP {Math.round(snapshot.cash_value_gbp).toLocaleString()}</span>
              <span>{snapshot.valuation_basis}</span>
            </div>
          ))}
          {pnlSnapshots.length === 0 && (
            <div className="data-table-row six"><strong>n/a</strong><span>n/a</span><span>{t("status.unknown")}</span><span>n/a</span><span>n/a</span><span>{t("data.unavailable")}</span></div>
          )}
        </div>
      </div>
    </div>
  );
}
