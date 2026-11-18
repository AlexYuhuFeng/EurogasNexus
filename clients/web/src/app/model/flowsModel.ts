/**
 * Research → Fundamentals → Flows (CP-17), the pure part: where north-west Europe's supply came
 * from, day by day, as shares of the supply the three sources make (Norwegian pipeline gas,
 * LNG send-out, storage withdrawal). A day storage injects instead of withdrawing, it supplies
 * nothing: its share is zero and the day is counted, so the chart says why storage vanishes
 * in summer. Tested in tests/flowsModel.test.ts.
 */
import type { NweBalanceDayDTO } from "../../api/client.ts";

export interface SupplyShares {
  days: string[];
  pipeline: (number | null)[];
  lng: (number | null)[];
  storage: (number | null)[];
  /** Days storage injected (its share counted as zero). */
  injectionDays: number;
}

export function supplyShares(history: readonly NweBalanceDayDTO[]): SupplyShares {
  const out: SupplyShares = { days: [], pipeline: [], lng: [], storage: [], injectionDays: 0 };
  for (const day of history) {
    const pipeline = day.norway_gwh;
    const lng = day.lng_gwh;
    const net = day.storage_net_withdrawal_gwh;
    out.days.push(day.day);
    if (pipeline == null || lng == null || net == null) {
      out.pipeline.push(null);
      out.lng.push(null);
      out.storage.push(null);
      continue;
    }
    const storage = Math.max(0, net);
    if (net < 0) out.injectionDays += 1;
    const total = pipeline + lng + storage;
    if (!(total > 0)) {
      out.pipeline.push(null);
      out.lng.push(null);
      out.storage.push(null);
      continue;
    }
    out.pipeline.push(Number(((100 * pipeline) / total).toFixed(2)));
    out.lng.push(Number(((100 * lng) / total).toFixed(2)));
    out.storage.push(Number(((100 * storage) / total).toFixed(2)));
  }
  return out;
}
