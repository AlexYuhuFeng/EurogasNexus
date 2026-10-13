/**
 * Backtest refusal feedback (HISTORICAL-BOUNDARY-20261008).
 *
 * The run is the workspace header's primary action, so a server refusal used to leave the
 * panel unchanged: the button re-enabled and the error lived only in controller state that
 * no surface rendered, which reads as a successful no-op. The panel must show the backend's
 * own safe message under a localised heading, and it must not hide the action behind a
 * client-side guess — the server remains the authority.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("the backtest panel reports a server refusal as a localised alert", () => {
  const panel = readWebSource("components/strategy/StrategyBacktestWorkspace.tsx");

  // The refusal is rendered whenever the controller holds one, with a stable, readable
  // accessibility role so the message is not merely visual.
  assert.match(panel, /\{controller\.error && \(/);
  assert.match(panel, /role="alert"/);
  assert.match(panel, /t\("strategy_lab\.run_refused"\)/);
  // The backend's own safe message stays visible beside the heading: the surface reports
  // the refusal rather than re-wording it.
  assert.match(panel, /\{controller\.error\}/);
  // The refusal is not hidden behind the configure/result tab switch.
  const tabs = panel.indexOf("strategy-mode-tabs");
  const refusal = panel.indexOf("controller.error &&");
  const configSection = panel.indexOf('{mode === "configure" && (');
  assert.ok(tabs > -1 && refusal > tabs && refusal < configSection);
});

test("the refusal heading exists in both locales and says something different", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  assert.ok(en["strategy_lab.run_refused"], "en is missing strategy_lab.run_refused");
  assert.ok(zh["strategy_lab.run_refused"], "zh is missing strategy_lab.run_refused");
  assert.notEqual(en["strategy_lab.run_refused"], zh["strategy_lab.run_refused"]);
});
