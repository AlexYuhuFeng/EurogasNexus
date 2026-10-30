import assert from "node:assert/strict";
import test from "node:test";

import type { PositionLadderRowDTO } from "../src/api/client.ts";
import {
  barShare,
  groupLadderByMonth,
  ladderMonthLabel,
  overallHedgeRatio,
} from "../src/app/model/positionLadderModel.ts";

const rows: PositionLadderRowDTO[] = [
  { hub: "TTF", month: "2026-12", physical_mwh: 310_000, financial_mwh: 0, net_mwh: 310_000, hedge_ratio: 0 },
  { hub: "NBP", month: "2026-12", physical_mwh: -62_000, financial_mwh: 0, net_mwh: -62_000, hedge_ratio: 0 },
  { hub: "TTF", month: "2026-11", physical_mwh: 300_000, financial_mwh: -180_000, net_mwh: 120_000, hedge_ratio: 0.6 },
];

test("months come in delivery order with their net", () => {
  const months = groupLadderByMonth(rows);
  assert.deepEqual(months.map((m) => [m.month, m.net_mwh]), [["2026-11", 120_000], ["2026-12", 248_000]]);
  assert.equal(ladderMonthLabel("2026-11"), "Nov-26");
});

test("hedge ratio and bar widths", () => {
  assert.equal(overallHedgeRatio({ totals: { physical_mwh: 548_000, financial_mwh: -180_000, net_mwh: 368_000 } }), 180_000 / 548_000);
  assert.equal(overallHedgeRatio({ totals: { physical_mwh: 0, financial_mwh: 10, net_mwh: 10 } }), null);
  assert.equal(barShare(310_000, rows), 1);
  assert.equal(barShare(-62_000, rows), 0.2);
});
