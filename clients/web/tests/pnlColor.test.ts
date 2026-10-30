import assert from "node:assert/strict";
import test from "node:test";

import { applyPnlColorConvention, pnlClass } from "../src/app/model/pnlColor.ts";

test("sign decides the class; zero and unknown stay neutral", () => {
  assert.equal(pnlClass(12.5), "pnl-profit");
  assert.equal(pnlClass(-0.01), "pnl-loss");
  assert.equal(pnlClass(0), "");
  assert.equal(pnlClass(null), "");
  assert.equal(pnlClass(Number.NaN), "");
});

test("the convention is set on the root and defaults to green-up", () => {
  const root = { dataset: {} as DOMStringMap };
  applyPnlColorConvention("red_up", root);
  assert.equal(root.dataset.pnl, "red_up");
  applyPnlColorConvention("anything", root);
  assert.equal(root.dataset.pnl, "green_up");
});
