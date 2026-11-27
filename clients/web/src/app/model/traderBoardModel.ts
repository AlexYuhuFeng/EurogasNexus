/**
 * Desk → Board (SMALL_DESK_PLAN step 4, section 9): the one screen the desk keeps open beside
 * its trading screen. This module is the pure part, tested in tests/traderBoard.test.ts:
 *
 * - **Contracts down, hubs across.** The rows are the owner's: within-day, day-ahead, weekend,
 *   balance of month, three months, two quarters, two seasons, next calendar year, named as the
 *   execution screen names them (WD, DA, WE, BOM, Dec-26, Q1-27, Sum-27, Cal-27).
 * - **A board cell** is the latest quote this desk holds for that hub and contract: bid and
 *   offer always, last and change on the day (mid against the previous close), each in the
 *   hub's own quotation (NBP in pence per therm, the others in EUR/MWh). Nothing is converted
 *   here that the stored quote did not already state: NBP's stored GBP/MWh goes to p/th with
 *   the units authority's therm, never through FX. A contract with no quote is "no source",
 *   never a number. Real and simulated quotes never compete: a real quote wins its cell.
 * - **Spreads** come from the server's spread board (`/api/research/spreads/board?pairs=`);
 *   this module applies the owner's transport rule to its figures (the published short-term
 *   capacity price plus the flow charge by default; the flow charge alone where the firm's
 *   bookings cover the route) and puts a spread with an NBP leg in pence per therm at the rate
 *   the server used for that close.
 * - **Position** comes from the position ladder (monthly MWh by hub, physical and financial)
 *   and is shown on the board's rows: th/d at NBP, MW on the continent. The prompt rows (WD,
 *   DA, WE) have no daily position in the ladder yet and say so.
 */
import type { MarketQuoteDTO, PositionLadderRowDTO } from "../../api/client.ts";
import type { BoardTenorDTO, BoardTimeRowDTO, SpreadBoardDTO } from "../../api/spreads.ts";
import { isQuoteStale, quoteMid } from "./boardQuote.ts";
import { netPosition } from "./positionLadderModel.ts";

/** The desk's five hubs in the owner's order. */
export const BOARD_HUBS = ["NBP", "TTF", "ZTP", "THE", "PVB"] as const;
export type BoardHub = (typeof BOARD_HUBS)[number];

/** Therms in one MWh (1 th = 29.3071 kWh, the units authority's therm). */
export const THERMS_PER_MWH = 1000 / 29.3071;
export const KWH_PER_THERM = 29.3071;

/** The hub's quotation: NBP in pence per therm, the continent in EUR per MWh. */
export function hubPriceUnit(hub: string): "p/th" | "EUR/MWh" {
  return hub.toUpperCase() === "NBP" ? "p/th" : "EUR/MWh";
}

/** Decimals a price is shown with in the hub's quotation: NBP's tick is 0.01 p/th. */
export function priceDecimals(hub: string): number {
  return hub.toUpperCase() === "NBP" ? 2 : 3;
}

/** The hub's position unit: therms per day at NBP, MW on the continent. */
export function hubPositionUnit(hub: string): "th/d" | "MW" {
  return hub.toUpperCase() === "NBP" ? "th/d" : "MW";
}

/* ------------------------------------------------------------------ contracts */

export type ContractKind = "wd" | "da" | "we" | "bom" | "month" | "quarter" | "season" | "cal";

