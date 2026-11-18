/** Supply shares (CP-17 Flows): hand-computed; an injection day gives storage no share. */
import assert from "node:assert/strict";
import test from "node:test";

import { supplyShares } from "../src/app/model/flowsModel.ts";

const day = (d: string, norway: number | null, lng: number | null, storage: number | null) =>
  ({ day: d, norway_gwh: norway, lng_gwh: lng, storage_net_withdrawal_gwh: storage, call_gwh: 0 }) as never;

test("shares of the supply the three sources make, summing to 100", () => {
  // 3,000 + 1,000 + 1,000 = 5,000: 60 / 20 / 20.
  const shares = supplyShares([day("2026-11-15", 3000, 1000, 1000)]);
  assert.deepEqual([shares.pipeline[0], shares.lng[0], shares.storage[0]], [60, 20, 20]);
});

test("a day storage injects gives it no share and is counted; a gap stays a gap", () => {
  const shares = supplyShares([day("2026-07-01", 3000, 1000, -500), day("2026-07-02", null, 1000, 0)]);
  assert.deepEqual([shares.pipeline[0], shares.lng[0], shares.storage[0]], [75, 25, 0]);
  assert.equal(shares.injectionDays, 1);
  assert.deepEqual([shares.pipeline[1], shares.lng[1], shares.storage[1]], [null, null, null]);
});
