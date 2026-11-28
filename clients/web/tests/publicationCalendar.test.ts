/**
 * Package G: the desk's calendar (Desk → Board → Calendar), its lines in the events list, and
 * the administrators' list of watched publications. Hand-maintained items say so; fetched ones
 * carry their published and fetched times on demand. Dates are illustrative.
 */
import assert from "node:assert/strict";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { PublicationCalendarItemDTO, WatchedPublicationDTO } from "../src/api/client.ts";
import { boardEvents, calendarEvents, calendarSource } from "../src/app/model/traderEventsModel.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

const h = React.createElement;
const t = (key: string, options?: Record<string, unknown>) =>
  options && Object.keys(options).length ? `${key}(${Object.entries(options).map(([k, v]) => `${k}=${String(v)}`).join(",")})` : key;
const NOW = Date.parse("2026-12-21T06:00:00Z");

function item(overrides: Partial<PublicationCalendarItemDTO>): PublicationCalendarItemDTO {
  return {
    key: "closed:ICE_FUTURES_EUROPE:2026-12-28",
    kind: "non_trading_day",
    at: "2026-12-28T00:00:00+00:00",
    day: "2026-12-28",
    title: "ICE Futures Europe UK natural gas (NBP): closed",
    hubs: ["NBP"],
    source: {
      publication_id: "ice-futures-europe-trading-schedule",
      publisher: "ICE Futures Europe",
      title: "ICE Futures Europe trading schedule",
      url: "https://www.ice.com/publicdocs/Trading_Schedule.pdf",
      basis: "hand_maintained",
      fetched_at_utc: null,
      published_at_utc: null,
      changed_at_utc: null,
      attribution: "",
      checked: false,
    },
    ...overrides,
  };
}

const AUCTION = item({
  key: "auction:entsog-auction-calendar:firm:monthly:2027-01-01",
  kind: "auction",
  at: "2026-12-21T08:00:00+00:00",
  day: undefined,
  title: "Monthly auction, firm: January 2027 (ENTSOG calendar 2026/27)",
  hubs: ["TTF", "ZTP", "THE", "PVB"],
  capacity: "firm",
  source: {
    publication_id: "entsog-cam-auction-calendar",
    publisher: "ENTSOG",
    title: "ENTSOG CAM network code auction calendar",
    url: "https://www.entsog.eu/sites/default/files/2025-12/calendar.xlsx",
    basis: "fetched",
    fetched_at_utc: "2026-12-20T06:00:00+00:00",
    published_at_utc: "2025-11-12T00:00:00+00:00",
    changed_at_utc: "2026-11-28T06:00:00+00:00",
    attribution: "Source: ENTSOG and/or its members, CAM NC Auction Calendar",
  },
});

test("calendar lines join the events list for the coming week, never as an alarm", () => {
  const far = item({ key: "closed:EEX:2027-03-26", at: "2027-03-26T00:00:00+00:00", hubs: ["TTF"] });
  const interruptible = { ...AUCTION, key: "auction:x:interruptible", capacity: "interruptible" as const };
  const changed = item({ key: "confirm:entsog", kind: "source_changed", at: "2026-11-01T00:00:00+00:00", hubs: ["TTF"] });
  const lines = calendarEvents([item({}), AUCTION, far, interruptible, changed], new Set(["NBP"]), NOW, t);
  assert.deepEqual(lines.map((line) => line.key).sort(), [
    "calendar:auction:entsog-auction-calendar:firm:monthly:2027-01-01",
    "calendar:closed:ICE_FUTURES_EUROPE:2026-12-28",
    "calendar:confirm:entsog",
  ]);
  const holiday = lines.find((line) => line.key.endsWith("2026-12-28"))!;
  assert.equal(holiday.kind, "calendar");
  assert.equal(holiday.touchesBook, true, "the desk holds NBP");
  assert.equal(holiday.source, "calendar.source.hand(publisher=ICE Futures Europe)");
  assert.equal(calendarSource(AUCTION, t), "ENTSOG");
  const events = boardEvents([], [], new Set(), lines);
  assert.equal(events[0]!.key, "calendar:closed:ICE_FUTURES_EUROPE:2026-12-28", "the latest due first");
});

test("the calendar panel marks hand-maintained lines and keeps provenance on demand", async () => {
  const { load } = await loadApiStore();
  const { PublicationCalendar, dueWords, provenanceText } = await load<typeof import("../src/components/PublicationCalendar.tsx")>(
    "/src/components/PublicationCalendar.tsx",
  );
  const html = renderToStaticMarkup(h(PublicationCalendar, { items: [item({}), AUCTION], nowMs: NOW, t }));
  assert.match(html, /data-calendar-kind="non_trading_day"/);
  assert.match(html, /data-basis="hand_maintained"/);
  assert.match(html, /calendar\.hand_maintained/);
  assert.match(html, /href="https:\/\/www\.ice\.com\/publicdocs\/Trading_Schedule\.pdf"/);
  assert.equal(dueWords("2026-12-28T00:00:00Z", NOW, t), "calendar.due.in_d(count=7)");
  const provenance = provenanceText(AUCTION, t, (iso) => iso.slice(0, 10));
  assert.match(provenance, /calendar\.published\(time=2025-11-12\)/);
  assert.match(provenance, /calendar\.fetched\(time=2026-12-20\)/);
  assert.match(provenance, /ENTSOG and\/or its members/);
  assert.match(provenanceText(item({}), t, (iso) => iso), /calendar\.not_checked/);
});

test("the watched publications list puts what needs a person first", async () => {
  const { load } = await loadApiStore();
  const { watchOrder } = await load<typeof import("../src/components/WatchedPublicationsPanel.tsx")>(
    "/src/components/WatchedPublicationsPanel.tsx",
  );
  const row = (publication_id: string, state: WatchedPublicationDTO["state"]) =>
    ({ publication_id, title: publication_id, state }) as WatchedPublicationDTO;
  const ordered = watchOrder([row("b", "link_only"), row("a", "current"), row("c", "needs_confirmation"), row("d", "hand_maintained")]);
  assert.deepEqual(ordered.map((r) => r.state), ["needs_confirmation", "current", "hand_maintained", "link_only"]);
  // A withdrawn consent and a refusing site come before what runs; not yet implemented after.
  const consented = watchOrder([row("e", "not_implemented"), row("f", "current"), row("g", "consent_withdrawn"), row("h", "site_refuses")]);
  assert.deepEqual(consented.map((r) => r.state), ["site_refuses", "consent_withdrawn", "current", "not_implemented"]);
});

test("a fetched calendar line names the consent it was fetched under, on demand", async () => {
  const { load } = await loadApiStore();
  const { provenanceText } = await load<typeof import("../src/components/PublicationCalendar.tsx")>("/src/components/PublicationCalendar.tsx");
  const text = provenanceText(
    {
      key: "early:EEX:2026-12-24",
      kind: "early_close",
      at: "2026-12-24T00:00:00+00:00",
      title: "EEX: shorter hours",
      hubs: ["TTF"],
      source: { publication_id: "eex-holiday-calendar", publisher: "EEX", title: "t", url: null, basis: "fetched", fetched_at_utc: "2026-11-28T10:00:00+00:00", published_at_utc: null, changed_at_utc: null, attribution: "", consent: "fetched under written consent (reported 2026-11-28, own use, no resale)" },
    },
    (key, options) => (options ? `${key}:${JSON.stringify(options)}` : key),
    (iso) => iso,
  );
  assert.match(text, /calendar\.consent:.*fetched under written consent/);
});
