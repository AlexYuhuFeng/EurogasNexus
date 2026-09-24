/**
 * Runtime data availability: the shell's status badge states what the workspace batch
 * reported about the runtime store's own data, and nothing more.
 *
 * September 2026 authenticated-HMI audit (readiness semantics, P1): the numeric Market
 * surface printed that provenance as "Source posture: Ready" while the projection slices
 * beside it were stale or missing. Runtime connectivity is not market-data fitness, so the
 * labels are runtime-data-availability statements shared by the header, settings and the
 * market grid, in both locales, and fail-closed for anything the store type does not model.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  RUNTIME_DATA_AVAILABILITY_CAPTION_KEY,
  dataPlaneState,
  runtimeDataAvailability,
  runtimeDataAvailabilityLabelKey,
  runtimeStoreStatus,
} from "../src/app/model/dataPlaneStatus.ts";
import { degradedSlices, sliceReadings } from "../src/app/model/marketContextModel.ts";
import type { MarketContextProjectionDTO } from "../src/api/client.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function readLocale(name: "en" | "zh"): Record<string, string> {
  return JSON.parse(readWebSource(`i18n/${name}.json`)) as Record<string, string>;
}

const STATES = ["available", "partial", "delayed", "unavailable", "unknown"] as const;

test("the store's dataStatus maps onto runtime data availability, fail-closed", () => {
  assert.equal(runtimeDataAvailability("runtime"), "available");
  assert.equal(runtimeDataAvailability("partial"), "partial");
  // The slot the store type still carries with no producer keeps its own, non-healthy label.
  assert.equal(runtimeDataAvailability("delayed"), "delayed");
  // The runtime store reported no usable data (no URL configured, or connectivity failed).
  assert.equal(runtimeDataAvailability("unavailable"), "unavailable");
  // Nothing else - nothing loaded yet, a case variant, or a token the client has never
  // heard of - may be guessed at.
  for (const value of ["", "runtime ", "RUNTIME", "ready", "mystery", null, undefined]) {
    assert.equal(runtimeDataAvailability(value), "unknown", JSON.stringify(value));
  }

  // The chip tone stays fail-closed: only a store that answered takes the healthy tone.
  assert.equal(dataPlaneState("runtime"), "ready");
  for (const value of ["partial", "delayed", "unavailable", "mystery", null]) {
    assert.notEqual(dataPlaneState(value), "ready", String(value));
  }

  // One label per state, all shared, with one caption naming what they are about.
  assert.deepEqual(
    STATES.map(runtimeDataAvailabilityLabelKey),
    [
      "data.runtime_available",
      "data.runtime_partial",
      "data.runtime_delayed",
      "data.runtime_unavailable",
      "data.runtime_unknown",
    ],
  );
  assert.equal(RUNTIME_DATA_AVAILABILITY_CAPTION_KEY, "data.runtime_availability");
});

test("the labels are runtime-data statements in both locales, never readiness or freshness", () => {
  const en = readLocale("en");
  const zh = readLocale("zh");
  for (const [locale, translations] of [["en", en], ["zh", zh]] as const) {
    const subject = locale === "en" ? /runtime data/i : /运行时数据/;
    for (const state of STATES) {
      const key = runtimeDataAvailabilityLabelKey(state);
      const label = translations[key];
      assert.match(label ?? "", subject, `${locale} ${key} must name the runtime store's data`);
      // Overall readiness is a different claim, and freshness was never read from provenance.
      assert.equal(label.includes(translations["data.ready"]), false, `${locale} ${key}`);
      assert.equal(/ready|fresh|live|real-?time|market/i.test(label), false, `${locale} ${key}`);
    }
    assert.equal(typeof translations[RUNTIME_DATA_AVAILABILITY_CAPTION_KEY], "string", locale);
  }

  // The one detail line the badges show keeps the store in it and says what it is not.
  assert.match(en["data.runtime_detail"], /runtime PostgreSQL/i);
  assert.match(zh["data.runtime_detail"], /运行时 PostgreSQL/);
  assert.equal(/ready/i.test(en["data.runtime_detail"]), false);
});

test("all three renderers show the shared availability label, not the overall vocabulary", () => {
  const captioned = ["components/SettingsCenter.tsx", "components/MarketCockpit.tsx"];
  for (const file of [...captioned, "components/WorkspaceTopBar.tsx"]) {
    const source = readWebSource(file);
    assert.match(source, /runtimeDataAvailability\(/, file);
    assert.match(source, /runtimeDataAvailabilityLabelKey\(/, file);
    assert.equal(source.includes("dataPlaneLabelKey("), false, `${file} still reads data.<state>`);
    assert.equal(source.includes('"data.ready"'), false, file);
    assert.equal(
      source.includes("RUNTIME_DATA_AVAILABILITY_CAPTION_KEY"),
      captioned.includes(file),
      file,
    );
  }
});

/**
 * The audit's own case: the runtime store answered (`dataStatus === "runtime"`) while the
 * market projection on the same screen reported stale and missing slices. The surface may
 * say the runtime store answered; it may not read as an overall "Ready" or as fresh market
 * data, and the degradation it has is still disclosed by the projection strip.
 */
