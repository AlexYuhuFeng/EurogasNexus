/**
 * Today (UX-05, M.6): the first screen. It answers "what changed, and does it touch us?" in four
 * rows, all from one server read (`GET /api/desk/today`), with nothing recomputed here:
 *
 * 1. Key figures: front-month prices with their day change, the net position today and for the
 *    front month, and the headroom on the tightest limit.
 * 2. What changed: open alerts and outages, each with "Why".
 * 3. Our book against the market: position by hub with its mark and day P&L change.
 * 4. Fundamentals: storage fill and the supply call, with the balance table below.
 *
 * Every figure shows its value, unit, and its state in words when it is not current; a simulated
 * figure carries the simulated marker beside the value itself (AGENTS.md rule 17). An empty
 * section says the server's reason and next step on one line; a section the caller may not see
 * is absent.
 */
import { useMemo, type ReactNode } from "react";

import type {
  DeskTodayDTO,
  TodayBookRowDTO,
  TodayChangesRowDTO,
  TodayEmptyDTO,
  TodayFigureDTO,
  TodayFundamentalsRowDTO,
  TodayKeyFiguresRowDTO,
  TodayPriceDTO,
} from "@/api/client";
import {
  ageText,
  figureAnchorId,
  formatChange,
  formatValue,
  isEmptyEntry,
  shortDay,
  stateWords,
  timeWindow,
} from "@/app/model/todayModel";
import { pnlClass } from "@/app/model/pnlColor";
import { GasForPowerPanel } from "@/components/GasForPowerPanel";
import { MethodNote } from "@/components/MethodNote";
import { NweBalancePanel } from "@/components/NweBalancePanel";
import { WhyButton } from "@/components/WhyButton";
import { ReportLink } from "@/components/ReportLink";
import { Chart, Sparkline, type ChartData } from "@/components/ui/charts";
import {
  Button,
  DataGrid,
  EmptyState,
  KeyFigure,
  Panel,
  Popover,
  Skeleton,
  StatusBadge,
  type CellState,
  type DataGridColumn,
  type FigureState,
} from "@/components/ui";

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
  /**
   * The inspector hand-off for a price: returns how to open its observation (source, time,
   * state), or null when this desk holds no observation behind it.
   */
  onInspectPrice?: (price: TodayPriceDTO) => (() => void) | null;
}

