import type {
  PortfolioLiveSummaryDTO,
  PortfolioPnlSnapshotDTO,
  ScreenOrderObservationDTO,
} from "@/api/client";
import { pnlClass } from "@/app/model/pnlColor";
import { DataGrid, type DataGridColumn } from "@/components/ui";
import { WhyButton } from "./WhyButton";
import { api } from "@/api/client";
import { useCachedRead } from "@/app/data/readCache";
import { formatMeasure } from "@/app/time/valueFormat";

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
  const booksRead = useCachedRead("/portfolio/books", () => api.tradingBooks());
  const bookNames = new Map((booksRead.data?.data.books ?? []).map((book) => [book.book_id, book.name]));
  const orderColumns: DataGridColumn<ScreenOrderObservationDTO>[] = [
    { id: "venue", header: t("orders.col.venue"), rowHeader: true, sortable: true, value: (order) => order.venue },
    { id: "side", header: t("orders.col.side"), sortable: true, value: (order) => order.side },
    { id: "hub", header: t("orders.col.hub"), sortable: true, value: (order) => order.hub },
    {
      id: "quantity",
      header: t("orders.col.quantity"),
      unit: "MWh",
      type: "number",
      sortable: true,
      // Filled volume is the position; an order still working shows what is left.
      value: (order) => (order.filled_quantity_mwh > 0 ? order.filled_quantity_mwh : order.remaining_quantity_mwh),
      format: (value) => (value as number).toLocaleString("en-GB"),
      cellTitle: (order) => t("orders.quantity_hint").replace("{{filled}}", order.filled_quantity_mwh.toLocaleString()).replace("{{total}}", order.quantity_mwh.toLocaleString()).replace("{{remaining}}", order.remaining_quantity_mwh.toLocaleString()),
    },
    // Prices are quoted per order in the venue's unit, so the unit is in the cell.
    { id: "price", header: t("orders.col.price"), type: "number", sortable: true, value: (order) => order.price, render: (order) => <>{formatMeasure("price", order.price)} <small className="ds-grid-unit">{order.unit}</small></> },
    { id: "status", header: t("orders.col.status"), sortable: true, value: (order) => order.status },
  ];
  const pnlColumns: DataGridColumn<PortfolioPnlSnapshotDTO>[] = [
    // The book by name; its id on hover (owner: no internal ids on screen).
    { id: "portfolio", header: t("orders.col.portfolio"), rowHeader: true, value: (snapshot) => bookNames.get(snapshot.portfolio_id) ?? snapshot.portfolio_id, cellTitle: (snapshot) => snapshot.portfolio_id },
    { id: "valuation", header: t("orders.col.valuation"), type: "date", value: (snapshot) => snapshot.valuation_time_utc, format: (value) => formatTimestamp(value as string) },
    { id: "quantity", header: t("orders.col.quantity"), unit: "MWh", type: "number", value: (snapshot) => snapshot.quantity_mwh, format: (value) => (value as number).toLocaleString("en-GB") },
    {
      id: "indicative",
      header: t("orders.col.indicative"),
      unit: "GBP",
      type: "number",
      value: (snapshot) => snapshot.indicative_pnl_gbp,
      render: (snapshot) => (
        <span className="limit-status-cell">
          <span className={pnlClass(snapshot.indicative_pnl_gbp)}>{Math.round(snapshot.indicative_pnl_gbp).toLocaleString("en-GB")}</span>
          <WhyButton subject="pnl" id={snapshot.pnl_snapshot_id} label={`P&L ${bookNames.get(snapshot.portfolio_id) ?? snapshot.portfolio_id}`} t={t} />
        </span>
      ),
    },
    { id: "cash", header: t("orders.col.cash"), unit: "GBP", type: "number", value: (snapshot) => snapshot.cash_value_gbp, format: (value) => Math.round(value as number).toLocaleString("en-GB") },
    { id: "basis", header: t("orders.col.basis"), value: (snapshot) => snapshot.valuation_basis },
  ];

  return (
    <div className="workspace-grid orders-page">
      {/* One line of counts, not four tiles of "Unknown"; the read-only note is the heading's
          tooltip (#69). PnL totals show only when the backend measured them. */}
      <div className="span-3 metric-inline orders-summary" title={t("orders.subtitle")}>
        {portfolioSummary?.total_indicative_pnl_gbp != null && (
          <div><span>{t("portfolio.indicative_pnl")}</span><strong className={pnlClass(portfolioSummary.total_indicative_pnl_gbp)}>{formatGbpTotal(portfolioSummary.total_indicative_pnl_gbp, t)}</strong></div>
        )}
        {portfolioSummary?.total_cash_value_gbp != null && (
          <div><span>{t("portfolio.cash_value")}</span><strong>{formatGbpTotal(portfolioSummary.total_cash_value_gbp, t)}</strong></div>
        )}
        <div><span>{t("portfolio.open_orders")}</span><strong>{portfolioSummary?.open_order_count ?? screenOrders.length}</strong></div>
        <div><span>{t("orders.filled_orders")}</span><strong>{portfolioSummary?.filled_order_count ?? "n/a"}</strong></div>
      </div>
      <div className="workspace-panel span-3">
        <h2 title={t("orders.subtitle")}>{t("orders.screen_orders")}</h2>
        <DataGrid
          id="screen-orders"
          className="orders-table"
          label={t("orders.screen_orders")}
          columns={orderColumns}
          rows={screenOrders}
          rowKey={(order) => order.order_observation_id}
          density="compact"
          maxHeight="min(60vh, 560px)"
          // The row carries the observation's own id, so the acceptance sweep compares it with
          // the projection read by exact id (`scripts/uat/readToRender.mjs`).
          rowAttributes={(order) => ({ "data-record": "screen-order", "data-record-id": order.order_observation_id })}
          empty={<p className="muted panel-empty-line" data-empty-state="screen-orders">{t("orders.none_screen")}</p>}
        />
      </div>
      {pnlSnapshots.length === 0 ? (
        // No snapshot is one line under the table above, not a table with a row of n/a (#69).
        <p className="span-3 muted panel-empty-line" data-empty-state="pnl-snapshots">
          {t("orders.pnl_snapshots")}: {t("orders.none_pnl")}
        </p>
      ) : (
      <div className="workspace-panel span-3">
        <h2>{t("orders.pnl_snapshots")}</h2>
        <DataGrid
          id="pnl-snapshots"
          label={t("orders.pnl_snapshots")}
          columns={pnlColumns}
          rows={pnlSnapshots.slice(0, 8)}
          rowKey={(snapshot) => snapshot.pnl_snapshot_id}
          density="compact"
          // The row carries the snapshot's own id, so the acceptance sweep compares it with the
          // projection read by exact id (`scripts/uat/readToRender.mjs`).
          rowAttributes={(snapshot) => ({ "data-record": "pnl-snapshot", "data-record-id": snapshot.pnl_snapshot_id })}
        />
      </div>
      )}
    </div>
  );
}
