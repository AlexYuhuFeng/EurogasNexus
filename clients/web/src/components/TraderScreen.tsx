/**
 * Desk → Board (SMALL_DESK_PLAN step 4 and section 9): the one screen the desk keeps open beside
 * its trading screen. Four panels on one 1920 × 1080 screen without scrolling:
 *
 * - **Hub prices**: contracts down, NBP, TTF, ZTP, THE and PVB across, bid and offer always with
 *   last and the change on the day, each hub in its own quotation; the source and time of a quote
 *   on hover; the stale mark in the cell; "no source" where nothing prices it (rule 17: never a
 *   simulated number that reads as a price; a simulated price carries the sim mark, or the
 *   page's one "Source: simulated prices" line when every price is simulated).
 * - **Spreads**: the desk's hub pairs net of transport (the owner's rule, stated on screen) and
 *   the time spreads at each hub, all from the server's spread board.
 * - **Book**: today's P&L per currency (a desk estimate before the ETRM close) and the position
 *   on the board's rows, th/d at NBP and MW on the continent. Seam: the position source is the
 *   position ladder; captured deals reach it through the sibling work on the ladder and the
 *   live stream, which this screen reads without change.
 * - **Fundamentals**: storage, supply and interconnectors, LNG send-out, outages and weather,
 *   GB in mcm/d and the continent in GWh/d, each with its date and source on hover.
 *
 * Alerts are in the shell's strip; the stale and "server cannot be reached" states are the
 * shell's (ConnectionNotice, LiveValue). No order leaves this screen (AGENTS rule 8).
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { api, type FlowObsDTO, type MarketQuoteDTO, type NormalizedMarketObsDTO, type OutageEventDTO, type StorageEntityDTO } from "@/api/client";
import type { SpreadBoardDTO } from "@/api/spreads";
import type { DealPnlDTO } from "@/api/deals";
import { readKey, useCachedRead } from "@/app/data/readCache";
import { useCompactWidth } from "@/app/shell/useShellLayout";
import { useInstantFormatter } from "@/app/time/useInstant";
import { formatMeasure } from "@/app/time/valueFormat";
import { sourceSystemLabel } from "@/app/model/enumLabels";
import { boardReasonText } from "@/app/model/spreadsBoard";
import {
  BOARD_HUBS,
  boardContracts,
  boardSimulation,
  buildBoard,
  gasDayOf,
  gwhToMcm,
  hubPositionUnit,
  hubPriceUnit,
  hubSpreadRows,
  mcmToGwh,
  pairsParam,
  priceDecimals,
  positionOnBoard,
  timeSpreads,
  TIME_SPREAD_KEYS,
  type BoardCell,
  type BoardContract,
  type HubSpreadRow,
  type PositionCell,
  type SpreadFigure,
  type TimeSpreadCell,
  type TimeSpreadKey,
} from "@/app/model/traderBoardModel";
import { pnlClass } from "@/app/model/pnlColor";
import { DEFAULT_SELECTION, selectionKey, type BoardSelection } from "@/app/model/traderDetailModel";
import { Button, DataGrid, DirectionMark, EmptyState, Instant, KeyFigure, Segmented, StatusBadge, type DataGridColumn } from "@/components/ui";
import { directionOf } from "@/components/ui/dataGridModel";
import { TraderDetail } from "@/components/TraderDetail";
import { boardEvents, calendarEvents, isAlertEvent, licensedSlot, type BoardEvent } from "@/app/model/traderEventsModel";
import { PublicationCalendar } from "@/components/PublicationCalendar";
import { SimulatedScope, simulatedScopeOf, useSimulatedPills } from "@/components/ui/SimulatedScope";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const HUBS: readonly string[] = BOARD_HUBS;

/* ------------------------------------------------------------------ shared bits */

/** The sim mark beside a simulated value, unless the whole screen says it once. */
function SimMark({ t }: { t: Translate }) {
  if (!useSimulatedPills()) return null;
  return (
    <span className="ds-cell-mark" data-state="simulated" title={t("board.sim_long")}>
      <span aria-hidden="true">{t("board.sim")}</span>
      <span className="ds-visually-hidden">{t("board.sim_long")}</span>
    </span>
  );
}

function price(value: number | null, hub?: string): string {
  return formatMeasure("price", value, hub ? { decimals: priceDecimals(hub) } : {});
}

const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "27 Nov" (English) or "11月27日" (Chinese): the day a published price is for. */
export function publishedDay(day: string, t: Translate): string {
  const mm = Number(day.slice(5, 7));
  const dd = Number(day.slice(8, 10));
  if (!mm || !dd) return day;
  return t("board.published.day", { dd, mm, mon: MONTH_ABBR[mm - 1] });
}

/** The title of a published daily price: what it is, its day and delivery, its source. */
export function publishedTitle(cell: BoardCell, t: Translate): string {
  const published = cell.published!;
  const delivery = published.deliveryStart && published.deliveryEnd && published.deliveryStart !== published.deliveryEnd ? `${published.deliveryStart} – ${published.deliveryEnd}` : published.deliveryStart ?? published.day;
  return [
    t("board.published.title", {
      name: published.name || sourceSystemLabel(cell.source ?? ""),
      kind: t(`board.published.kind_long.${published.kind}`),
      day: published.day,
      delivery,
      status: t(`board.published.status.${published.status === "preliminary" ? "preliminary" : "final"}`),
    }),
    published.publisher ?? "",
    published.consent ?? "",
    cell.unit,
  ].filter(Boolean).join(" · ");
}

function change(value: number | null, hub?: string): string {
  return value === null ? "" : formatMeasure("change", value, hub ? { decimals: priceDecimals(hub) } : {});
}

/** One line under a panel: provenance and method, quiet. */
function Foot({ children }: { children: ReactNode }) {
  return <p className="trader-foot">{children}</p>;
}

/* ------------------------------------------------------------------ price board */

interface BoardRow {
  contract: BoardContract;
  cells: Record<string, BoardCell>;
}

export interface PriceBoardProps {
  contracts: readonly BoardContract[];
  cells: Record<string, Record<string, BoardCell>>;
  hubs?: readonly string[];
  t: Translate;
  /** The instant a quote is shown at, in the reader's zone ("16:08 CET"). */
  formatTime?: (iso: string | null) => string;
  compact?: boolean;
  /** A price cell or a hub's head was chosen: the detail panel follows it. */
  onSelect?: (selection: BoardSelection) => void;
  /** The chosen item's key (`selectionKey`), marked on the board. */
  selected?: string | null;
  /** Quotes not read yet: each cell says it is reading, never "no source" before the answer. */
  loading?: boolean;
}

