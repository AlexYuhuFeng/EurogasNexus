import type { PositionLadderDTO, PositionLadderRowDTO } from "@/api/client";

/** Months in delivery order, each with its hubs, as a trader reads a position ladder. */
export interface LadderMonth {
  month: string;
  rows: PositionLadderRowDTO[];
  net_mwh: number;
}

export function groupLadderByMonth(rows: readonly PositionLadderRowDTO[]): LadderMonth[] {
  const months = new Map<string, LadderMonth>();
  for (const row of rows) {
    const month = months.get(row.month) ?? { month: row.month, rows: [], net_mwh: 0 };
    month.rows.push(row);
    month.net_mwh += row.net_mwh;
    months.set(row.month, month);
  }
  return [...months.values()].sort((a, b) => a.month.localeCompare(b.month));
}

/** Share of physical volume offset by financial trades across the whole ladder. */
export function overallHedgeRatio(ladder: Pick<PositionLadderDTO, "totals">): number | null {
  const { physical_mwh, financial_mwh } = ladder.totals;
  return Math.abs(physical_mwh) < 1e-9 ? null : -financial_mwh / physical_mwh;
}

/** The trading-screen label for a month key: 2026-11 becomes Nov-26. */
export function ladderMonthLabel(month: string): string {
  const [year, number] = month.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[Number(number) - 1] ?? number}-${year.slice(2)}`;
}

/** Width of a net-position bar as a share of the largest absolute net in the ladder. */
export function barShare(value: number, rows: readonly PositionLadderRowDTO[]): number {
  const largest = Math.max(1, ...rows.map((row) => Math.abs(row.net_mwh)));
  return Math.min(1, Math.abs(value) / largest);
}
