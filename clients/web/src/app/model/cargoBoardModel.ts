/**
 * The cargo board and cargo plan (Desk → Cargoes, QA-L-05): the pure part. Sorting and pinning,
 * the header strip's sums, the keyboard map, import age, unit conversion, the energy waterfall,
 * send-out by gas day, suggestion arithmetic, the hedge editor's validation and the what-if
 * comparison. No DOM and no fetch: tested in tests/cargoBoardModel.test.ts.
 *
 * Every figure comes from `GET /api/lng/cargoes/plans` and `GET /api/lng/cargoes/{id}/plan`;
 * nothing here invents a number. Advice only: nothing is executed, booked or nominated.
 */
import type {
  CargoHedgeLegDTO,
  CargoPlanBoardLineDTO,
  CargoPlanBodyDTO,
  CargoPlanChangeDTO,
  CargoPlanMonthDTO,
  CargoPlanSuggestionDTO,
} from "../../api/client.ts";

export type SlotStatus = CargoPlanBodyDTO["slot_status"];

/* ------------------------------------------------------------------ status */

/** A missed slot or no slot at all: the row pins to the top of the board. */
export function isPinned(line: Pick<CargoPlanBoardLineDTO, "slot_status">): boolean {
  return line.slot_status === "missed" || line.slot_status === "no_slot";
}

export type CargoTone = "ok" | "watch" | "breach" | "stale" | "neutral";

/** The status colour; the status is always written out too (colour is never the only cue). */
export function statusTone(line: Pick<CargoPlanBoardLineDTO, "slot_status" | "error">): CargoTone {
  if (line.error) return "stale";
  switch (line.slot_status) {
    case "on_time":
      return "ok";
    case "waiting":
      return "watch";
    case "missed":
    case "no_slot":
      return "breach";
    default:
      return "neutral";
  }
}

/* ------------------------------------------------------------------ sorting */

function instantMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

/** When the line's next action is due (ms), or null when it has none with a due time. */
export function nextDueMs(line: Pick<CargoPlanBoardLineDTO, "next_action">): number | null {
  return instantMs(line.next_action?.due_utc ?? null);
}

/**
 * The board's order: missed and no-slot rows first (missed before no slot), then by next action
 * due (none last), then by ETA, then by cargo id; a cargo whose plan could not be built last
 * (its row says what the import must carry).
 */
export function sortCargoBoard<L extends CargoPlanBoardLineDTO>(lines: readonly L[]): L[] {
  const group = (line: L) => (line.error ? 3 : line.slot_status === "missed" ? 0 : line.slot_status === "no_slot" ? 1 : 2);
  // Ascending, a missing instant last.
  const byInstant = (left: number | null, right: number | null) =>
    left === right ? 0 : left === null ? 1 : right === null ? -1 : left - right;
  return [...lines].sort(
    (left, right) =>
      group(left) - group(right) ||
      byInstant(nextDueMs(left), nextDueMs(right)) ||
      byInstant(instantMs(left.eta_utc), instantMs(right.eta_utc)) ||
      left.cargo_id.localeCompare(right.cargo_id),
  );
}

/* ------------------------------------------------------------------ header strip */

export interface OpenCell {
  hub: string;
  month: string;
  /** Net open energy, MWh (physical + hedge; long is positive). */
  net_mwh: number;
  cargoes: number;
}

export interface HeaderStrip {
  /** Open energy by hub and delivery month over every cargo on the board, month order. */
  open: OpenCell[];
  /** The earliest futures expiry that matters for any cargo, with its cargo. */
  nextExpiry: { cargo_id: string; hub: string | null; month: string | null; due_utc: string } | null;
  /** Cargoes that need action today: a missed or no-slot row, or a next action due by `dayEndMs`. */
  needActionToday: number;
  /** Cargoes whose plan could not be built. */
  unplanned: number;
}

