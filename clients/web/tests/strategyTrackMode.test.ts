/** Research -> Spreads -> Track: which kind of shadow run a StrategySpec starts. */
import assert from "node:assert/strict";
import test from "node:test";

import type { StrategySpecDTO } from "../src/api/spreads.ts";
import { trackModeOf } from "../src/app/model/strategyTrack.ts";

function spec(tenors: string[], kind: string, rule: StrategySpecDTO["rule"]): StrategySpecDTO {
  return {
    kind,
    legs: tenors.map((tenor, index) => ({ hub: index ? "NBP" : "TTF", tenor, weight: index ? -1 : 1 })),
    rule,
  } as unknown as StrategySpecDTO;
}

const RULE = { kind: "zscore", lookback: 20, entry_z: 2, exit_z: 0.5 } as const;

test("a backtested daily rule on prompt legs is tracked daily with that rule", () => {
  assert.equal(trackModeOf(spec(["DA", "DA"], "history", RULE)), "daily");
  assert.equal(trackModeOf(spec(["WD", "DA"], "history", RULE)), "daily");
});

test("prompt legs without a daily rule are tracked intraday", () => {
  assert.equal(trackModeOf(spec(["WD", "DA"], "history", null)), "intraday");
  assert.equal(trackModeOf(spec(["WE", "BOM"], "curve", null)), "intraday");
});

test("anything else cannot be tracked", () => {
  assert.equal(trackModeOf(spec(["M+1", "Q+1"], "history", null)), null);
  assert.equal(trackModeOf(spec(["DA"], "history", RULE)), null);
  assert.equal(trackModeOf(null), null);
});
