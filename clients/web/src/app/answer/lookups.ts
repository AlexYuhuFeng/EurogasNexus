/**
 * Tier 2 of the answer bar: plain, deterministic reads through the existing public API, as
 * the pages that own each number read them. No model. Each answer carries its as-of time and
 * source, a simulated figure says so as the hub board does, and Enter opens the task where
 * the number lives. The reads are injected (`AnswerReads`) so the shaping is testable, and
 * every read takes the AbortSignal the bar cancels a stale look-up with.
 *
 * What is read:
 * - prices: the Today read's front-month close and day change (`GET /api/desk/today`), a
 *   delivery month from the normalised curve (`GET /api/market/normalized`), a prompt product
 *   (WD, DA, WE, BOM) from the quote ladder (`GET /api/market/quotes`) the board uses;
 * - storage: the NW Europe fill from the Today read, a country from the storage trajectory
 *   (`GET /api/storage/target-trajectory`); LNG and Norway from the Today read's NW Europe
 *   balance, or a country's terminals (`GET /api/lng/observations`);
 * - outages: `GET /api/physical/outages` (14 days), as the Events task lists them;
 * - a price conversion for a future delivery period: `POST /api/market/normalise`, which
 *   converts at that period's forward FX and states the rate, method and dates (`forward.ts`);
 * - the book (only offered with `portfolio.read`; the server re-checks): the Today read's
 *   positions, the position ladder, credit exposure and the contract library.
 */

import type {
  CreditExposureRowDTO,
  DeskTodayDTO,
  LngObsDTO,
  MarketQuoteDTO,
  NormalizedMarketObsDTO,
  OutageEventDTO,
  PositionLadderDTO,
  StorageTrajectoryDTO,
  TodayPriceDTO,
  UnitsReferenceDTO,
  UpstreamContractDTO,
} from "../../api/client.ts";
import type { NormaliseRequestDTO, NormaliseResponseDTO } from "../../api/comparablePrices.ts";
import { buildMarketLadder } from "../model/marketLadderModel.ts";
import { forwardAnswer, forwardRequest } from "./forward.ts";
import { formatChange, formatValue } from "../model/todayModel.ts";
import type { AnswerText, AnswerView } from "./answerModel.ts";
import type { LookupIntent } from "./intent.ts";
import { monthLabel } from "./gasDay.ts";
import { clipboardNumber } from "./numbers.ts";
import { deskUnitLabel } from "./units.ts";

export interface AnswerReads {
  deskToday(signal: AbortSignal): Promise<DeskTodayDTO>;
  normalizedPrices(signal: AbortSignal): Promise<{ rows: NormalizedMarketObsDTO[]; limit: number }>;
  quotes(signal: AbortSignal): Promise<MarketQuoteDTO[]>;
  storage(code: string, signal: AbortSignal): Promise<StorageTrajectoryDTO | null>;
  lng(signal: AbortSignal): Promise<LngObsDTO[]>;
  outages(signal: AbortSignal): Promise<OutageEventDTO[]>;
  ladder(signal: AbortSignal): Promise<PositionLadderDTO>;
  credit(signal: AbortSignal): Promise<{ rows: CreditExposureRowDTO[]; as_of: string }>;
  contracts(signal: AbortSignal): Promise<UpstreamContractDTO[]>;
  /** `POST /api/market/normalise`: a price conversion with a delivery period. */
  normalise(body: NormaliseRequestDTO, signal: AbortSignal): Promise<NormaliseResponseDTO>;
  units(): UnitsReferenceDTO | null;
}

const SIM_SOURCE = /_sim$/i;

/** The UTC calendar day of a date or instant, as an ISO date: answerText writes it in the
 * reader's language ("24 Nov", "11月24日"). */
function shortDay(iso: string | null | undefined): string {
  if (!iso) return "";
  const parsed = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toISOString().slice(0, 10);
}

function asOfLine(asOf: string | null | undefined, source?: string | null): AnswerText {
  return source
    ? { key: "answer.as_of_source", values: { as_of: shortDay(asOf), source } }
    : { key: "answer.as_of", values: { as_of: shortDay(asOf) } };
}

function copyOf(value: number, unit: string, decimals: number): AnswerView["copy"] {
  const number = clipboardNumber(Number(value.toFixed(decimals)), decimals);
  return { value: number, withUnit: `${number} ${unit}` };
}

