/**
 * Today (UX-05; design basis 2, section E): the first screen, all from one server read
 * (`GET /api/desk/today`), with nothing recomputed here. Four rows, in the order the person's
 * role composition gives (`roleComposition.ts` `todayRows`):
 *
 * - My market: DA and front month per focus hub with the day change and a 30-day sparkline,
 *   then the spreads against TTF in one unit with the route cost ("in/out of the money").
 * - My book: net position today and front month, the tightest limit, the book by hub.
 * - What needs me: at most five ranked items (opportunities, outages at my hubs, limits); when
 *   nothing qualifies, one sentence in the next row's header and no row.
 * - Fundamentals: storage by country against its history, the supply call against its 7-day
 *   average, LNG send-out against yesterday.
 *
 * No filter strip: Today is about today (E.1).
 *
 * Every figure shows its value, unit, and its state in words when it is not current; a simulated
 * figure carries the simulated marker beside the value itself (AGENTS.md rule 17). An empty
 * section says the server's reason and next step on one line; a section the caller may not see
 * is absent.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type ForwardBalanceDTO } from "@/api/client";
import { headlinePhrase } from "@/app/model/forwardBalanceModel";
import { useCompactWidth } from "@/app/shell/useShellLayout";

import type {
  DeskTodayDTO,
  GasDayTargetDTO,
  TodayBookRowDTO,
  TodayEmptyDTO,
  TodayFigureDTO,
  TodayFundamentalsRowDTO,
  TodayKeyFiguresRowDTO,
  TodayMarketDTO,
  TodayMarketFigureDTO,
  TodayNeedsMeRowDTO,
  TodayPriceDTO,
  TodaySpreadDTO,
} from "@/api/client";
import type { TodayRowKey } from "@/app/experience/roleComposition";
import { unitLabel } from "@/app/model/instrumentPicker";
import { formatGasDay } from "@/app/time/timeFormat";
import { useInstantFormatter } from "@/app/time/useInstant";
import { SimulatedScope, useSimulatedPills } from "@/components/ui/SimulatedScope";
import {
  figureAnchorId,
  formatChange,
  formatValue,
  isEmptyEntry,
  spreadEmptyText,
  shortDay,
  stateWords,
} from "@/app/model/todayModel";
import { pnlClass } from "@/app/model/pnlColor";
import { MethodNote } from "@/components/MethodNote";
import { StorageByCountryPanel } from "@/components/StorageByCountryPanel";
import { WhyButton } from "@/components/WhyButton";
import { ChecklistRow } from "@/components/today/ChecklistRow";
import { GasDayRow } from "@/components/today/GasDayRow";
import { ReconciliationRow } from "@/components/today/ReconciliationRow";
import { GasDayStrip } from "@/components/today/GasDayStrip";
import { useConvertedAmount, useConvertedPrice, useConvertedQuantity } from "@/app/time/useConversion";
import type { ConvertedText } from "@/app/time/valueFormat";
import { ConvertedValue } from "@/components/ui/ConvertedValue";
import { Sparkline } from "@/components/ui/charts";
import {
  Button,
  DataGrid,
  EmptyState,
  KeyFigure,
  Popover,
  Skeleton,
  StatusBadge,
  type CellState,
  type DataGridColumn,
  type FigureState,
} from "@/components/ui";
import { formatMeasure } from "@/app/time/valueFormat";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface TodayScreenProps {
  today: DeskTodayDTO | null;
  loading: boolean;
  error: string | null;
  t: Translate;
  language: string;
  nowMs: number;
  onRefresh: () => void;
  onOpenBrief: () => void;
  onOpenLimits: () => void;
  onOpenOutages: () => void;
  /** The rows in the person's order (design basis 2, E.3); absent rows are not shown. */
  rows?: readonly TodayRowKey[];
  /** Whether the person may read the book (`portfolio.read`): My book is absent otherwise. */
  canSeeBook?: boolean;
  /** The header line is drawn by the page's context strip (the cockpit), not by Today. */
  headInStrip?: boolean;
  /** Open Research → Fundamentals on a view (storage, balance), where the full charts are. */
  onOpenFundamentals?: (view: "storage" | "balance") => void;
  /** Open Prices, where a market sparkline's full chart is. */
  onOpenPrices?: () => void;
  /** Open where a "My gas day" line is acted on or evidenced (Book, Prices → prompt). */
  onOpenGasDay?: (target: GasDayTargetDTO) => void;
  /** A one-line gas-day strip above the rows (the trader's composition). */
  gasDayStrip?: boolean;
  /** Whether the reader may record a checklist status (`gas_day.record`; the server checks). */
  canRecordGasDay?: boolean;
  /** Open what a "What needs me" item names. */
  onOpenNeed?: (item: TodayNeedsMeRowDTO["items"][number]) => void;
  /**
   * The inspector hand-off for a price: returns how to open its observation (source, time,
   * state), or null when this desk holds no observation behind it.
   */
  onInspectPrice?: (price: TodayPriceDTO) => (() => void) | null;
}

