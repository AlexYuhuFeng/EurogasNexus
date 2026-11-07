import assert from "node:assert/strict";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import type { MonitoringAlertDTO } from "../src/api/client.ts";
import { buildTickerItems, type TickerItem, type TickerOutage } from "../src/app/model/tickerItems.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key}:${Object.values(options).join("|")}` : key;

function alert(id: string, severity: MonitoringAlertDTO["severity"], status = "open", at = "2026-11-07T08:00:00Z") {
  return { alert_id: id, severity, status, title_en: `Alert ${id}`, title_zh_cn: `告警 ${id}`,
    updated_at_utc: at, detected_at_utc: at } as unknown as MonitoringAlertDTO;
}

function outage(id: string, unavailable: number, technical: number, status = "active"): TickerOutage {
  return { event_id: id, facility_name: `Asset ${id}`, balancing_zone: "NBP", event_type: "unplanned",
    status, start_utc: "2026-11-07T06:00:00Z", unit: "mcm/d", unavailable_capacity: unavailable,
    technical_capacity: technical, unavailable_gwh_d: unavailable * 10.83 };
}

test("critical first, then newest; only open alerts and outages active now", () => {
  const items = buildTickerItems(
    [alert("a1", "warning", "open", "2026-11-07T07:00:00Z"), alert("a2", "info", "acknowledged"),
     alert("a3", "critical")],
    [outage("o1", 52, 70), outage("o2", 9, 40), outage("o3", 50, 60, "scheduled")],
    "en", t,
  );
  assert.deepEqual(items.map((item) => item.id), ["alert:a3", "outage:o1", "alert:a1", "outage:o2"]);
  // Most of an asset out is critical; a partial derate is a warning.
  assert.equal(items.find((item) => item.id === "outage:o1")?.severity, "critical");
  assert.equal(items.find((item) => item.id === "outage:o2")?.severity, "warning");
});

test("alert titles follow the user's language", () => {
  const [item] = buildTickerItems([alert("a1", "critical")], [], "zh-CN", t);
  assert.equal(item.text, "告警 a1");
});

async function renderTicker(items: TickerItem[]) {
  const { load } = await loadApiStore();
  const { BreakingTicker } = await load<{ BreakingTicker: React.ComponentType<{ items: TickerItem[]; t: typeof t; onOpen: () => void }> }>("/src/components/BreakingTicker.tsx");
  return renderToStaticMarkup(React.createElement(BreakingTicker, { items, t, onOpen: () => undefined }));
}

test("no bar when there is nothing to say; 'Breaking' with anything critical", async () => {
  assert.equal(await renderTicker([]), "");
  const calm = await renderTicker(buildTickerItems([alert("a1", "warning")], [], "en", t));
  assert.match(calm, /ticker\.latest/);
  const hot = await renderTicker(buildTickerItems([alert("a1", "critical")], [], "en", t));
  assert.match(hot, /ticker\.breaking/);
  assert.match(hot, /has-critical/);
  // The loop's second copy is hidden from assistive technology and the tab order.
  assert.match(hot, /aria-hidden="true"/);
  assert.match(hot, /tabindex="-1"/);
});

test("the ticker pauses on hover and focus and stays still with reduced motion", () => {
  const css = readFileSync(new URL("../src/styles/design-system.css", import.meta.url), "utf8");
  assert.match(css, /\.breaking-ticker:hover \.ticker-track,\s*\.breaking-ticker:focus-within \.ticker-track/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\) \{\s*\.ticker-track,/);
});
