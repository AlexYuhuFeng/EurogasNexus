import type { PositionLadderDTO, PositionLadderRowDTO } from "@/api/client";
import { formatDeliveryMonth } from "../time/timeFormat.ts";

/** Months in delivery order, each with its hubs, as a trader reads a position ladder. */
export interface LadderMonth {
  month: string;
  rows: PositionLadderRowDTO[];
  net_mwh: number;
}

/** The net position a trader reads: flat-price exposure (an index-priced contract is on its
 * index, not long the flat price); an older server sends only the net volume. */
export function netPosition(row: { net_mwh: number; price_exposure_mwh?: number }): number {
  return row.price_exposure_mwh ?? row.net_mwh;
}

export function groupLadderByMonth(rows: readonly PositionLadderRowDTO[]): LadderMonth[] {
  const months = new Map<string, LadderMonth>();
  for (const row of rows) {
    const month = months.get(row.month) ?? { month: row.month, rows: [], net_mwh: 0 };
    month.rows.push(row);
    month.net_mwh += netPosition(row);
    months.set(row.month, month);
  }
  return [...months.values()].sort((a, b) => a.month.localeCompare(b.month));
}

/** Share of the physical flat-price exposure offset by financial trades across the ladder
 * (an index-priced contract has none to hedge). */
export function overallHedgeRatio(ladder: Pick<PositionLadderDTO, "totals">): number | null {
  const { physical_mwh, financial_mwh, index_mwh } = ladder.totals;
  const exposed = physical_mwh + (index_mwh ?? 0);
  return Math.abs(exposed) < 1e-9 ? null : -financial_mwh / exposed;
}

/** The trading-screen label for a month key: 2026-11 becomes Nov-26. */
export function ladderMonthLabel(month: string): string {
  return formatDeliveryMonth(month);
}

/** Width of a net-position bar as a share of the largest absolute net in the ladder. */
export function barShare(value: number, rows: readonly PositionLadderRowDTO[]): number {
  const largest = Math.max(1, ...rows.map((row) => Math.abs(netPosition(row))));
  return Math.min(1, Math.abs(value) / largest);
}

/**
 * Provenance on demand (QA-L-03): the firm's cargoes behind a ladder row, one line per cargo id
 * with its plan send-out and recorded hedge; undefined for a row with no cargo.
 */
export function cargoTitle(
  row: Pick<PositionLadderRowDTO, "cargoes">,
  t: (key: string, options?: Record<string, unknown>) => string,
  format: (value: number) => string,
): string | undefined {
  if (!row.cargoes || row.cargoes.length === 0) return undefined;
  return row.cargoes
    .map((cargo) =>
      t("position.cargo_line", { cargo: cargo.cargo_id, physical: format(cargo.physical_mwh), financial: format(cargo.financial_mwh) }),
    )
    .join("\n");
}