/** The simulated marker beside a value: a short word, its meaning for screen readers. */
export function SimulatedMark({ t }: { t: Translate }) {
  // Not on every value when the whole page is simulated: the page says it once (SimulatedScope).
  if (!useSimulatedPills()) return null;
  return (
    <span className="ds-cell-mark" data-state="simulated" title={t("today.simulated_long")}>
      <span aria-hidden="true">{t("today.simulated_short")}</span>
      <span className="ds-visually-hidden">{t("today.simulated_long")}</span>
    </span>
  );
}

export function simulatedCell(t: Translate): CellState {
  return { kind: "simulated", label: t("today.simulated_short"), description: t("today.simulated_long") };
}

function figureState(figure: TodayFigureDTO): FigureState {
  return figure.state === "current" ? "current" : figure.state;
}

/** A figure on Today: anchor for the stale list, value, unit, state in words, simulated marker. */
function Figure({
  figure,
  label,
  t,
  nowMs,
  delta,
  detail,
  action,
  notes,
  size = "lg",
  valueClassName,
  signed = false,
  wide = false,
  converted,
  convertedMode,
  live = false,
}: {
  figure: TodayFigureDTO;
  label: ReactNode;
  t: Translate;
  nowMs: number;
  delta?: { text: ReactNode; value: number | null | undefined };
  detail?: ReactNode;
  action?: ReactNode;
  notes?: ReactNode;
  size?: "md" | "lg";
  /** A position: always signed (+ long, − short) in neutral ink. */
  signed?: boolean;
  /** Takes two columns of the strip (a figure with a named counterparty under it). */
  wide?: boolean;
  valueClassName?: string;
  /** The value in the reader's reporting currency / energy unit (design basis G3). */
  converted?: ConvertedText | null;
  convertedMode?: "hover" | "line";
  /** Flash when the value moves (a price, a position: they update while Today is open). */
  live?: boolean;
}) {
  const words = stateWords(figure, nowMs, t);
  return (
    <div className={wide ? "today-figure is-wide" : "today-figure"} id={figureAnchorId(figure.key)} tabIndex={-1} data-figure-key={figure.key}>
      <KeyFigure
        label={label}
        value={formatValue(figure.value, figure.unit, signed)}
        unit={unitLabel(figure.unit)}
        size={size}
        delta={delta}
        state={figureState(figure)}
        stateLabel={words ?? undefined}
        detail={detail}
        action={action}
        notes={notes}
        valueClassName={valueClassName}
        marker={figure.simulated ? <SimulatedMark t={t} /> : undefined}
        // Provenance on demand: the source is the figure's tooltip, not a link beside it.
        title={figure.source ?? undefined}
        converted={converted}
        convertedMode={convertedMode}
        live={live ? { watch: figure.value, identity: `${figure.key}|${figure.unit}` } : undefined}
      />
    </div>
  );
}

function Empty({ empty, id }: { empty: TodayEmptyDTO; id: string }) {
  // The code stays available to support, never in the visible copy.
  return (
    <div className="today-empty" data-empty-code={empty.code} title={empty.code}>
      <EmptyState compact id={id} reason={empty.reason} next={empty.action} />
    </div>
  );
}