/** The strip over the board: sums only, from the rows the board shows. */
export function headerStrip(lines: readonly CargoPlanBoardLineDTO[], dayEndMs: number): HeaderStrip {
  const cells = new Map<string, OpenCell>();
  let nextExpiry: HeaderStrip["nextExpiry"] = null;
  let need = 0;
  let unplanned = 0;
  for (const line of lines) {
    if (line.error) {
      unplanned += 1;
      continue;
    }
    for (const month of line.months ?? []) {
      const key = `${month.month}|${month.hub}`;
      const cell = cells.get(key) ?? { hub: month.hub, month: month.month, net_mwh: 0, cargoes: 0 };
      cell.net_mwh += month.net_mwh;
      cell.cargoes += 1;
      cells.set(key, cell);
    }
    const expiry = line.next_expiry;
    const expiryMs = instantMs(expiry?.due_utc ?? null);
    if (expiry && expiryMs !== null && (nextExpiry === null || expiryMs < Date.parse(nextExpiry.due_utc))) {
      nextExpiry = { cargo_id: line.cargo_id, hub: expiry.hub, month: expiry.from_month, due_utc: expiry.due_utc! };
    }
    const due = nextDueMs(line);
    if (isPinned(line) || (due !== null && due <= dayEndMs)) need += 1;
  }
  const open = [...cells.values()]
    .filter((cell) => Math.abs(cell.net_mwh) >= 1)
    .sort((left, right) => left.month.localeCompare(right.month) || left.hub.localeCompare(right.hub));
  return { open, nextExpiry, needActionToday: need, unplanned };
}

/** The end of the calendar day that holds `nowMs` in `timeZone` (ms epoch). */
export function endOfDayMs(nowMs: number, timeZone: string): number {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(nowMs));
  const part = (type: string) => Number(parts.find((item) => item.type === type)?.value ?? 0);
  const elapsed = ((part("hour") * 60 + part("minute")) * 60 + part("second")) * 1000 + (nowMs % 1000);
  return nowMs - elapsed + 24 * 3_600_000 - 1;
}

/* ------------------------------------------------------------------ keyboard */

export type BoardKeyAction = "up" | "down" | "open" | "what_if" | "hedge";

/**
 * The board's keys: ↑ and ↓ move, Enter opens the plan, `w` opens the what-if, `h` the hedge
 * editor. A key with Ctrl, Alt or Meta held is the shell's, never the board's.
 */
export function boardKeyAction(event: { key: string; ctrlKey?: boolean; altKey?: boolean; metaKey?: boolean }): BoardKeyAction | null {
  if (event.ctrlKey || event.altKey || event.metaKey) return null;
  switch (event.key) {
    case "ArrowUp":
      return "up";
    case "ArrowDown":
      return "down";
    case "Enter":
      return "open";
    case "w":
    case "W":
      return "what_if";
    case "h":
    case "H":
      return "hedge";
    default:
      return null;
  }
}

/* ------------------------------------------------------------------ import age and ETA change */

/**
 * How often an import is expected, in hours. No source declares a cadence for cargo files, so
 * the board states its own: the ETRM sends a daily file; a vessel feed updates within hours.
 */
export const IMPORT_CADENCE_HOURS = { etrm: 24, vessel_feed: 6 } as const;

export function importCadenceHours(sourceSystem: string | null | undefined): number {
  const source = String(sourceSystem ?? "").toUpperCase();
  return /KPLER|AIS|VORTEXA|VESSEL|_SIM$/.test(source) ? IMPORT_CADENCE_HOURS.vessel_feed : IMPORT_CADENCE_HOURS.etrm;
}

export interface ImportAge {
  hours: number;
  cadenceHours: number;
  stale: boolean;
}

export function importAge(line: Pick<CargoPlanBoardLineDTO, "imported_at_utc" | "source_system">, nowMs: number): ImportAge | null {
  const at = instantMs(line.imported_at_utc ?? null);
  if (at === null) return null;
  const hours = Math.max(0, (nowMs - at) / 3_600_000);
  const cadenceHours = importCadenceHours(line.source_system);
  return { hours, cadenceHours, stale: hours > cadenceHours };
}

