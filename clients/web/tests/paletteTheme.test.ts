/**
 * The command palette takes every colour from the design-system role tokens, so its
 * selected row, focus ring and help text follow the theme. A fixed fallback colour made the
 * selected row white-on-white in the dark theme.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync(new URL("../src/components/CommandPalette.css", import.meta.url), "utf8");

test("the palette uses role tokens only: no fixed colour and no legacy variable", () => {
  assert.equal(css.match(/#[0-9a-fA-F]{3,8}\b/g), null, "fixed colour in CommandPalette.css");
  const legacy = [...css.matchAll(/var\((--[a-z-]+)/g)].map((m) => m[1]).filter((name) => !name.startsWith("--ds-"));
  assert.deepEqual([...new Set(legacy)], []);
});
