import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { directionOf, nextFlash } from "../src/components/ui/dataGridModel.ts";

// UX R2 (research/16B, P-19): a live cell flashes neutrally on a real tick only, and says the
// direction with a glyph that stays, not with colour or motion.

test("a new value of the same instrument is a tick with a direction", () => {
  const first = nextFlash(null, "TTF|mid|DA", 34.1);
  assert.deepEqual(first, { identity: "TTF|mid|DA", value: 34.1, count: 0, direction: null });
  const up = nextFlash(first, "TTF|mid|DA", 34.25);
  assert.equal(up.count, 1);
  assert.equal(up.direction, "up");
  const down = nextFlash(up, "TTF|mid|DA", 34.0);
  assert.equal(down.count, 2);
  assert.equal(down.direction, "down");
  assert.equal(nextFlash(down, "TTF|mid|DA", 34.0), down, "the same value is no tick and no re-render");
});

test("a tenor switch shows another contract: it resets quietly, with no flash and no direction", () => {
  const ticked = nextFlash(nextFlash(null, "TTF|mid|DA", 34.1), "TTF|mid|DA", 34.3);
  const switched = nextFlash(ticked, "TTF|mid|MA", 36.9);
  assert.deepEqual(switched, { identity: "TTF|mid|MA", value: 36.9, count: 0, direction: null });
});

test("a change that is not a number flashes without a direction", () => {
  const status = nextFlash(nextFlash(null, "C1|status|", "planned"), "C1|status|", "loading");
  assert.equal(status.count, 1);
  assert.equal(status.direction, null);
  assert.equal(directionOf(0), null);
  assert.equal(directionOf(Number.NaN), null);
  assert.equal(directionOf(-0.001), "down");
});

test("the flash is neutral, uses the duration token, and the dead green ticker rule is gone", () => {
  const css = readFileSync(new URL("../src/components/ui/datagrid.css", import.meta.url), "utf8");
  assert.match(css, /\.ds-cell-flash\[data-flash="a"\] \{\s*animation: ds-flash-a var\(--ds-duration-flash\)/);
  assert.doesNotMatch(css, /ds-flash-[ab] \d+ms/);
  assert.doesNotMatch(css, /--ds-(positive|negative|status-ok|status-breach|pnl)/, "the flash carries no direction colour");
  const tokens = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");
  assert.match(tokens, /--ds-duration-flash: 400ms;/);
  const app = readFileSync(new URL("../src/styles/app.css", import.meta.url), "utf8");
  assert.doesNotMatch(app, /market-price-ticker|market-tick-update/);
});

test("the grid keys the flash to row, column and instrument, and the board passes the tenor", () => {
  const grid = readFileSync(new URL("../src/components/ui/DataGrid.tsx", import.meta.url), "utf8");
  assert.match(grid, /identity=\{`\$\{rowId\}\|\$\{column\.id\}\|\$\{column\.flashIdentity\?\.\(row\) \?\? ""\}`\}/);
  assert.match(grid, /<DirectionMark direction=\{state\.direction\} announce \/>/);
  const board = readFileSync(new URL("../src/components/MarketTerminal.tsx", import.meta.url), "utf8");
  assert.match(board, /flash: true,[\s\S]{0,200}flashIdentity: \(row\) => row\.tenor,/);
});
