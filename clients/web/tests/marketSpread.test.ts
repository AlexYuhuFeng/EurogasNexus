/**
 * The displayed hub spread must be one definition, and must not depend on row order.
 *
 * Why this test exists
 * --------------------
 * `MarketTerminal` indexed `/api/market/spreads` by hub pair and period only:
 *
 *     direct.set(`${from}:${to}:${period}`, spread)
 *     reverse.set(`${to}:${from}:${period}`, spread)
 *
 * The seeded day-ahead TTF/NBP pair arrives six times, once per venue combination, with
 * six values between 2.0578 and 2.1928. Every iteration overwrote the previous one, so
 * the number shown was the last row the API happened to return, and the lookup negated
 * it — turning a hub that trades above TTF into a negative "spread to TTF".
 *
 * The assertions below are the properties that failure violated: determinism under
 * reordering, one sign convention, and a stated venue and direction for every value.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  createHubSpreadResolver,
  directionalSpread,
  premiumOverTtf,
} from "../src/app/marketSpread.ts";
import type { MarketSpreadDTO } from "../src/api/client.ts";

/** The shape the live endpoint returns for one seeded hub pair and period. */
function row(
  from_hub: string,
  to_hub: string,
  period: string,
  spread_eur_mwh: number,
  from_venue: string,
  to_venue: string,
): MarketSpreadDTO {
  return {
    spread_id: `${from_hub}-${to_hub}-${from_venue}-${to_venue}-${spread_eur_mwh}`,
    name: `${from_hub} -> ${to_hub} ${period}`,
    from_venue,
    to_venue,
    from_hub,
    to_hub,
    spread_eur_mwh,
    period,
  };
}

/** Six venues quoting the same pair, in the order the live response returned them. */
const SEEDED = [
  row("TTF", "NBP", "day-ahead", 2.1078, "EEX", "EEX"),
  row("TTF", "NBP", "day-ahead", 2.1928, "EEX", "ICE OCM"),
  row("TTF", "NBP", "day-ahead", 2.1378, "EEX", "Trayport"),
  row("TTF", "NBP", "day-ahead", 2.0578, "ICE OCM", "EEX"),
  row("TTF", "NBP", "day-ahead", 2.1428, "ICE OCM", "ICE OCM"),
  row("TTF", "NBP", "day-ahead", 2.0878, "Trayport", "Trayport"),
];

test("a direction quoted directly is preferred over one derived by negation", () => {
  const resolved = directionalSpread(SEEDED, "TTF", "NBP", "day-ahead");
  assert.ok(resolved, "the TTF->NBP spread should resolve");
  assert.equal(resolved.derived_from_reverse, false, "this direction is quoted directly");
  assert.equal(resolved.from_venue, "EEX");
  assert.equal(resolved.to_venue, "EEX");
});

test("the resolved value does not change when the rows are reordered", () => {
  const forwards = createHubSpreadResolver(SEEDED)("TTF", "NBP", "day-ahead");
  const backwards = createHubSpreadResolver([...SEEDED].reverse())("TTF", "NBP", "day-ahead");

  assert.ok(forwards && backwards);
  assert.equal(
    forwards.value_eur_mwh,
    backwards.value_eur_mwh,
    "the spread changed when the response order changed, so it is not a property of the market",
  );
  assert.equal(forwards.from_venue, backwards.from_venue);
  assert.equal(forwards.to_venue, backwards.to_venue);
});

test("every rotation of the response yields the same spread", () => {
  const first = createHubSpreadResolver(SEEDED)("TTF", "NBP", "day-ahead");
  assert.ok(first);
  for (let offset = 1; offset < SEEDED.length; offset += 1) {
    const rotated = [...SEEDED.slice(offset), ...SEEDED.slice(0, offset)];
    const resolved = createHubSpreadResolver(rotated)("TTF", "NBP", "day-ahead");
    assert.ok(resolved, `rotation ${offset} did not resolve`);
    assert.equal(
      resolved.value_eur_mwh,
      first.value_eur_mwh,
      `rotation ${offset} produced a different spread (${resolved.value_eur_mwh} vs ${first.value_eur_mwh})`,
    );
  }
});