export interface BoardContract {
  /** Stable key ("WD", "M1", "Q2", "S1", "CAL1"). */
  key: string;
  /** As the execution screen writes it ("DA", "Jan-27", "Q2-27", "Win-27", "Cal-27"). */
  label: string;
  kind: ContractKind;
  /** First month of delivery (YYYY-MM) and months covered; null for the prompt days. */
  firstMonth: string | null;
  months: number;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function monthKey(year: number, monthIndex: number): string {
  const y = year + Math.floor(monthIndex / 12);
  const m = ((monthIndex % 12) + 12) % 12;
  return `${y}-${String(m + 1).padStart(2, "0")}`;
}

function yy(year: number): string {
  return String(year % 100).padStart(2, "0");
}

/** The gas day a UTC instant falls in (the day starts 05:00 UTC, 06:00 CET). */
export function gasDayOf(nowMs: number): string {
  return new Date(nowMs - 5 * 3_600_000).toISOString().slice(0, 10);
}

/**
 * The board's twelve rows for a gas day: WD, DA, WE, BOM, the next three months, the next two
 * quarters and the next two seasons that have not started, and the next calendar year.
 */
export function boardContracts(gasDay: string): BoardContract[] {
  const year = Number(gasDay.slice(0, 4));
  const month = Number(gasDay.slice(5, 7)) - 1;
  const rows: BoardContract[] = [
    { key: "WD", label: "WD", kind: "wd", firstMonth: null, months: 0 },
    { key: "DA", label: "DA", kind: "da", firstMonth: null, months: 0 },
    { key: "WE", label: "WE", kind: "we", firstMonth: null, months: 0 },
    { key: "BOM", label: "BOM", kind: "bom", firstMonth: monthKey(year, month), months: 1 },
  ];
  for (let ahead = 1; ahead <= 3; ahead += 1) {
    const key = monthKey(year, month + ahead);
    const m = Number(key.slice(5, 7)) - 1;
    rows.push({ key: `M${ahead}`, label: `${MONTHS[m]}-${yy(Number(key.slice(0, 4)))}`, kind: "month", firstMonth: key, months: 1 });
  }
  // The next quarter that has not started.
  let q = Math.floor(month / 3) + 1;
  let qYear = year;
  for (let index = 1; index <= 2; index += 1, q += 1) {
    if (q > 3) {
      q = 0;
      qYear += 1;
    }
    rows.push({ key: `Q${index}`, label: `Q${q + 1}-${yy(qYear)}`, kind: "quarter", firstMonth: monthKey(qYear, q * 3), months: 3 });
  }
  // Seasons: summer Apr-Sep, winter Oct-Mar (named by the year it starts). The next one not started.
  let seasonStart = month >= 3 && month <= 8 ? monthKey(year, 9) : month >= 9 ? monthKey(year + 1, 3) : monthKey(year, 3);
  for (let index = 1; index <= 2; index += 1) {
    const sy = Number(seasonStart.slice(0, 4));
    const sm = Number(seasonStart.slice(5, 7)) - 1;
    rows.push({ key: `S${index}`, label: `${sm === 3 ? "Sum" : "Win"}-${yy(sy)}`, kind: "season", firstMonth: seasonStart, months: 6 });
    seasonStart = monthKey(sy, sm + 6);
  }
  rows.push({ key: "CAL1", label: `Cal-${yy(year + 1)}`, kind: "cal", firstMonth: monthKey(year + 1, 0), months: 12 });
  return rows;
}

/** The months a contract delivers in (YYYY-MM), empty for the prompt days. */
export function contractMonths(contract: BoardContract): string[] {
  if (!contract.firstMonth) return [];
  const year = Number(contract.firstMonth.slice(0, 4));
  const month = Number(contract.firstMonth.slice(5, 7)) - 1;
  return Array.from({ length: contract.months }, (_, index) => monthKey(year, month + index));
}

/* ------------------------------------------------------------------ quotes */

const PROMPT_PRODUCTS: Record<string, ContractKind> = {
  "within-day": "wd",
  wd: "wd",
  "day-ahead": "da",
  da: "da",
  weekend: "we",
  we: "we",
  "balance-of-month": "bom",
  bom: "bom",
};

/** The board row a quote prices, or null when it prices none of them. */
export function contractOfQuote(quote: Pick<MarketQuoteDTO, "product" | "delivery_start_utc" | "delivery_end_utc">, contracts: readonly BoardContract[]): BoardContract | null {
  const product = quote.product.toLowerCase().replace(/[_\s]+/g, "-");
  const prompt = PROMPT_PRODUCTS[product];
  if (prompt) return contracts.find((item) => item.kind === prompt) ?? null;
  if (product === "month-ahead" || product === "ma" || product === "m+1") return contracts.find((item) => item.key === "M1") ?? null;
  // A curve product by its delivery window: the month it starts in and how many months it runs.
  const start = Date.parse(quote.delivery_start_utc);
  const end = Date.parse(quote.delivery_end_utc);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  // The gas day starts at 05:00 or 06:00 UTC, so a window is read twelve hours in.
  const first = new Date(start + 12 * 3_600_000);
  const last = new Date(end - 12 * 3_600_000);
  const firstMonth = monthKey(first.getUTCFullYear(), first.getUTCMonth());
  const months = (last.getUTCFullYear() - first.getUTCFullYear()) * 12 + last.getUTCMonth() - first.getUTCMonth() + 1;
  return contracts.find((item) => item.firstMonth === firstMonth && item.months === months && item.kind !== "bom") ?? null;
}

/** A stored price in the hub's quotation, or null when that needs an FX rate. */
export function inHubUnit(hub: string, value: number | null | undefined, currency: string, unit: string): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  const stored = `${currency}/${unit}`.replace(/\s+/g, "").toUpperCase();
  const plain = unit.replace(/\s+/g, "").toUpperCase();
  if (hubPriceUnit(hub) === "EUR/MWh") return stored === "EUR/MWH" || plain === "EUR/MWH" ? value : null;
  if (/^(GBP\/)?(GBP|P|GBX)\/TH$/.test(stored) || /^(P|GBP|GBX)\/TH$/.test(plain)) return value;
  if (stored === "GBP/MWH" || plain === "GBP/MWH") return (value * 100) / THERMS_PER_MWH;
  return null;
}

