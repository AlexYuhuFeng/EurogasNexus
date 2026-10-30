import { useEffect, useMemo, useState } from "react";

import { api, ApiError, type SpreadAnalysisDTO, type SpreadSeriesDTO } from "@/api/client";
import {
  defaultSpreadDraft,
  MAX_SPREAD_LEGS,
  seriesKey,
  seriesLabel,
  spreadAnalysisRequest,
  spreadDraftBlocker,
  spreadFormula,
  type SpreadLabDraft,
} from "@/app/model/spreadLabModel";
import { StrategyLineChart } from "./StrategyLabCharts";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface SpreadLabWorkspaceProps {
  t: Translate;
}

function num(value: number | null | undefined, digits = 2): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })
    : "–";
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.detail as { message?: string } | undefined;
    return detail?.message ?? error.message;
  }
  return error instanceof Error ? error.message : String(error);
}

/**
 * Pick two to four daily series, weight them, read the spread's level, z-score and history,
 * and see whether one declared rule on it would have paid - in one screen, without saving a
 * strategy first. Freeze-and-shadow stays in the Design/Backtest tasks for rules worth keeping.
 */
export function SpreadLabWorkspace({ t }: SpreadLabWorkspaceProps) {
  const [catalogue, setCatalogue] = useState<SpreadSeriesDTO[] | null>(null);
  const [draft, setDraft] = useState<SpreadLabDraft | null>(null);
  const [result, setResult] = useState<SpreadAnalysisDTO | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    let live = true;
    api
      .spreadSeries()
      .then((response) => {
        if (!live) return;
        setCatalogue(response.data);
        setDraft(defaultSpreadDraft(response.data));
      })
      .catch((caught: unknown) => live && setError(errorMessage(caught)));
    return () => {
      live = false;
    };
  }, []);

  const blocker = draft && catalogue ? spreadDraftBlocker(draft, catalogue) : null;
  const formula = draft && catalogue ? spreadFormula(draft, catalogue) : "";

  async function run() {
    if (!draft || !catalogue || blocker) return;
    setRunning(true);
    setError(null);
    try {
      const response = await api.spreadAnalysis(spreadAnalysisRequest(draft, catalogue));
      setResult(response.data);
      setWarnings(response.meta.warnings ?? []);
    } catch (caught) {
      setResult(null);
      setError(errorMessage(caught));
    } finally {
      setRunning(false);
    }
  }

  const charts = useMemo(() => {
    if (!result) return null;
    return {
      spread: result.points.map((point) => ({ label: point.date, value: point.spread })),
      zscore: result.points.map((point) => ({ label: point.date, value: point.zscore })),
      pnl: result.points.map((point) => ({ label: point.date, value: point.cumulative_pnl })),
    };
  }, [result]);

  if (catalogue === null) {
    return <p className="muted">{error ?? t("spread_lab.loading")}</p>;
  }
  if (catalogue.length === 0 || !draft) {
    return <p className="muted">{t("spread_lab.no_series")}</p>;
  }

  const update = (patch: Partial<SpreadLabDraft>) => setDraft({ ...draft, ...patch });
  const updateRule = (patch: Partial<SpreadLabDraft["rule"]>) =>
    setDraft({ ...draft, rule: { ...draft.rule, ...patch } });
  const currency = result?.unit.split("/")[0] ?? "";

  return (
    <section className="spread-lab" aria-label={t("spread_lab.title")}>
      <form
        className="spread-lab-form"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void run();
        }}
      >
        <fieldset className="spread-lab-legs">
          <legend>{t("spread_lab.legs")}</legend>
          {draft.legs.map((leg, index) => (
            <div className="spread-lab-leg" key={`leg-${index}`}>
              <label>
                <span>{t("spread_lab.weight")}</span>
                <input
                  type="number"
                  step="0.1"
                  value={leg.weight}
                  onChange={(event) => {
                    const legs = [...draft.legs];
                    legs[index] = { ...leg, weight: Number(event.target.value) };
                    update({ legs });
                  }}
                />
              </label>
              <label className="spread-lab-series">
                <span>{t("spread_lab.series", { index: index + 1 })}</span>
                <select
                  value={leg.seriesKey}
                  onChange={(event) => {
                    const legs = [...draft.legs];
                    legs[index] = { ...leg, seriesKey: event.target.value };
                    update({ legs });
                  }}
                >
                  <option value="">{t("spread_lab.pick_series")}</option>
                  {catalogue.map((series) => (
                    <option key={seriesKey(series)} value={seriesKey(series)}>
                      {seriesLabel(series)} · {series.unit} · {series.days}d
                    </option>
                  ))}
                </select>
              </label>
              {draft.legs.length > 1 && (
                <button
                  type="button"
                  className="ghost"
                  aria-label={t("spread_lab.remove_leg", { index: index + 1 })}
                  onClick={() => update({ legs: draft.legs.filter((_, other) => other !== index) })}
                >
                  ×
                </button>
              )}
            </div>
          ))}
          {draft.legs.length < MAX_SPREAD_LEGS && (
            <button
              type="button"
              className="ghost"
              onClick={() => update({ legs: [...draft.legs, { seriesKey: "", weight: -1 }] })}
            >
              {t("spread_lab.add_leg")}
            </button>
          )}
          <p className="spread-lab-formula" aria-live="polite">
            {t("spread_lab.formula")}: <strong>{formula}</strong>
          </p>
        </fieldset>

        <fieldset className="spread-lab-rule">
          <legend>{t("spread_lab.rule")}</legend>
          <label>
            <span>{t("spread_lab.rule_kind")}</span>
            <select
              value={draft.rule.kind}
              onChange={(event) => updateRule({ kind: event.target.value as "zscore" | "threshold" })}
            >
              <option value="zscore">{t("spread_lab.rule_zscore")}</option>
              <option value="threshold">{t("spread_lab.rule_threshold")}</option>
            </select>
          </label>
          <label>
            <span>{t("spread_lab.lookback")}</span>
            <input type="number" min={5} step={1} value={draft.rule.lookback}
              onChange={(event) => updateRule({ lookback: Number(event.target.value) })} />
          </label>
          {draft.rule.kind === "zscore" ? (
            <>
              <label>
                <span>{t("spread_lab.entry_z")}</span>
                <input type="number" step="0.1" value={draft.rule.entry_z}
                  onChange={(event) => updateRule({ entry_z: Number(event.target.value) })} />
              </label>
              <label>
                <span>{t("spread_lab.exit_z")}</span>
                <input type="number" step="0.1" value={draft.rule.exit_z}
                  onChange={(event) => updateRule({ exit_z: Number(event.target.value) })} />
              </label>
            </>
          ) : (
            <>
              <label>
                <span>{t("spread_lab.low")}</span>
                <input type="number" step="any" value={draft.rule.low ?? ""}
                  onChange={(event) => updateRule({ low: event.target.value === "" ? null : Number(event.target.value) })} />
              </label>
              <label>
                <span>{t("spread_lab.high")}</span>
                <input type="number" step="any" value={draft.rule.high ?? ""}
                  onChange={(event) => updateRule({ high: event.target.value === "" ? null : Number(event.target.value) })} />
              </label>
            </>
          )}
          <label>
            <span>{t("spread_lab.volume")}</span>
            <input type="number" min={1} step="any" value={draft.rule.volume_mwh_per_day}
              onChange={(event) => updateRule({ volume_mwh_per_day: Number(event.target.value) })} />
          </label>
          <label>
            <span>{t("spread_lab.cost")}</span>
            <input type="number" min={0} step="any" value={draft.rule.cost_per_mwh}
              onChange={(event) => updateRule({ cost_per_mwh: Number(event.target.value) })} />
          </label>
          <label>
            <span>{t("spread_lab.from")}</span>
            <input type="date" value={draft.dateFrom} onChange={(event) => update({ dateFrom: event.target.value })} />
          </label>
          <label>
            <span>{t("spread_lab.to")}</span>
            <input type="date" value={draft.dateTo} onChange={(event) => update({ dateTo: event.target.value })} />
          </label>
        </fieldset>

        <div className="spread-lab-actions">
          <button type="submit" disabled={Boolean(blocker) || running} title={blocker ? t(blocker) : undefined}>
            {running ? t("spread_lab.running") : t("spread_lab.run")}
          </button>
          {blocker && <span className="muted">{t(blocker)}</span>}
          <span className="muted">{t("spread_lab.no_look_ahead")}</span>
        </div>
      </form>

      {error && <p role="alert" className="spread-lab-error">{error}</p>}
      {warnings.length > 0 && (
        <ul className="spread-lab-warnings">{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      )}

      {result && charts && (
        <div className="spread-lab-result" data-spread-analysis={result.analysis_hash.slice(0, 12)}>
          <div className="strategy-kpi-strip">
            <div><span>{t("spread_lab.stat.last")}</span><strong>{num(result.statistics.last)} {result.unit}</strong></div>
            <div><span>{t("spread_lab.stat.mean_std")}</span><strong>{num(result.statistics.mean)} ± {num(result.statistics.std)}</strong></div>
            <div><span>{t("spread_lab.stat.zscore")}</span><strong>{num(result.statistics.zscore_last)}</strong></div>
            <div><span>{t("spread_lab.stat.percentile")}</span><strong>{num(result.statistics.percentile_last, 0)}%</strong></div>
            <div><span>{t("spread_lab.stat.half_life")}</span><strong>{num(result.statistics.half_life_days, 1)} d</strong></div>
            <div><span>{t("spread_lab.stat.range")}</span><strong>{num(result.statistics.min)} … {num(result.statistics.max)}</strong></div>
            <div><span>{t("spread_lab.metric.pnl")}</span><strong>{num(result.metrics.total_pnl, 0)} {currency}</strong></div>
            <div><span>{t("spread_lab.metric.trades")}</span><strong>{result.metrics.trades ?? 0} · {t("spread_lab.metric.hit_rate")} {num(result.metrics.hit_rate == null ? null : result.metrics.hit_rate * 100, 0)}%</strong></div>
            <div><span>{t("spread_lab.metric.drawdown")}</span><strong>{num(result.metrics.max_drawdown, 0)} {currency}</strong></div>
            <div><span>{t("spread_lab.metric.sharpe")}</span><strong>{num(result.metrics.sharpe_annualised)}</strong></div>
          </div>
          <StrategyLineChart points={charts.spread} title={t("spread_lab.chart.spread")} unit={result.unit} />
          <StrategyLineChart points={charts.zscore} title={t("spread_lab.chart.zscore")} unit="σ" height={120} />
          <StrategyLineChart points={charts.pnl} title={t("spread_lab.chart.pnl")} unit={currency} height={140} />
          <details className="spread-lab-trades">
            <summary>{t("spread_lab.trades", { count: result.trades.length })}</summary>
            <table>
              <thead>
                <tr>
                  <th scope="col">{t("spread_lab.trade.direction")}</th>
                  <th scope="col">{t("spread_lab.trade.opened")}</th>
                  <th scope="col">{t("spread_lab.trade.entry")}</th>
                  <th scope="col">{t("spread_lab.trade.closed")}</th>
                  <th scope="col">{t("spread_lab.trade.exit")}</th>
                  <th scope="col">{t("spread_lab.trade.pnl")} ({currency})</th>
                </tr>
              </thead>
              <tbody>
                {result.trades.map((trade) => (
                  <tr key={`${trade.opened}-${trade.direction}`}>
                    <td>{t(`spread_lab.trade.${trade.direction}`)}</td>
                    <td>{trade.opened}</td>
                    <td>{num(trade.entry_spread)}</td>
                    <td>{trade.closed ?? t("spread_lab.trade.open")}</td>
                    <td>{num(trade.exit_spread)}</td>
                    <td className={trade.pnl >= 0 ? "pos" : "neg"}>{num(trade.pnl, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          <p className="muted spread-lab-hash">
            {t("spread_lab.hash")}: <code>{result.analysis_hash.slice(0, 16)}</code>
          </p>
        </div>
      )}
    </section>
  );
}