/** How far the last change moved the ETA, hours (later is positive); null when it did not. */
export function etaChangeHours(line: Pick<CargoPlanBoardLineDTO, "eta_utc" | "changed">): number | null {
  const before = instantMs(line.changed?.eta_before_utc ?? null);
  const now = instantMs(line.eta_utc ?? null);
  if (before === null || now === null || !line.changed?.kinds.includes("eta")) return null;
  return (now - before) / 3_600_000;
}

/* ------------------------------------------------------------------ units */

export const ENERGY_DISPLAY_UNITS = ["GWh", "TBtu", "Mth"] as const;
export type EnergyDisplayUnit = (typeof ENERGY_DISPLAY_UNITS)[number];

/** MMBtu per MWh (1 MWh = 3.412141633 MMBtu); a therm is a tenth of an MMBtu. */
export const MMBTU_PER_MWH = 3.412141633;

/** Energy in MWh in a display unit: GWh, TBtu (10^12 Btu) or million therms. */
export function convertEnergy(mwh: number, unit: EnergyDisplayUnit): number {
  if (unit === "GWh") return mwh / 1000;
  if (unit === "TBtu") return (mwh * MMBTU_PER_MWH) / 1_000_000;
  return (mwh * MMBTU_PER_MWH * 10) / 1_000_000;
}

export function energyDigits(unit: EnergyDisplayUnit): number {
  return unit === "GWh" ? 0 : 2;
}

/* ------------------------------------------------------------------ cover and countdown */

/** A month's cover chip: hedged share of the physical gas (null: nothing physical there). */
export function coverTone(month: Pick<CargoPlanMonthDTO, "cover_ratio" | "physical_mwh" | "hedge_mwh">): CargoTone {
  const ratio = month.cover_ratio;
  if (ratio === null || ratio === undefined) return Math.abs(month.hedge_mwh) >= 1 ? "breach" : "neutral";
  if (ratio >= 0.95 && ratio <= 1.05) return "ok";
  if (ratio > 1.05 || ratio >= 0.5) return "watch";
  return "breach";
}

export interface Countdown {
  overdue: boolean;
  days: number;
  hours: number;
  minutes: number;
}

/** The time left to a due instant, in whole days, hours and minutes. */
export function countdown(dueMs: number, nowMs: number): Countdown {
  const left = dueMs - nowMs;
  const minutesTotal = Math.floor(Math.abs(left) / 60_000);
  return {
    overdue: left < 0,
    days: Math.floor(minutesTotal / 1440),
    hours: Math.floor((minutesTotal % 1440) / 60),
    minutes: minutesTotal % 60,
  };
}

/** The countdown as the desk writes it: "2d 4h", "3h 20m", "45m". */
export function countdownText(value: Countdown): string {
  if (value.days > 0) return `${value.days}d ${value.hours}h`;
  if (value.hours > 0) return `${value.hours}h ${value.minutes}m`;
  return `${value.minutes}m`;
}

/* ------------------------------------------------------------------ slot window bar */

export interface SlotBar {
  /** Window start and end, and the ETA, as shares of the bar (0-1). */
  windowStart: number;
  windowEnd: number;
  eta: number;
  /** The ETA relative to the window. */
  position: "before" | "inside" | "after";
}

/** Where the ETA falls against the slot window, for the row's mini bar; null without both. */
export function slotBar(line: Pick<CargoPlanBoardLineDTO, "eta_utc" | "slot">): SlotBar | null {
  const start = instantMs(line.slot?.window_start_utc ?? null);
  const end = instantMs(line.slot?.window_end_utc ?? null);
  const eta = instantMs(line.eta_utc ?? null);
  if (start === null || end === null || eta === null || end <= start) return null;
  const width = end - start;
  const from = Math.min(start, eta) - width * 0.25;
  const to = Math.max(end, eta) + width * 0.25;
  const share = (value: number) => (value - from) / (to - from);
  return {
    windowStart: share(start),
    windowEnd: share(end),
    eta: share(eta),
    position: eta < start ? "before" : eta > end ? "after" : "inside",
  };
}

/* ------------------------------------------------------------------ the plan */

