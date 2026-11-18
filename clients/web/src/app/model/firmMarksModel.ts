/**
 * The firm's marks grid (CP-14, B.7 "Enter marks"): hub × month in each hub's native unit.
 * Pure helpers; the server validates every cell again (unknown hub, period, unit, implausible
 * value) and stores the class "firm's mark" whatever the client sends.
 */

/** Hubs offered in the grid, each with its native quotation (NBP in pence per therm). */
export const MARK_HUBS: readonly { code: string; unit: string }[] = [
  { code: "TTF", unit: "EUR/MWh" },
  { code: "THE", unit: "EUR/MWh" },
  { code: "PEG", unit: "EUR/MWh" },
  { code: "ZTP", unit: "EUR/MWh" },
  { code: "NBP", unit: "GBp/th" },
  { code: "PSV", unit: "EUR/MWh" },
  { code: "PVB", unit: "EUR/MWh" },
  { code: "CEGH", unit: "EUR/MWh" },
];

export interface MarkRow {
  hub: string;
  /** Month ("YYYY-MM") → the typed text. */
  values: Record<string, string>;
}

/** The next `count` delivery months after `today`, as "YYYY-MM" (front month first). */
export function nextMonths(today: Date, count: number): string[] {
  const months: string[] = [];
  let year = today.getUTCFullYear();
  let month = today.getUTCMonth() + 1;
  for (let index = 0; index < count; index += 1) {
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
    months.push(`${year}-${String(month).padStart(2, "0")}`);
  }
  return months;
}

export type MarkCells =
  | { cells: { hub: string; period: string; value: number; unit: string }[] }
  | { error: "empty" | "not_a_number" | "duplicate_hub"; cell: string };

/** The typed grid as cells for the server; blanks are skipped, a non-number names its cell. */
export function markRowsToCells(rows: readonly MarkRow[], months: readonly string[]): MarkCells {
  const seen = new Set<string>();
  const cells: { hub: string; period: string; value: number; unit: string }[] = [];
  for (const row of rows) {
    if (seen.has(row.hub)) return { error: "duplicate_hub", cell: row.hub };
    seen.add(row.hub);
    const unit = MARK_HUBS.find((hub) => hub.code === row.hub)?.unit ?? "EUR/MWh";
    for (const month of months) {
      const text = (row.values[month] ?? "").trim().replace(",", ".");
      if (!text) continue;
      const value = Number(text);
      if (!Number.isFinite(value)) return { error: "not_a_number", cell: `${row.hub} ${month}` };
      cells.push({ hub: row.hub, period: month, value, unit });
    }
  }
  if (cells.length === 0) return { error: "empty", cell: "" };
  return { cells };
}
