/**
 * Desk → Board's detail panel: one chart that follows the cell, column head, spread or
 * fundamentals line the trader last chose (app/model/traderDetailModel.ts). The charts are the
 * product's own canvas charts (components/ui/charts, uPlot). A choice with no history held is
 * one line saying so and what would supply it, never a simulated line; a simulated series is
 * marked; every chart names its as-of time and source; when the screen is not current the
 * chart says it is stale (a canvas is not muted by the page's stale rule).
 */
import { useMemo, useState } from "react";

import { api, type FlowObsDTO, type MarketQuoteDTO, type NormalizedMarketObsDTO } from "@/api/client";
import type { SpreadBoardDTO } from "@/api/spreads";
import { useScreenFreshness } from "@/app/data/connection";
import { readKey, useCachedRead } from "@/app/data/readCache";
import { sourceSystemLabel } from "@/app/model/enumLabels";
import { seasonChart } from "@/app/model/storageByCountry";
import { historyLabel } from "@/app/model/historyLabel";
import {
  curveShape,
  dailyCloses,
  forwardCurves,
  historyProduct,
  intradayPoints,
  observationSeries,
  referenceClose,
  spreadHistory,
  type BoardSelection,
  type PriceRange,
} from "@/app/model/traderDetailModel";
import { hubPriceUnit, hubSpreadRows, type BoardContract } from "@/app/model/traderBoardModel";
import { formatMeasure } from "@/app/time/valueFormat";
import { useInstantFormatter } from "@/app/time/useInstant";
import { Chart } from "@/components/ui/charts";
import type { ChartData } from "@/components/ui/charts/chartModel";
import { EmptyState, Segmented, StatusBadge } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface DetailProps {
  selection: BoardSelection;
  contracts: readonly BoardContract[];
  quotes: readonly MarketQuoteDTO[];
  markets: readonly NormalizedMarketObsDTO[];
  spreads: SpreadBoardDTO | null | undefined;
  flows: { totals: { code: string; spark: { day: string; flow_7d_gwh_d: number | null }[]; as_of: string; simulated: boolean }[] } | null | undefined;
  lng: { countries: { code: string; spark: { day: string; send_out_7d_gwh_d: number | null }[]; as_of: string; simulated: boolean; sources: string[] }[] } | null | undefined;
  points: readonly FlowObsDTO[] | null | undefined;
  gasDay: string;
  nowMs: number;
  t: Translate;
  height: number;
}

/** "No source": the one line a chart with no history gives, and what would supply it. */
export function NoSourceChart({ title, reason, t }: { title: string; reason: string; t: Translate }) {
  return (
    <div className="trader-detail-empty" data-detail-state="no-source">
      <h3>{title}</h3>
      <EmptyState compact reason={t("board.no_source")} next={reason} />
    </div>
  );
}

function gasDayStartIso(gasDay: string): string {
  return `${gasDay}T05:00:00.000Z`;
}