export interface WaterfallStepInput {
  id: string;
  /** Translation key of the step's name. */
  labelKey: string;
  value: number;
  kind: "total" | "delta";
}

/**
 * The energy waterfall: the cargo record's loaded energy, less boil-off and gas in kind, to the
 * delivered energy the plan states. With no berth (missed, no slot) nothing is unloaded: the
 * waterfall ends at the energy aboard at the ETA. Both ends are stated figures, so a plan that
 * does not add up shows the difference instead of a convincing picture.
 */
export function energyWaterfall(loadedMwh: number | null | undefined, plan: CargoPlanBodyDTO): WaterfallStepInput[] {
  const berthed = plan.slot_status === "on_time" || plan.slot_status === "waiting";
  const steps: WaterfallStepInput[] = [];
  if (loadedMwh !== null && loadedMwh !== undefined) {
    steps.push({ id: "loaded", labelKey: "lng.cargo.waterfall.loaded", value: loadedMwh, kind: "total" });
  }
  steps.push({ id: "boil_off", labelKey: "lng.cargo.waterfall.boil_off", value: -plan.boil_off_mwh, kind: "delta" });
  if (berthed) {
    steps.push({ id: "gas_in_kind", labelKey: "lng.cargo.waterfall.gas_in_kind", value: -plan.gas_in_kind_mwh, kind: "delta" });
    steps.push({ id: "delivered", labelKey: "lng.cargo.waterfall.delivered", value: plan.delivered_mwh, kind: "total" });
  } else {
    steps.push({ id: "aboard", labelKey: "lng.cargo.waterfall.aboard", value: plan.energy_at_eta_mwh ?? 0, kind: "total" });
  }
  return steps;
}

/** The send-out by gas day adds up to the delivered energy (MWh difference; 0 when it does). */
export function sendOutGap(plan: CargoPlanBodyDTO): number {
  const sent = plan.send_out.reduce((sum, day) => sum + day.mwh, 0);
  return Math.round((sent - plan.delivered_mwh) * 10) / 10;
}

export interface SendOutSeries {
  /** Delivery month ("2026-12"). */
  month: string;
  values: (number | null)[];
}

/**
 * Send-out by gas day as one bar series per delivery month: the bars change colour at the
 * month boundary, so a cargo straddling two months reads as two blocks of gas.
 */
export function sendOutByMonth(plan: CargoPlanBodyDTO): { days: string[]; series: SendOutSeries[] } {
  const days = plan.send_out.map((day) => day.gas_day);
  const months = [...new Set(days.map((day) => day.slice(0, 7)))];
  const series = months.map((month) => ({
    month,
    values: plan.send_out.map((day) => (day.gas_day.startsWith(month) ? day.mwh : null)),
  }));
  return { days, series };
}

/** Whole days from `nowMs` to the end of a last trading day ("2026-11-27"), floor at 0. */
export function daysToLastTrade(lastTradingDay: string, nowMs: number): number {
  const end = Date.parse(`${lastTradingDay}T23:59:59Z`);
  if (!Number.isFinite(end)) return 0;
  return Math.max(0, Math.floor((end - nowMs) / 86_400_000));
}

/** Suggestions in the order they fall due; one without a due time after those with one. */
export function suggestionsByDue(items: readonly CargoPlanSuggestionDTO[]): CargoPlanSuggestionDTO[] {
  return items
    .map((item, index) => ({ item, index, due: instantMs(item.due_utc) }))
    .sort((left, right) => {
      if (left.due === null && right.due === null) return left.index - right.index;
      if (left.due === null) return 1;
      if (right.due === null) return -1;
      return left.due - right.due || left.index - right.index;
    })
    .map((entry) => entry.item);
}

export interface Arithmetic {
  key: string;
  values: Record<string, string | number>;
}

/** Whole MWh: the component writes the number in the reader's language. */
function fmt(mwh: number): number {
  return Math.round(mwh);
}

/**
 * The sum behind a suggestion, from the hub months the plan states (MWh, signed: long positive,
 * a short hedge negative). Null when the suggestion carries no figure to show.
 */
