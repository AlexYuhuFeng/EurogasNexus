import assert from "node:assert/strict";
import test from "node:test";

import type { GasDayCutoffDTO } from "../src/api/client.ts";
import { formatQuantity, mwText, nextCutoff, timeLeft } from "../src/app/model/gasDayModel.ts";

const cut = (key: GasDayCutoffDTO["key"], at: string): GasDayCutoffDTO => ({
  key, name: null, at_utc: at, basis: "assumption", source: "default", passed: false,
});

test("the next cut-off is the first one still ahead; none after the gas day ends", () => {
  const cuts = [
    cut("nomination", "2026-11-18T13:00:00+00:00"),
    cut("last_renomination", "2026-11-20T02:00:00+00:00"),
    cut("gas_day_end", "2026-11-20T05:00:00+00:00"),
  ];
  const now = Date.parse("2026-11-19T09:15:00Z");
  assert.equal(nextCutoff(cuts, now)?.key, "last_renomination");
  assert.deepEqual(timeLeft(cuts[1].at_utc, now), { hours: 16, minutes: 45 });
  assert.equal(nextCutoff(cuts, Date.parse("2026-11-20T03:00:00Z"))?.key, "gas_day_end");
  assert.equal(nextCutoff(cuts, Date.parse("2026-11-20T06:00:00Z")), null);
  assert.deepEqual(timeLeft(cuts[0].at_utc, now), { hours: 0, minutes: 0 });
});

test("quantities read in desk format, signed for the net, MW beside a continental figure", () => {
  assert.equal(formatQuantity({ value: 781264, unit: "th/d", mwh: 22896.6 }, true), "+781,264");
  assert.equal(formatQuantity({ value: -503.3, unit: "MWh/d", mwh: -503.3, mw: -21 }, true), "−503");
  assert.equal(formatQuantity({ value: 0.2, unit: "MWh/d", mwh: 0.2 }, true), "0");
  assert.equal(mwText({ value: -503.3, unit: "MWh/d", mwh: -503.3, mw: -21 }, true), "−21");
  assert.equal(mwText({ value: 781264, unit: "th/d", mwh: 22896.6 }), null);
});
