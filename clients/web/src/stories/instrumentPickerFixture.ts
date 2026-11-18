/**
 * A fixture instrument catalogue (the `GET /api/market/instruments` shape) for the picker's
 * story page and tests. It lists instruments only, never a price. THE is marked simulated so
 * the `sim` mark is exercised; nothing here is presented as market data.
 */

import type {
  InstrumentCatalogueDTO,
  InstrumentDTO,
  InstrumentProductKind,
  InstrumentSourceClass,
} from "../api/comparablePrices.ts";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const yy = (year: number) => String(year % 100).padStart(2, "0");

function instrument(
  hub: string,
  kind: InstrumentProductKind,
  code: string,
  tenor: string,
  nativeUnit: string,
  options: { sourceClass?: InstrumentSourceClass; observations?: number; asOf: string },
): InstrumentDTO {
  const sourceClass = options.sourceClass ?? "indicative";
  const observations = options.observations ?? 260;
  return {
    id: `${hub}:${code}`,
    hub,
    instrument_kind: "outright",
    product_kind: kind,
    code,
    label: `${hub} ${code}`,
    tenor,
    native_unit: nativeUnit,
    currency: nativeUnit.startsWith("GBp") ? "GBP" : nativeUnit.split("/")[0],
    stored_unit: nativeUnit === "GBp/th" ? "GBP/MWh" : nativeUnit,
    source_class: sourceClass,
    simulated: sourceClass === "simulated",
    best_source: sourceClass === "simulated" ? "DEMO_Sim" : "Settlement_Import",
    sources: [],
    observations,
    thin: observations < 30,
    first: "2025-11-17",
    last: options.asOf.slice(0, 10),
    last_as_of: options.asOf,
    delivery: null,
    expired: false,
  };
}

/** Hubs with spot, rolling, month, quarter, season and year tenors from `today`. */
export function fixtureCatalogue(today: Date): InstrumentCatalogueDTO {
  const asOf = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - 1, 18)).toISOString();
  const year = today.getUTCFullYear();
  const month = today.getUTCMonth();
  const months = (count: number) =>
    Array.from({ length: count }, (_, index) => {
      const at = year * 12 + month + 1 + index;
      return { code: `${MONTHS[at % 12]}-${yy(Math.floor(at / 12))}`, iso: `${Math.floor(at / 12)}-${String((at % 12) + 1).padStart(2, "0")}` };
    });
  const quarter = Math.floor(month / 3);
  const quarters = Array.from({ length: 4 }, (_, index) => {
    const at = year * 4 + quarter + 1 + index;
    return `Q${(at % 4) + 1}-${yy(Math.floor(at / 4))}`;
  });
  const hub = (
    code: string,
    name: string,
    unit: string,
    spec: { monthCount: number; sourceClass?: InstrumentSourceClass; spot?: string[]; thinMonths?: boolean },
  ) => {
    const options = { sourceClass: spec.sourceClass, asOf };
    const kinds: Array<{ kind: InstrumentProductKind; instruments: InstrumentDTO[] }> = [];
    const spot = (spec.spot ?? ["DA"]).map((item) => instrument(code, "spot", item, item === "DA" ? "day-ahead" : item === "WD" ? "within-day" : item.toLowerCase(), unit, options));
    if (spot.length) kinds.push({ kind: "spot", instruments: spot });
    if (spec.monthCount > 0) {
      kinds.push({ kind: "rolling", instruments: [instrument(code, "rolling", "M+1", "month-ahead", unit, options)] });
      kinds.push({
        kind: "month",
        instruments: months(spec.monthCount).map((item, index) =>
          instrument(code, "month", item.code, item.iso, unit, { ...options, observations: spec.thinMonths && index > 8 ? 12 : 180 }),
        ),
      });
      kinds.push({ kind: "quarter", instruments: quarters.map((item) => instrument(code, "quarter", item, item.toLowerCase(), unit, options)) });
      kinds.push({
        kind: "season",
        instruments: [`Sum-${yy(year + 1)}`, `Win-${yy(year + 1)}`].map((item) => instrument(code, "season", item, item.toLowerCase(), unit, options)),
      });
      kinds.push({
        kind: "year",
        instruments: [`Cal-${yy(year + 1)}`, `Cal-${yy(year + 2)}`].map((item) => instrument(code, "year", item, item.toLowerCase(), unit, options)),
      });
    }
    const all = kinds.flatMap((item) => item.instruments);
    return {
      hub: code,
      name,
      country: "",
      native_unit: unit,
      currency: unit.startsWith("GBp") ? "GBP" : unit.split("/")[0],
      instrument_count: all.length,
      source_class: spec.sourceClass ?? ("indicative" as InstrumentSourceClass),
      simulated: spec.sourceClass === "simulated",
      last_as_of: asOf,
      kinds: kinds.map((item) => ({ ...item, count: item.instruments.length })),
    };
  };
  return {
    levels: ["hub", "product_kind", "tenor"],
    product_kinds: ["spot", "rolling", "month", "quarter", "season", "year", "other"],
    thin_series_days: 30,
    as_of: asOf,
    hubs: [
      hub("TTF", "Title Transfer Facility", "EUR/MWh", { monthCount: 18, spot: ["WD", "DA", "WE"], thinMonths: true }),
      hub("NBP", "National Balancing Point", "GBp/th", { monthCount: 12, spot: ["WD", "DA"] }),
      hub("THE", "Trading Hub Europe", "EUR/MWh", { monthCount: 6, sourceClass: "simulated" }),
      hub("PEG", "Point d'Échange de Gaz", "EUR/MWh", { monthCount: 3 }),
      hub("ZTP", "Zeebrugge Trading Point", "EUR/MWh", { monthCount: 3, spot: ["DA"] }),
      hub("HH", "Henry Hub", "USD/MMBtu", { monthCount: 0, spot: ["Spot"], sourceClass: "sourced" }),
    ],
  };
}
