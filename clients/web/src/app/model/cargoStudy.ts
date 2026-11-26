/**
 * Research → Cargo & netback (design basis 2, D.2 item 3; CP-18): the study's form, its request
 * and the shapes its charts take. Every figure comes from the server's cargo chain
 * (`POST /api/lng/cargo-economics`); this module only arranges the form and the response.
 *
 * The voyage: no sea-distance table ships with the product (the freight-route table starts
 * empty), so the desk states the voyage itself, as a distance at a speed or as days laden, and
 * the result says so. Saved routes are offered once the firm has recorded any.
 */
import { inQuoteUnit, quoteUnit } from "./priceCharts.ts";
import { formatDeliveryMonth } from "../time/timeFormat.ts";
import type { CargoEconomicsDTO, CargoInput, CargoResultDTO, CargoTerminalDTO, FreightRouteDTO } from "@/api/client";

export type VoyageMode = "route" | "distance" | "days";

/** The form as typed: text, so a cleared field stays cleared (empty = use the assumption set). */
export interface CargoForm {
  term: "FOB" | "DES";
  arrivalMonth: string;
  pricingMonth: string;
  hh: string;
  slope: string;
  fee: string;
  cargoSize: string;
  voyageMode: VoyageMode;
  routeId: string;
  distanceNm: string;
  speedKn: string;
  ladenDays: string;
  ballast: "round" | "one_way";
  hire: string;
  boilOff: string;
  ballastFuel: string;
  portCost: string;
  insurance: string;
  canalCost: string;
  desPrice: string;
  desCurrency: "EUR" | "GBP" | "USD";
  /** The firm's assumption set chosen ("" = the organisation's approved set, if any). */
  assumptionSetId: string;
  /** Terminals to compare (empty = every terminal with terms or a tariff). */
  terminalIds: string[];
}

/** The figures an assumption set supplies; emptied when the desk picks a set, so the set applies. */
export const SET_FIELDS = ["cargoSize", "slope", "fee", "speedKn", "hire", "boilOff", "ballastFuel", "portCost", "insurance"] as const;

/** The form with the set's figures left to the set (each can still be typed over). */
export function withSet(form: CargoForm, setId: string): CargoForm {
  const next: CargoForm = { ...form, assumptionSetId: setId };
  if (setId) for (const field of SET_FIELDS) next[field] = "";
  return next;
}