function PriceDetail({ selection, contracts, quotes, gasDay, nowMs, t, height, stale }: DetailProps & { selection: Extract<BoardSelection, { kind: "price" }>; stale: string | null }) {
  const [chosenRange, setRange] = useState<PriceRange | null>(null);
  const contract = contracts.find((item) => item.key === selection.contract) ?? null;
  const product = contract ? historyProduct(contract, selection.hub) : null;
  // One year of closes, read once per day (the key changes with the day, not the clock).
  const since = new Date(nowMs - 366 * 86_400_000).toISOString().slice(0, 10);
  const history = useCachedRead(
    product ? readKey("/market/observations", { product, from_utc: since, limit: 1000 }) : null,
    () => api.marketObservations({ from_utc: `${since}T00:00:00Z`, product: product!, limit: 1000 }).then((response) => response.data),
  );
  const quote = useMemo(() => {
    const mine = quotes.filter((item) => item.hub.toUpperCase() === selection.hub && contract && (item.product.toLowerCase() === (contract.key === "M1" ? "month-ahead" : { wd: "within-day", da: "day-ahead", we: "weekend" }[contract.kind as "wd" | "da" | "we"] ?? "")));
    return mine.sort((a, b) => Number(a.simulated) - Number(b.simulated) || b.observed_at_utc.localeCompare(a.observed_at_utc))[0] ?? null;
  }, [quotes, selection.hub, contract]);
  const series = useMemo(() => observationSeries(history.data ?? [], selection.hub), [history.data, selection.hub]);
  const unit = hubPriceUnit(selection.hub);
  const title = t("board.detail.price_title", { hub: selection.hub, contract: contract?.label ?? selection.contract });
  const start = gasDayStartIso(gasDay);
  // Today first; until today has two ticks the panel opens on the month, and says so.
  const todayTicks = new Set(intradayPoints(series.points, start, quote, selection.hub).map((point) => point.at)).size;
  const range: PriceRange = chosenRange ?? (todayTicks >= 2 ? "intraday" : "1m");
  const fellBack = chosenRange === null && range === "1m";
  const controls = (
    <Segmented
      label={t("board.detail.range")}
      value={range}
      onChange={setRange}
      options={[
        { value: "intraday", label: t("board.detail.intraday") },
        { value: "1m", label: t("board.detail.1m") },
        { value: "1y", label: t("board.detail.1y") },
      ]}
    />
  );
  let data: ChartData | null = null;
  if (range === "intraday") {
    const today = intradayPoints(series.points, start, quote, selection.hub);
    const close = referenceClose(series.points, start, quote, selection.hub);
    if (today.length > 0) {
      data = {
        axis: "time",
        x: today.map((point) => point.at),
        xTitle: t("board.detail.time"),
        unit,
        series: [{ id: "price", label: title, values: today.map((point) => point.value), style: "step", simulated: series.simulated || Boolean(quote?.simulated), decimals: 3 }],
        rules: close !== null ? [{ id: "close", value: close, label: t("board.detail.prior_close", { value: formatMeasure("price", close) }), kind: "threshold" }] : [],
      };
    }
  } else {
    const days = range === "1m" ? 31 : 366;
    const closes = dailyCloses(series.points, new Date(nowMs - days * 86_400_000).toISOString());
    if (closes.length > 0) {
      data = {
        axis: "gas-day",
        x: closes.map((point) => point.at),
        xTitle: t("chart.gas_day"),
        unit,
        series: [{ id: "close", label: title, values: closes.map((point) => point.value), simulated: series.simulated, decimals: 3 }],
      };
    }
  }
  if (!data) {
    if (history.loading) return <EmptyState compact reason={t("board.loading")} />;
    return (
      <>
        <div className="trader-detail-controls">{controls}</div>
        <NoSourceChart title={title} reason={t("board.detail.price_no_source", { hub: selection.hub })} t={t} />
      </>
    );
  }
  return (
    <Chart
      id="trader-detail-price"
      title={title}
      data={data}
      t={t}
      height={height}
      asOf={series.asOf ?? quote?.observed_at_utc ?? null}
      state={stale}
      simulated={series.simulated}
      controls={controls}
      compact
      note={[
        t("board.detail.source", { source: series.source ? sourceSystemLabel(series.source) : quote ? sourceSystemLabel(quote.source_system) : "–" }),
        fellBack ? t("board.detail.fell_back") : null,
      ].filter(Boolean).join(" · ")}
    />
  );
}

function CurveDetail({ selection, markets, t, height, stale }: DetailProps & { selection: Extract<BoardSelection, { kind: "curve" }>; stale: string | null }) {
  const since = new Date(Date.now() - 9 * 86_400_000).toISOString().slice(0, 10);
  const recent = useCachedRead(readKey("/market/observations", { from_utc: since, limit: 2000 }), () =>
    api.marketObservations({ from_utc: `${since}T00:00:00Z`, limit: 2000 }).then((response) => response.data),
  );
  const curve = useMemo(() => forwardCurves([...markets, ...(recent.data ?? [])], selection.hub), [markets, recent.data, selection.hub]);
  const title = t("board.detail.curve_title", { hub: selection.hub });
  if (curve.months.length < 2) return <NoSourceChart title={title} reason={t("board.detail.curve_no_source", { hub: selection.hub })} t={t} />;
  const shape = curveShape(curve.today);
  const data: ChartData = {
    axis: "period",
    x: curve.months,
    xTitle: t("board.detail.delivery_month"),
    unit: hubPriceUnit(selection.hub),
    series: [
      { id: "week", label: t("board.detail.week_ago"), values: curve.weekAgo, ghost: true, simulated: curve.simulated, decimals: 3 },
      { id: "day", label: t("board.detail.day_ago"), values: curve.dayAgo, ghost: true, simulated: curve.simulated, decimals: 3 },
      { id: "today", label: t("board.detail.today"), values: curve.today, style: "points", colour: 1, simulated: curve.simulated, decimals: 3 },
    ],
  };
  const missing = [curve.dayAgo, curve.weekAgo].some((values) => values.every((value) => value === null));
  return (
    <Chart
      id="trader-detail-curve"
      title={title}
      subtitle={shape ? t(`board.detail.shape.${shape}`) : undefined}
      data={data}
      t={t}
      height={height}
      asOf={curve.asOf}
      state={stale}
      simulated={curve.simulated}
      compact
      note={[t("board.detail.source", { source: curve.source ? sourceSystemLabel(curve.source) : "–" }), missing ? t("board.detail.curve_earlier_missing") : null].filter(Boolean).join(" · ")}
    />
  );
}

