import assert from "node:assert/strict";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { IntradayOpportunityDTO } from "../src/api/client.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

async function render(opportunities: IntradayOpportunityDTO[], compact = false) {
  const { load } = await loadApiStore();
  const { IntradayDecisionFeed } = await load<{ IntradayDecisionFeed: React.ComponentType<{ opportunities: IntradayOpportunityDTO[]; compact: boolean; t: (key: string) => string }> }>("/src/components/IntradayDecisionFeed.tsx");
  return renderToStaticMarkup(React.createElement(IntradayDecisionFeed, {
    opportunities, compact, t: (key: string) => key,
  }));
}

function candidate(index: number, status = "ACTIONABLE_REVIEW"): IntradayOpportunityDTO {
  return {
    opportunity_id: String(index), route_id: String(index), status,
    detected_at_utc: "2026-11-05T09:00:00Z", product: "DA",
    buy_venue: "A", sell_venue: "B", missing_inputs: [], warnings: [],
    confidence_score: 0,
  } as IntradayOpportunityDTO;
}

test("an empty feed reports unknown scan coverage", async () => {
  const html = await render([]);
  assert.match(html, /intraday\.coverage_unknown/);
  assert.doesNotMatch(html, /intraday\.monitoring|intraday\.no_candidates/);
});

test("expired-only results offer history instead of claiming scan coverage", async () => {
  const html = await render([candidate(1, "EXPIRED")]);
  assert.match(html, /intraday\.show_expired/);
  assert.match(html, /intraday\.expired_only/);
});

test("compact feed counts all unique actionable candidates before clipping", async () => {
  const html = await render([1, 2, 3, 4, 4].map((index) => candidate(index)), true);
  assert.match(html, />4 intraday\.active</);
  assert.equal((html.match(/<details/g) ?? []).length, 3);
});
