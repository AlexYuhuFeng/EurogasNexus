/**
 * What the Prices charts plot (UX-09), from the normalized market rows the board already reads.
 *
 * - The forward curve of one hub: the latest close of each delivery month ("2026-12"), in the
 *   hub's quotation (NBP in pence per therm, TTF in EUR/MWh: AGENTS.md rule 17). NBP rows are
 *   stored per MWh in GBP; the change to p/th is a unit conversion, not FX.
 * - The NBP–TTF spread by delivery month, in p/th: both legs from the backend's GBP-normalized
 *   price (`price_gbp_mwh`, converted by the backend at its declared ECB rate), so the client
 *   does no FX arithmetic; the difference is then put in pence per therm.
 *
 * Pure: no DOM, tested with `node --test`.
 */

/** MWh in one therm (100,000 Btu): 1 GBP/MWh is 2.9307107 p/th. */
export const MWH_PER_THERM = 0.029307107;

export interface CurveRow {
  hub: string;
  tenor: string;
  price: number;
  unit: string;
  observed_at_utc: string;
  is_gas_price?: boolean;
  price_gbp_mwh?: number | null;
  source_system?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface CurvePoints {
  months: string[];
  values: (number | null)[];
  unit: string;
  simulated: boolean;
  /** The newest observation behind the points (ISO). */
  asOf: string | null;
}

const MONTH = /^\d{4}-\d{2}$/;

/** The quotation a hub is shown in (the desk's own). */
export function quoteUnit(hub: string): string {
  return hub.toUpperCase() === "NBP" ? "GBp/th" : "EUR/MWh";
}

/** A price in the hub's quotation, or null when the stored unit cannot be put in it. */
export function inQuoteUnit(hub: string, price: number, unit: string): number | null {
  const target = quoteUnit(hub);
  const normalized = unit.replace(/\s+/g, "");
  if (normalized.toUpperCase() === target.toUpperCase()) return price;
  if (target === "GBp/th" && normalized.toUpperCase() === "GBP/MWH") return price * 100 * MWH_PER_THERM;
  if (target === "GBp/th" && /^(p\/th|GBX\/th)$/i.test(normalized)) return price;
  return null;
}

function isSimulated(row: CurveRow): boolean {
  return /_sim$/i.test(row.source_system ?? "") || row.metadata_json?.simulated === true;
}

/** The latest row per delivery month of one hub (later observation wins; provider over demo). */
function latestByMonth(rows: readonly CurveRow[], hub: string): Map<string, CurveRow> {
  const latest = new Map<string, CurveRow>();
  for (const row of rows) {
    if (row.hub?.toUpperCase() !== hub.toUpperCase() || !MONTH.test(row.tenor) || row.is_gas_price === false) continue;
    if (!Number.isFinite(row.price)) continue;
    const held = latest.get(row.tenor);
    const better = !held
      || (isSimulated(held) && !isSimulated(row))
      || (isSimulated(held) === isSimulated(row) && Date.parse(row.observed_at_utc) > Date.parse(held.observed_at_utc));
    if (better) latest.set(row.tenor, row);
  }
  return latest;
}

/** Hubs with at least two delivery months on the curve, majors first. */
export function curveHubs(rows: readonly CurveRow[]): string[] {
  const counts = new Map<string, number>();
  for (const row of rows) if (row.hub && MONTH.test(row.tenor)) counts.set(row.hub.toUpperCase(), (counts.get(row.hub.toUpperCase()) ?? 0) + 1);
  const order = ["TTF", "NBP", "THE", "PEG", "ZTP", "PSV"];
  return [...counts].filter(([, count]) => count >= 2).map(([hub]) => hub)
    .sort((a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99) || a.localeCompare(b));
}

/** Every month from the first to the last, so a month without a quote is a gap, not skipped. */
function monthRange(months: readonly string[]): string[] {
  if (months.length === 0) return [];
  const sorted = [...months].sort();
  const out: string[] = [];
  let [year, month] = sorted[0].split("-").map(Number);
  const last = sorted[sorted.length - 1];
  for (let guard = 0; guard < 240; guard += 1) {
    const key = `${year}-${String(month).padStart(2, "0")}`;
    out.push(key);
    if (key >= last) break;
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return out;
}

/** One hub's forward curve by delivery month, in its quotation; `fromMonth` drops past months. */
export function forwardCurve(rows: readonly CurveRow[], hub: string, fromMonth?: string): CurvePoints {
  const latest = latestByMonth(rows, hub);
  const months = monthRange([...latest.keys()].filter((month) => !fromMonth || month >= fromMonth));
  const used = months.map((month) => latest.get(month)).filter((row): row is CurveRow => Boolean(row));
  return {
    months,
    values: months.map((month) => {
      const row = latest.get(month);
      if (!row) return null;
      const value = inQuoteUnit(hub, row.price, row.unit);
      return value == null ? null : Number(value.toFixed(4));
    }),
    unit: quoteUnit(hub),
    simulated: used.length > 0 && used.every(isSimulated),
    asOf: used.reduce<string | null>((newest, row) => (!newest || row.observed_at_utc > newest ? row.observed_at_utc : newest), null),
  };
}

/**
 * NBP minus TTF by delivery month in p/th, from both legs' backend GBP/MWh prices. A month
 * where either leg is missing, or has no GBP price, is a gap.
 */
export function nbpTtfSpread(rows: readonly CurveRow[], fromMonth?: string): CurvePoints {
  const nbp = latestByMonth(rows, "NBP");
  const ttf = latestByMonth(rows, "TTF");
  const both = [...nbp.keys()].filter((month) => ttf.has(month) && (!fromMonth || month >= fromMonth));
  const months = monthRange(both);
  const used: CurveRow[] = [];
  const values = months.map((month) => {
    const near = nbp.get(month);
    const far = ttf.get(month);
    if (!near || !far || near.price_gbp_mwh == null || far.price_gbp_mwh == null) return null;
    used.push(near, far);
    return Number(((near.price_gbp_mwh - far.price_gbp_mwh) * 100 * MWH_PER_THERM).toFixed(4));
  });
  return {
    months,
    values,
    unit: "GBp/th",
    simulated: used.length > 0 && used.some(isSimulated),
    asOf: used.reduce<string | null>((newest, row) => (!newest || row.observed_at_utc > newest ? row.observed_at_utc : newest), null),
  };
}