const PRICE_TARGET = { kind: "task", mode: "desk", task: "prices" } as const;
const FUNDAMENTALS_TARGET = { kind: "task", mode: "desk", task: "today" } as const;

function priceDecimals(_unit: string): number {
  return 3;
}

function noPrice(label: string, reasonKey: string): AnswerView {
  return {
    kind: "price",
    label,
    value: null,
    sentence: { key: "answer.price.none" },
    lines: [{ key: reasonKey }],
    target: PRICE_TARGET,
  };
}

function fromToday(price: TodayPriceDTO, label: string): AnswerView {
  const unit = deskUnitLabel(price.unit);
  const value = price.value as number;
  return {
    kind: "price",
    label,
    value: formatValue(value, price.unit),
    unit,
    delta: price.day_change === null ? null : { text: formatChange(price.day_change, price.unit), value: price.day_change },
    simulated: price.simulated,
    lines: [
      // Days go as ISO dates and are written in the reader's language where the line is drawn
      // (answerText); a simulated close says so in words, not in the server's English label.
      price.simulated
        ? { key: "answer.price.close_simulated", values: { day: price.close_day ?? "" } }
        : { key: "answer.price.close", values: { day: price.close_day ?? "", source: price.source ?? "" } },
      ...(price.day_change_vs ? [{ key: "answer.price.change_vs", values: { day: price.day_change_vs } }] : []),
    ],
    asOf: price.as_of,
    copy: copyOf(value, unit, priceDecimals(unit)),
    target: PRICE_TARGET,
  };
}

/** A curve row in the hub's quotation: NBP's GBP/MWh is written in pence per therm. */
function inNativeUnit(row: NormalizedMarketObsDTO, units: UnitsReferenceDTO | null): { value: number; unit: string } {
  const stored = row.unit.includes("/") ? row.unit : `${row.currency}/${row.unit}`;
  if (row.hub.toUpperCase() === "NBP" && /^GBP\/MWh$/i.test(stored) && units?.energy_in_mwh.th) {
    return { value: row.price * 100 * units.energy_in_mwh.th, unit: "GBp/th" };
  }
  return { value: row.price, unit: stored };
}

async function priceAnswer(intent: Extract<LookupIntent, { kind: "price" }>, reads: AnswerReads, signal: AbortSignal): Promise<AnswerView> {
  const { hub, tenor } = intent;
  if (tenor.kind === "prompt") {
    const label = `${hub} ${tenor.code}`;
    const rows = buildMarketLadder(await reads.quotes(signal), [hub]);
    const row = rows.find((item) => item.label === tenor.code);
    const cell = row?.cells[hub];
    if (!cell || (!cell.bid && !cell.offer)) return noPrice(label, "market.awaiting_feed");
    const bid = cell.bid, offer = cell.offer;
    const unit = deskUnitLabel((bid ?? offer)!.priceUnit);
    const mid = bid && offer ? (bid.price + offer.price) / 2 : (bid ?? offer)!.price;
    return {
      kind: "price",
      label,
      value: formatValue(mid, (bid ?? offer)!.priceUnit),
      unit,
      simulated: Boolean(bid?.simulated || offer?.simulated),
      lines: [
        { key: "answer.price.bid_offer", values: { bid: bid ? formatValue(bid.price, bid.priceUnit) : "–", offer: offer ? formatValue(offer.price, offer.priceUnit) : "–" } },
        asOfLine((bid ?? offer)!.observedAtUtc, (bid ?? offer)!.source),
      ],
      asOf: (bid ?? offer)!.observedAtUtc,
      copy: copyOf(mid, unit, 3),
      target: PRICE_TARGET,
    };
  }
  const today = await reads.deskToday(signal);
  const prices = (today.rows[0]?.prices ?? []).filter((item): item is TodayPriceDTO => "value" in item && item.hub === hub && item.value !== null);
  if (tenor.kind === "front") {
    const front = prices[0];
    if (front) return fromToday(front, front.label);
  }
  const wanted = tenor.kind === "month"
    ? `${tenor.year}-${String(tenor.month + 1).padStart(2, "0")}`
    : null;
  const todayMonth = prices.find((item) => wanted && item.product === monthLabel(Number(wanted.slice(0, 4)), Number(wanted.slice(5)) - 1));
  if (todayMonth) return fromToday(todayMonth, todayMonth.label);
  const label = tenor.kind === "month" ? `${hub} ${tenor.label}` : `${hub} ${today.front_month ?? ""}`.trim();
  const { rows, limit } = await reads.normalizedPrices(signal);
  const tenorKey = wanted ?? "month-ahead";
  const matching = rows
    .filter((row) => row.hub.toUpperCase() === hub && row.tenor === tenorKey && row.is_gas_price !== false)
    .sort((a, b) => Date.parse(b.observed_at_utc ?? "") - Date.parse(a.observed_at_utc ?? ""));
  const latest = matching[0];
  if (!latest) return noPrice(label, rows.length >= limit ? "answer.price.capped" : "market.no_price_rows");
  const native = inNativeUnit(latest, reads.units());
  const unit = deskUnitLabel(native.unit);
  const previous = matching[1] ? inNativeUnit(matching[1], reads.units()) : null;
  const change = previous ? native.value - previous.value : null;
  return {
    kind: "price",
    label,
    value: formatValue(native.value, native.unit),
    unit,
    delta: change === null ? null : { text: formatChange(change, native.unit), value: change },
    simulated: SIM_SOURCE.test(latest.source_system ?? "") || latest.metadata_json?.simulated === true,
    lines: [asOfLine(latest.observed_at_utc, latest.source_system)],
    asOf: latest.observed_at_utc,
    copy: copyOf(native.value, unit, 3),
    target: PRICE_TARGET,
  };
}

