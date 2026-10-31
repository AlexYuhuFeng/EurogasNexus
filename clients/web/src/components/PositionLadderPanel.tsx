import { useEffect, useMemo, useState } from "react";

import { api, downloadReportCsv, type PositionLadderDTO } from "@/api/client";
import {
  barShare,
  groupLadderByMonth,
  ladderMonthLabel,
  overallHedgeRatio,
} from "@/app/model/positionLadderModel";
import { pnlClass } from "@/app/model/pnlColor";

type Translate = (key: string, options?: Record<string, unknown>) => string;

function mwh(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "–";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString("en-GB")}`;
}

function money(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "–";
  return Math.round(value).toLocaleString("en-GB");
}

function price(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "–" : value.toFixed(3);
}

function percent(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "–" : `${Math.round(value * 100)}%`;
}

function useLadder(months: number, groupBy = "hub", reportingCurrency = "") {
  const [ladder, setLadder] = useState<PositionLadderDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api
      .positionLadder(months, undefined, { groupBy, reportingCurrency: reportingCurrency || undefined })
      .then((response) => live && setLadder(response.data))
      .catch((caught: unknown) => live && setError(caught instanceof Error ? caught.message : String(caught)));
    return () => {
      live = false;
    };
  }, [months, groupBy, reportingCurrency]);
  return { ladder, error };
}

function SummaryStrip({ ladder, t }: { ladder: PositionLadderDTO; t: Translate }) {
  return (
    <div className="position-summary" data-position-summary="true">
      <div><span>{t("position.net")}</span><strong>{mwh(ladder.totals.net_mwh)} MWh</strong></div>
      <div><span>{t("position.physical")}</span><strong>{mwh(ladder.totals.physical_mwh)}</strong></div>
      <div><span>{t("position.financial")}</span><strong>{mwh(ladder.totals.financial_mwh)}</strong></div>
      <div><span>{t("position.hedged")}</span><strong>{percent(overallHedgeRatio(ladder))}</strong></div>
      <div>
        <span>{t("position.mtm")}{ladder.reporting_currency ? ` (${ladder.reporting_currency})` : ""}</span>
        <strong className={pnlClass(ladder.mark_to_market)}>{money(ladder.mark_to_market)}</strong>
      </div>
      <div>
        <span>{t("position.var")}</span>
        <strong title={t("position.var_help", { count: ladder.var_observations })}>{money(ladder.var_95_1d)}</strong>
      </div>
    </div>
  );
}

/** Compact strip for the Portfolio overview: what management reads first. */
export function PositionRiskSummary({ t }: { t: Translate }) {
  const { ladder } = useLadder(12);
  if (!ladder || ladder.rows.length === 0) return null;
  return (
    <section className="workspace-panel span-3 position-ladder-panel" aria-label={t("position.title")}>
      <h2>{t("position.title")}</h2>
      <SummaryStrip ladder={ladder} t={t} />
    </section>
  );
}

/**
 * Physical supply and sales next to screen hedges, by delivery month and hub: how long or short
 * the desk is, where, when, and how much of it is hedged.
 */
export function PositionLadderPanel({ t }: { t: Translate }) {
  const [months, setMonths] = useState(12);
  const [groupBy, setGroupBy] = useState("hub");
  const [currency, setCurrency] = useState("");
  const { ladder, error } = useLadder(months, groupBy, currency);
  const grouped = useMemo(() => groupLadderByMonth(ladder?.rows ?? []), [ladder]);

  return (
    <section className="workspace-panel span-3 position-ladder-panel" aria-labelledby="position-ladder-title">
      <div className="panel-title-row">
        <h2 id="position-ladder-title">{t("position.title")}</h2>
        <label className="position-horizon">
          <span>{t("position.horizon")}</span>
          <select value={months} onChange={(event) => setMonths(Number(event.target.value))}>
            {[3, 6, 12, 24].map((value) => (
              <option key={value} value={value}>{t("position.months", { count: value })}</option>
            ))}
          </select>
        </label>
        <label className="position-horizon">
          <span>{t("position.group_by")}</span>
          <select value={groupBy} onChange={(event) => setGroupBy(event.target.value)}>
            {["hub", "firm", "legal_entity", "region", "business", "book"].map((value) => (
              <option key={value} value={value}>{t(`position.level_${value}`)}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="report-export"
          onClick={() =>
            void downloadReportCsv("/portfolio/position-ladder", {
              months: String(months),
              ...(groupBy !== "hub" ? { group_by: groupBy } : {}),
              ...(currency ? { reporting_currency: currency } : {}),
            })
          }
        >
          {t("report.export_csv")}
        </button>
        <label className="position-horizon">
          <span>{t("position.reporting_currency")}</span>
          <select value={currency} onChange={(event) => setCurrency(event.target.value)}>
            <option value="">{t("position.currency_auto")}</option>
            {["EUR", "GBP", "USD", "CAD"].map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      {ladder?.rollup && ladder.rollup.length > 0 && (
        <table className="position-ladder" data-position-rollup="true">
          <thead>
            <tr>
              <th scope="col">{t(`position.level_${ladder.group_by ?? groupBy}`)}</th>
              <th scope="col" className="num">{t("position.physical")}</th>
              <th scope="col" className="num">{t("position.financial")}</th>
              <th scope="col" className="num">{t("position.net")}</th>
              <th scope="col" className="num">{t("position.hedged")}</th>
              <th scope="col" className="num">{t("position.mtm")}</th>
            </tr>
          </thead>
          <tbody>
            {ladder.rollup.map((row) => (
              <tr key={row.group} data-record="position-rollup-row">
                <th scope="row">{row.group === "UNASSIGNED" ? t("position.unassigned") : row.group}</th>
                <td className="num">{mwh(row.physical_mwh)}</td>
                <td className="num">{mwh(row.financial_mwh)}</td>
                <td className={`num ${row.net_mwh >= 0 ? "long" : "short"}`}>{mwh(row.net_mwh)}</td>
                <td className="num">{percent(row.hedge_ratio)}</td>
                <td className={`num ${pnlClass(row.mark_to_market)}`}>{money(row.mark_to_market)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {ladder && ladder.rows.length === 0 && <p className="muted">{t("position.empty")}</p>}
      {ladder && ladder.rows.length > 0 && (
        <>
          <SummaryStrip ladder={ladder} t={t} />
          <table className="position-ladder" data-position-ladder="true">
            <thead>
              <tr>
                <th scope="col">{t("position.month")}</th>
                <th scope="col">{t("position.hub")}</th>
                <th scope="col" className="num">{t("position.physical")}</th>
                <th scope="col" className="num">{t("position.financial")}</th>
                <th scope="col" className="num">{t("position.net")}</th>
                <th scope="col">{t("position.net_bar")}</th>
                <th scope="col" className="num">{t("position.hedged")}</th>
                <th scope="col" className="num">{t("position.mark")}</th>
              </tr>
            </thead>
            <tbody>
              {grouped.map((month) =>
                month.rows.map((row, index) => (
                  <tr key={`${row.month}-${row.hub}`} data-record="position-row">
                    {index === 0 && (
                      <th scope="rowgroup" rowSpan={month.rows.length}>{ladderMonthLabel(month.month)}</th>
                    )}
                    <td>{row.hub}</td>
                    <td className="num">{mwh(row.physical_mwh)}</td>
                    <td className="num">{mwh(row.financial_mwh)}</td>
                    <td className={`num ${row.net_mwh >= 0 ? "long" : "short"}`}>{mwh(row.net_mwh)}</td>
                    <td className="position-bar-cell" aria-hidden="true">
                      <span
                        className={`position-bar ${row.net_mwh >= 0 ? "long" : "short"}`}
                        style={{ width: `${barShare(row.net_mwh, ladder.rows) * 50}%` }}
                      />
                    </td>
                    <td className="num">{percent(row.hedge_ratio)}</td>
                    <td
                      className="num"
                      data-mark-method={row.mark_method ?? undefined}
                      title={row.mark_method ? t(`position.mark_${row.mark_method}`) : undefined}
                    >
                      {price(row.mark)}
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
          <ul className="position-notes">
            {ladder.warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </>
      )}
    </section>
  );
}