/** Contracts down, hubs across; Bid | Offer | Last | Chg under each hub, in its quotation. */
export function PriceBoard({ contracts, cells, hubs = HUBS, t, formatTime = (iso) => iso ?? "", compact = false, onSelect, selected = null, loading = false }: PriceBoardProps) {
  const rows = useMemo<BoardRow[]>(() => contracts.map((contract) => ({ contract, cells: cells[contract.key] ?? {} })), [contracts, cells]);
  const columns = useMemo<DataGridColumn<BoardRow>[]>(() => {
    const out: DataGridColumn<BoardRow>[] = [
      {
        id: "contract",
        header: t("board.contract"),
        rowHeader: true,
        width: "64px",
        value: (row) => row.contract.label,
        cellAttributes: (row) => ({ "data-contract": row.contract.key }),
      },
    ];
    for (const hub of hubs) {
      const headLabel = <span className="trader-hub-head">{hub}<span className="ds-grid-unit">{hubPriceUnit(hub)}</span></span>;
      const group = {
        id: hub,
        header: onSelect ? (
          <button
            type="button"
            className="trader-select trader-hub-button"
            data-select={`curve:${hub}`}
            aria-pressed={selected === `curve:${hub}`}
            title={t("board.detail.open_curve", { hub })}
            onClick={() => onSelect({ kind: "curve", hub })}
          >
            {headLabel}
          </button>
        ) : headLabel,
        title: t("board.hub_unit", { hub, unit: hubPriceUnit(hub) }),
      };
      const cellOf = (row: BoardRow) => row.cells[hub];
      const title = (row: BoardRow) => {
        const cell = cellOf(row);
        if (!cell || cell.status === "no_source") return t("board.no_source_long", { hub, contract: row.contract.label });
        if (cell.status === "unit") return t("board.unit_long");
        if (cell.published) return publishedTitle(cell, t);
        return t("board.cell_title", {
          source: cell.simulated ? t("board.simulated_source", { source: sourceSystemLabel(cell.source ?? "") }) : sourceSystemLabel(cell.source ?? ""),
          time: formatTime(cell.observedAt),
          unit: cell.unit,
        });
      };
      const priced = (row: BoardRow) => cellOf(row)?.status === "priced";
      out.push(
        {
          id: `${hub}-bid`,
          header: t("board.bid"),
          type: "number",
          group,
          keepWhenEmpty: true,
          value: (row) => cellOf(row)?.bid ?? null,
          render: (row) => {
            const cell = cellOf(row);
            const key = `price:${row.contract.key}:${hub}`;
            const content = !cell || cell.status !== "priced" ? (
              <span className="trader-no-source" data-no-source={loading ? undefined : hub} data-reading={loading ? hub : undefined}>
                {loading ? t("board.reading") : cell?.status === "unit" ? t("board.unit_short") : t("board.no_source")}
              </span>
            ) : cell.published ? (
              // A published daily figure has no bid: its place says the day the figure is for.
              <span className="trader-published-day" data-published-day={cell.published.day} data-consent-withdrawn={cell.published.consentWithdrawn ? "true" : undefined}>
                {publishedDay(cell.published.day, t)}
              </span>
            ) : price(cell.bid, hub);
            if (!onSelect) return content;
            return (
              <button
                type="button"
                className="trader-select trader-cell-button"
                data-select={key}
                aria-pressed={selected === key}
                aria-label={t("board.detail.open_price", { hub, contract: row.contract.label })}
                onClick={() => onSelect({ kind: "price", contract: row.contract.key, hub })}
              >
                {content}
              </button>
            );
          },
          flash: true,
          flashTone: "direction",
          flashQuiet: (row) => Boolean(cellOf(row)?.stale),
          cellTitle: title,
          cellClassName: (row) => (priced(row) ? (cellOf(row)?.stale ? "is-stale" : undefined) : "is-empty"),
          cellAttributes: (row) => ({ "data-cell": `${row.contract.key}:${hub}`, "data-stale": cellOf(row)?.stale ? "true" : undefined, "data-published": cellOf(row)?.published ? cellOf(row)!.published!.kind : undefined }),
        },
        {
          id: `${hub}-offer`,
          header: t("board.offer"),
          type: "number",
          group,
          keepWhenEmpty: true,
          value: (row) => cellOf(row)?.offer ?? null,
          render: (row) => {
            const cell = cellOf(row);
            if (!cell || cell.status !== "priced") return "";
            // ...and the offer's place says what it is (an index, a daily price), never a side.
            if (cell.published) return <span className="trader-published-kind">{t(`board.published.kind.${cell.published.kind}`)}</span>;
            return price(cell.offer, hub);
          },
          // The quote's own stale mark, once per hub and contract, in the offer's glyph place.
          staleLabel: (row) => (priced(row) && cellOf(row)?.stale ? t("stale.value_since", { time: formatTime(cellOf(row)!.observedAt) }) : null),
          flash: true,
          flashTone: "direction",
          flashQuiet: (row) => Boolean(cellOf(row)?.stale),
          cellTitle: title,
          cellClassName: (row) => (priced(row) ? (cellOf(row)?.stale ? "is-stale" : undefined) : "is-empty"),
        },
        {
          id: `${hub}-last`,
          header: t("board.last"),
          type: "number",
          group,
          keepWhenEmpty: true,
          value: (row) => cellOf(row)?.last ?? null,
          render: (row) => (priced(row) ? price(cellOf(row)!.last, hub) : ""),
          flash: true,
          flashTone: "direction",
          flashQuiet: (row) => Boolean(cellOf(row)?.stale),
          cellTitle: title,
          // A published daily price's figure is its Last: it reads as the cell's price.
          cellClassName: (row) => (priced(row) ? (cellOf(row)?.published ? "trader-published-last" : "trader-secondary") : "is-empty"),
        },
        {
          id: `${hub}-chg`,
          header: t("board.chg"),
          headerTitle: t("board.chg_long"),
          type: "number",
          group,
          keepWhenEmpty: true,
          value: (row) => cellOf(row)?.change ?? null,
          render: (row) => {
            const cell = cellOf(row);
            if (!cell || cell.status !== "priced") return "";
            return (
              <>
                {change(cell.change, hub)}
                <DirectionMark direction={directionOf(cell.change)} />
                {cell.simulated ? <SimMark t={t} /> : null}
              </>
            );
          },
          cellTitle: (row) => {
            const cell = cellOf(row);
            if (cell?.published && cell.closeDay) return t("board.published.chg_title", { day: cell.closeDay, today: cell.published.day });
            return cell?.closeDay ? t("board.chg_title", { day: cell.closeDay }) : title(row);
          },
          cellClassName: (row) => (priced(row) ? "trader-secondary" : "is-empty"),
        },
      );
    }
    return out;
  }, [hubs, t, formatTime, onSelect, selected, loading]);
  return (
    <DataGrid
      id="trader-board"
      label={t("board.prices_title")}
      columns={columns}
      // The twelve contracts are the board's definition, drawn whatever data exists: before the
      // first read a cell says it is reading, after it a cell with no quote says "no source".
      rows={rows}
      rowKey={(row) => row.contract.key}
      density={compact ? "compact" : "regular"}
      phoneLayout="scroll"
      className="trader-board-grid"
      tableAttributes={{ "data-trader-board": "", "data-market-board": "trader" }}
      rowAttributes={(row) => ({ "data-record": "board-contract", "data-record-id": row.contract.key })}
      rowClassName={(row) => (selected?.startsWith(`price:${row.contract.key}:`) ? "trader-row-chosen" : undefined)}
    />
  );
}

/* ------------------------------------------------------------------ spreads */

function spreadText(figure: SpreadFigure | null, field: "gross" | "net", t: Translate): ReactNode {
  if (!figure) return "–";
  const value = figure[field];
  if (value === null) return <span className="trader-muted">{field === "net" && figure.available ? t("board.spread.no_route") : "–"}</span>;
  return formatMeasure("spread", value);
}