/** The simulated marker beside a value: a short word, its meaning for screen readers. */
export function SimulatedMark({ t }: { t: Translate }) {
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
}) {
  const words = stateWords(figure, nowMs, t);
  return (
    <div className={wide ? "today-figure is-wide" : "today-figure"} id={figureAnchorId(figure.key)} tabIndex={-1} data-figure-key={figure.key}>
      <KeyFigure
        label={label}
        value={formatValue(figure.value, figure.unit, signed)}
        unit={figure.unit}
        size={size}
        delta={delta}
        state={figureState(figure)}
        stateLabel={words ?? undefined}
        detail={detail}
        action={action}
        notes={notes}
        valueClassName={valueClassName}
        marker={figure.simulated ? <SimulatedMark t={t} /> : undefined}
        title={figure.source ?? undefined}
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

function PriceFigure({ price, t, nowMs, onInspect }: { price: TodayPriceDTO; t: Translate; nowMs: number; onInspect?: (() => void) | null }) {
  const label = `${price.hub} ${price.product}`;
  return (
    <Figure
      figure={price}
      label={label}
      t={t}
      nowMs={nowMs}
      notes={
        onInspect ? (
          <button type="button" className="ds-inline-link" data-inspect-price={price.hub} aria-label={t("today.source_of", { name: label })} title={t("today.source_of", { name: label })} onClick={onInspect}>
            {t("today.source")}
          </button>
        ) : undefined
      }
      delta={
        price.day_change == null
          ? undefined
          : { text: t("today.day_change", { change: formatChange(price.day_change, price.unit), day: shortDay(price.day_change_vs) }), value: price.day_change }
      }
      detail={t("today.close_of", { day: shortDay(price.close_day) })}
    />
  );
}

function KeyFiguresRow({ row, t, nowMs, language, onOpenLimits, onInspectPrice }: { row: TodayKeyFiguresRowDTO; t: Translate; nowMs: number; language: string; onOpenLimits: () => void; onInspectPrice?: TodayScreenProps["onInspectPrice"] }) {
  const limit = row.tightest_limit;
  return (
    <RowSection id="key_figures" title={t("today.row.key_figures")}>
      <div className="today-figures">
        {row.prices.map((price) =>
          isEmptyEntry(price) ? (
            <div key={price.key} className="today-figure today-figure-empty">
              <span className="today-figure-label">{price.hub}</span>
              <Empty empty={price.empty} id={`today-${price.key}`} />
            </div>
          ) : (
            <PriceFigure key={price.key} price={price as TodayPriceDTO} t={t} nowMs={nowMs} onInspect={onInspectPrice?.(price as TodayPriceDTO)} />
          ),
        )}
        {row.prices_empty && <Empty empty={row.prices_empty} id="today-prices" />}
        {row.position && (
          <>
            <Figure
              figure={row.position.today}
              label={t("today.net_today")}
              t={t}
              nowMs={nowMs}
              signed
              notes={<MethodNote method={row.position.today.method} subject={t("today.net_today")} t={t} />}
            />
            <Figure
              figure={row.position.front_month}
              label={t("today.net_front", { month: row.position.front_month.label.split(" ").pop() })}
              t={t}
              nowMs={nowMs}
              signed
            />
          </>
        )}
        {row.position_empty && <Empty empty={row.position_empty} id="today-position" />}
        {limit && (
          <Figure
            figure={limit}
            label={t(`today.tightest_${limit.kind}`)}
            t={t}
            nowMs={nowMs}
            wide
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
    </RowSection>
  );
}

/* ------------------------------------------------------------------ row 2 */

function ChangesRow({ row, t, nowMs, language, onOpenOutages }: { row: TodayChangesRowDTO; t: Translate; nowMs: number; language: string; onOpenOutages: () => void }) {
  const zh = language.toLowerCase().startsWith("zh");
  const { alerts, outages } = row;
  return (
    <RowSection id="changes" title={t("today.row.changes")}>
      {row.empty ? (
        <Empty empty={row.empty} id="today-changes" />
      ) : (
        <div className="today-changes">
          <Panel
            title={t("today.alerts")}
            level={3}
            meta={t("today.alert_counts", { open: alerts.counts.open, critical: alerts.counts.critical, warning: alerts.counts.warning })}
          >
            {alerts.items.length === 0 ? (
              <EmptyState compact reason={t("today.no_alerts")} />
            ) : (
              <ul className="today-list">
                {alerts.items.map((alert) => (
                  <li key={alert.alert_id} data-severity={alert.severity}>
                    <StatusBadge tone={alert.severity === "critical" ? "breach" : "watch"}>{t(`today.severity.${alert.severity}`)}</StatusBadge>
                    <span className="today-list-text">{zh && alert.title_zh ? alert.title_zh : alert.title}</span>
                    {alert.simulated && <SimulatedMark t={t} />}
                    <span className="today-list-time">{ageText(alert.as_of, nowMs, t)}</span>
                    <WhyButton subject={alert.why.subject} id={alert.why.id} label={alert.title} language={language} t={t} />
                    <ReportLink subject={{ kind: "alert", id: alert.alert_id }} label={alert.title} t={t} />
                  </li>
                ))}
              </ul>
            )}
            {alerts.more > 0 && <p className="today-more">{t("today.more", { count: alerts.more })}</p>}
          </Panel>
          <Panel
            title={t("today.outages")}
            level={3}
            meta={t("today.outage_counts", { active: outages.counts.active, scheduled: outages.counts.scheduled, days: outages.horizon_days })}
            actions={<Button variant="quiet" onClick={onOpenOutages}>{t("today.open_outages")}</Button>}
          >
            {outages.items.length === 0 ? (
              <EmptyState compact reason={t("today.no_outages", { days: outages.horizon_days })} />
            ) : (
              <ul className="today-list">
                {outages.items.map((outage) => (
                  <li key={outage.event_id}>
                    <StatusBadge tone="neutral">{t(`today.outage_status.${outage.status}`, { defaultValue: outage.status })}</StatusBadge>
                    <span className="today-list-text">
                      <strong>{outage.facility}</strong>
                      {outage.zone ? <span className="muted"> {outage.zone}</span> : null}
                      <span className="muted"> · {timeWindow(outage.start_utc, outage.end_utc)}</span>
                    </span>
                    <span className="today-list-figure">
                      {outage.unavailable == null ? "–" : formatValue(outage.unavailable, outage.unit ?? "")}
                      {outage.unit ? <small className="ds-grid-unit">{outage.unit}</small> : null}
                      {outage.simulated && <SimulatedMark t={t} />}
                    </span>
                    <WhyButton subject={outage.why.subject} id={outage.why.id} label={outage.facility} language={language} t={t} />
                    <ReportLink subject={{ kind: "outage", id: String(outage.event_id) }} label={outage.facility} t={t} />
                  </li>
                ))}
              </ul>
            )}
            {outages.more > 0 && <p className="today-more">{t("today.more", { count: outages.more })}</p>}
          </Panel>
        </div>
      )}
    </RowSection>
  );
}

/* ------------------------------------------------------------------ row 3 */

type BookHub = TodayBookRowDTO["hubs"][number];

function stateCell(figure: TodayFigureDTO | null | undefined, t: Translate, nowMs: number): CellState | null {
  if (!figure) return null;
  if (figure.state !== "current") {
    const words = stateWords(figure, nowMs, t) ?? figure.state;
    return { kind: figure.state === "manual" ? "manual" : figure.state === "late" ? "late" : "stale", label: words, description: words };
  }
  return figure.simulated ? simulatedCell(t) : null;
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

function BookRow({ row, frontMonth, t, nowMs, keyFigures }: { row: TodayBookRowDTO; frontMonth: string; t: Translate; nowMs: number; keyFigures?: TodayKeyFiguresRowDTO }) {
  const labels = useMemo(() => priceLabels(keyFigures), [keyFigures]);
  const pnlMethod = row.hubs.map((hub) => ("method" in hub.day_pnl_change ? hub.day_pnl_change.method : undefined)).find(Boolean);
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
      },
      {
        id: "front",
        header: frontMonth,
        unit: "MWh/d",
        type: "number",
        sortable: true,
        value: (hub) => hub.position_front_month.value,
        format: (value) => formatValue(value as number, "MWh/d", true),
      },
      {
        id: "open",
        header: t("today.book.net_open", { months: row.horizon_months ?? 12 }),
        unit: "MWh",
        type: "number",
        sortable: true,
        value: (hub) => hub.net_open_mwh,
        format: (value) => formatValue(value as number, "MWh", true),
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
              {formatValue(hub.mark.value, hub.mark.unit)} <small className="ds-grid-unit">{hub.mark.unit}</small>
            </>
          ) : "–",
        state: (hub) => stateCell(hub.mark, t, nowMs),
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
            </>
          );
        },
        state: (hub) => (isEmptyEntry(hub.day_pnl_change) ? null : stateCell(hub.day_pnl_change as TodayFigureDTO, t, nowMs)),
        cellAttributes: (hub) => ({ id: figureAnchorId(`pnl.day_change.${hub.hub}`) }),
      },
    ],
    [frontMonth, labels, nowMs, row.horizon_months, t],
  );
  return (
    <RowSection id="book" title={t("today.row.book")} actions={pnlMethod ? <MethodNote method={pnlMethod} subject={t("today.book.day_pnl")} t={t} /> : undefined}>
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

type StorageEntry = Exclude<TodayFundamentalsRowDTO["storage"], { empty: TodayEmptyDTO }>;

/** NW Europe fill over the season, against the same gas days a year earlier and the EU target. */
function StorageSeasonChart({ storage, t, nowMs }: { storage: StorageEntry; t: Translate; nowMs: number }) {
  const data = useMemo<ChartData>(() => {
    const season = storage.season ?? [];
    const simulated = storage.latest.simulated;
    return {
      axis: "gas-day",
      x: season.map((point) => point.day),
      xTitle: t("chart.gas_day"),
      unit: "%",
      series: [
        { id: "fill", label: t("today.storage_chart.this_year"), values: season.map((point) => point.fill_pct), simulated, decimals: 1 },
        { id: "previous", label: t("today.storage_chart.previous_year"), values: season.map((point) => point.previous_year_fill_pct), simulated, colour: 8, decimals: 1 },
        ...(storage.target
          ? [{ id: "target", label: t("today.storage_chart.target", { pct: storage.target.pct }), values: season.map(() => storage.target!.pct), reference: true, decimals: 0 }]
          : []),
      ],
    };
  }, [storage, t]);
  return (
    <section className="workspace-panel today-chart-panel" aria-labelledby="chart-storage-season-title">
      <Chart
        id="storage-season"
        title={t("today.storage_chart.title")}
        data={data}
        t={t}
        height={200}
        asOf={storage.latest.as_of}
        state={stateWords(storage.latest, nowMs, t) ?? undefined}
        simulated={storage.latest.simulated}
        note={storage.target ? t("today.storage_chart.note", { pct: storage.target.pct, open: storage.target.window_open, deadline: storage.target.deadline }) : undefined}
      />
    </section>
  );
}

function FundamentalsRow({ row, t, nowMs }: { row: TodayFundamentalsRowDTO; t: Translate; nowMs: number }) {
  const storage = row.storage;
  const balance = row.balance;
  const balanceSimulated = !isEmptyEntry(balance) && balance.latest.simulated;
  return (
    <RowSection id="fundamentals" title={t("today.row.fundamentals")}>
      {row.empty ? (
        <Empty empty={row.empty} id="today-fundamentals" />
      ) : (
        <div className="today-figures today-fundamentals">
          {isEmptyEntry(storage) ? (
            <Empty empty={storage.empty} id="today-storage" />
          ) : (
            <div className="today-fundamental">
              <Figure
                figure={storage.latest}
                label={t("today.storage_fill")}
                t={t}
                nowMs={nowMs}
                detail={t("today.storage_inventory", { twh: formatValue(storage.inventory_twh, "TWh"), day: shortDay(storage.latest.as_of) })}
              />
              <Sparkline
                values={storage.series.map((point) => point.fill_pct)}
                days={storage.series.map((point) => point.day)}
                simulated={storage.latest.simulated}
                label={t("today.storage_spark", { days: storage.series.length })}
              />
            </div>
          )}
          {isEmptyEntry(balance) ? (
            <Empty empty={balance.empty} id="today-balance" />
          ) : (
            <div className="today-fundamental">
              <Figure
                figure={balance.latest}
                label={t("today.supply_call")}
                t={t}
                nowMs={nowMs}
                detail={t("today.supply_call_detail", { day: shortDay(balance.latest.as_of) })}
              />
              <Sparkline
                values={balance.series.map((point) => point.call_gwh)}
                days={balance.series.map((point) => point.day)}
                simulated={balance.latest.simulated}
                label={t("today.balance_spark", { days: balance.series.length })}
              />
            </div>
          )}
        </div>
      )}
      <div className="today-fundamentals-detail">
        {!isEmptyEntry(storage) && storage.season && storage.season.length > 1 && (
          <StorageSeasonChart storage={storage} t={t} nowMs={nowMs} />
        )}
        <NweBalancePanel t={t} simulated={balanceSimulated} />
        <GasForPowerPanel t={t} />
      </div>
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
  if (!today) return null;
  const stale = today.stale_figures;
  return (
    <span className="today-freshness" data-today-freshness={today.simulated ? "demo" : stale.length ? "stale" : "current"}>
      {today.simulated && (
        <StatusBadge tone="simulated" title={today.simulated_notice ?? undefined}>
          {t("today.demo_data")}
        </StatusBadge>
      )}
      {stale.length > 0 && (
        <Popover
          label={t("today.stale_title")}
          id="stale-figures"
          width="sm"
          placement="bottom-end"
          trigger={(props) => (
            <button {...props} type="button" className={`today-stale-trigger${today.simulated ? "" : " is-degraded"}`}>
              {t("today.stale_link", { count: stale.length })}
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

export function TodayScreen({ today, loading, error, t, language, nowMs, onRefresh, onOpenBrief, onOpenLimits, onOpenOutages, onInspectPrice }: TodayScreenProps) {
  if (!today) {
    return (
      <div className="today" data-today="loading">
        {loading ? <Skeleton label={t("today.loading")} rows={6} /> : <EmptyState reason={t("today.failed")} next={error ?? undefined} action={<Button onClick={onRefresh}>{t("market.refresh")}</Button>} />}
      </div>
    );
  }
  const [keyFigures, changes, book, fundamentals] = today.rows;
  return (
    <div className="today" data-today="ready">
      <div className="today-head">
        <p className="today-asof">
          {/* The as-of instant is on the context line above (one time, one place). */}
          {t("today.as_of", { gasDay: today.gas_day, front: today.front_month })}
        </p>
        <div className="today-head-actions">
          <Button variant="quiet" onClick={onOpenBrief}>{t("brief.open")}</Button>
          <Button variant="quiet" onClick={onRefresh} loading={loading}>{t("market.refresh")}</Button>
        </div>
      </div>
      {today.warnings.length > 0 && (
        <ul className="today-warnings">{today.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      )}
      {keyFigures && <KeyFiguresRow row={keyFigures} t={t} nowMs={nowMs} language={language} onOpenLimits={onOpenLimits} onInspectPrice={onInspectPrice} />}
      {changes && <ChangesRow row={changes} t={t} nowMs={nowMs} language={language} onOpenOutages={onOpenOutages} />}
      {book && <BookRow row={book} frontMonth={today.front_month} t={t} nowMs={nowMs} keyFigures={keyFigures} />}
      {fundamentals && <FundamentalsRow row={fundamentals} t={t} nowMs={nowMs} />}
    </div>
  );
}