function balanceAnswer(today: DeskTodayDTO, field: "norway_gwh" | "lng_gwh", kind: "norway" | "lng"): AnswerView {
  const balance = today.rows[3]?.balance;
  const label: AnswerText = { key: kind === "norway" ? "answer.norway.label" : "answer.lng.label_nwe" };
  if (!balance || "empty" in balance || !balance.series.length) {
    return { kind, label, value: null, sentence: { key: "answer.fundamentals.none" }, lines: [], target: FUNDAMENTALS_TARGET };
  }
  const last = balance.series[balance.series.length - 1];
  const week = balance.series.length >= 8 ? balance.series[balance.series.length - 8] : null;
  const change = week ? last[field] - week[field] : null;
  return {
    kind,
    label,
    value: formatValue(last[field], "GWh/d"),
    unit: "GWh/d",
    delta: change === null ? null : { text: formatChange(change, "GWh/d"), value: change },
    simulated: balance.latest.simulated,
    lines: [
      ...(week ? [{ key: "answer.vs_day", values: { day: shortDay(week.day) } }] : []),
      asOfLine(last.day, balance.latest.source),
    ],
    asOf: last.day,
    copy: copyOf(last[field], "GWh/d", 0),
    target: FUNDAMENTALS_TARGET,
  };
}