function transportTitle(figure: SpreadFigure | null, t: Translate): string | undefined {
  if (!figure || !figure.available) return figure?.reason ? boardReasonText(figure.reason, t) : undefined;
  const parts: string[] = [];
  if (figure.basis === "held") parts.push(t("board.spread.held_title"));
  else if (figure.basis === "part") parts.push(t("board.spread.part_title"));
  else if (figure.basis === "default") parts.push(t("board.spread.default_title"));
  else parts.push(t("board.spread.unpriced_title"));
  if (figure.capacity !== null) parts.push(t("board.spread.capacity_part", { value: formatMeasure("tariff", figure.capacity), product: figure.capacityProduct ?? "" }));
  if (figure.flow !== null) parts.push(t("board.spread.flow_part", { value: formatMeasure("tariff", figure.flow) }));
  if (figure.factor !== null && figure.gbpPerEur !== null) {
    parts.push(t("board.spread.nbp_rate", { rate: formatMeasure("fx_rate", figure.gbpPerEur), day: figure.closeDay ?? "" }));
  }
  if (figure.direction) parts.push(t("board.spread.flows", { direction: figure.direction }));
  return parts.join(" · ");
}

export interface SpreadsProps {
  rows: readonly HubSpreadRow[];
  time: Record<TimeSpreadKey, Record<string, TimeSpreadCell>>;
  hubs?: readonly string[];
  t: Translate;
  compact?: boolean;
  onSelect?: (selection: BoardSelection) => void;
  selected?: string | null;
}

/** Hub spreads net of transport, and the time spreads at each hub. */
export function Spreads({ rows, time, hubs = HUBS, t, compact = false, onSelect, selected = null }: SpreadsProps) {
  const pairColumns = useMemo<DataGridColumn<HubSpreadRow>[]>(() => {
    const tenorColumns = (tenor: "da" | "ma"): DataGridColumn<HubSpreadRow>[] => {
      const group = { id: tenor, header: t(`board.spread.${tenor}`) };
      const fig = (row: HubSpreadRow) => row[tenor];
      return [
        { id: `${tenor}-gross`, header: t("board.spread.gross"), type: "number", group, keepWhenEmpty: true, value: (row) => fig(row)?.gross ?? null, render: (row) => (fig(row)?.available ? spreadText(fig(row), "gross", t) : <span className="trader-muted">{t("board.no_source")}</span>), cellTitle: (row) => transportTitle(fig(row), t), cellAttributes: (row) => ({ "data-spread": `${row.pair}:${tenor}`, "data-unit": fig(row)?.unit }) },
        { id: `${tenor}-cost`, header: t("board.spread.transport"), type: "number", group, keepWhenEmpty: true, value: (row) => fig(row)?.transport ?? null, render: (row) => (fig(row)?.transport != null ? <span data-basis={fig(row)!.basis}>{formatMeasure("spread", fig(row)!.transport, { signed: false })}{fig(row)!.basis === "held" ? <span className="trader-basis" aria-hidden="true">{t("board.spread.held_short")}</span> : null}</span> : ""), cellTitle: (row) => transportTitle(fig(row), t), cellAttributes: (row) => ({ "data-basis": fig(row)?.basis }) },
        { id: `${tenor}-net`, header: t("board.spread.net"), type: "number", group, keepWhenEmpty: true, value: (row) => fig(row)?.net ?? null, render: (row) => (fig(row)?.available ? <strong className="trader-net">{spreadText(fig(row), "net", t)}{fig(row)?.simulated ? <SimMark t={t} /> : null}</strong> : ""), cellTitle: (row) => transportTitle(fig(row), t) },
      ];
    };
    return [
      {
        id: "pair",
        header: t("board.spread.pair"),
        rowHeader: true,
        value: (row) => row.pair,
        render: (row) => (
          <span className="trader-pair">
            {row.pair.replace("–", " − ")}
            <span className="ds-grid-unit">{row.da?.unit ?? row.ma?.unit ?? ""}</span>
          </span>
        ),
        cellTitle: (row) => (row.route ? t("board.spread.route", { route: row.route }) : undefined),
      },
      ...tenorColumns("da"),
      ...tenorColumns("ma"),
    ];
  }, [t]);
  const timeRows = useMemo(() => TIME_SPREAD_KEYS.map((key) => ({ key, cells: time[key] ?? {} })), [time]);
  const timeColumns = useMemo<DataGridColumn<{ key: TimeSpreadKey; cells: Record<string, TimeSpreadCell> }>[]>(
    () => [
      { id: "spread", header: t("board.spread.time"), rowHeader: true, value: (row) => t(`board.time.${row.key}`) },
      ...hubs.map<DataGridColumn<{ key: TimeSpreadKey; cells: Record<string, TimeSpreadCell> }>>((hub) => ({
        id: hub,
        header: hub,
        unit: hubPriceUnit(hub),
        type: "number",
        keepWhenEmpty: true,
        value: (row) => row.cells[hub]?.value ?? null,
        render: (row) => {
          const cell = row.cells[hub];
          if (!cell || cell.value === null) return <span className="trader-muted">–</span>;
          return (
            <>
              {formatMeasure("spread", cell.value)}
              {cell.simulated ? <SimMark t={t} /> : null}
            </>
          );
        },
        cellTitle: (row) => {
          const cell = row.cells[hub];
          if (cell?.reason) return boardReasonText(cell.reason, t);
          if (row.key === "da_wd") return t("board.time.da_wd_title");
          return cell?.label ?? undefined;
        },
      })),
    ],
    [hubs, t],
  );
  return (
    <>
      <DataGrid
        id="trader-spreads"
        label={t("board.spreads_title")}
        columns={pairColumns}
        rows={rows}
        rowKey={(row) => row.pair}
        density={compact ? "compact" : "regular"}
        phoneLayout="scroll"
        empty={t("board.spread.empty")}
        rowAttributes={(row) => ({ "data-record": "hub-spread", "data-record-id": row.pair, "data-select": `spread:${row.pair}` })}
        onRowAction={onSelect ? (row) => onSelect({ kind: "spread", pair: row.pair, tenor: row.da?.available || !row.ma?.available ? "DA" : "MA" }) : undefined}
        selectedKey={onSelect ? (selected?.startsWith("spread:") ? selected.split(":")[1] ?? null : null) : undefined}
      />
      <p className="trader-rule" data-transport-rule="">{t("board.spread.rule")}</p>
      <DataGrid
        id="trader-time-spreads"
        label={t("board.spread.time")}
        columns={timeColumns}
        rows={timeRows}
        rowKey={(row) => row.key}
        density="compact"
        phoneLayout="scroll"
      />
    </>
  );
}

/* ------------------------------------------------------------------ book */

type PositionView = "net" | "physical" | "financial";

interface PositionRow {
  contract: BoardContract;
  cells: Record<string, PositionCell>;
}

export interface BookProps {
  contracts: readonly BoardContract[];
  position: Record<string, Record<string, PositionCell>> | null;
  pnl: DealPnlDTO | null;
  hubs?: readonly string[];
  t: Translate;
  compact?: boolean;
  /** Why the position could not be read (a permission, a failed read). */
  positionEmpty?: string | null;
}