test("opposite directions are equal in magnitude and opposite in sign", () => {
  const forward = directionalSpread(SEEDED, "TTF", "NBP", "day-ahead");
  const back = directionalSpread(SEEDED, "NBP", "TTF", "day-ahead");
  assert.ok(forward && back);
  assert.equal(
    back.value_eur_mwh,
    -forward.value_eur_mwh,
    "the two directions must mirror each other",
  );
});

test("the premium over TTF is positive for a hub that trades above TTF", () => {
  // The seeded day-ahead TTF->NBP spread is positive, which means NBP is dearer. The
  // screen previously rendered that as roughly -2.09 beside the label "spread to TTF".
  const premium = premiumOverTtf(SEEDED, "NBP", "day-ahead");
  assert.ok(premium, "the NBP premium over TTF should resolve");
  assert.ok(
    premium.value_eur_mwh > 0,
    `a hub quoted above TTF must show a positive premium, got ${premium.value_eur_mwh}`,
  );
  assert.equal(premium.from_hub, "TTF");
  assert.equal(premium.to_hub, "NBP");
});

test("the premium equals the TTF-to-hub directional spread, not its reverse", () => {
  const premium = premiumOverTtf(SEEDED, "NBP", "day-ahead");
  const forward = directionalSpread(SEEDED, "TTF", "NBP", "day-ahead");
  const backward = directionalSpread(SEEDED, "NBP", "TTF", "day-ahead");
  assert.ok(premium && forward && backward);
  assert.equal(
    premium.value_eur_mwh,
    forward.value_eur_mwh,
    "the premium is price(NBP) - price(TTF), which is the TTF->NBP direction",
  );
  assert.equal(
    premium.value_eur_mwh,
    -backward.value_eur_mwh,
    "taking the NBP->TTF direction would invert the sign, which is the defect",
  );
});

test("TTF's premium over itself is zero rather than null", () => {
  const premium = premiumOverTtf(SEEDED, "TTF", "day-ahead");
  assert.ok(premium, "the strip renders TTF as 0, so this must not be null");
  assert.equal(premium.value_eur_mwh, 0);
});

test("hub and period matching is case-insensitive and period-specific", () => {
  const upper = directionalSpread(SEEDED, "ttf", "nbp", "day-ahead");
  const lower = directionalSpread(SEEDED, "TTF", "NBP", "day-ahead");
  assert.ok(upper && lower);
  assert.equal(upper.value_eur_mwh, lower.value_eur_mwh);

  assert.equal(
    directionalSpread(SEEDED, "TTF", "NBP", "within-day"),
    null,
    "a different period must not be answered by another period's row",
  );
});

test("a row with a non-finite amount is ignored rather than poisoning the result", () => {
  const withGarbage = [
    ...SEEDED,
    row("TTF", "NBP", "day-ahead", Number.NaN, "AAAA", "AAAA"),
  ];
  const resolved = directionalSpread(withGarbage, "TTF", "NBP", "day-ahead");
  assert.ok(resolved);
  assert.ok(Number.isFinite(resolved.value_eur_mwh));
  assert.equal(resolved.from_venue, "EEX", "a venue sorting first alphabetically must not win");
});

test("a direction present only as the reverse of a quoted row still resolves, negated", () => {
  const oneSided = [row("TTF", "NBP", "day-ahead", 2.5, "EEX", "EEX")];
  const resolved = directionalSpread(oneSided, "NBP", "TTF", "day-ahead");
  assert.ok(resolved, "the reverse direction should be derivable");
  assert.equal(resolved.value_eur_mwh, -2.5);
  assert.equal(resolved.derived_from_reverse, true);
});

test("an empty response resolves nothing rather than inventing a premium", () => {
  assert.equal(directionalSpread([], "NBP", "TTF", "day-ahead"), null);
  assert.equal(premiumOverTtf([], "NBP", "day-ahead"), null);
});
