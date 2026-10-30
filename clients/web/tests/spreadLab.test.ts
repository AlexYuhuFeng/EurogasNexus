import assert from "node:assert/strict";
import test from "node:test";

import type { SpreadSeriesDTO } from "../src/api/client.ts";
import {
  defaultSpreadDraft,
  seriesKey,
  spreadAnalysisRequest,
  spreadDraftBlocker,
  spreadFormula,
} from "../src/app/model/spreadLabModel.ts";

function series(hub: string, tenor: string, unit = "EUR/MWh", simulated = false): SpreadSeriesDTO {
  return {
    hub, tenor, source_system: "EEX", currency: "EUR", unit,
    first: "2026-01-02", last: "2026-10-29", days: 200, simulated,
  };
}

const CATALOGUE = [
  series("NBP", "day-ahead", "GBP/MWh"),
  series("THE", "month-ahead"),
  series("TTF", "month-ahead"),
  series("PEG", "month-ahead", "EUR/MWh", true),
];

test("the lab opens on a recognisable same-tenor, same-unit spread of real series", () => {
  const draft = defaultSpreadDraft(CATALOGUE);
  assert.deepEqual(
    draft.legs.map((leg) => [leg.seriesKey, leg.weight]),
    [["THE|month-ahead|EEX", 1], ["TTF|month-ahead|EEX", -1]],
  );
  assert.equal(spreadFormula(draft, CATALOGUE), "THE month-ahead −TTF month-ahead");
  assert.equal(spreadDraftBlocker(draft, CATALOGUE), null);
  const request = spreadAnalysisRequest(draft, CATALOGUE);
  assert.equal(request.legs[1].hub, "TTF");
  assert.equal(request.date_from, null);
});

test("blockers name the first thing a trader has to fix", () => {
  const draft = defaultSpreadDraft(CATALOGUE);
  assert.equal(
    spreadDraftBlocker({ ...draft, legs: [{ seriesKey: seriesKey(CATALOGUE[0]), weight: 1 }, draft.legs[1]] }, CATALOGUE),
    "spread_lab.blocker.unit_mismatch",
  );
  assert.equal(
    spreadDraftBlocker({ ...draft, legs: [draft.legs[0], { seriesKey: "", weight: -1 }] }, CATALOGUE),
    "spread_lab.blocker.leg_missing",
  );
  assert.equal(
    spreadDraftBlocker({ ...draft, rule: { ...draft.rule, exit_z: 3 } }, CATALOGUE),
    "spread_lab.blocker.exit_above_entry",
  );
  assert.equal(
    spreadDraftBlocker({ ...draft, rule: { ...draft.rule, kind: "threshold", low: 2, high: 1 } }, CATALOGUE),
    "spread_lab.blocker.band_order",
  );
});