function RowSection({ id, title, meta, actions, children }: { id: string; title: string; meta?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className={`today-row today-row-${id}`} aria-labelledby={`today-row-${id}`} data-today-row={id}>
      <header className="today-row-head">
        <h2 id={`today-row-${id}`}>{title}</h2>
        {meta ? <span className="today-row-meta">{meta}</span> : null}
        {actions ? <div className="today-row-actions">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

/* ------------------------------------------------------------------ row 1 */

/** A net position: signed, native MWh/d first, the reader's energy unit on hover (G10). */
function PositionFigure(props: { figure: TodayFigureDTO; label: ReactNode; t: Translate; nowMs: number; notes?: ReactNode }) {
  const converted = useConvertedQuantity({ value: props.figure.value, unit: props.figure.unit, simulated: props.figure.simulated });
  return <Figure {...props} signed converted={converted} live />;
}

/** A day P&L in another currency than the reader reports in: the converted figure under it, at
 * the rate of the P&L's own day (G3, G5), its rate and method in the title. */
function PnlInReportingCurrency({ change }: { change: TodayFigureDTO }) {
  const converted = useConvertedAmount({ amount: change.value, currency: change.unit, valueDate: change.as_of?.slice(0, 10), subject: "pnl", simulated: change.simulated });
  return <ConvertedValue converted={converted} mode="line" compact />;
}

function MarketFigure({ figure, t, nowMs, onInspect }: { figure: TodayMarketFigureDTO; t: Translate; nowMs: number; onInspect?: (() => void) | null }) {
  const name = `${figure.hub} ${figure.product}`;
  // Provenance on demand: the name opens the Inspector (source, time, state); no "Source" link.
  const label = onInspect ? (
    <button type="button" className="today-figure-name" data-inspect-price={figure.hub} title={t("today.source_of", { name })} onClick={onInspect}>
      {name}
    </button>
  ) : name;
  // Native first (G1); the reader's currency and unit on hover, with the rate that made it.
  const converted = useConvertedPrice({ value: figure.value, unit: figure.unit, product: figure.product, simulated: figure.simulated });
  return (
    <Figure
      figure={figure}
      converted={converted}
      label={label}
      t={t}
      nowMs={nowMs}
      size="md"
      live
      delta={figure.day_change == null ? undefined : { text: formatChange(figure.day_change, figure.unit), value: figure.day_change }}
      detail={t("today.close_of", { day: shortDay(figure.close_day) })}
    />
  );
}

function SpreadLine({ spread, t, language }: { spread: TodayMarketDTO["spreads"][number]; t: Translate; language: string }) {
  if (isEmptyEntry(spread)) {
    return (
      <li className="today-spread" data-spread={spread.pair} data-empty-code={spread.empty.code}>
        <span className="today-spread-pair">{spread.pair}</span>
        <span className="muted" title={spread.empty.reason}>{spreadEmptyText(spread.empty, t, language)}</span>
      </li>
    );
  }
  const item = spread as TodaySpreadDTO;
  const route = item.route_cost;
  const fx = item.fx ? t("today.market.fx", { base: item.fx.base, quote: item.fx.quote, rate: formatMeasure("fx_rate", Number(item.fx.rate)) }) : undefined;
  return (
    <li className="today-spread" data-spread={item.pair} id={figureAnchorId(item.key)} tabIndex={-1}>
      <span className="today-spread-pair">{item.label}</span>
      <strong className="today-spread-value" title={fx}>
        {formatValue(item.value, item.unit, true)} <small className="ds-grid-unit">{unitLabel(item.unit)}</small>
      </strong>
      {item.simulated && <SimulatedMark t={t} />}
      {route.value != null && route.verdict ? (
        <span className="today-spread-route" data-verdict={route.verdict} title={(route.via ?? []).join(" · ")}>
          {route.from && route.to && <>{route.from} → {route.to}{" · "}</>}
          {t("today.market.route_cost", { value: formatValue(route.value, route.unit), unit: route.unit })}
          {route.net != null && <>{" · "}{t("today.market.net", { value: formatValue(route.net, route.unit, true) })}</>}
          {" · "}
          <strong>{t(`today.market.${route.verdict}`)}</strong>
        </span>
      ) : (
        <span className="today-spread-route muted" title={route.reason}>{t("today.market.no_route")}</span>
      )}
    </li>
  );
}

function MarketRow({ market, t, nowMs, language, onInspectPrice, onOpenPrices }: { market: TodayMarketDTO; t: Translate; nowMs: number; language: string; onInspectPrice?: TodayScreenProps["onInspectPrice"]; onOpenPrices?: () => void }) {
  return (
    <RowSection id="market" title={t("today.row.market")}>
      <div className="today-market">
        {market.hubs.map((hub) => {
          const front = hub.front_month;
          return (
            <div key={hub.hub} className="today-market-hub" data-hub={hub.hub}>
              {hub.empty ? (
                <>
                  <span className="today-figure-label">{hub.hub}</span>
                  <Empty empty={hub.empty} id={`today-market-${hub.hub}`} />
                </>
              ) : (
                <>
                  {hub.day_ahead && <MarketFigure figure={hub.day_ahead} t={t} nowMs={nowMs} />}
                  {front && <MarketFigure figure={front} t={t} nowMs={nowMs} onInspect={onInspectPrice?.(front as unknown as TodayPriceDTO)} />}
                  {front && front.series.length > 1 && (
                    <Sparkline
                      values={front.series.map((point) => point.value)}
                      days={front.series.map((point) => point.day)}
                      simulated={front.simulated}
                      label={t("today.market.series", { name: `${front.hub} ${front.product}`, days: market.series_days })}
                      unit={unitLabel(front.unit)}
                      decimals={2}
                      t={t}
                      onOpen={onOpenPrices}
                    />
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
      {market.spreads.length > 0 && (
        <ul className="today-spreads" aria-label={t("today.market.spreads")}>
          {market.spreads.map((spread) => <SpreadLine key={spread.pair} spread={spread} t={t} language={language} />)}
        </ul>
      )}
    </RowSection>
  );
}

function needTitle(item: TodayNeedsMeRowDTO["items"][number], zh: boolean): string {
  return zh && item.title_zh ? item.title_zh : item.title;
}

function NeedsMeRow({ row, t, language, onOpen }: { row: TodayNeedsMeRowDTO; t: Translate; nowMs: number; language: string; onOpen?: TodayScreenProps["onOpenNeed"] }) {
  const zh = language.toLowerCase().startsWith("zh");
  const formatInstant = useInstantFormatter();
  return (
    <RowSection id="needs_me" title={t("today.row.needs_me")} meta={row.more > 0 ? t("today.needs.more", { count: row.more }) : undefined}>
      <ol className="today-needs">
        {row.items.map((item) => {
          const tone = item.kind === "limit" ? (item.status === "breach" ? "breach" : "watch") : item.kind === "opportunity" && item.lane === "must_act" ? "breach" : item.kind === "nomination" ? (item.urgency === "overdue" ? "breach" : "watch") : item.kind === "cargo" || item.kind === "reconciliation" ? (item.status === "breach" || item.urgency === "overdue" ? "breach" : "watch") : "neutral";
          return (
            <li key={`${item.kind}:${item.id}`} data-need={item.kind}>
              <StatusBadge tone={tone}>{t(`today.needs.kind.${item.kind}${item.kind === "opportunity" && item.lane ? `.${item.lane}` : ""}`)}</StatusBadge>
              <button type="button" className="ds-inline-link today-need-title" onClick={() => onOpen?.(item)}>
                {needTitle(item, zh)}
              </button>
              <span className="today-need-detail muted">
                {item.kind === "outage" && item.hub ? t(item.touches_book ? "today.needs.touches_book" : "today.needs.at_hub", { hub: item.hub }) : null}
                {item.kind === "outage" && item.size?.value != null ? ` · ${formatValue(item.size.value, item.size.unit ?? "")} ${item.size.unit ?? ""}` : null}
                {item.kind === "opportunity" && item.headline?.value != null ? `${item.headline.value} ${item.headline.unit ?? ""}${item.period ? ` · ${item.period}` : ""}` : null}
                {item.kind === "limit" && item.utilisation_pct != null ? t("today.used", { pct: Math.round(item.utilisation_pct) }) : null}
                {item.kind === "nomination" ? [item.hub, item.step ? t(`today.checklist.step.${item.step}`) : null, item.status ? t(`today.checklist.status.${item.status}`) : null].filter(Boolean).join(" · ") : null}
                {item.kind === "cargo" && item.role ? t("today.needs.cargo_for", { role: t(`lng.cargo.role.${item.role}`) }) : null}
                {item.kind === "reconciliation" && item.break_kind ? [t(`recon.kind.${item.break_kind}`), item.quantity ? t("recon.at_risk", { mwh: Math.round(Math.abs(item.quantity.mwh)).toLocaleString("en-GB"), kwh: Math.round(Math.abs(item.quantity.kwh_h)).toLocaleString("en-GB") }) : null].filter(Boolean).join(" · ") : null}
              </span>
              {/* A scheduling break says why in the server's words (SCHED-1). */}
              {item.kind === "reconciliation" && (zh ? item.explanation_zh : item.explanation) && (
                <span className="today-need-detail today-need-why">{zh ? item.explanation_zh : item.explanation}</span>
              )}
              {item.simulated && <SimulatedMark t={t} />}
              {/* An outage says since when it is out; a standing limit state has no news age. */}
              {item.kind === "outage" && item.since_utc && (() => {
                const since = formatInstant(item.since_utc);
                return since ? <time className="today-list-time" dateTime={since.iso} title={since.title}>{t("today.needs.since", { when: since.text })}</time> : null;
              })()}
              {/* A cargo message says by when its first step is due (LNG-2). */}
              {(item.kind === "cargo" || item.kind === "reconciliation") && item.deadline_utc && (() => {
                const due = formatInstant(item.deadline_utc);
                return due ? <time className="today-list-time" dateTime={due.iso} title={due.title}>{t("today.needs.due", { when: due.text })}</time> : null;
              })()}
              {item.why && <WhyButton subject={item.why.subject} id={item.why.id} label={item.title} language={language} t={t} />}
            </li>
          );
        })}
      </ol>
    </RowSection>
  );
}

/* ------------------------------------------------------------------ row 3 */

type BookHub = TodayBookRowDTO["hubs"][number];

function stateCell(figure: TodayFigureDTO | null | undefined, t: Translate, nowMs: number, pills = true): CellState | null {
  if (!figure) return null;
  if (figure.state !== "current") {
    const words = stateWords(figure, nowMs, t) ?? figure.state;
    return { kind: figure.state === "manual" ? "manual" : figure.state === "late" ? "late" : "stale", label: words, description: words };
  }
  return figure.simulated && pills ? simulatedCell(t) : null;
}

/** Key-figure labels by figure key ("price.NBP" -> "NBP Dec-26"), for the mark's same-as note. */
function priceLabels(row: TodayKeyFiguresRowDTO | undefined): Record<string, string> {
  const labels: Record<string, string> = {};
  for (const price of row?.prices ?? []) if ("label" in price && price.label) labels[price.key] = price.label;
  return labels;
}

/** The mark's provenance on demand: its close, the key figure it is, and its per-MWh value. */
function markTitle(mark: NonNullable<BookHub["mark"]>, labels: Record<string, string>, t: Translate): string {
  const parts = [t("today.close_of", { day: shortDay(mark.as_of ?? "") })];
  if (mark.same_as) parts.push(t("today.book.mark_same_as", { price: labels[mark.same_as] ?? mark.same_as.replace(/^price\./, "") }));
  if (mark.value_mwh != null && mark.unit_mwh && mark.unit_mwh !== mark.unit) {
    parts.push(t("today.book.mark_per_mwh", { value: formatValue(mark.value_mwh, mark.unit_mwh), unit: mark.unit_mwh }));
  }
  return parts.join(" · ");
}

/** My book's headline: net position today and front month, and the tightest limit. */
function BookFigures({ row, t, nowMs, language, onOpenLimits }: { row: TodayKeyFiguresRowDTO; t: Translate; nowMs: number; language: string; onOpenLimits: () => void }) {
  const limit = row.tightest_limit;
  // A limit is tested in the currency it was approved in (G7); the reporting currency is a
  // second line under it when they differ.
  const limitConverted = useConvertedAmount({ amount: limit?.value, currency: limit?.unit ?? "EUR", subject: "limit", simulated: limit?.simulated });
  if (!row.position && !limit && !row.limit_empty) return null;
  return (
    <div className="today-figures today-book-figures">
      {row.position && (
        <>
          <PositionFigure
            figure={row.position.today}
            label={t("today.net_today")}
            t={t}
            nowMs={nowMs}
            notes={<MethodNote method={row.position.today.method} subject={t("today.net_today")} t={t} />}
          />
          <PositionFigure
            figure={row.position.front_month}
            label={t("today.net_front", { month: row.position.front_month.label.split(" ").pop() })}
            t={t}
            nowMs={nowMs}
          />
        </>
      )}
      {limit && (
        <Figure
          figure={limit}
          label={t(`today.tightest_${limit.kind}`)}
          t={t}
          nowMs={nowMs}
          wide
          converted={limitConverted}
          convertedMode="line"
          detail={
            <span className="today-limit-detail">
              <span className="today-limit-name">{limit.name}</span>
              <span aria-hidden="true">·</span>
              <span className="today-limit-used" data-status={limit.status}>
                {t("today.used", { pct: Math.round(limit.utilisation_pct) })}
              </span>
            </span>
          }
          notes={
            <>
              <WhyButton subject={limit.why.subject} id={limit.why.id} label={limit.name} language={language} t={t} />
              <MethodNote method={limit.method} subject={t(`today.tightest_${limit.kind}`)} t={t} />
            </>
          }
          action={
            <button type="button" className="ds-inline-link today-limit-link" onClick={onOpenLimits}>
              {t("today.limit_counts", { breach: limit.counts.breach, watch: limit.counts.watch })}
            </button>
          }
        />
      )}
      {row.limit_empty && <Empty empty={row.limit_empty} id="today-limit" />}
    </div>
  );
}

function BookRow({ row, frontMonth, t, nowMs, keyFigures, language, onOpenLimits }: { row: TodayBookRowDTO; frontMonth: string; t: Translate; nowMs: number; keyFigures?: TodayKeyFiguresRowDTO; language: string; onOpenLimits: () => void }) {
  const labels = useMemo(() => priceLabels(keyFigures), [keyFigures]);
  const pnlMethod = row.hubs.map((hub) => ("method" in hub.day_pnl_change ? hub.day_pnl_change.method : undefined)).find(Boolean);
  const pills = useSimulatedPills();
  const columns = useMemo<DataGridColumn<BookHub>[]>(
    () => [
      { id: "hub", header: t("today.book.hub"), rowHeader: true, sortable: true, value: (hub) => hub.hub },
      {
        id: "today",
        header: t("today.book.today"),
        unit: "MWh/d",
        type: "number",
        sortable: true,
        value: (hub) => hub.position_today.value,
        format: (value) => formatValue(value as number, "MWh/d", true),
        flash: true,
      },
      {
        id: "front",
        header: frontMonth,
        unit: "MWh/d",
        type: "number",
        sortable: true,
        value: (hub) => hub.position_front_month.value,
        format: (value) => formatValue(value as number, "MWh/d", true),
        flash: true,
      },
      {
        id: "open",
        header: t("today.book.net_open", { months: row.horizon_months ?? 12 }),
        unit: "MWh",
        type: "number",
        sortable: true,
        value: (hub) => hub.net_open_mwh,
        format: (value) => formatValue(value as number, "MWh", true),
        flash: true,
      },
      {
        id: "mark",
        header: t("today.book.mark"),
        type: "number",
        value: (hub) => hub.mark?.value ?? null,
        // Hubs mark in their own currency: the unit is per row.
        render: (hub) =>
          hub.mark ? (
            <>
              {formatValue(hub.mark.value, hub.mark.unit)} <small className="ds-grid-unit">{unitLabel(hub.mark.unit)}</small>
            </>
          ) : "–",
        flash: true,
        flashIdentity: (hub) => hub.mark?.unit ?? "",
        state: (hub) => stateCell(hub.mark, t, nowMs, pills),
        cellTitle: (hub) => (hub.mark?.as_of ? markTitle(hub.mark, labels, t) : undefined),
      },
      {
        id: "pnl",
        header: t("today.book.day_pnl"),
        type: "number",
        value: (hub) => ("empty" in hub.day_pnl_change ? null : hub.day_pnl_change.value),
        render: (hub) => {
          const change = hub.day_pnl_change;
          if (isEmptyEntry(change)) return <span className="muted" title={change.empty.code}>{change.empty.reason}</span>;
          return (
            <>
              <span className={pnlClass(change.value)}>{formatValue(change.value, change.unit, true)}</span>{" "}
              <small className="ds-grid-unit">{change.unit}</small>
              <PnlInReportingCurrency change={change as TodayFigureDTO} />
            </>
          );
        },
        flash: true,
        flashIdentity: (hub) => ("empty" in hub.day_pnl_change ? "" : hub.day_pnl_change.unit),
        state: (hub) => (isEmptyEntry(hub.day_pnl_change) ? null : stateCell(hub.day_pnl_change as TodayFigureDTO, t, nowMs, pills)),
        cellAttributes: (hub) => ({ id: figureAnchorId(`pnl.day_change.${hub.hub}`) }),
      },
    ],
    [frontMonth, labels, nowMs, pills, row.horizon_months, t],
  );
  return (
    <RowSection id="book" title={t("today.row.book")} actions={pnlMethod ? <MethodNote method={pnlMethod} subject={t("today.book.day_pnl")} t={t} /> : undefined}>
      {keyFigures && <BookFigures row={keyFigures} t={t} nowMs={nowMs} language={language} onOpenLimits={onOpenLimits} />}
      {row.empty ? (
        <Empty empty={row.empty} id="today-book" />
      ) : (
        <DataGrid
          id="today-book"
          label={t("today.row.book")}
          columns={columns}
          rows={row.hubs}
          rowKey={(hub) => hub.hub}
          density="regular"
          rowAttributes={(hub) => ({ "data-record": "today-book-hub", "data-hub": hub.hub })}
        />
      )}
    </RowSection>
  );
}

/* ------------------------------------------------------------------ row 4 */

/**
 * The forward balance's one line (CP-25) on Today: tighter or looser than normal over the
 * next 14 days and why, from the same read as Fundamentals -> Balance (its headline mode).
 */
function ForwardHeadline({ t, onOpen }: { t: Translate; onOpen?: () => void }) {
  const [dto, setDto] = useState<ForwardBalanceDTO | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api
      .fundamentalsForwardBalance({ summary: true }, { signal: controller.signal })
      .then((response) => setDto(response.data))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);
  const phrase = headlinePhrase(dto);
  if (!phrase) return null;
  return (
    <p className="today-forward-headline" data-today-forward={dto?.headline?.direction}>
      <strong>{t(phrase.key, phrase.values)}</strong> {t(String(phrase.values.driver), phrase.values)}
      {dto?.simulated && <> <SimulatedMark t={t} /></>}
      {onOpen && (
        <>
          {" "}
          <button type="button" className="link-button" onClick={onOpen}>{t("fb.today_open")}</button>
        </>
      )}
    </p>
  );
}

function FundamentalsRow({ row, t, nowMs, language, quiet, onOpenFundamentals }: { row: TodayFundamentalsRowDTO; t: Translate; nowMs: number; language: string; quiet?: string | null; onOpenFundamentals?: TodayScreenProps["onOpenFundamentals"] }) {
  const storage = row.storage;
  const balance = row.balance;
  return (
    <RowSection id="fundamentals" title={t("today.row.fundamentals")} meta={quiet ? <span data-today-quiet="">{t("today.needs.quiet")}</span> : undefined}>
      {row.empty ? (
        <Empty empty={row.empty} id="today-fundamentals" />
      ) : (
        <div className="today-fundamentals-grid">
          <ForwardHeadline t={t} onOpen={onOpenFundamentals ? () => onOpenFundamentals("balance") : undefined} />
          {/* Storage by country against its history (CP-04): Europe first, then the countries
              of my hubs and the largest; an empty storage read still says why here. */}
          {isEmptyEntry(storage) ? (
            <Empty empty={storage.empty} id="today-storage" />
          ) : (
            <section className="workspace-panel today-chart-panel" data-today-storage="by-country">
              <StorageByCountryPanel t={t} language={language} summary onOpenFull={onOpenFundamentals ? () => onOpenFundamentals("storage") : undefined} />
            </section>
          )}
          {isEmptyEntry(balance) ? (
            <Empty empty={balance.empty} id="today-balance" />
          ) : (
            <div className="today-figures today-fundamentals">
              <div className="today-fundamental">
                <Figure
                  figure={balance.latest}
                  label={t("today.supply_call")}
                  t={t}
                  nowMs={nowMs}
                  delta={
                    balance.call_7d_avg_gwh == null || balance.latest.value == null
                      ? undefined
                      : { text: t("today.supply_call_vs_avg", { avg: formatValue(balance.call_7d_avg_gwh, "GWh/d") }), value: null }
                  }
                  detail={t("today.supply_call_detail", { day: shortDay(balance.latest.as_of) })}
                />
                <Sparkline
                  values={balance.series.map((point) => point.call_gwh)}
                  days={balance.series.map((point) => point.day)}
                  simulated={balance.latest.simulated}
                  label={t("today.supply_call")}
                  unit={balance.latest.unit || "GWh/d"}
                  decimals={0}
                  t={t}
                  onOpen={onOpenFundamentals ? () => onOpenFundamentals("balance") : undefined}
                />
              </div>
              {balance.lng_gwh != null && (
                <div className="today-fundamental today-lng" data-today-lng="">
                  <span className="today-figure-label">{t("today.lng_sendout")}</span>
                  <strong>
                    {formatValue(balance.lng_gwh, "GWh/d")} <small className="ds-grid-unit">GWh/d</small>
                  </strong>
                  {balance.latest.simulated && <SimulatedMark t={t} />}
                  {balance.lng_vs_yesterday_gwh != null && (
                    <span className="muted"> {t("today.lng_vs_yesterday", { change: formatChange(balance.lng_vs_yesterday_gwh, "GWh/d") })}</span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </RowSection>
  );
}


/* ---------------------------------------------------------- freshness (FRESH-02) */

/** Move focus to a figure on the page by its key; false when it is not on this page. */
export function focusFigure(key: string): boolean {
  const target = document.getElementById(figureAnchorId(key));
  if (!target) return false;
  target.scrollIntoView({ block: "center" });
  const focusable = target.matches("[tabindex]") ? target : target.closest<HTMLElement>("tr") ?? target;
  if (!focusable.hasAttribute("tabindex")) focusable.setAttribute("tabindex", "-1");
  focusable.focus({ preventScroll: true });
  return true;
}

/**
 * The named list of figures that are not current, each leading to where it is shown. One list,
 * used by Today's freshness line and the top bar's status panel, so both say the same thing.
 */
export function StaleFigureList({
  figures,
  t,
  nowMs,
  onChoose,
}: {
  figures: DeskTodayDTO["stale_figures"];
  t: Translate;
  nowMs: number;
  onChoose: (key: string) => void;
}) {
  return (
    <ul className="today-stale-list" data-stale-figures={figures.length}>
      {figures.map((figure) => (
        <li key={figure.key}>
          <button type="button" className="today-stale-item" onClick={() => onChoose(figure.key)}>
            <span>{figure.label}</span>
            <span className="today-stale-state" data-state={figure.state}>
              {stateWords({ ...figure, simulated: false }, nowMs, t) ?? figure.state}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/**
 * The page's freshness line. Late or stale figures are named in a popover, each leading to where
 * it is shown; the demo desk says "Demo data" once instead of counting a static store as stale.
 */
export function TodayFreshness({ today, t, nowMs }: { today: DeskTodayDTO | null; t: Translate; nowMs: number }) {
  const compact = useCompactWidth();
  if (!today) return null;
  const stale = today.stale_figures;
  return (
    // Demo mode is said once, quietly, by the shell (the badge beside the mark and the account
    // menu); the page's simulated-prices banner still marks every simulated figure.
    <span className="today-freshness" data-today-freshness={today.simulated ? "demo" : stale.length ? "stale" : "current"}>
      {stale.length > 0 && (
        <Popover
          label={t("today.stale_title")}
          id="stale-figures"
          width="sm"
          placement="bottom-end"
          trigger={(props) => (
            <button {...props} type="button" className={`today-stale-trigger${today.simulated ? "" : " is-degraded"}`}>
              {t(compact ? "today.stale_link_short" : "today.stale_link", { count: stale.length })}
            </button>
          )}
        >
          {(close) => (
            <>
              <h3>{t("today.stale_title")}</h3>
              <StaleFigureList
                figures={stale}
                t={t}
                nowMs={nowMs}
                onChoose={(key) => {
                  close();
                  focusFigure(key);
                }}
              />
            </>
          )}
        </Popover>
      )}
      {!today.simulated && stale.length === 0 && <span className="today-fresh">{t("today.all_current")}</span>}
    </span>
  );
}

/* ------------------------------------------------------------------ screen */

const DEFAULT_ROWS: readonly TodayRowKey[] = ["market", "book", "needs_me", "fundamentals"];

/** Today's lead on the page's one header line: the gas day and front month, in the desk's words. */
export function TodayHeadline({ today, language, t }: { today: DeskTodayDTO | null; language: string; t: Translate }) {
  if (!today) return null;
  return (
    <span className="today-asof" data-today-headline="">
      {t("today.as_of", { gasDay: formatGasDay(today.gas_day, language), front: today.front_month })}
    </span>
  );
}

/** Desk brief and Refresh, on the same header line. */
export function TodayHeadActions({ t, loading, onOpenBrief, onRefresh }: { t: Translate; loading: boolean; onOpenBrief: () => void; onRefresh: () => void }) {
  return (
    <span className="today-head-actions">
      <Button variant="quiet" data-hint-anchor="desk-brief" onClick={onOpenBrief}>{t("brief.open")}</Button>
      <Button variant="quiet" onClick={onRefresh} loading={loading}>{t("market.refresh")}</Button>
    </span>
  );
}

export function TodayScreen({ today, loading, error, t, language, nowMs, onRefresh, onOpenBrief, onOpenLimits, onInspectPrice, rows = DEFAULT_ROWS, canSeeBook = true, onOpenNeed, onOpenPrices, headInStrip = false, onOpenFundamentals, onOpenGasDay, canRecordGasDay = false, gasDayStrip = false }: TodayScreenProps) {
  if (!today) {
    return (
      <div className="today" data-today="loading">
        {loading ? <Skeleton label={t("today.loading")} rows={6} /> : <EmptyState reason={t("today.failed")} next={error ?? undefined} action={<Button onClick={onRefresh}>{t("market.refresh")}</Button>} />}
      </div>
    );
  }
  const [keyFigures, , book, fundamentals, needsMe, gasDay, checklist] = today.rows;
  const quiet = needsMe && needsMe.items.length === 0 ? needsMe.quiet : null;
  const render: Record<TodayRowKey, () => ReactNode> = {
    market: () => (keyFigures?.market ? <MarketRow key="market" market={keyFigures.market} t={t} nowMs={nowMs} language={language} onInspectPrice={onInspectPrice} onOpenPrices={onOpenPrices} /> : null),
    book: () => (canSeeBook && book ? <BookRow key="book" row={book} frontMonth={today.front_month} t={t} nowMs={nowMs} keyFigures={keyFigures} language={language} onOpenLimits={onOpenLimits} /> : null),
    needs_me: () => (needsMe && needsMe.items.length > 0 ? <NeedsMeRow key="needs_me" row={needsMe} t={t} nowMs={nowMs} language={language} onOpen={onOpenNeed} /> : null),
    checklist: () => (canSeeBook && checklist ? <ChecklistRow key="checklist" row={checklist} t={t} language={language} nowMs={nowMs} canRecord={canRecordGasDay} onOpen={onOpenGasDay} onRecorded={onRefresh} /> : null),
    reconciliation: () => (canSeeBook ? <ReconciliationRow key="reconciliation" gasDay={today.gas_day} t={t} language={language} nowMs={nowMs} /> : null),
    gas_day: () => (canSeeBook && gasDay ? <GasDayRow key="gas_day" row={gasDay} t={t} language={language} nowMs={nowMs} onOpen={onOpenGasDay} /> : null),
    fundamentals: () => (fundamentals ? <FundamentalsRow key="fundamentals" row={fundamentals} t={t} nowMs={nowMs} language={language} quiet={quiet} onOpenFundamentals={onOpenFundamentals} /> : null),
  };
  const scope = today.all_simulated ? "all" : today.simulated ? "mixed" : "none";
  return (
    <SimulatedScope scope={scope} notice={t("today.all_simulated")}>
    <div className="today" data-today="ready">
      {/* One header line (gas day, as of, data feeds, brief, refresh): the page's context strip
          carries it when the cockpit composes Today; standalone, it is drawn here. */}
      {!headInStrip && (
        <div className="today-head">
          <TodayHeadline today={today} language={language} t={t} />
          <TodayHeadActions t={t} loading={loading} onOpenBrief={onOpenBrief} onRefresh={onRefresh} />
        </div>
      )}
      {today.warnings.length > 0 && (
        <ul className="today-warnings">{today.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      )}
      {gasDayStrip && canSeeBook && rows.includes("gas_day") && <GasDayStrip gasDay={gasDay} checklist={checklist} t={t} nowMs={nowMs} />}
      {quiet && !rows.includes("fundamentals") && <p className="today-quiet" data-today-quiet="">{t("today.needs.quiet")}</p>}
      {rows.map((key) => render[key]())}
    </div>
    </SimulatedScope>
  );
}
