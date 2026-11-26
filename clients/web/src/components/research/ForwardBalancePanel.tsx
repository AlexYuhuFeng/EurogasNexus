import { useEffect, useMemo, useState } from "react";

import { api, type ForwardBalanceDTO, type ForwardBalanceQuery } from "@/api/client";
import {
  balanceChart,
  bandPosition,
  forwardRows,
  headlinePhrase,
  storageChart,
  type ForwardRow,
} from "@/app/model/forwardBalanceModel";
import { DataGrid, Segmented, Skeleton, UpdatingMark, type DataGridColumn } from "@/components/ui";
import { Chart } from "@/components/ui/charts";
import { gasDayLabel, periodLabel } from "@/components/ui/charts/chartModel";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const SHIFTS = [-3, -2, -1, 0, 1, 2, 3];

function gwh(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "–" : Math.round(value).toLocaleString("en-GB");
}

/**
 * Fundamentals → Balance, first: supply and demand dated forward (CP-25). It leads with the
 * one line a desk reads ("tighter than normal by …, mainly because …"), then the balance and
 * the implied storage path, then the table; every figure carries its error and every line
 * says where it comes from. A temperature and an outage what-if re-ask the server, and the
 * result names what was set by hand. A volume balance, not a price forecast.
 */
export function ForwardBalancePanel({ t }: { t: Translate }) {
  const [query, setQuery] = useState<ForwardBalanceQuery>({});
  const [dto, setDto] = useState<ForwardBalanceDTO | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [outageLine, setOutageLine] = useState<"norway" | "lng">("norway");
  const [outageGwh, setOutageGwh] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api
      .fundamentalsForwardBalance(query, { signal: controller.signal })
      .then((response) => {
        setDto(response.data);
        setNotes(response.meta?.warnings ?? []);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : String(caught));
      })
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [query]);

  const phrase = headlinePhrase(dto);
  const balance = useMemo(() => (dto && dto.daily.length ? balanceChart(dto, t) : null), [dto, t]);
  const path = useMemo(() => (dto ? storageChart(dto, t) : null), [dto, t]);
  const rows = useMemo(() => forwardRows(dto), [dto]);
  const unit = dto?.unit ?? "GWh/d";
  const columns = useMemo<DataGridColumn<ForwardRow>[]>(() => {
    const mark = dto?.simulated
      ? () => ({ kind: "simulated" as const, label: t("today.simulated_short"), description: t("today.simulated_long") })
      : undefined;
    return [
      {
        id: "period",
        header: t("fb.period"),
        rowHeader: true,
        value: (row) => row.period,
        state: mark,
        render: (row) => (row.kind === "day" ? gasDayLabel(row.period) : <strong>{periodLabel(row.period)}</strong>),
      },
      {
        id: "demand",
        header: t("fb.demand"),
        unit,
        type: "number",
        value: (row) => row.demand,
        render: (row) => (
          <>
            {gwh(row.demand)}
            {row.error != null && <small className="muted"> ±{gwh(row.error)}</small>}
          </>
        ),
        cellTitle: (row) =>
          [
            row.normal != null ? t("fb.normal_was", { gwh: gwh(row.normal) }) : t("fb.month_normal_weather"),
            row.error != null && row.errorBasis ? t(`fb.error_basis.${row.errorBasis}`, { gwh: gwh(row.error) }) : null,
          ].filter(Boolean).join("\n"),
      },
      {
        id: "norway",
        header: t("nwe.norway"),
        unit,
        type: "number",
        value: (row) => row.norway,
        render: (row) => <>{gwh(row.norway)}{row.outage ? " *" : ""}</>,
        cellTitle: (row) => (row.outage ? t("nwe.outage", { gwh: gwh(row.outage) }) : undefined),
      },
      { id: "lng", header: t("nwe.lng"), unit, type: "number", value: (row) => row.lng, format: (value) => gwh(value as number) },
      { id: "storage", header: t("fb.storage_draw"), unit, type: "number", value: (row) => row.storage, format: (value) => gwh(value as number) },
      { id: "gap", header: t("fb.gap"), unit, type: "number", value: (row) => row.gap, format: (value) => gwh(value as number) },
      {
        id: "fill",
        header: t("nwe.fill"),
        unit: "%",
        type: "number",
        value: (row) => row.fill,
        render: (row) => {
          const where = bandPosition(row.fill, row.bandLow, row.bandHigh);
          return (
            <>
              {row.fill == null ? "–" : row.fill.toFixed(1)}
              {where && where !== "within" && <small className="muted"> {t(`fb.band_${where}`)}</small>}
            </>
          );
        },
        cellTitle: (row) => (row.bandLow != null && row.bandHigh != null ? `${dto?.storage.band_label ?? ""}: ${row.bandLow.toFixed(1)}–${row.bandHigh.toFixed(1)} %` : undefined),
      },
    ];
  }, [dto, t, unit]);

  const target = dto?.storage.target;
  const overridden = dto?.overridden ?? [];
  const shift = query.temperature_shift_c ?? 0;
  const applyOutage = () => {
    const value = Number(outageGwh);
    setQuery((current) => ({ ...current, outage_line: value > 0 ? outageLine : undefined, outage_gwh_d: value > 0 ? value : undefined }));
  };

  return (
    <section className="workspace-panel span-3 forward-balance-panel" aria-labelledby="fb-title" data-forward-balance={dto ? "ready" : "loading"}>
      <div className="panel-title-row">
        <h2 id="fb-title">{t("fb.title")}</h2>
        <UpdatingMark active={loading && Boolean(dto)} label={t("fb.loading")} />
      </div>
      {error && <p role="alert">{error}</p>}
      {loading && !dto && !error && <Skeleton label={t("fb.loading")} rows={4} />}
      {phrase ? (
        <p className="fb-headline" data-fb-direction={dto?.headline?.direction}>
          <strong>{t(phrase.key, phrase.values)}</strong> {t(String(phrase.values.driver), phrase.values)}
          {dto?.simulated && <small className="muted"> · {t("today.simulated_short")}</small>}
        </p>
      ) : (
        dto && <p className="panel-empty-line">{notes.at(-1) ?? t("fb.empty")}</p>
      )}
      {overridden.length > 0 && (
        <p className="fb-overridden" role="status">
          {t("fb.overridden", { inputs: overridden.map((name) => t(`fb.input.${name}`)).join(", ") })}
        </p>
      )}
      <div className="fb-whatif" role="group" aria-label={t("fb.whatif")}>
        <span className="fb-whatif-label">{t("fb.whatif_temperature")}</span>
        <Segmented
          label={t("fb.whatif_temperature")}
          size="sm"
          options={SHIFTS.map((value) => ({ value: String(value), label: `${value > 0 ? "+" : ""}${value}`, title: `${value > 0 ? "+" : ""}${value} °C` }))}
          value={String(shift)}
          onChange={(value) => setQuery((current) => ({ ...current, temperature_shift_c: Number(value) || undefined }))}
        />
        <label className="fb-whatif-outage">
          <span>{t("fb.whatif_outage")}</span>
          <select value={outageLine} onChange={(event) => setOutageLine(event.target.value as "norway" | "lng")}>
            <option value="norway">{t("nwe.norway")}</option>
            <option value="lng">{t("nwe.lng")}</option>
          </select>
          <input inputMode="decimal" value={outageGwh} placeholder="GWh/d" aria-label={t("fb.outage_gwh")} onChange={(event) => setOutageGwh(event.target.value)} />
          <button type="button" onClick={applyOutage}>{t("fb.apply")}</button>
        </label>
        {overridden.length > 0 && (
          <button type="button" className="link-button" onClick={() => { setQuery({}); setOutageGwh(""); }}>{t("fb.reset")}</button>
        )}
      </div>
      {balance && <Chart id="fb-balance-chart" title={t("fb.chart_balance", { unit })} data={balance} t={t} height={220} asOf={dto?.as_of ?? null} simulated={dto?.simulated} />}
      {path && <Chart id="fb-storage-chart" title={t("fb.chart_storage")} data={path} t={t} height={200} asOf={dto?.storage.as_of ?? null} simulated={dto?.simulated} />}
      {target && (
        <p className="panel-meaning" data-fb-target>
          {target.implied_fill_pct == null
            ? t("fb.target_beyond", { pct: target.pct, date: gasDayLabel(target.deadline, true) })
            : t("fb.target_implied", { pct: target.pct, date: gasDayLabel(target.deadline, true), fill: target.implied_fill_pct.toFixed(1), gap: (target.gap_pts ?? 0).toFixed(1) })}
        </p>
      )}
      {rows.length > 0 && (
        <DataGrid
          id="forward-balance"
          label={t("fb.title")}
          columns={columns}
          rows={rows}
          rowKey={(row) => row.key}
          density="compact"
          rowAttributes={(row) => ({ "data-record": "forward-balance", "data-kind": row.kind })}
          tableAttributes={{ "data-forward-balance-table": "true" }}
        />
      )}
      {dto && (
        <details className="tool-fold" data-fb-evidence>
          <summary>{t("fb.evidence")}</summary>
          <ul className="position-notes">
            {dto.lines.map((line) => (
              <li key={line.id} data-fb-line={line.id} data-fb-class={line.class}>
                <strong>{t(`fb.line.${line.id}`)}</strong> · {t(`fb.class.${line.class}`)} · {line.source}
                {line.as_of && <> · {t("fb.as_of", { date: line.as_of.length === 7 ? periodLabel(line.as_of) : gasDayLabel(line.as_of, true) })}</>}
                {line.note && <> · {line.note}</>}
              </li>
            ))}
          </ul>
          {dto.demand_model && (
            <p className="panel-meaning">
              {t("fb.model", {
                a: gwh(dto.demand_model.a_gwh_d),
                b: dto.demand_model.b_gwh_d_per_hdd.toFixed(0),
                r2: dto.demand_model.r2.toFixed(2),
                months: dto.demand_model.months,
                resid: gwh(dto.demand_model.residual_std_gwh_d),
              })}
            </p>
          )}
          <table className="fb-backtest" data-fb-backtest>
            <caption>{t("fb.backtest_caption", { origins: dto.backtest.daily.origins })}</caption>
            <thead>
              <tr><th scope="col">{t("fb.horizon")}</th><th scope="col">{t("fb.mae")}</th><th scope="col">MAPE</th><th scope="col">{t("fb.bias")}</th></tr>
            </thead>
            <tbody>
              {dto.backtest.daily.horizons.map((row) => (
                <tr key={row.horizon_days}>
                  <th scope="row">D+{row.horizon_days}</th>
                  <td>{gwh(row.mae_gwh_d)}</td>
                  <td>{row.mape_pct == null ? "–" : `${row.mape_pct.toFixed(1)} %`}</td>
                  <td>{gwh(row.bias_gwh_d)}</td>
                </tr>
              ))}
              <tr>
                <th scope="row">{t("fb.month_ahead")}</th>
                <td>{gwh(dto.backtest.monthly.mae_gwh_d)}</td>
                <td>–</td>
                <td>{t("fb.months_n", { n: dto.backtest.monthly.n })}</td>
              </tr>
            </tbody>
          </table>
          <p className="panel-meaning" data-fb-curve>
            {dto.forward_curve.months.length
              ? t("fb.curve", { hub: dto.forward_curve.hub, prices: dto.forward_curve.months.map((m) => `${periodLabel(m.month)} ${m.price.toFixed(2)}`).join(" · ") })
              : t("fb.curve_none", { hub: dto.forward_curve.hub })}
          </p>
          <ul className="position-notes">
            <li>{t("fb.method")}</li>
            <li>{dto.not_a_price_forecast}</li>
            <li>{dto.zone_note}</li>
            <li>{dto.weather_reference.attribution} ({dto.weather_reference.licence})</li>
            {notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        </details>
      )}
    </section>
  );
}