test("a runtime status beside stale or missing market slices never reads as overall Ready", () => {
  const projection = {
    slices: {
      quotes: { available: true, row_count: 42, freshness: { state: "STALE" } },
      normalized_quotes: { available: false, row_count: 0, freshness: { state: "MISSING" } },
    },
  } as unknown as MarketContextProjectionDTO;

  const degraded = degradedSlices(projection);
  assert.equal(degraded.some((reading) => reading.freshnessState === "STALE"), true);
  assert.equal(degraded.some((reading) => !reading.available), true);
  assert.equal(
    sliceReadings(projection).some((reading) => reading.freshnessState === "FRESH"),
    false,
    "the fixture is the degraded reading the audit found",
  );

  const labelKey = runtimeDataAvailabilityLabelKey(runtimeDataAvailability("runtime"));
  assert.equal(labelKey, "data.runtime_available");
  for (const [locale, translations] of [["en", readLocale("en")], ["zh", readLocale("zh")]] as const) {
    assert.notEqual(translations[labelKey], translations["data.ready"], locale);
    assert.equal(/ready|fresh|live/i.test(translations[labelKey]), false, locale);
  }

  // The market grid's runtime cell is built from that label and the shared caption only,
  // and the projection strip beside it still carries the stale/missing disclosure.
  const cockpit = readWebSource("components/MarketCockpit.tsx");
  assert.match(cockpit, /t\(runtimeDataAvailabilityLabelKey\(runtimeAvailability\)\)/);
  assert.match(cockpit, /t\(RUNTIME_DATA_AVAILABILITY_CAPTION_KEY\)/);
  assert.match(cockpit, /<MarketContextStrip/);
  assert.match(readWebSource("components/MarketContextStrip.tsx"), /degraded=\{degradedSlices\(/);
});

/**
 * The pre-read window. Until the workspace batch answers, nothing about the runtime store has been
 * read, so the shell's badge may not say "Runtime data unavailable" - that is a verdict, and the
 * store holds no reading for it. The store's own token for that window is `unknown`, which the
 * label vocabulary already renders as "Runtime data availability unknown".
 */
test("the store reports an unread runtime status as unknown, not as unavailable", () => {
  const store = readWebSource("stores/api.ts");
  assert.match(store, /dataStatus: "unknown" \| "runtime" \| "delayed" \| "partial" \| "unavailable";/);
  assert.match(store, /dataStatus: "unknown",/);
  assert.match(store, /workspaceLoading: false,/);
  // The status slice's absence is read through the three-valued resolver, never as a bare null.
  assert.match(store, /const runtimeStatus = runtimeStoreStatus\(runtimeDb\);/);
  assert.equal(store.includes('!runtimeDb || !runtimeDb.database_url_present'), false);
  assert.equal(runtimeStoreStatus(null), "unknown");
  assert.equal(runtimeDataAvailability("unknown"), "unknown");
  assert.notEqual(runtimeDataAvailabilityLabelKey(runtimeDataAvailability("unknown")), "data.runtime_unavailable");
  assert.equal(dataPlaneState("unknown"), "unavailable", "the chip tone stays fail-closed");
});