function SpreadDetail({ selection, spreads, t, height, stale }: DetailProps & { selection: Extract<BoardSelection, { kind: "spread" }>; stale: string | null }) {
  const rows = hubSpreadRows(spreads);
  const row = rows.find((item) => item.pair === selection.pair);
  const figure = selection.tenor === "DA" ? row?.da : row?.ma;
  const tenor = spreads?.locational.find((item) => item.pair === selection.pair)?.tenors.find((item) => item.tenor === selection.tenor);
  const title = t("board.detail.spread_title", { pair: selection.pair.replace("–", " − "), tenor: t(`board.spread.${selection.tenor.toLowerCase()}`) });
  const history = spreadHistory(tenor, figure?.factor ?? null, figure?.transport ?? null);
  if (!history || !figure) return <NoSourceChart title={title} reason={t("board.detail.spread_no_source")} t={t} />;
  const data: ChartData = {
    axis: "gas-day",
    x: history.days,
    xTitle: t("chart.gas_day"),
    unit: figure.unit,
    series: [{ id: "gross", label: t("board.spread.gross"), values: history.values, simulated: history.simulated, decimals: 3 }],
    rules: [
      { id: "zero", value: 0, kind: "zero" },
      ...(history.low !== null ? [{ id: "low", value: history.low, label: t("board.detail.range_low", { days: history.rangeDays ?? 0 }), kind: "threshold" as const }] : []),
      ...(history.high !== null ? [{ id: "high", value: history.high, label: t("board.detail.range_high", { days: history.rangeDays ?? 0 }), kind: "threshold" as const }] : []),
      ...(history.transport !== null ? [{ id: "transport", value: Math.sign(history.values[history.values.length - 1] ?? 1) * history.transport, label: t("board.detail.transport_line"), kind: "target" as const }] : []),
    ],
  };
  return (
    <Chart
      id="trader-detail-spread"
      title={title}
      data={data}
      t={t}
      height={height}
      asOf={history.asOf}
      state={stale}
      simulated={history.simulated}
      compact
      note={t("board.detail.spread_note", { count: history.values.length })}
    />
  );
}

function StorageDetail({ selection, t, height, stale }: DetailProps & { selection: Extract<BoardSelection, { kind: "storage" }>; stale: string | null }) {
  const code = selection.code;
  const read = useCachedRead(readKey("/fundamentals/storage", { region: "eu", season: code }), (signal) =>
    api.fundamentalsStorage({ region: "eu", season: [code] }, { signal }).then((response) => response.data),
  );
  const entity = code === "EU" ? read.data?.region ?? null : read.data?.countries.find((item) => item.code === code) ?? null;
  const title = t("board.detail.storage_title", { name: code === "EU" ? t("board.fund.eu_total") : code });
  const chart = useMemo(
    () =>
      entity
        ? seasonChart(
            entity,
            {
              lastYear: (year) => t("storage_panel.last_year", { year }),
              thisYear: (year) => year,
              mean: (count) => t("chart.history.mean", { count }),
              history: (history) => historyLabel(history, t),
              range: (years) => t("chart.history.range", { count: years.length, first: years[0] ?? "", last: years[years.length - 1] ?? "" }),
              target: (pct) => t("storage_panel.target_rule", { pct }),
              xTitle: t("storage_panel.day_of_gas_year"),
            },
            entity.season?.band ? t("storage_panel.compare_mean", { count: entity.season.band.years.length }) : t("storage_panel.compare_last_year"),
          )
        : null,
    [entity, t],
  );
  if (read.loading && !read.data) return <EmptyState compact reason={t("board.loading")} />;
  if (!entity || !chart) return <NoSourceChart title={title} reason={t("board.detail.storage_no_source", { code })} t={t} />;
  return (
    <Chart
      id="trader-detail-storage"
      title={title}
      subtitle={chart.subtitle}
      data={chart.data}
      compare={chart.compare}
      t={t}
      height={height}
      asOf={entity.as_of}
      state={stale}
      simulated={entity.simulated}
      compact
      note={t("board.detail.source", { source: entity.sources.map((item) => sourceSystemLabel(item)).join(", ") || "–" })}
    />
  );
}

