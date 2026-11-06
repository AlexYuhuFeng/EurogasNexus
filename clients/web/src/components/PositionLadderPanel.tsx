import { useEffect, useMemo, useState } from "react";

import { api, type PositionLadderDTO } from "@/api/client";
import { ReportExport } from "./ReportExport";
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
  return value == null || !Number.isFinite(value) ? "–" : `${Math.round(value * 100) + 0}%`;
}

function hedgeText(ratio: number | null | undefined, t: Translate): string {
  return ratio != null && Number.isFinite(ratio) && Math.round(ratio * 100) < 0
    ? t("position.hedge_adds", { pct: percent(-ratio) })
    : percent(ratio);
}

/**
 * The hedge cell. A negative ratio means the trades point the same way as the physical
 * position (bought on top of a long), so they add risk instead of hedging it: shown as
 * "adds N%", flagged, never as a negative hedge.
 */
function HedgeCell({ ratio, t }: { ratio: number | null | undefined; t: Translate }) {
  if (ratio != null && Number.isFinite(ratio) && Math.round(ratio * 100) < 0) {
    return (
      <td className="num warning-text" title={t("position.hedge_adds_hint")}>
        {t("position.hedge_adds", { pct: percent(-ratio) })}
      </td>
    );
  }
  return <td className="num">{percent(ratio)}</td>;
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
      <div><span>{t("position.hedged")}</span><strong>{hedgeText(overallHedgeRatio(ladder), t)}</strong></div>
      <div>
        <span>{t("position.mtm")}{ladder.reporting_currency ? ` (${ladder.reporting_currency})` : ""}</span>
        <strong className={pnlClass(ladder.mark_to_market)}>{money(ladder.mark_to_market)}</strong>
      </div>
      {/* Gross by month adds information only when months offset; equal to |net| it repeats it. */}
      {ladder.totals.gross_tenor_mwh !== undefined &&
        Math.abs(ladder.totals.gross_tenor_mwh) !== Math.abs(ladder.totals.net_mwh) && (
        <div>
          <span>{t("position.gross_tenor")}</span>
          <strong title={t("position.gross_tenor_help")}>{mwh(ladder.totals.gross_tenor_mwh)} MWh</strong>
        </div>
      )}
      <div>
        <span>{t("position.var")}</span>
        {ladder.offsetting_hubs && ladder.offsetting_hubs.length > 0 ? (
          // A calendar spread is never shown as zero risk (#53).
          <strong className="position-var-withheld" title={t("position.var_withheld_help")}>
            {t("position.var_withheld").replace("{{hubs}}", ladder.offsetting_hubs.join(", "))}
          </strong>
        ) : (
          <strong title={ladder.var_95_1d == null ? undefined : t("position.var_help", { count: ladder.var_observations })}>{money(ladder.var_95_1d)}</strong>
        )}
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
        <ReportExport t={t}
          path="/portfolio/position-ladder"
          params={{
            months: String(months),
              ...(groupBy !== "hub" ? { group_by: groupBy } : {}),
              ...(currency ? { reporting_currency: currency } : {}),
          }}
        />
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
                <HedgeCell ratio={row.hedge_ratio} t={t} />
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
                    <HedgeCell ratio={row.hedge_ratio} t={t} />
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
          <TenorShockScenario ladder={ladder} months={months} currency={currency} t={t} />
          <ul className="position-notes">
            {ladder.warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </>
      )}
    </section>
  );
}

/**
 * A price shock per hub and delivery month applied to the open position (#53). Each month moves
 * on its own, so a calendar spread that is flat at the hub shows the loss a curve twist causes.
 * Months held without a shock are listed, never assumed to move by zero silently.
 */
function TenorShockScenario({
  ladder,
  months,
  currency,
  t,
}: {
  ladder: PositionLadderDTO;
  months: number;
  currency: string;
  t: Translate;
}) {
  const keys = useMemo(
    () => ladder.rows.filter((row) => Math.abs(row.net_mwh) > 1e-9).map((row) => `${row.hub}:${row.month}`),
    [ladder],
  );
  const [shocks, setShocks] = useState<Record<string, string>>({});
  const [result, setResult] = useState<PositionLadderDTO["scenario"]>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  if (keys.length === 0) return null;
  const run = async () => {
    const list = Object.entries(shocks)
      .filter(([, value]) => value.trim() !== "" && Number.isFinite(Number(value)))
      .map(([key, value]) => `${key}:${Number(value)}`);
    if (list.length === 0) return;
    setBusy(true);
    setFailure(null);
    try {
      const response = await api.positionLadder(months, undefined, {
        reportingCurrency: currency || undefined,
        shocks: list,
      });
      setResult(response.data.scenario ?? null);
    } catch (caught) {
      setFailure(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="position-scenario" data-position-scenario="true">
      <summary>{t("position.scenario_title")}</summary>
      <p className="muted">{t("position.scenario_help")}</p>
      <div className="position-scenario-grid">
        {keys.map((key) => {
          const [hub, month] = key.split(":");
          return (
            <label key={key}>
              <span>{hub} {ladderMonthLabel(month ?? "")}</span>
              <input
                type="number"
                step="0.01"
                inputMode="decimal"
                value={shocks[key] ?? ""}
                placeholder="0.00"
                onChange={(event) => setShocks((current) => ({ ...current, [key]: event.target.value }))}
              />
            </label>
          );
        })}
      </div>
      <button type="button" disabled={busy} onClick={() => void run()}>{t("position.scenario_run")}</button>
      {failure && <p role="alert">{failure}</p>}
      {result && (
        <div className="position-scenario-result" role="status">
          <strong className={pnlClass(result.pnl)}>
            {t("position.scenario_pnl")}: {money(result.pnl)} {ladder.reporting_currency ?? ""}
          </strong>
          {result.unshocked.length > 0 && (
            <small className="muted">{t("position.scenario_unshocked")}: {result.unshocked.join(", ")}</small>
          )}
          {result.excluded_no_fx.length > 0 && (
            <small className="muted">{t("position.scenario_no_fx")}: {result.excluded_no_fx.join(", ")}</small>
          )}
        </div>
      )}
    </details>
  );
}