/** "12-01" (the target's month and day) as "1 Dec". */
function monthDay(value: string): string {
  const match = /^(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;
  return new Date(Date.UTC(2000, Number(match[1]) - 1, Number(match[2]))).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

async function storageAnswer(country: string | null, reads: AnswerReads, signal: AbortSignal): Promise<AnswerView> {
  const today = await reads.deskToday(signal);
  const nwe = today.rows[3]?.storage;
  const nweLatest = nwe && !("empty" in nwe) ? nwe : null;
  if (!country) {
    if (!nweLatest || nweLatest.latest.value === null) {
      return { kind: "storage", label: { key: "answer.storage.label_nwe" }, value: null, sentence: { key: "answer.fundamentals.none" }, lines: [], target: FUNDAMENTALS_TARGET };
    }
    const series = nweLatest.series;
    const week = series.length >= 8 ? series[series.length - 8] : null;
    const value = nweLatest.latest.value;
    const change = week?.fill_pct != null ? value - week.fill_pct : null;
    return {
      kind: "storage",
      label: { key: "answer.storage.label_nwe" },
      value: formatValue(value, "%"),
      unit: "%",
      delta: change === null ? null : { text: `${formatChange(change, "%")} pp`, value: change },
      simulated: nweLatest.latest.simulated,
      lines: [
        { key: "answer.storage.inventory", values: { twh: formatValue(series[series.length - 1]?.inventory_twh ?? null, "TWh") } },
        ...(week ? [{ key: "answer.vs_day", values: { day: shortDay(week.day) } }] : []),
        asOfLine(nweLatest.latest.as_of, nweLatest.latest.source),
      ],
      asOf: nweLatest.latest.as_of,
      copy: copyOf(value, "%", 2),
      target: FUNDAMENTALS_TARGET,
    };
  }
  const trajectory = await reads.storage(country, signal);
  const label: AnswerText = { key: "answer.storage.label_country", values: { country } };
  if (!trajectory) {
    return { kind: "storage", label, value: null, sentence: { key: "answer.storage.none_country", values: { country } }, lines: [], target: FUNDAMENTALS_TARGET };
  }
  return {
    kind: "storage",
    label,
    value: formatValue(trajectory.fill_pct, "%"),
    unit: "%",
    // The country read carries no simulated flag of its own: it is the same storage dataset
    // as the NW Europe figure, so it is labelled as that one is.
    simulated: Boolean(nweLatest?.latest.simulated),
    lines: [
      { key: "answer.storage.of_capacity", values: { twh: formatValue(trajectory.inventory_twh, "TWh"), capacity: formatValue(trajectory.working_capacity_twh, "TWh") } },
      { key: `answer.storage.status.${trajectory.status}`, values: { target: trajectory.target_pct, deadline: monthDay(trajectory.deadline) } },
      asOfLine(trajectory.as_of_gas_day),
    ],
    asOf: trajectory.as_of_gas_day,
    copy: copyOf(trajectory.fill_pct, "%", 2),
    target: FUNDAMENTALS_TARGET,
  };
}

async function lngCountryAnswer(country: string, reads: AnswerReads, signal: AbortSignal): Promise<AnswerView> {
  const rows = (await reads.lng(signal)).filter((row) => (row.country ?? "").toUpperCase() === country && row.send_out_twh_d !== null);
  const label: AnswerText = { key: "answer.lng.label_country", values: { country } };
  const latestEnd = rows.reduce((latest, row) => ((row.period_end_utc ?? "") > latest ? row.period_end_utc ?? "" : latest), "");
  const day = rows.filter((row) => row.period_end_utc === latestEnd);
  if (!day.length) {
    return { kind: "lng", label, value: null, sentence: { key: "answer.lng.none_country", values: { country } }, lines: [], target: FUNDAMENTALS_TARGET };
  }
  const gwh = day.reduce((sum, row) => sum + (row.send_out_twh_d ?? 0) * 1000, 0);
  const source = day[0].source_system ?? null;
  return {
    kind: "lng",
    label,
    value: formatValue(gwh, "GWh/d"),
    unit: "GWh/d",
    simulated: day.some((row) => SIM_SOURCE.test(row.source_system ?? "")),
    lines: [
      { key: "answer.lng.terminals", values: { count: day.length } },
      asOfLine(day[0].period_start_utc, source),
    ],
    asOf: day[0].period_start_utc ?? null,
    copy: copyOf(gwh, "GWh/d", 0),
    target: FUNDAMENTALS_TARGET,
  };
}

async function outagesAnswer(intent: Extract<LookupIntent, { kind: "outages" }>, reads: AnswerReads, signal: AbortSignal): Promise<AnswerView> {
  const all = await reads.outages(signal);
  const facility = intent.facility?.toLowerCase() ?? null;
  const rows = all.filter((row) =>
    (!intent.zone || (row.balancing_zone ?? "").toUpperCase() === intent.zone) &&
    (!facility || `${row.facility_name} ${row.facility_id}`.toLowerCase().includes(facility)));
  const scope = intent.zone ?? intent.facility ?? null;
  const label: AnswerText = scope ? { key: "answer.outages.label_scope", values: { scope } } : { key: "answer.outages.label" };
  const target = { kind: "task", mode: "desk", task: "events" } as const;
  if (!rows.length) {
    return { kind: "outages", label, value: "0", sentence: null, lines: [{ key: "answer.outages.none" }], target, copy: { value: "0", withUnit: "0" } };
  }
  const active = rows.filter((row) => row.status === "active");
  const sized = active.filter((row) => typeof row.unavailable_gwh_d === "number");
  const offline = sized.reduce((sum, row) => sum + (row.unavailable_gwh_d as number), 0);
  const top = [...rows]
    .sort((a, b) => (b.unavailable_gwh_d ?? -1) - (a.unavailable_gwh_d ?? -1))
    .slice(0, 3)
    .map((row) => `${row.facility_name || row.facility_id} (${row.balancing_zone || "–"}) ${typeof row.unavailable_gwh_d === "number" ? `${formatValue(row.unavailable_gwh_d, "GWh/d")} GWh/d` : `${formatValue(row.unavailable_capacity, row.unit)} ${row.unit}`}${row.end_utc ? ` → ${shortDay(row.end_utc)}` : ""}`);
  const latest = rows.reduce((max, row) => ((row.published_at_utc ?? "") > max ? row.published_at_utc ?? "" : max), "");
  return {
    kind: "outages",
    label,
    value: String(active.length),
    unit: { key: "answer.outages.active_unit" },
    simulated: rows.some((row) => (row.source_reference ?? "").toLowerCase().startsWith("demo") || SIM_SOURCE.test(row.source_system ?? "")),
    lines: [
      {
        key: sized.length === active.length ? "answer.outages.offline" : "answer.outages.offline_partial",
        values: { gwh: formatValue(offline, "GWh/d"), scheduled: rows.length - active.length, sized: sized.length, active: active.length },
      },
      { key: "answer.outages.top", values: { items: top.join(" · ") } },
      asOfLine(latest || null, "REMIT"),
    ],
    asOf: latest || null,
    copy: { value: String(active.length), withUnit: String(active.length) },
    target,
  };
}

function daysIn(month: string): number {
  const [year, index] = month.split("-").map(Number);
  return new Date(Date.UTC(year, index, 0)).getUTCDate();
}

async function positionAnswer(intent: Extract<LookupIntent, { kind: "position" }>, reads: AnswerReads, signal: AbortSignal): Promise<AnswerView> {
  const target = { kind: "task", mode: "book", task: "position" } as const;
  if (intent.month && intent.hub) {
    const ladder = await reads.ladder(signal);
    const month = `${intent.month.year}-${String(intent.month.month + 1).padStart(2, "0")}`;
    const row = ladder.rows.find((item) => item.hub.toUpperCase() === intent.hub && item.month === month);
    const label = `${intent.hub} ${intent.month.label}`;
    if (!row) return { kind: "position", label, value: null, sentence: { key: "answer.position.none" }, lines: [], target };
    const perDay = row.net_mwh / daysIn(month);
    return {
      kind: "position",
      label: { key: "answer.position.label_for", values: { what: label } },
      value: formatValue(perDay, "MWh/d", true),
      unit: "MWh/d",
      lines: [
        { key: "answer.position.month_total", values: { mwh: formatValue(row.net_mwh, "MWh", true), physical: formatValue(row.physical_mwh, "MWh", true), financial: formatValue(row.financial_mwh, "MWh", true) } },
        asOfLine(ladder.horizon.start),
      ],
      asOf: ladder.horizon.start,
      copy: copyOf(perDay, "MWh/d", 0),
      target,
    };
  }
  const today = await reads.deskToday(signal);
  const figures = intent.hub
    ? (() => {
        const hub = today.rows[2]?.hubs?.find((item) => item.hub.toUpperCase() === intent.hub);
        return hub ? { today: hub.position_today, front: hub.position_front_month } : null;
      })()
    : today.rows[0]?.position
      ? { today: today.rows[0].position.today, front: today.rows[0].position.front_month }
      : null;
  const label: AnswerText = { key: "answer.position.label_for", values: { what: intent.hub ?? "" } };
  if (!figures || figures.today.value === null) {
    return { kind: "position", label: intent.hub ? label : { key: "answer.position.label" }, value: null, sentence: { key: "answer.position.none" }, lines: [], target };
  }
  return {
    kind: "position",
    label: intent.hub ? label : { key: "answer.position.label" },
    value: formatValue(figures.today.value, "MWh/d", true),
    unit: "MWh/d",
    lines: [
      { key: "answer.position.front", values: { label: figures.front.label, value: formatValue(figures.front.value, "MWh/d", true) } },
      asOfLine(figures.today.as_of),
    ],
    asOf: figures.today.as_of,
    copy: copyOf(figures.today.value, "MWh/d", 0),
    target,
  };
}

function money(value: number, currency: string): string {
  const symbol = currency === "EUR" ? "€" : currency === "GBP" ? "£" : currency === "USD" ? "$" : `${currency} `;
  const sign = value < 0 ? "−" : "";
  const magnitude = Math.abs(value);
  return magnitude >= 1e6 ? `${sign}${symbol}${(magnitude / 1e6).toFixed(2)}m` : `${sign}${symbol}${Math.round(magnitude).toLocaleString("en-GB")}`;
}

async function creditAnswer(name: string, reads: AnswerReads, signal: AbortSignal): Promise<AnswerView> {
  const { rows, as_of } = await reads.credit(signal);
  const wanted = name.toLowerCase();
  const matches = rows.filter((row) => row.counterparty.toLowerCase().includes(wanted) || row.counterparty_id.toLowerCase() === wanted);
  const target = { kind: "task", mode: "book", task: "limits" } as const;
  const row = matches[0];
  if (!row) {
    return { kind: "credit", label: name, value: null, sentence: { key: "answer.credit.none", values: { name } }, lines: [], target };
  }
  return {
    kind: "credit",
    label: { key: "answer.credit.label", values: { name: row.counterparty } },
    value: money(row.headroom, row.currency),
    unit: null,
    lines: [
      { key: `answer.credit.status.${row.status}`, values: { used: row.utilisation_pct === null ? "–" : row.utilisation_pct.toFixed(0), exposure: money(row.net_exposure, row.currency), limit: money(row.limit, row.currency) } },
      ...(matches.length > 1 ? [{ key: "answer.more_matches", values: { count: matches.length - 1 } }] : []),
      asOfLine(as_of),
    ],
    asOf: as_of,
    copy: { value: clipboardNumber(row.headroom, 0), withUnit: `${clipboardNumber(row.headroom, 0)} ${row.currency}` },
    target,
  };
}

async function contractAnswer(name: string, reads: AnswerReads, signal: AbortSignal): Promise<AnswerView> {
  const wanted = name.toLowerCase();
  const matches = (await reads.contracts(signal)).filter((row) =>
    `${row.contract_name ?? ""} ${row.contract_id}`.toLowerCase().includes(wanted));
  const target = { kind: "task", mode: "deals", task: "contracts" } as const;
  const row = matches[0];
  if (!row) return { kind: "contract", label: name, value: null, sentence: { key: "answer.contract.none", values: { name } }, lines: [], target };
  const quantity = Number(row.delivery_quantity_mwh_per_day ?? 0);
  return {
    kind: "contract",
    label: row.contract_name || row.contract_id,
    value: formatValue(quantity, "MWh/d"),
    unit: "MWh/d",
    lines: [
      { key: "answer.contract.detail", values: { point: row.delivery_point_name ?? "–", year: row.gas_year ?? "–" } },
      ...(matches.length > 1 ? [{ key: "answer.more_matches", values: { count: matches.length - 1 } }] : []),
      ...(row.updated_at_utc ? [asOfLine(row.updated_at_utc)] : []),
    ],
    asOf: row.updated_at_utc ?? null,
    copy: copyOf(quantity, "MWh/d", 0),
    target,
  };
}

/** The answer for a tier 2 look-up. Throws when a read fails (the bar shows nothing then). */
export async function lookup(intent: LookupIntent, reads: AnswerReads, signal: AbortSignal): Promise<AnswerView> {
  switch (intent.kind) {
    case "price":
      return priceAnswer(intent, reads, signal);
    case "storage":
      return storageAnswer(intent.country, reads, signal);
    case "lng":
      return intent.country ? lngCountryAnswer(intent.country, reads, signal) : balanceAnswer(await reads.deskToday(signal), "lng_gwh", "lng");
    case "norway":
      return balanceAnswer(await reads.deskToday(signal), "norway_gwh", "norway");
    case "outages":
      return outagesAnswer(intent, reads, signal);
    case "position":
      return positionAnswer(intent, reads, signal);
    case "credit":
      return creditAnswer(intent.counterparty, reads, signal);
    case "contract":
      return contractAnswer(intent.name, reads, signal);
    case "convert":
      return forwardAnswer(intent, await reads.normalise(forwardRequest(intent), signal));
  }
}