export type CellStatus = "priced" | "no_source" | "unit";

export interface BoardCell {
  hub: string;
  contract: string;
  status: CellStatus;
  bid: number | null;
  offer: number | null;
  last: number | null;
  /** Mid against the previous close, in the hub's quotation. */
  change: number | null;
  unit: string;
  simulated: boolean;
  stale: boolean;
  source: string | null;
  observedAt: string | null;
  closeDay: string | null;
  /** The quote's id, for the inspector. */
  quoteId: string | null;
}

function metaNumber(quote: MarketQuoteDTO, key: string): number | null {
  const value = quote.metadata_json?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function better(candidate: MarketQuoteDTO, held: MarketQuoteDTO | undefined, hub = candidate.hub): boolean {
  if (!held) return true;
  // A quote the board can put in the hub's quotation wins over one it cannot (an NBP quote
  // stored in EUR would need an FX rate); then a real quote over a simulated one; then the newer.
  const fits = (quote: MarketQuoteDTO) => inHubUnit(hub, 1, quote.currency, quote.unit) !== null;
  if (fits(held) !== fits(candidate)) return fits(candidate);
  if (held.simulated !== candidate.simulated) return held.simulated;
  return Date.parse(candidate.observed_at_utc) > Date.parse(held.observed_at_utc);
}

/**
 * Every cell of the board: `cells[contractKey][hub]`. `nowMs` ages each quote on this browser's
 * clock against its source's cadence (`stale_after_seconds`), as the Prices board does.
 */
export function buildBoard(
  quotes: readonly MarketQuoteDTO[],
  contracts: readonly BoardContract[],
  hubs: readonly string[],
  nowMs: number,
): Record<string, Record<string, BoardCell>> {
  const wanted = new Set(hubs.map((hub) => hub.toUpperCase()));
  const best = new Map<string, MarketQuoteDTO>();
  const closes = new Map<string, MarketQuoteDTO>();
  for (const quote of quotes) {
    const hub = quote.hub.toUpperCase();
    if (!wanted.has(hub)) continue;
    const contract = contractOfQuote(quote, contracts);
    if (!contract) continue;
    const key = `${contract.key}|${hub}`;
    if (better(quote, best.get(key))) best.set(key, quote);
    // A streamed quote arrives without its close: keep the newest that carries one, per source,
    // so a change on the day never mixes one feed's mid with another's close.
    const closeKey = `${key}|${quote.source_system}`;
    if (quote.close_price != null && better(quote, closes.get(closeKey))) closes.set(closeKey, quote);
  }
  const out: Record<string, Record<string, BoardCell>> = {};
  for (const contract of contracts) {
    const row: Record<string, BoardCell> = {};
    for (const hubCode of hubs) {
      const hub = hubCode.toUpperCase();
      const quote = best.get(`${contract.key}|${hub}`);
      const unit = hubPriceUnit(hub);
      if (!quote) {
        row[hub] = { hub, contract: contract.key, status: "no_source", bid: null, offer: null, last: null, change: null, unit, simulated: false, stale: false, source: null, observedAt: null, closeDay: null, quoteId: null };
        continue;
      }
      const native = (value: number | null | undefined) => inHubUnit(hub, value, quote.currency, quote.unit);
      // The screen's own native figures when the import kept them (NBP in p/th as printed).
      const nativeUnit = typeof quote.metadata_json?.native_unit === "string" ? String(quote.metadata_json.native_unit) : null;
      const useNative = nativeUnit !== null && inHubUnit(hub, 1, "", nativeUnit) === 1;
      const bid = useNative ? metaNumber(quote, "native_bid") ?? native(quote.bid_price) : native(quote.bid_price);
      const offer = useNative ? metaNumber(quote, "native_ask") ?? native(quote.ask_price) : native(quote.ask_price);
      const last = native(quote.last_price);
      const closeQuote = closes.get(`${contract.key}|${hub}|${quote.source_system}`);
      const close = closeQuote ? native(closeQuote.close_price) : null;
      const mid = native(quoteMid(quote));
      const priced = bid !== null || offer !== null || last !== null;
      const convertible = native(1) !== null;
      const ageSeconds = Math.max((nowMs - Date.parse(quote.observed_at_utc)) / 1000, 0);
      row[hub] = {
        hub,
        contract: contract.key,
        status: !convertible ? "unit" : priced ? "priced" : "no_source",
        bid,
        offer,
        last,
        change: mid !== null && close !== null ? mid - close : null,
        unit,
        simulated: Boolean(quote.simulated),
        stale: isQuoteStale(quote, Number.isFinite(ageSeconds) ? ageSeconds : null, quote.stale_after_seconds ?? null),
        source: quote.source_system,
        observedAt: quote.observed_at_utc,
        closeDay: closeQuote?.close_day ?? null,
        quoteId: quote.quote_id,
      };
    }
    out[contract.key] = row;
  }
  return out;
}

/** Whether any priced cell is simulated, and whether all of them are. */
export function boardSimulation(cells: Record<string, Record<string, BoardCell>>): boolean[] {
  return Object.values(cells)
    .flatMap((row) => Object.values(row))
    .filter((cell) => cell.status === "priced")
    .map((cell) => cell.simulated);
}

/* ------------------------------------------------------------------ spreads */

/** The owner's hub spreads (section 9), first hub minus second. */
export const HUB_SPREAD_PAIRS: readonly (readonly [string, string])[] = [
  ["TTF", "NBP"],
  ["ZTP", "NBP"],
  ["TTF", "ZTP"],
  ["TTF", "THE"],
  ["PVB", "TTF"],
];

export function pairsParam(pairs: readonly (readonly [string, string])[] = HUB_SPREAD_PAIRS): string {
  return pairs.map(([a, b]) => `${a}-${b}`).join(",");
}

export type TransportBasis =
  /** No capacity booked on the route: short-term capacity plus the flow charge (the default). */
  | "default"
  /** The firm's bookings cover the route: the flow charge alone. */
  | "held"
  /** Part of the route is booked: still priced on the default, and said so. */
  | "part"
  /** The route is not fully priced: no net. */
  | "unpriced";

export interface SpreadFigure {
  tenor: "DA" | "MA";
  available: boolean;
  /** Why not, in the server's codes (said in words by the caller). */
  reason: BoardTenorDTO | null;
  gross: number | null;
  transport: number | null;
  net: number | null;
  basis: TransportBasis;
  /** Gas flows from → to for the spread to earn (the cheaper hub to the dearer). */
  direction: string | null;
  unit: "p/th" | "EUR/MWh";
  /** p/th per EUR/MWh at the close's FX, when the spread has an NBP leg. */
  factor: number | null;
  /** GBP per EUR implied by that factor (the rate shown on demand). */
  gbpPerEur: number | null;
  closeDay: string | null;
  simulated: boolean;
  /** What the transport is made of (EUR/MWh): capacity and flow charges, for the title. */
  capacity: number | null;
  flow: number | null;
  capacityProduct: string | null;
}

/**
 * One spread tenor from the server's board, with the owner's transport rule applied and, with
 * an NBP leg, in pence per therm at the FX the server used for the close (read off the NBP
 * leg's own native and per-MWh figures: no rate of this client's).
 */
export function spreadFigure(tenor: BoardTenorDTO): SpreadFigure {
  const code = tenor.tenor;
  const nbp = tenor.legs?.find((leg) => leg.hub.toUpperCase() === "NBP");
  const factor = nbp && nbp.value ? nbp.native_value / nbp.value : null;
  const unit = factor !== null ? "p/th" : "EUR/MWh";
  const scale = (value: number | null | undefined) => (value == null || !Number.isFinite(value) ? null : factor !== null ? value * factor : value);
  const base: SpreadFigure = {
    tenor: code,
    available: tenor.available,
    reason: tenor.available ? null : tenor,
    gross: null,
    transport: null,
    net: null,
    basis: "unpriced",
    direction: tenor.direction ?? null,
    unit,
    factor,
    // p/th per EUR/MWh = GBP/EUR × 100 ÷ (th per MWh); so GBP/EUR = factor × th-per-MWh ÷ 100.
    gbpPerEur: factor !== null ? (factor * THERMS_PER_MWH) / 100 : null,
    closeDay: tenor.close_day ?? null,
    simulated: Boolean(tenor.simulated),
    capacity: tenor.route?.marginal?.capacity ?? null,
    flow: tenor.route?.marginal?.holder ?? null,
    capacityProduct: tenor.route?.marginal?.product ?? tenor.route?.product ?? null,
  };
  if (!tenor.available || tenor.gross == null) return base;
  base.gross = scale(tenor.gross);
  const marginal = tenor.route?.marginal;
  const held = marginal?.capacity_held;
  let cost: number | null = null;
  if (held === "all" && marginal && marginal.holder != null) {
    cost = marginal.holder;
    base.basis = "held";
  } else if (tenor.cost != null) {
    cost = tenor.cost;
    base.basis = held === "part" ? "part" : "default";
  }
  if (cost === null) return base;
  base.transport = scale(cost);
  base.net = scale(Math.abs(tenor.gross) - cost);
  return base;
}

export interface HubSpreadRow {
  pair: string;
  hub: string;
  reference: string;
  route: string | null;
  da: SpreadFigure | null;
  ma: SpreadFigure | null;
}

export function hubSpreadRows(board: SpreadBoardDTO | null | undefined): HubSpreadRow[] {
  return (board?.locational ?? []).map((row) => {
    const ma = row.tenors.find((tenor) => tenor.tenor === "MA");
    const da = row.tenors.find((tenor) => tenor.tenor === "DA");
    const priced = [da, ma].find((tenor) => tenor?.route?.hubs?.length);
    return {
      pair: row.pair,
      hub: row.hub,
      reference: row.reference,
      route: priced?.route?.hubs?.join(" → ") ?? null,
      da: da ? spreadFigure(da) : null,
      ma: ma ? spreadFigure(ma) : null,
    };
  });
}

export interface TimeSpreadCell {
  value: number | null;
  unit: string;
  available: boolean;
  reason: BoardTimeRowDTO | null;
  simulated: boolean;
  label: string | null;
}

/** The owner's time spreads at each hub, in the hub's quotation. */
export const TIME_SPREAD_KEYS = ["da_wd", "da_ma", "m1_m2", "win_sum"] as const;
export type TimeSpreadKey = (typeof TIME_SPREAD_KEYS)[number];

/**
 * Time spreads per hub: DA − WD from the board's own mids (the server's board has no
 * within-day close), the rest from the server's spread board in the hub's quotation.
 */
export function timeSpreads(
  board: SpreadBoardDTO | null | undefined,
  cells: Record<string, Record<string, BoardCell>>,
  hubs: readonly string[],
): Record<TimeSpreadKey, Record<string, TimeSpreadCell>> {
  const out = Object.fromEntries(TIME_SPREAD_KEYS.map((key) => [key, {} as Record<string, TimeSpreadCell>])) as Record<TimeSpreadKey, Record<string, TimeSpreadCell>>;
  for (const hubCode of hubs) {
    const hub = hubCode.toUpperCase();
    const unit = hubPriceUnit(hub);
    const da = cells.DA?.[hub];
    const wd = cells.WD?.[hub];
    const mid = (cell: BoardCell | undefined) => (cell && cell.bid !== null && cell.offer !== null ? (cell.bid + cell.offer) / 2 : null);
    // One source for both legs: a spread across two feeds' quotes would be a feed difference.
    const sameSource = Boolean(da && wd && da.source === wd.source);
    const daMid = sameSource ? mid(da) : null;
    const wdMid = sameSource ? mid(wd) : null;
    out.da_wd[hub] = {
      value: daMid !== null && wdMid !== null ? daMid - wdMid : null,
      unit,
      available: daMid !== null && wdMid !== null,
      reason: null,
      simulated: Boolean(da?.simulated || wd?.simulated),
      label: null,
    };
    const series = board?.time.find((item) => item.hub.toUpperCase() === hub);
    for (const key of ["da_ma", "m1_m2", "win_sum"] as const) {
      const row = series?.rows.find((item) => (key === "win_sum" ? item.key === "win_sum" : item.key === key));
      const value = row?.available ? row.native_value ?? row.value ?? null : null;
      out[key][hub] = {
        value,
        unit,
        available: Boolean(row?.available && value !== null),
        reason: row && !row.available ? row : null,
        simulated: Boolean(series?.simulated),
        label: row?.label ?? null,
      };
    }
  }
  return out;
}

/* ------------------------------------------------------------------ position */

export interface PositionCell {
  physical: number | null;
  financial: number | null;
  net: number | null;
  unit: "th/d" | "MW";
  /** No daily position in the ladder for the prompt days. */
  prompt: boolean;
}

function daysInMonth(month: string): number {
  const year = Number(month.slice(0, 4));
  const m = Number(month.slice(5, 7));
  return new Date(Date.UTC(year, m, 0)).getUTCDate();
}

/** MWh over a set of months as a rate: MW (MWh per hour) or th/d. */
export function asRate(mwh: number, months: readonly string[], unit: "th/d" | "MW"): number {
  const days = months.reduce((sum, month) => sum + daysInMonth(month), 0);
  if (days <= 0) return 0;
  return unit === "MW" ? mwh / (days * 24) : (mwh / days) * THERMS_PER_MWH;
}

/**
 * The position on the board's rows: the ladder's monthly MWh summed over each contract's months,
 * as a rate in the hub's position unit. The prompt days have no figure (the ladder is monthly).
 */
export function positionOnBoard(
  rows: readonly PositionLadderRowDTO[],
  contracts: readonly BoardContract[],
  hubs: readonly string[],
): Record<string, Record<string, PositionCell>> {
  const byKey = new Map<string, PositionLadderRowDTO[]>();
  for (const row of rows) {
    const key = `${row.hub.toUpperCase()}|${row.month.slice(0, 7)}`;
    byKey.set(key, [...(byKey.get(key) ?? []), row]);
  }
  const out: Record<string, Record<string, PositionCell>> = {};
  for (const contract of contracts) {
    const months = contractMonths(contract);
    const row: Record<string, PositionCell> = {};
    for (const hubCode of hubs) {
      const hub = hubCode.toUpperCase();
      const unit = hubPositionUnit(hub);
      if (months.length === 0) {
        row[hub] = { physical: null, financial: null, net: null, unit, prompt: true };
        continue;
      }
      let physical = 0;
      let financial = 0;
      let net = 0;
      for (const month of months) {
        for (const item of byKey.get(`${hub}|${month}`) ?? []) {
          physical += item.physical_mwh;
          financial += item.financial_mwh;
          net += netPosition(item);
        }
      }
      row[hub] = {
        physical: asRate(physical, months, unit),
        financial: asRate(financial, months, unit),
        net: asRate(net, months, unit),
        unit,
        prompt: false,
      };
    }
    out[contract.key] = row;
  }
  return out;
}

/* ------------------------------------------------------------------ fundamentals units */

/** GWh as million cubic metres at a calorific value (kWh/m³): GB volumes in mcm. */
export function gwhToMcm(gwh: number, gcvKwhPerM3: number): number {
  return gwh / gcvKwhPerM3;
}

/** Million cubic metres as GWh at a calorific value (kWh/m³): continental volumes in GWh. */
export function mcmToGwh(mcm: number, gcvKwhPerM3: number): number {
  return mcm * gcvKwhPerM3;
}