/** The 30 days behind a supply line, and its unit: totals and LNG in GWh/d, points as stored. */
export function flowSeries(
  key: string,
  flows: DetailProps["flows"],
  lng: DetailProps["lng"],
  points: DetailProps["points"],
  patterns: Readonly<Record<string, RegExp>>,
): { days: string[]; values: (number | null)[]; unit: string; simulated: boolean; asOf: string | null; source: string | null } | null {
  if (key === "norway_gb" || key === "norway_eu") {
    const row = flows?.totals.find((item) => item.code === (key === "norway_gb" ? "uk_terminal" : "norway"));
    if (!row || row.spark.length === 0) return null;
    return { days: row.spark.map((point) => point.day), values: row.spark.map((point) => point.flow_7d_gwh_d), unit: "GWh/d", simulated: row.simulated, asOf: row.as_of, source: "ENTSOG" };
  }
  if (key.startsWith("lng-")) {
    const row = lng?.countries.find((item) => item.code === key.slice(4));
    if (!row || row.spark.length === 0) return null;
    return { days: row.spark.map((point) => point.day), values: row.spark.map((point) => point.send_out_7d_gwh_d), unit: "GWh/d", simulated: row.simulated, asOf: row.as_of, source: row.sources[0] ?? null };
  }
  const pattern = patterns[key];
  if (!pattern) return null;
  const byDay = new Map<string, FlowObsDTO>();
  for (const row of points ?? []) {
    if (!pattern.test(row.point_name)) continue;
    const day = row.period_start_utc.slice(0, 10);
    const held = byDay.get(day);
    if (!held || String(row.observed_at_utc ?? "") > String(held.observed_at_utc ?? "")) byDay.set(day, row);
  }
  const days = [...byDay.keys()].sort().slice(-30);
  if (days.length === 0) return null;
  const last = byDay.get(days[days.length - 1]!)!;
  return {
    days,
    values: days.map((day) => byDay.get(day)!.flow_mcm_d),
    unit: "mcm/d",
    simulated: /_sim$/i.test(last.source_system ?? ""),
    asOf: days[days.length - 1]!,
    source: last.source_system ?? null,
  };
}

function FlowDetail({ selection, flows, lng, points, t, height, stale, patterns }: DetailProps & { selection: Extract<BoardSelection, { kind: "flow" }>; stale: string | null; patterns: Readonly<Record<string, RegExp>> }) {
  const title = t("board.detail.flow_title", { name: selection.key.startsWith("lng-") ? t("board.fund.lng_country", { country: selection.key.slice(4) }) : t(`board.fund.flow.${selection.key}`) });
  const series = flowSeries(selection.key, flows, lng, points, patterns);
  if (!series) return <NoSourceChart title={title} reason={t("board.detail.flow_no_source")} t={t} />;
  const data: ChartData = {
    axis: "gas-day",
    x: series.days,
    xTitle: t("chart.gas_day"),
    unit: series.unit,
    series: [{ id: "flow", label: title, values: series.values, style: "step", simulated: series.simulated, decimals: 1 }],
  };
  return (
    <Chart
      id="trader-detail-flow"
      title={title}
      data={data}
      t={t}
      height={height}
      asOf={series.asOf}
      state={stale}
      simulated={series.simulated}
      compact
      note={[t("board.detail.source", { source: series.source ? sourceSystemLabel(series.source) : "–" }), series.unit === "GWh/d" ? t("board.detail.flow_7d") : null].filter(Boolean).join(" · ")}
    />
  );
}

export function TraderDetail(props: DetailProps & { patterns: Readonly<Record<string, RegExp>> }) {
  const freshness = useScreenFreshness();
  const format = useInstantFormatter();
  const stale = freshness.current
    ? null
    : freshness.since !== null
      ? props.t("stale.value_since", { time: format(freshness.since)?.text ?? "" })
      : props.t("stale.value");
  const { selection } = props;
  return (
    <div className="trader-detail" data-detail={selection.kind} data-detail-stale={stale ? "true" : undefined}>
      {stale ? (
        <StatusBadge tone="stale" className="trader-detail-stale">
          {stale}
        </StatusBadge>
      ) : null}
      {selection.kind === "price" && <PriceDetail key={`${selection.contract}:${selection.hub}`} {...props} selection={selection} stale={stale} />}
      {selection.kind === "curve" && <CurveDetail {...props} selection={selection} stale={stale} />}
      {selection.kind === "spread" && <SpreadDetail {...props} selection={selection} stale={stale} />}
      {selection.kind === "storage" && <StorageDetail {...props} selection={selection} stale={stale} />}
      {selection.kind === "flow" && <FlowDetail {...props} selection={selection} stale={stale} />}
    </div>
  );
}