export function suggestionArithmetic(item: CargoPlanSuggestionDTO, months: readonly CargoPlanMonthDTO[], plan?: Pick<CargoPlanBodyDTO, "demurrage_hours" | "demurrage_cost">): Arithmetic | null {
  const month = (name: string | null) => months.find((row) => row.hub === item.hub && row.month === name) ?? null;
  if (item.kind === "roll") {
    const from = month(item.from_month);
    const to = month(item.to_month);
    if (!from || !to || item.mwh === null) return null;
    return {
      key: "lng.cargo.arith.roll",
      values: {
        from: item.from_month ?? "",
        fromPhysical: fmt(from.physical_mwh),
        fromHedge: fmt(from.hedge_mwh),
        fromNet: fmt(from.net_mwh),
        to: item.to_month ?? "",
        toPhysical: fmt(to.physical_mwh),
        toHedge: fmt(to.hedge_mwh),
        toNet: fmt(to.net_mwh),
        mwh: fmt(item.mwh),
      },
    };
  }
  if (item.kind === "sell" || item.kind === "buy_back" || item.kind === "short_notice") {
    const row = month(item.from_month);
    if (!row) return null;
    return {
      key: "lng.cargo.arith.net",
      values: { month: item.from_month ?? "", physical: fmt(row.physical_mwh), hedge: fmt(row.hedge_mwh), net: fmt(row.net_mwh) },
    };
  }
  if (item.kind === "find_slot") {
    const hedged = months.reduce((sum, row) => sum + row.hedge_mwh, 0);
    return { key: "lng.cargo.arith.find_slot", values: { hedge: fmt(hedged) } };
  }
  if (item.kind === "demurrage" && plan) {
    return {
      key: plan.demurrage_cost === null ? "lng.cargo.arith.demurrage_hours" : "lng.cargo.arith.demurrage",
      values: { hours: Math.round(plan.demurrage_hours), cost: plan.demurrage_cost === null ? 0 : fmt(plan.demurrage_cost) },
    };
  }
  if (item.kind === "deadline") {
    const row = month(item.from_month);
    return row ? { key: "lng.cargo.arith.deadline", values: { month: item.from_month ?? "", day: row.last_trading_day } } : null;
  }
  return null;
}

/* ------------------------------------------------------------------ hedge editor */

export interface HedgeRow {
  hub: string;
  month: string;
  /** As typed: signed MWh (a short hedge is negative). */
  mwh: string;
  reference: string;
}

export type HedgeFieldError = "hub_unknown" | "month_invalid" | "mwh_invalid" | "mwh_zero" | "reference_long" | "duplicate";

export const MAX_HEDGE_LEGS = 48;
export const MAX_HEDGE_MWH = 10_000_000;
const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

export interface HedgeValidation {
  /** Per row, the field errors (an empty list: the row is valid). */
  rows: HedgeFieldError[][];
  /** Too many legs for one set. */
  tooMany: boolean;
  /** The legs to send when every row is valid; null otherwise. */
  legs: CargoHedgeLegDTO[] | null;
}

/** The editor's rows as the server would accept them (the PUT validates again). */
export function validateHedges(rows: readonly HedgeRow[], knownHubs: readonly string[]): HedgeValidation {
  const hubs = new Set(knownHubs.map((hub) => hub.toUpperCase()));
  const seen = new Set<string>();
  const errors = rows.map((row) => {
    const out: HedgeFieldError[] = [];
    const hub = row.hub.trim().toUpperCase();
    if (!hubs.has(hub)) out.push("hub_unknown");
    if (!MONTH.test(row.month.trim())) out.push("month_invalid");
    const text = row.mwh.trim().replace(/[\s,_]/g, "").replace(/−/g, "-");
    const value = text === "" ? Number.NaN : Number(text);
    if (!Number.isFinite(value) || Math.abs(value) > MAX_HEDGE_MWH) out.push("mwh_invalid");
    else if (value === 0) out.push("mwh_zero");
    if (row.reference.trim().length > 160) out.push("reference_long");
    const key = `${hub}|${row.month.trim()}|${row.reference.trim()}`;
    if (seen.has(key)) out.push("duplicate");
    seen.add(key);
    return out;
  });
  const tooMany = rows.length > MAX_HEDGE_LEGS;
  const valid = !tooMany && errors.every((list) => list.length === 0);
  return {
    rows: errors,
    tooMany,
    legs: valid
      ? rows.map((row) => ({
          hub: row.hub.trim().toUpperCase(),
          month: row.month.trim(),
          mwh: Number(row.mwh.trim().replace(/[\s,_]/g, "").replace(/−/g, "-")),
          reference: row.reference.trim() || null,
        }))
      : null,
  };
}

