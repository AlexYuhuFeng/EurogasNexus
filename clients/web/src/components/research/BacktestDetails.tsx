/**
 * Research → Spreads → history with a rule: what a trader and a risk manager need under the
 * headline figures. The assumptions line (execution, cost and where it came from, sizing,
 * roll, tariff, FX), the warning when there are too few trades, P&L per MWh and for the size,
 * the equity curve with its drawdown, the worst trade, the later share of the history as an
 * out-of-sample check, and the trades. Every figure is the server's (`analysis`).
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import "@/styles/promptDesk.css";
import { Chart, type ChartData } from "@/components/ui/charts";

export interface BacktestAnalysis {
  points: Array<{ date: string; cumulative_pnl?: number; drawdown?: number }>;
  metrics: Record<string, number | boolean | null>;
  trades?: Array<{ opened: string; closed: string | null; direction: string; entry_spread: number; exit_spread: number | null; pnl: number; pnl_per_mwh?: number; holding_days?: number | null }>;
  assumptions?: string;
  limitations?: string[];
  periods?: Record<string, { days: number; pnl: number; closed_trades: number; hit_rate: number | null; from?: string }>;
}

function fixed(value: number | null | undefined, places: number): string {
  return value === null || value === undefined || Number.isNaN(value) ? "–" : value.toFixed(places);
}

export function BacktestDetails({ analysis, unit, currency, simulated }: { analysis: BacktestAnalysis; unit: string; currency: string; simulated: boolean }) {
  const { t } = useTranslation();
  const metrics = analysis.metrics;
  const data = useMemo<ChartData>(() => ({
    axis: "gas-day",
    x: analysis.points.map((point) => point.date),
    xTitle: t("spreads.history.x"),
    unit: currency,
    series: [
      { id: "equity", label: t("backtest.equity"), values: analysis.points.map((point) => point.cumulative_pnl ?? null), simulated, decimals: 0 },
      { id: "drawdown", label: t("backtest.drawdown"), values: analysis.points.map((point) => point.drawdown ?? null), simulated, decimals: 0 },
    ],
    rules: [{ id: "zero", value: 0, kind: "zero" as const }],
  }), [analysis.points, currency, simulated, t]);
  const trades = analysis.trades ?? [];
  const tooFew = metrics.too_few_trades === true;
  return (
    <section className="backtest-details" data-backtest-details>
      {analysis.assumptions && (
        <p className="backtest-assumptions" data-backtest-assumptions>
          <strong>{t("backtest.assumptions")}</strong> {analysis.assumptions}
        </p>
      )}
      {tooFew && <p className="prompt-sim" role="note" data-backtest-too-few>{t("backtest.too_few", { count: Number(metrics.closed_trades ?? 0) })}</p>}
      <dl className="prompt-figures">
        <div data-figure="pnl-per-mwh"><dt>{t("backtest.pnl_per_mwh", { unit })}</dt><dd>{fixed(metrics.pnl_per_mwh as number, 3)}</dd></div>
        <div data-figure="max-drawdown"><dt>{t("backtest.max_drawdown", { currency })}</dt><dd>{fixed(metrics.max_drawdown as number, 0)}</dd></div>
        <div data-figure="worst-trade"><dt>{t("backtest.worst_trade", { currency })}</dt><dd>{fixed(metrics.worst_trade as number, 0)}</dd></div>
        <div><dt>{t("backtest.holding")}</dt><dd>{fixed(metrics.average_holding_days as number, 1)}</dd></div>
        <div><dt>{t("backtest.roll_days")}</dt><dd>{String(metrics.roll_days_excluded ?? 0)}</dd></div>
        {analysis.periods && (["in_sample", "out_of_sample"] as const).map((key) => (
          <div key={key} data-figure={key}>
            <dt>{t(`backtest.${key}`, { from: analysis.periods?.out_of_sample?.from ?? "" })}</dt>
            <dd>{t("backtest.period_value", {
              pnl: fixed(analysis.periods?.[key]?.pnl, 0),
              trades: analysis.periods?.[key]?.closed_trades ?? 0,
              hit: analysis.periods?.[key]?.hit_rate === null || analysis.periods?.[key]?.hit_rate === undefined ? "–" : `${fixed((analysis.periods?.[key]?.hit_rate ?? 0) * 100, 0)} %`,
            })}</dd>
          </div>
        ))}
      </dl>
      <Chart id="backtest-equity" title={t("backtest.equity_title", { currency })} data={data} t={t} height={180} simulated={simulated} />
      {trades.length > 0 && (
        <div className="prompt-table-wrap" tabIndex={0} role="region" aria-label={t("backtest.trades")}>
          <table className="prompt-table" data-backtest-trades>
            <caption>{t("backtest.trades_caption", { unit, currency })}</caption>
            <thead>
              <tr>
                <th scope="col">{t("backtest.col.opened")}</th>
                <th scope="col">{t("backtest.col.closed")}</th>
                <th scope="col">{t("backtest.col.direction")}</th>
                <th scope="col" className="num">{t("backtest.col.entry")}</th>
                <th scope="col" className="num">{t("backtest.col.exit")}</th>
                <th scope="col" className="num">{t("backtest.col.per_mwh")}</th>
                <th scope="col" className="num">{t("backtest.col.pnl")}</th>
                <th scope="col" className="num">{t("backtest.col.days")}</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr key={trade.opened}>
                  <td>{trade.opened}</td>
                  <td>{trade.closed ?? t("backtest.open")}</td>
                  <td>{t(`backtest.direction.${trade.direction}`)}</td>
                  <td className="num">{fixed(trade.entry_spread, 3)}</td>
                  <td className="num">{fixed(trade.exit_spread, 3)}</td>
                  <td className="num">{fixed(trade.pnl_per_mwh, 3)}</td>
                  <td className="num">{fixed(trade.pnl, 0)}</td>
                  <td className="num">{trade.holding_days ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
