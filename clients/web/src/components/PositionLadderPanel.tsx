import { useEffect, useMemo, useState } from "react";

import { api, type PositionLadderDTO } from "@/api/client";
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

function percent(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "–" : `${Math.round(value * 100)}%`;
}

function useLadder(months: number) {
  const [ladder, setLadder] = useState<PositionLadderDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api
      .positionLadder(months)
      .then((response) => live && setLadder(response.data))
      .catch((caught: unknown) => live && setError(caught instanceof Error ? caught.message : String(caught)));
    return () => {
      live = false;
    };
  }, [months]);
  return { ladder, error };
}

function SummaryStrip({ ladder, t }: { ladder: PositionLadderDTO; t: Translate }) {
  return (
    <div className="position-summary" data-position-summary="true">
      <div><span>{t("position.net")}</span><strong>{mwh(ladder.totals.net_mwh)} MWh</strong></div>
      <div><span>{t("position.physical")}</span><strong>{mwh(ladder.totals.physical_mwh)}</strong></div>
      <div><span>{t("position.financial")}</span><strong>{mwh(ladder.totals.financial_mwh)}</strong></div>
      <div><span>{t("position.hedged")}</span><strong>{percent(overallHedgeRatio(ladder))}</strong></div>
      <div><span>{t("position.mtm")}</span><strong className={pnlClass(ladder.mark_to_market)}>{money(ladder.mark_to_market)}</strong></div>
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
  const { ladder, error } = useLadder(months);
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
      </div>
      {error && <p role="alert">{error}</p>}
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