/** The editor's starting rows: the legs held, else one empty row. */
export function hedgeRowsFrom(legs: readonly CargoHedgeLegDTO[] | null | undefined): HedgeRow[] {
  if (!legs?.length) return [{ hub: "", month: "", mwh: "", reference: "" }];
  return legs.map((leg) => ({ hub: leg.hub, month: leg.month, mwh: String(leg.mwh), reference: leg.reference ?? "" }));
}

/** Rows that would hedge each physical month in full (a short of the physical): a starting point. */
export function hedgeRowsCoveringPhysical(months: readonly CargoPlanMonthDTO[]): HedgeRow[] {
  return months
    .filter((month) => Math.abs(month.physical_mwh) >= 1)
    .map((month) => ({ hub: month.hub, month: month.month, mwh: String(-Math.round(month.physical_mwh)), reference: "" }));
}

/* ------------------------------------------------------------------ what-if */

export interface WhatIfRow {
  id: string;
  labelKey: string;
  before: number | string | null;
  after: number | string | null;
  /** after - before for figures; null for words and instants. */
  change: number | null;
}

/** The what-if as a before/after table: status, berth, the energy chain, demurrage, each month. */
export function whatIfRows(change: CargoPlanChangeDTO): WhatIfRow[] {
  const before = change.before;
  const after = change.after;
  if (!after) return [];
  const figure = (id: string, labelKey: string, pick: (plan: CargoPlanBodyDTO) => number | null) => {
    const left = pick(before);
    const right = pick(after);
    return { id, labelKey, before: left, after: right, change: left === null || right === null ? null : Math.round((right - left) * 10) / 10 };
  };
  const rows: WhatIfRow[] = [
    { id: "status", labelKey: "lng.cargo.whatif.status", before: before.slot_status, after: after.slot_status, change: null },
    { id: "berth", labelKey: "lng.cargo.whatif.berth", before: before.berth_utc, after: after.berth_utc, change: null },
    figure("boil_off", "lng.cargo.waterfall.boil_off", (plan) => plan.boil_off_mwh),
    figure("gas_in_kind", "lng.cargo.waterfall.gas_in_kind", (plan) => plan.gas_in_kind_mwh),
    figure("delivered", "lng.cargo.waterfall.delivered", (plan) => plan.delivered_mwh),
    figure("demurrage_hours", "lng.cargo.whatif.demurrage_hours", (plan) => plan.demurrage_hours),
    figure("demurrage_cost", "lng.cargo.whatif.demurrage_cost", (plan) => plan.demurrage_cost),
  ];
  for (const shift of change.months ?? []) {
    rows.push({
      id: `month:${shift.hub}:${shift.month}`,
      labelKey: "lng.cargo.whatif.month",
      before: shift.physical_before_mwh,
      after: shift.physical_after_mwh,
      change: shift.change_mwh,
    });
  }
  return rows;
}

/** A what-if moves only to a slot no other cargo holds; a held slot is listed and flagged. */
export function slotChoices<S extends { slot_id: string; free: boolean; window_start_utc: string }>(options: readonly S[]): { free: S[]; held: S[] } {
  const ordered = [...options].sort((left, right) => left.window_start_utc.localeCompare(right.window_start_utc));
  return { free: ordered.filter((slot) => slot.free), held: ordered.filter((slot) => !slot.free) };
}