/** Months from `month` (YYYY-MM), shifted by `by`. */
export function shiftMonth(month: string, by: number): string {
  const index = Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1 + by;
  return `${String(Math.floor(index / 12)).padStart(4, "0")}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** The arrival months the study offers: this month and the next `count - 1`. */
export function arrivalMonths(today: Date, count = 18): string[] {
  const first = `${today.getUTCFullYear()}-${String(today.getUTCMonth() + 1).padStart(2, "0")}`;
  return Array.from({ length: count }, (_, index) => shiftMonth(first, index));
}

/**
 * The design's worked example (C.3), every figure an assumption the desk can change: a US Gulf
 * cargo, 115 % HH + 2.50, 3.8 TBtu, 4,900 nm at 17 kn, 45,000 USD/day. Henry Hub is left empty:
 * the server reads the firm's mark or licensed data, else the EIA spot as an indicative proxy.
 */
export function exampleForm(today: Date, routes: readonly FreightRouteDTO[] = []): CargoForm {
  const arrival = shiftMonth(arrivalMonths(today, 1)[0], 2);
  return {
    term: "FOB",
    arrivalMonth: arrival,
    pricingMonth: shiftMonth(arrival, -1),
    hh: "",
    slope: "1.15",
    fee: "2.50",
    cargoSize: "3800000",
    voyageMode: routes.length > 0 ? "route" : "distance",
    routeId: routes[0]?.route_id ?? "",
    distanceNm: "4900",
    speedKn: "17",
    ladenDays: "12",
    ballast: "round",
    hire: "45000",
    boilOff: "0.10",
    ballastFuel: "2000",
    portCost: "150000",
    insurance: "0.05",
    canalCost: "",
    desPrice: "",
    desCurrency: "EUR",
    assumptionSetId: "",
    terminalIds: [],
  };
}

/**
 * What the page opens on (owner, 2026-11-19): the desk's standard cargo, US Gulf FOB arriving
 * M+2, priced from what is held. Every figure is left to the firm's records (a saved route, the
 * approved assumption set, the held Henry Hub); what they do not hold the server fills with the
 * desk standard, labelled as such. A figure typed in overrides it and is labelled "entered".
 */
export function standardForm(today: Date, routes: readonly FreightRouteDTO[] = []): CargoForm {
  const form = exampleForm(today, routes);
  for (const field of SET_FIELDS) form[field] = "";
  form.distanceNm = "";
  form.ladenDays = "";
  return form;
}

const num = (text: string): number | undefined => {
  const clean = text.trim().replace(/,/g, "");
  if (clean === "") return undefined;
  const value = Number(clean);
  return Number.isFinite(value) ? value : undefined;
};

/** The one-cargo request; empty fields are left out so the firm's assumption set applies. */
export function cargoRequest(form: CargoForm, seriesMonths = 12): {
  arrival_month: string;
  cargoes: CargoInput[];
  series_months: number;
  history_days: number;
  assumption_set_id?: string;
  terminal_ids?: string[];
} {
  // `standard`: what neither the form nor the firm's records hold is the desk standard (labelled).
  const cargo: CargoInput = { cargo_id: "study", term: form.term, q_load_mmbtu: num(form.cargoSize), standard: true };
  if (form.term === "DES") {
    cargo.des_price = num(form.desPrice);
    cargo.des_currency = form.desCurrency;
  } else {
    Object.assign(cargo, {
      pricing_month: form.pricingMonth || undefined,
      hh: num(form.hh),
      slope: num(form.slope),
      fee: num(form.fee),
      ballast: form.ballast,
      hire_per_day: num(form.hire),
      boil_off_pct_per_day: num(form.boilOff),
      ballast_fuel_mmbtu_per_day: num(form.ballastFuel),
      port_cost: num(form.portCost),
      insurance_pct: num(form.insurance),
      canal_cost: num(form.canalCost),
    });
    if (form.voyageMode === "route" && form.routeId) {
      cargo.route_id = form.routeId;
      cargo.speed_kn = num(form.speedKn);
    } else if (form.voyageMode === "days") {
      cargo.laden_days = num(form.ladenDays);
    } else {
      cargo.distance_nm = num(form.distanceNm);
      cargo.speed_kn = num(form.speedKn);
    }
  }
  const clean = Object.fromEntries(Object.entries(cargo).filter(([, value]) => value !== undefined)) as unknown as CargoInput;
  return {
    arrival_month: form.arrivalMonth,
    cargoes: [clean],
    series_months: form.term === "FOB" ? seriesMonths : 0,
    history_days: form.term === "FOB" ? HISTORY_DAYS : 0,
    ...(form.assumptionSetId ? { assumption_set_id: form.assumptionSetId } : {}),
    ...(form.terminalIds.length > 0 ? { terminal_ids: form.terminalIds } : {}),
  };
}

/** Days of Henry Hub against the hub the study asks for. */
export const HISTORY_DAYS = 365;

/** Which form field answers a blocked cargo (the server's reason). */
export function fieldForBlock(reason: string | null): keyof CargoForm | null {
  switch (reason) {
    case "no_hh_price": return "hh";
    case "no_fob_formula": return "slope";
    case "no_distance": return "distanceNm";
    case "no_charter_hire": return "hire";
    case "no_cargo_size": return "cargoSize";
    case "no_des_price": return "desPrice";
    case "no_boil_off_pct_per_day": return "boilOff";
    case "no_ballast_fuel_mmbtu_per_day": return "ballastFuel";
    case "no_port_load":
    case "no_port_discharge": return "portCost";
    case "no_insurance_pct": return "insurance";
    case "no_canal": return "canalCost";
    default: return null;
  }
}

export interface WaterfallLabels {
  step: (key: string) => string;
  hub: (hub: string, month: string) => string;
}

/** One terminal's margin, step by step, in the hub currency per MWh delivered. */
export function marginWaterfall(row: CargoTerminalDTO, labels: WaterfallLabels) {
  const simulatedHub = row.legs.some((leg) => leg.key === "hub" && leg.input_class === "simulated");
  return (row.steps ?? [])
    .filter((step) => step.amount !== null)
    .map((step) => ({
      id: step.key,
      label: step.key === "hub" ? labels.hub(row.hub, row.arrival_month) : labels.step(step.key),
      value: step.amount as number,
      kind: step.kind,
      simulated: (step.key === "hub" || step.kind === "total") && simulatedHub,
    }));
}

/** The priced terminals first (best margin first, as the server ranks them), then those left out. */
export function rankedTerminals(cargo: CargoResultDTO | null): { priced: CargoTerminalDTO[]; leftOut: CargoTerminalDTO[] } {
  const rows = cargo?.terminals ?? [];
  return { priced: rows.filter((row) => row.reason === null), leftOut: rows.filter((row) => row.reason !== null) };
}

/** Whether any hub price behind a cargo's priced rows is simulated, for the simulated scope. */
export function hubSimulatedFlags(cargo: CargoResultDTO | null): boolean[] {
  return rankedTerminals(cargo).priced.map((row) => row.legs.some((leg) => leg.key === "hub" && leg.input_class === "simulated"));
}

/** The delivered-spread line (design C.4) as chart columns: hub, delivered cost, arb. */
export function seriesChart(series: CargoEconomicsDTO["delivered_spread_series"]) {
  const points = series?.points ?? [];
  return {
    x: points.map((point) => point.arrival_month),
    hub: points.map((point) => point.hub_per_mwh),
    delivered: points.map((point) => point.delivered_per_mwh),
    arb: points.map((point) => point.arb_per_mwh),
    simulated: points.some((point) => point.grade === "simulated"),
    priced: points.filter((point) => point.arb_per_mwh !== null).length,
  };
}

/** Henry Hub as the result states it: value, class, source and, for a spot proxy, its day. */
export function henryHub(cargo: CargoResultDTO | null) {
  const leg = cargo?.legs.find((item) => item.key === "hh");
  if (!leg || leg.amount === null) return null;
  return {
    value: leg.amount,
    inputClass: leg.input_class,
    source: leg.source,
    proxy: /spot proxy/i.test(leg.source),
    day: /spot (\d{4}-\d{2}-\d{2})/.exec(leg.source)?.[1] ?? null,
    simulated: /\((?:demo, )?simulated\)/.test(leg.source),
  };
}

/** The daily Henry Hub-against-the-hub line as chart columns (gas days). */
export function historyChart(history: CargoEconomicsDTO["delivered_spread_history"]) {
  const points = history?.points ?? [];
  return {
    x: points.map((point) => point.day),
    hub: points.map((point) => point.hub_per_mwh),
    delivered: points.map((point) => point.delivered_per_mwh),
    arb: points.map((point) => point.arb_per_mwh),
    simulated: points.some((point) => point.simulated),
    last: points.length > 0 ? points[points.length - 1] : null,
  };
}

/**
 * A terminal's hub price as the desk quotes it (NBP in p/th) with the per-MWh figure the
 * comparison uses; continental hubs are already in their quotation.
 */
export function hubQuote(hub: string, perMwh: number | null, currency: string) {
  if (perMwh === null) return { value: null, unit: `${currency}/MWh`, perMwh: null, native: false };
  const converted = inQuoteUnit(hub, perMwh, `${currency}/MWh`);
  if (converted === null || quoteUnit(hub) === `${currency}/MWh`) return { value: perMwh, unit: `${currency}/MWh`, perMwh, native: false };
  return { value: converted, unit: quoteUnit(hub), perMwh, native: true };
}

/** Desk shorthand for a delivery month: "2027-01" → "Jan-27". */
export function monthLabel(month: string): string {
  return formatDeliveryMonth(month);
}

/**
 * A confirmed cargo (an LNG cargo confirmation under an MSPA, CONTRACT_TYPES.md) as the study's
 * inputs: term, size, arrival and pricing months and, for a Henry Hub formula, its slope and
 * constant. A Brent, hub or fixed formula fills what it can and leaves the HH terms as they
 * were, so nothing is priced on a formula the cargo does not have.
 */
export function formFromConfirmation(form: CargoForm, terms: Record<string, unknown>): CargoForm {
  const text = (value: unknown) => (value === null || value === undefined ? "" : String(value));
  const window = text(terms.narrowed_start) || text(terms.window_start);
  const next: CargoForm = {
    ...form,
    term: terms.delivery_term === "FOB" ? "FOB" : "DES",
    cargoSize: text(terms.quantity_mmbtu) || form.cargoSize,
    arrivalMonth: window ? window.slice(0, 7) : form.arrivalMonth,
    pricingMonth: text(terms.pricing_month) || form.pricingMonth,
    boilOff: text(terms.boil_off_pct_per_day) || form.boilOff,
  };
  if (terms.price_formula === "hh") {
    next.slope = text(terms.slope);
    next.fee = text(terms.constant);
  }
  return next;
}