/** Today's P&L per currency (desk estimate) and the position on the board's rows. */
export function Book({ contracts, position, pnl, hubs = HUBS, t, compact = false, positionEmpty = null }: BookProps) {
  const [view, setView] = useState<PositionView>("net");
  const rows = useMemo<PositionRow[]>(() => contracts.map((contract) => ({ contract, cells: position?.[contract.key] ?? {} })), [contracts, position]);
  const columns = useMemo<DataGridColumn<PositionRow>[]>(
    () => [
      { id: "contract", header: t("board.contract"), rowHeader: true, value: (row) => row.contract.label },
      ...hubs.map<DataGridColumn<PositionRow>>((hub) => ({
        id: hub,
        header: hub,
        unit: hubPositionUnit(hub),
        type: "number",
        keepWhenEmpty: true,
        value: (row) => row.cells[hub]?.[view] ?? null,
        render: (row) => {
          const cell = row.cells[hub];
          if (!cell || cell.prompt) return <span className="trader-muted">–</span>;
          return formatMeasure("volume", cell[view], { signed: true });
        },
        flash: true,
        cellTitle: (row) => {
          const cell = row.cells[hub];
          if (!cell) return undefined;
          if (cell.prompt) return t("board.book.prompt_title");
          return t("board.book.cell_title", {
            physical: formatMeasure("volume", cell.physical, { signed: true }),
            financial: formatMeasure("volume", cell.financial, { signed: true }),
            net: formatMeasure("volume", cell.net, { signed: true }),
            unit: cell.unit,
          });
        },
      })),
    ],
    [hubs, t, view],
  );
  const totals = pnl?.totals ?? [];
  return (
    <>
      <div className="trader-book-top">
      <div className="trader-pnl" data-trader-pnl="">
        {totals.length === 0 ? (
          <EmptyState compact reason={pnl ? t("board.book.no_pnl") : t("board.book.pnl_loading")} />
        ) : (
          totals.map((total) => {
            const value = Number(total.day);
            return (
              <KeyFigure
                key={total.currency}
                label={t("board.book.day_pnl", { currency: total.currency })}
                value={formatMeasure("pnl", Number.isFinite(value) ? value : null)}
                unit={total.currency}
                size="lg"
                valueClassName={pnlClass(value)}
                marker={pnl?.simulated_marks ? <SimMark t={t} /> : undefined}
                title={pnl?.method}
                live={{ watch: Number.isFinite(value) ? value : null, identity: `pnl|${total.currency}` }}
              />
            );
          })
        )}
      </div>
      <div className="trader-book-tools">
        <Segmented
          label={t("board.book.view")}
          value={view}
          onChange={setView}
          options={[
            { value: "net", label: t("board.book.net") },
            { value: "physical", label: t("board.book.physical") },
            { value: "financial", label: t("board.book.financial") },
          ]}
        />
      </div>
      </div>
      {positionEmpty ? (
        <EmptyState compact reason={positionEmpty} />
      ) : (
        <DataGrid
          id="trader-position"
          label={t("board.book.position")}
          columns={columns}
          rows={rows}
          rowKey={(row) => row.contract.key}
          density={compact ? "compact" : "regular"}
          phoneLayout="scroll"
          loading={position === null}
          rowAttributes={(row) => ({ "data-record": "position-contract", "data-record-id": row.contract.key })}
        />
      )}
      <div className="trader-order-row">
        <span className="trader-muted">{t("board.order.note")}</span>
        <Button size="sm" disabled title={t("board.order.note")}>
          {t("board.order.prepare")}
        </Button>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ fundamentals */

export interface FundamentalLine {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  /** A second figure (a day change, a share), already formatted. */
  detail?: string | null;
  asOf: string | null;
  source: string | null;
  simulated: boolean;
  /** Why there is no figure, one line. */
  empty?: string | null;
  measure?: "volume" | "percent" | "percent_change" | "temperature";
  /** What the detail panel shows for the line (storage band, last 30 days), when it has one. */
  select?: BoardSelection;
}

export interface FundamentalSection {
  key: string;
  title: string;
  lines: FundamentalLine[];
}

function FundamentalTable({ section, t, onSelect, selected }: { section: FundamentalSection; t: Translate; onSelect?: (selection: BoardSelection) => void; selected?: string | null }) {
  const selectable = Boolean(onSelect) && section.lines.some((line) => line.select);
  const columns = useMemo<DataGridColumn<FundamentalLine>[]>(
    () => [
      { id: "label", header: section.title, rowHeader: true, value: (line) => line.label },
      {
        id: "value",
        header: t("board.fund.value"),
        type: "number",
        keepWhenEmpty: true,
        value: (line) => line.value,
        render: (line) =>
          line.value === null ? (
            <span className="trader-muted" title={line.empty ?? undefined}>{line.empty ? t("board.fund.not_held") : "–"}</span>
          ) : (
            <>
              {formatMeasure(line.measure ?? "volume", line.value, { unit: line.measure === "percent" || line.measure === "temperature" ? undefined : line.unit, decimals: line.measure === "volume" ? (Math.abs(line.value) < 100 ? 1 : 0) : undefined, signed: line.measure === "temperature" || line.measure === "percent_change" ? true : undefined })}
              {line.simulated ? <SimMark t={t} /> : null}
            </>
          ),
        cellTitle: (line) =>
          line.value === null
            ? line.empty ?? undefined
            : t("board.fund.title", { day: line.asOf ?? "–", source: line.source ? sourceSystemLabel(line.source) : t("board.fund.source_unknown") }),
      },
      { id: "detail", header: "", type: "number", keepWhenEmpty: true, value: (line) => line.detail ?? null, render: (line) => <span className="trader-muted">{line.detail ?? ""}</span> },
    ],
    [section.title, t],
  );
  return (
    <DataGrid
      id={`trader-fund-${section.key}`}
      label={section.title}
      columns={columns}
      rows={section.lines}
      rowKey={(line) => line.key}
      density="compact"
      phoneLayout="scroll"
      rowAttributes={(line) => ({ "data-fundamental": line.key, "data-select": line.select ? selectionKey(line.select) : undefined })}
      onRowAction={selectable ? (line) => (line.select ? onSelect!(line.select) : undefined) : undefined}
      selectedKey={selectable ? section.lines.find((line) => line.select && selectionKey(line.select) === selected)?.key ?? null : undefined}
    />
  );
}

export function Fundamentals({ sections, t, note, onSelect, selected }: { sections: readonly FundamentalSection[]; t: Translate; note?: string | null; onSelect?: (selection: BoardSelection) => void; selected?: string | null }) {
  return (
    <div className="trader-fundamentals">
      {sections.map((section) => (
        <FundamentalTable key={section.key} section={section} t={t} onSelect={onSelect} selected={selected} />
      ))}
      {note ? <Foot>{note}</Foot> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ what just happened */

/** "12 min", "3 h", "2 d": how old an event is, beside its time. */
export function ageWords(at: string, nowMs: number, t: Translate): string {
  const ahead = Math.round((Date.parse(at) - nowMs) / 60_000);
  // A calendar line falls due later: say how far ahead ("in 3 d"), not "0 min ago".
  if (Number.isFinite(ahead) && ahead >= 60) {
    return ahead < 48 * 60 ? t("calendar.due.in_h", { count: Math.round(ahead / 60) }) : t("calendar.due.in_d", { count: Math.round(ahead / 1440) });
  }
  const minutes = Math.max(0, Math.round((nowMs - Date.parse(at)) / 60_000));
  if (!Number.isFinite(minutes)) return "";
  if (minutes < 60) return t("board.events.age_min", { count: minutes });
  if (minutes < 48 * 60) return t("board.events.age_h", { count: Math.round(minutes / 60) });
  return t("board.events.age_d", { count: Math.round(minutes / 1440) });
}

export interface EventsProps {
  events: readonly BoardEvent[];
  nowMs: number;
  t: Translate;
  /** The licensed headline services the registry names: shown as an empty slot. */
  licensed: { publishers: string } | null;
  onSelect?: (selection: BoardSelection) => void;
  selected?: string | null;
}

/** Newest first: time and age, what, the hubs it bears on, the book mark; source on hover. */
export function Events({ events, nowMs, t, licensed, onSelect, selected = null }: EventsProps) {
  const columns = useMemo<DataGridColumn<BoardEvent>[]>(
    () => [
      {
        id: "at",
        header: t("board.events.time"),
        value: (event) => event.at,
        render: (event) => (
          <span className="trader-event-time">
            <Instant value={event.at} date="auto" />
            <span className="trader-muted">{ageWords(event.at, nowMs, t)}</span>
          </span>
        ),
      },
      {
        id: "what",
        header: t("board.events.what"),
        rowHeader: true,
        value: (event) => event.what,
        render: (event) => (
          <span className="trader-event-what">
            <span className="trader-event-kind" data-kind={event.kind}>{t(`board.events.kind.${event.kind}`)}</span>
            {", "}
            {event.what}
            {event.size ? `, ${formatMeasure("volume", event.size.value, { unit: event.size.unit, decimals: Math.abs(event.size.value) < 100 ? 1 : 0 })}` : ""}
            {event.until ? <> {t("board.events.until")} <Instant value={event.until} date="always" /></> : null}
            {event.simulated ? <SimMark t={t} /> : null}
          </span>
        ),
        cellTitle: (event) => t("board.events.source", { source: sourceSystemLabel(event.source) }),
      },
      {
        id: "hubs",
        header: t("board.events.hubs"),
        value: (event) => event.hubs.join(" "),
        render: (event) => (
          <span className="trader-event-hubs">
            {event.hubs.join(" · ") || <span className="trader-muted">–</span>}
            {event.touchesBook ? <StatusBadge tone="info" className="trader-event-book">{t("board.events.your_book")}</StatusBadge> : null}
          </span>
        ),
      },
    ],
    [nowMs, t],
  );
  const selectable = Boolean(onSelect);
  return (
    <div className="trader-events" data-trader-events="">
      <DataGrid
        id="trader-events"
        label={t("board.events.title")}
        columns={columns}
        rows={events}
        rowKey={(event) => event.key}
        density="compact"
        phoneLayout="scroll"
        empty={t("board.events.empty")}
        rowAttributes={(event) => ({
          "data-event": event.kind,
          "data-event-key": event.key,
          "data-alert": isAlertEvent(event, nowMs) ? "true" : undefined,
          "data-touches-book": event.touchesBook ? "true" : undefined,
        })}
        rowClassName={(event) => (isAlertEvent(event, nowMs) ? "trader-event-new" : undefined)}
        onRowAction={selectable ? (event) => (event.select ? onSelect!(event.select) : undefined) : undefined}
        selectedKey={selectable ? events.find((event) => event.select && `${event.key}` === selected)?.key ?? null : undefined}
      />
      <p className="trader-foot" data-licensed-slot={licensed ? "empty" : undefined}>
        {licensed ? t("board.events.licensed_slot", { publishers: licensed.publishers }) : t("board.events.licensed_none")}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ fundamentals reads */

const STORAGE_COUNTRIES: readonly { code: string; label: string; gb?: boolean }[] = [
  { code: "GB", label: "GB", gb: true },
  { code: "NL", label: "NL" },
  { code: "DE", label: "DE" },
  { code: "BE", label: "BE" },
  { code: "ES", label: "ES" },
];

const LNG_COUNTRIES: readonly { code: string; gb?: boolean }[] = [
  { code: "GB", gb: true },
  { code: "NL" },
  { code: "BE" },
  { code: "FR" },
  { code: "DE" },
  { code: "ES" },
];

/** Interconnector and pipeline points by the name the flow read gives them. */
export const FLOW_POINTS: readonly { key: string; pattern: RegExp; gb: boolean }[] = [
  { key: "iuk", pattern: /\biuk\b|interconnector\s*uk/i, gb: true },
  { key: "bbl", pattern: /\bbbl\b|balgzand/i, gb: true },
  { key: "fr_es", pattern: /pirineos|irun|biriatou|larrau/i, gb: false },
  { key: "dz_es", pattern: /medgaz|almer[ií]a|tarifa|maghreb/i, gb: false },
];

interface FundamentalsInputs {
  storage?: { countries: StorageEntityDTO[]; region: StorageEntityDTO | null; missing: { code: string; reason: string }[] } | null;
  flows?: { totals: { code: string; flow_day_gwh_d: number | null; as_of: string; simulated: boolean }[] } | null;
  lng?: { countries: { code: string; send_out_day_gwh_d: number | null; as_of: string; sources: string[]; simulated: boolean }[]; missing: { code: string; reason: string }[] } | null;
  points?: FlowObsDTO[] | null;
  outages?: OutageEventDTO[] | null;
  balance?: { as_of: string | null; simulated: boolean; daily: { demand_gwh_d: number; demand_normal_gwh_d: number | null; hdd_change: number }[] } | null;
  gcv?: number | null;
}

/** The fundamentals panel's lines from the existing reads, GB in mcm/d and the continent in GWh/d. */
export function fundamentalSections(input: FundamentalsInputs, t: Translate): FundamentalSection[] {
  const gcv = input.gcv ?? null;
  const gbUnit = gcv ? "mcm/d" : "GWh/d";
  const gb = (gwh: number | null) => (gwh === null ? null : gcv ? gwhToMcm(gwh, gcv) : gwh);
  const storage: FundamentalLine[] = STORAGE_COUNTRIES.map(({ code, label, gb: isGb }) => {
    const row = input.storage?.countries.find((item) => item.code === code) ?? null;
    const missing = input.storage?.missing.find((item) => item.code === code);
    const netGwh = row && row.injection_twh_d !== null && row.withdrawal_twh_d !== null ? (row.injection_twh_d - row.withdrawal_twh_d) * 1000 : null;
    return {
      key: `storage-${code}`,
      label,
      value: row?.fill_pct ?? null,
      unit: "%",
      measure: "percent",
      detail: netGwh === null ? null : `${formatMeasure("volume", isGb ? gb(netGwh) : netGwh, { signed: true, decimals: 0 })} ${isGb ? gbUnit : "GWh/d"}`,
      asOf: row?.as_of ?? null,
      source: row?.sources?.[0] ?? null,
      simulated: Boolean(row?.simulated),
      empty: row ? null : missing?.reason ?? t("board.fund.storage_missing"),
      select: { kind: "storage", code },
    };
  });
  const region = input.storage?.region ?? null;
  storage.push({
    key: "storage-EU",
    label: t("board.fund.eu_total"),
    value: region?.fill_pct ?? null,
    unit: "%",
    measure: "percent",
    detail: region?.day_change_pts != null ? `${formatMeasure("percent_change", region.day_change_pts, { unit: "pts" })}` : null,
    asOf: region?.as_of ?? null,
    source: region?.sources?.[0] ?? null,
    simulated: Boolean(region?.simulated),
    empty: region ? null : t("board.fund.storage_missing"),
    select: { kind: "storage", code: "EU" },
  });
  const total = (code: string) => input.flows?.totals.find((item) => item.code === code) ?? null;
  const norwayGb = total("uk_terminal");
  const norwayEu = total("norway");
  const point = (key: string) => {
    const spec = FLOW_POINTS.find((item) => item.key === key)!;
    const rows = (input.points ?? []).filter((row) => spec.pattern.test(row.point_name));
    const latest = rows.sort((a, b) => b.period_start_utc.localeCompare(a.period_start_utc))[0] ?? null;
    return { spec, latest };
  };
  const pointLine = (key: string): FundamentalLine => {
    const { spec, latest } = point(key);
    const mcm = latest?.flow_mcm_d ?? null;
    return {
      key,
      label: t(`board.fund.flow.${key}`) + (latest?.direction ? ` · ${latest.direction}` : ""),
      value: mcm === null ? null : spec.gb ? mcm : gcv ? mcmToGwh(mcm, gcv) : mcm,
      unit: spec.gb || !gcv ? "mcm/d" : "GWh/d",
      asOf: latest?.period_start_utc?.slice(0, 10) ?? null,
      source: latest?.source_system ?? null,
      simulated: /_sim$/i.test(latest?.source_system ?? ""),
      empty: latest ? null : t("board.fund.flow_missing"),
      select: { kind: "flow", key },
    };
  };
  const supply: FundamentalLine[] = [
    {
      key: "norway_gb",
      label: t("board.fund.flow.norway_gb"),
      value: gb(norwayGb?.flow_day_gwh_d ?? null),
      unit: gbUnit,
      asOf: norwayGb?.as_of ?? null,
      source: norwayGb ? "ENTSOG" : null,
      simulated: Boolean(norwayGb?.simulated),
      empty: norwayGb ? null : t("board.fund.flow_missing"),
      select: { kind: "flow", key: "norway_gb" },
    },
    {
      key: "norway_eu",
      label: t("board.fund.flow.norway_eu"),
      value: norwayEu?.flow_day_gwh_d ?? null,
      unit: "GWh/d",
      asOf: norwayEu?.as_of ?? null,
      source: norwayEu ? "ENTSOG" : null,
      simulated: Boolean(norwayEu?.simulated),
      empty: norwayEu ? null : t("board.fund.flow_missing"),
      select: { kind: "flow", key: "norway_eu" },
    },
    pointLine("iuk"),
    pointLine("bbl"),
    pointLine("fr_es"),
    pointLine("dz_es"),
  ];
  const lng: FundamentalLine[] = LNG_COUNTRIES.map(({ code, gb: isGb }) => {
    const row = input.lng?.countries.find((item) => item.code === code) ?? null;
    const missing = input.lng?.missing.find((item) => item.code === code);
    const gwh = row?.send_out_day_gwh_d ?? null;
    return {
      key: `lng-${code}`,
      label: t("board.fund.lng_country", { country: code }),
      value: isGb ? gb(gwh) : gwh,
      unit: isGb ? gbUnit : "GWh/d",
      asOf: row?.as_of ?? null,
      source: row?.sources?.[0] ?? null,
      simulated: Boolean(row?.simulated),
      empty: row ? null : missing?.reason ?? t("board.fund.lng_missing"),
      select: { kind: "flow", key: `lng-${code}` },
    };
  });
  const outages: FundamentalLine[] = (input.outages ?? [])
    .filter((item) => item.status?.toLowerCase() !== "ended")
    .sort((a, b) => (b.unavailable_gwh_d ?? 0) - (a.unavailable_gwh_d ?? 0))
    .slice(0, 4)
    .map((item) => {
      const isGb = item.balancing_zone?.toUpperCase() === "NBP" || item.balancing_zone?.toUpperCase() === "GB";
      const value = isGb ? item.capacity_impact_mcm_d ?? gb(item.unavailable_gwh_d ?? null) : item.unavailable_gwh_d ?? null;
      return {
        key: `outage-${item.event_id}`,
        label: `${item.facility_name}`,
        value: value === null ? null : -Math.abs(value),
        unit: isGb ? (item.capacity_impact_mcm_d != null || gcv ? "mcm/d" : "GWh/d") : "GWh/d",
        detail: t(`board.fund.outage.${item.event_type?.toLowerCase() === "planned" ? "planned" : "unplanned"}`),
        asOf: item.published_at_utc?.slice(0, 10) ?? item.start_utc?.slice(0, 10) ?? null,
        source: item.source_system ?? "REMIT",
        simulated: Boolean(item.simulated),
        empty: value === null ? t("board.fund.outage_no_size") : null,
      };
    });
  if (outages.length === 0) {
    outages.push({ key: "outage-none", label: t("board.fund.outage_none"), value: null, unit: "", asOf: null, source: null, simulated: false, empty: t("board.fund.outage_none_long") });
  }
  const day = input.balance?.daily?.[0] ?? null;
  const demandPct = day && day.demand_normal_gwh_d ? ((day.demand_gwh_d - day.demand_normal_gwh_d) / day.demand_normal_gwh_d) * 100 : null;
  const weather: FundamentalLine[] = [
    {
      key: "weather-nwe-temp",
      label: t("board.fund.weather.nwe_temp"),
      value: day ? -day.hdd_change : null,
      unit: "°C",
      measure: "temperature",
      asOf: input.balance?.as_of ?? null,
      source: "Eurostat",
      simulated: Boolean(input.balance?.simulated),
      empty: day ? null : t("board.fund.weather_missing"),
    },
    {
      key: "weather-nwe-demand",
      label: t("board.fund.weather.nwe_demand"),
      value: demandPct,
      unit: "%",
      measure: "percent_change",
      asOf: input.balance?.as_of ?? null,
      source: "ENTSOG",
      simulated: Boolean(input.balance?.simulated),
      empty: demandPct === null ? t("board.fund.weather_missing") : null,
    },
    { key: "weather-gb", label: t("board.fund.weather.gb"), value: null, unit: "", asOf: null, source: null, simulated: false, empty: t("board.fund.weather_region_missing") },
    { key: "weather-iberia", label: t("board.fund.weather.iberia"), value: null, unit: "", asOf: null, source: null, simulated: false, empty: t("board.fund.weather_region_missing") },
  ];
  return [
    { key: "storage", title: t("board.fund.storage"), lines: storage },
    { key: "supply", title: t("board.fund.supply"), lines: supply },
    { key: "lng", title: t("board.fund.lng"), lines: lng },
    { key: "outages", title: t("board.fund.outages"), lines: outages },
    { key: "weather", title: t("board.fund.weather"), lines: weather },
  ];
}

/* ------------------------------------------------------------------ the screen */

/** Fill the viewport below the screen's top edge, so the page itself never scrolls. */
function useFitHeight(enabled: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || !enabled) {
      element?.style.removeProperty("height");
      return;
    }
    // The screen ends at the window's bottom (the page's bottom padding is taken off on this task,
    // trader-screen.css), so its height is one subtraction; a value is written only when it
    // changes, so the observers below settle instead of refitting each other's refit.
    const fit = () => {
      const top = element.getBoundingClientRect().top + window.scrollY;
      const height = Math.max(Math.floor(window.innerHeight - top), 0);
      if (element.style.height !== `${height}px`) element.style.height = `${height}px`;
      // Anything still below the screen (a padding another stylesheet adds) is taken off once.
      const over = document.documentElement.scrollHeight - window.innerHeight;
      if (over > 0) element.style.height = `${Math.max(height - over, 0)}px`;
    };
    // Anything that moves the screen's top edge (a notice under the top bar that appears after
    // the first read, the strip, a font that arrives late) or adds height below it refits it,
    // once per frame: the page itself must never scroll (CI saw 1084 > 1080 on a slow runner).
    let frame = 0;
    const schedule = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        fit();
      });
    };
    fit();
    window.addEventListener("resize", schedule);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(schedule);
    // The body may be a fixed-height box that never resizes, so watch the screen's own ancestors
    // (the main area grows when anything above the screen grows) and whatever sits above it.
    for (let node: HTMLElement | null = element.parentElement; node; node = node.parentElement) {
      observer?.observe(node);
      for (let sibling = node.firstElementChild; sibling; sibling = sibling.nextElementSibling) {
        if (sibling !== element && !sibling.contains(element)) observer?.observe(sibling);
      }
    }
    const mutations = typeof MutationObserver === "undefined" ? null : new MutationObserver(schedule);
    mutations?.observe(document.body, { childList: true, subtree: true });
    void document.fonts?.ready.then(schedule);
    return () => {
      window.removeEventListener("resize", schedule);
      observer?.disconnect();
      mutations?.disconnect();
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [enabled]);
  return ref;
}

/** Whether the screen is wide enough for the detail panel beside the fundamentals (1600 px). */
function useWide(): boolean {
  const query = "(min-width: 1600px)";
  const [wide, setWide] = useState(() => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(query).matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const media = window.matchMedia(query);
    const onChange = () => setWide(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return wide;
}

const FLOW_PATTERNS: Readonly<Record<string, RegExp>> = Object.fromEntries(FLOW_POINTS.map((item) => [item.key, item.pattern]));

export interface TraderScreenProps {
  quotes: readonly MarketQuoteDTO[];
  /** The store's normalised observations (today's curve per hub). */
  markets?: readonly NormalizedMarketObsDTO[];
  /** The quotes have not been read yet: the board shows its loading rows, not "no source". */
  quotesLoading?: boolean;
  nowMs: number;
  t: Translate;
  /** Whether the reader may read the book (`portfolio.read`); the Book panel says so otherwise. */
  canSeeBook: boolean;
  /** Compact rows (the person's density, or a short screen). */
  compact?: boolean;
}

export function TraderScreen({ quotes, markets = [], quotesLoading = false, nowMs, t, canSeeBook, compact: compactPreference = false }: TraderScreenProps) {
  // The detail panel follows the last choice; it is kept while the reads refresh (state, not data).
  const [selection, setSelection] = useState<BoardSelection>(DEFAULT_SELECTION);
  const chosen = selectionKey(selection);
  const wide = useWide();
  const [side, setSide] = useState<"fundamentals" | "events" | "calendar" | "detail">("fundamentals");
  const [lower, setLower] = useState<"fundamentals" | "events" | "calendar">("fundamentals");
  const select = (next: BoardSelection) => {
    setSelection(next);
    // Below 1600 px the chart and the fundamentals share one place: a choice shows the chart.
    if (next.kind === "price" || next.kind === "curve" || next.kind === "spread") setSide("detail");
  };
  const phone = useCompactWidth();
  const [short, setShort] = useState(() => typeof window !== "undefined" && window.innerHeight < 1000);
  useEffect(() => {
    const onResize = () => setShort(window.innerHeight < 1000);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  const compact = compactPreference || short;
  const gasDay = gasDayOf(nowMs);
  const contracts = useMemo(() => boardContracts(gasDay), [gasDay]);
  const cells = useMemo(() => buildBoard(quotes, contracts, HUBS, nowMs), [quotes, contracts, nowMs]);
  const format = useInstantFormatter();
  const formatTime = useMemo(() => (iso: string | null) => (iso ? format(iso, { date: "auto" })?.text ?? iso : "–"), [format]);

  const pairs = pairsParam();
  const spreads = useCachedRead<SpreadBoardDTO>(readKey("/research/spreads/board", { hubs: HUBS.join(","), pairs }), (signal) => api.spreadsBoard(HUBS, { signal }, pairs).then((r) => r.data));
  const ladder = useCachedRead(canSeeBook ? readKey("/portfolio/position-ladder", { months: 15 }) : null, (signal) => api.positionLadder(15, { signal }).then((r) => r.data));
  const pnl = useCachedRead(canSeeBook ? readKey("/desk/deals/pnl", { day: gasDay }) : null, (signal) => api.dealPnl(gasDay, { signal }).then((r) => r.data));
  const storage = useCachedRead(readKey("/fundamentals/storage", { region: "eu", focus: "GB,NL,DE,BE,ES" }), (signal) => api.fundamentalsStorage({ region: "eu", focus: ["GB", "NL", "DE", "BE", "ES"] }, { signal }).then((r) => r.data));
  const flows = useCachedRead(readKey("/fundamentals/flows"), (signal) => api.fundamentalsFlows([], { signal }).then((r) => r.data));
  const lng = useCachedRead(readKey("/fundamentals/lng"), (signal) => api.fundamentalsLng([], { signal }).then((r) => r.data));
  const points = useCachedRead(readKey("/physical/flows"), (signal) => api.flowObservations({ signal }).then((r) => r.data));
  const outages = useCachedRead(readKey("/physical/outages", { horizon_days: 14, grouped: true }), (signal) => api.outages(14, { signal }, { grouped: true }).then((r) => r.data));
  const balance = useCachedRead(readKey("/fundamentals/forward-balance", { summary: true }), (signal) => api.fundamentalsForwardBalance({ summary: true }, { signal }).then((r) => r.data));
  const news = useCachedRead(readKey("/news", { order: "time", limit: 30 }), (signal) => api.news({ order: "time", limit: 30 }, { signal }).then((r) => ({ items: r.data, sources: r.meta?.sources ?? [] })));
  // Package G: holidays, auction windows and reminders from where they are published.
  const calendar = useCachedRead(readKey("/publications/calendar", { days: 60 }), (signal) => api.publicationCalendar(60, { signal }).then((r) => r.data.items));
  const ontology = useCachedRead(readKey("/analysis/ontology"), (signal) => api.ontology({ signal }).then((r) => r.data));

  const spreadRows = useMemo(() => hubSpreadRows(spreads.data), [spreads.data]);
  const time = useMemo(() => timeSpreads(spreads.data, cells, HUBS), [spreads.data, cells]);
  const position = useMemo(() => (ladder.data ? positionOnBoard(ladder.data.rows, contracts, HUBS) : null), [ladder.data, contracts]);
  const gcv = ontology.data?.units?.volume_to_energy?.gcv_kwh_per_m3 ?? null;
  const sections = useMemo(
    () =>
      fundamentalSections(
        {
          storage: storage.data,
          flows: flows.data,
          lng: lng.data,
          points: points.data,
          outages: outages.data,
          balance: balance.data,
          gcv,
        },
        t,
      ),
    [storage.data, flows.data, lng.data, points.data, outages.data, balance.data, gcv, t],
  );
  const fundNote = gcv
    ? t("board.fund.units_note", { gcv: formatMeasure("unit_value", gcv), conditions: ontology.data?.units?.volume_to_energy?.reference_conditions ?? "" })
    : t("board.fund.units_note_no_gcv");

  // One rule for the simulated mark (SimulatedScope): every price simulated → one source line.
  const flags = boardSimulation(cells);
  const scope = simulatedScopeOf(flags);
  const priced = flags.length;
  const staleCount = Object.values(cells).flatMap((row) => Object.values(row)).filter((cell) => cell.status === "priced" && cell.stale).length;
  const newest = Object.values(cells)
    .flatMap((row) => Object.values(row))
    .map((cell) => cell.observedAt)
    .filter((value): value is string => Boolean(value))
    .sort()
    .pop() ?? null;
  const fitRef = useFitHeight(!phone);
  const positionEmpty = !canSeeBook ? t("board.book.no_permission") : ladder.error && !ladder.data ? t("board.book.position_failed") : null;

  const bookHubs = useMemo(() => new Set((ladder.data?.rows ?? []).filter((row) => Math.abs(row.net_mwh) > 0).map((row) => row.hub.toUpperCase())), [ladder.data]);
  const calendarLines = useMemo(() => calendarEvents(calendar.data ?? [], bookHubs, nowMs, t), [calendar.data, bookHubs, nowMs, t]);
  const events = useMemo(() => boardEvents(outages.data ?? [], news.data?.items ?? [], bookHubs, calendarLines), [outages.data, news.data, bookHubs, calendarLines]);
  const newCount = events.filter((event) => isAlertEvent(event, nowMs)).length;
  const eventsLabel = newCount > 0 ? t("board.events.tab_new", { count: newCount }) : t("board.events.title");
  const sideSwitch = (
    <Segmented
      label={t("board.side.label")}
      value={side}
      onChange={setSide}
      options={[
        { value: "fundamentals", label: t("board.fund.title_panel") },
        { value: "events", label: eventsLabel },
        { value: "calendar", label: t("calendar.title") },
        { value: "detail", label: t("board.detail.title") },
      ]}
    />
  );
  const lowerSwitch = (
    <Segmented
      label={t("board.side.label")}
      value={lower}
      onChange={setLower}
      options={[
        { value: "fundamentals", label: t("board.fund.title_panel") },
        { value: "events", label: eventsLabel },
        { value: "calendar", label: t("calendar.title") },
      ]}
    />
  );
  const lowerView = wide ? lower : side === "events" || side === "calendar" ? side : "fundamentals";
  const spreadScope = simulatedScopeOf(
    spreadRows.flatMap((row) => [row.da, row.ma]).filter((figure): figure is SpreadFigure => Boolean(figure?.available)).map((figure) => figure.simulated),
  );
  const fundScope = simulatedScopeOf(sections.flatMap((section) => section.lines).filter((line) => line.value !== null).map((line) => line.simulated));

  return (
    <>
      <div ref={fitRef} className="trader-screen" data-trader-screen="" data-density={compact ? "compact" : undefined} data-layout={wide ? "wide" : "narrow"}>
        <section className="trader-panel trader-area-board" aria-labelledby="trader-board-title" data-trader-panel="board">
          <header className="trader-panel-head">
            <h2 id="trader-board-title">{t("board.prices_title")}</h2>
            <span className="trader-meta">{newest ? t("board.as_of", { time: formatTime(newest) }) : quotesLoading ? "" : t("board.no_prices")}</span>
            {staleCount > 0 ? <span className="trader-degraded" data-stale-count={staleCount}>{t("board.stale_count", { count: staleCount })}</span> : null}
          </header>
          <div className="trader-panel-body">
            <SimulatedScope scope={scope} notice={t("board.all_simulated")}>
              <PriceBoard contracts={contracts} cells={cells} t={t} formatTime={formatTime} compact={compact} onSelect={select} selected={chosen} loading={quotesLoading} />
            </SimulatedScope>
          </div>
          <Foot>
            {priced === 0 ? t("board.foot_no_entitlement") : t("board.foot")}
          </Foot>
        </section>

        <section className="trader-panel trader-area-spreads" aria-labelledby="trader-spreads-title" data-trader-panel="spreads">
          <header className="trader-panel-head">
            <h2 id="trader-spreads-title">{t("board.spreads_title")}</h2>
            <span className="trader-meta">{spreads.data ? t("board.spreads_meta", { day: spreads.data.as_of }) : ""}</span>
          </header>
          <div className="trader-panel-body">
            {spreads.loading && !spreads.data ? (
              <EmptyState compact reason={t("board.loading")} />
            ) : spreads.error && !spreads.data ? (
              <EmptyState compact reason={t("board.spread.failed")} />
            ) : (
              <SimulatedScope scope={spreadScope} notice={t("board.all_simulated")}>
                <Spreads rows={spreadRows} time={time} t={t} compact={compact} onSelect={select} selected={chosen} />
              </SimulatedScope>
            )}
          </div>
        </section>

        <section className="trader-panel trader-area-book" aria-labelledby="trader-book-title" data-trader-panel="book">
          <header className="trader-panel-head">
            <h2 id="trader-book-title">{t("board.book.title")}</h2>
            <StatusBadge tone="info">{t("board.book.estimate")}</StatusBadge>
            <span className="trader-meta">{t("board.book.units")}</span>
          </header>
          <div className="trader-panel-body">
            <Book contracts={contracts} position={canSeeBook ? position : null} pnl={pnl.data ?? null} t={t} compact={compact} positionEmpty={positionEmpty} />
          </div>
        </section>

        {(wide || side === "detail") && (
          <section className="trader-panel trader-area-detail" aria-labelledby="trader-detail-title" data-trader-panel="detail">
            <header className="trader-panel-head">
              <h2 id="trader-detail-title">{t("board.detail.title")}</h2>
              {!wide ? sideSwitch : <span className="trader-meta">{t("board.detail.hint")}</span>}
            </header>
            <div className="trader-panel-body">
              <TraderDetail
                selection={selection}
                contracts={contracts}
                quotes={quotes}
                markets={markets}
                spreads={spreads.data}
                flows={flows.data}
                lng={lng.data}
                points={points.data}
                gasDay={gasDay}
                nowMs={nowMs}
                t={t}
                height={wide ? (compact ? 200 : 250) : 220}
                patterns={FLOW_PATTERNS}
              />
            </div>
          </section>
        )}

        {(wide || side !== "detail") && (
        <section className="trader-panel trader-area-fund" aria-labelledby="trader-fund-title" data-trader-panel={lowerView}>
          <header className="trader-panel-head">
            <h2 id="trader-fund-title" className="ds-visually-hidden">{lowerView === "events" ? t("board.events.title") : lowerView === "calendar" ? t("calendar.title") : t("board.fund.title_panel")}</h2>
            {wide ? lowerSwitch : sideSwitch}
            <span className="trader-meta">{lowerView === "events" ? t("board.events.meta") : lowerView === "calendar" ? t("calendar.meta") : t("board.fund.meta")}</span>
          </header>
          <div className="trader-panel-body">
            {lowerView === "events" ? (
              <Events events={events} nowMs={nowMs} t={t} licensed={licensedSlot(news.data?.sources)} onSelect={select} selected={null} />
            ) : lowerView === "calendar" ? (
              <PublicationCalendar items={calendar.data ?? null} nowMs={nowMs} t={t} loading={calendar.loading} failed={Boolean(calendar.error)} formatTime={formatTime} />
            ) : (
              <SimulatedScope scope={fundScope} notice={t("board.fund.all_simulated")}>
                <Fundamentals sections={sections} t={t} note={fundNote} onSelect={select} selected={chosen} />
              </SimulatedScope>
            )}
          </div>
        </section>
        )}
      </div>
    </>
  );
}
