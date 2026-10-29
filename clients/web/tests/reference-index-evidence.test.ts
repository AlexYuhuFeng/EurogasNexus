/**
 * The Web/Tauri EEX reference-index evidence section, rendered through the real
 * component and the project's own Vite test harness.
 *
 * The tests are about evidence truth, not formatting:
 *
 * - the backend's exact source string and unit are rendered verbatim, including
 *   long precision and a negative index value;
 * - a null `publication_time_utc` stays unknown and is never replaced by the
 *   receipt; the receipt is shown under "First received";
 * - every delivery period remains present, with a deterministic period/id order,
 *   and the focused hub filters on the backend-normalized `hub`;
 * - an invalid or missing exact claim is an explicit diagnostic, never the
 *   canonical float or a zero;
 * - 51 observations paginate at 50 with the total visible, and a new data key
 *   resets the page;
 * - English and Chinese dictionaries have the same keys and both render.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after, before } from "node:test";

import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { NormalizedMarketObsDTO } from "../src/api/client.ts";
import {
  closeApiStoreHarness,
  loadApiStore,
  type ApiStoreHarness,
} from "./support/apiStoreHarness.ts";

const originalWindow = (globalThis as { window?: unknown }).window;
(globalThis as { window?: unknown }).window = {
  location: { origin: "http://localhost:3000" },
};

after(closeApiStoreHarness);
after(() => {
  (globalThis as { window?: unknown }).window = originalWindow;
});

interface ReferenceIndexComponentProps {
  markets: NormalizedMarketObsDTO[];
  focusedHub?: string | null;
  t: (key: string) => string;
}

interface ReferenceIndexModule {
  ReferenceIndexEvidence: React.ComponentType<ReferenceIndexComponentProps>;
  REFERENCE_INDEX_PAGE_SIZE: number;
  clampReferenceIndexPage: (page: number, totalRows: number) => number;
  reconcileReferenceIndexPage: (
    previous: { dataKey: string; page: number },
    dataKey: string,
    totalRows: number,
  ) => { dataKey: string; page: number };
  referenceIndexPageRows: <T>(rows: T[], page: number) => T[];
}

let harness: ApiStoreHarness;
let referenceIndex: ReferenceIndexModule;

before(async () => {
  harness = await loadApiStore();
  referenceIndex = await harness.load<ReferenceIndexModule>(
    "/src/components/ReferenceIndexEvidence.tsx",
  );
});

function loadDictionary(name: "en" | "zh"): Record<string, string> {
  const text = readFileSync(
    new URL(`../src/i18n/${name}.json`, import.meta.url),
    "utf8",
  );
  return JSON.parse(text.replace(/^\ufeff/, "")) as Record<string, string>;
}

const EN = loadDictionary("en");
const ZH = loadDictionary("zh");

const translator = (dictionary: Record<string, string>) => (key: string): string =>
  dictionary[key] ?? key;

const en = translator(EN);
const zh = translator(ZH);

const LONG_EXACT = "-12.345678901234567890123456789012345678901234567890";
const RECEIPT = "2026-10-29T14:54:05.623743+00:00";
const SHA256 = "019f2286f8124be81c57d5b95e5df31497665f9ee877390122149b7842951707";

function observation(
  overrides: Partial<NormalizedMarketObsDTO> = {},
): NormalizedMarketObsDTO {
  const base: NormalizedMarketObsDTO = {
    observation_id: "eex-ngp-r1-000000000000000000000000000000000000000000000000",
    market_venue: "EEX",
    product: "TTF NGP",
    price: 777.77,
    unit: "EUR/MWh",
    currency: "EUR",
    period_start_utc: "2026-10-29T05:00:00+00:00",
    period_end_utc: "2026-10-30T05:00:00+00:00",
    observed_at_utc: RECEIPT,
    source_system: "EEX",
    source_reference: "eex-ttf-ngp-15-mins",
    source_record_id: "2026-10-29-20261029T0600-final",
    hub: "TTF",
    tenor: "TTF NGP",
    is_gas_price: true,
    price_gbp_mwh: 888.88,
    price_gbp_mwh_exact: "10.500000000000000000000001",
    price_gbp_mwh_provenance: "exact_source_decimal_times_float_fx_approximation",
    source_price_status: "exact",
    source_price_exact: LONG_EXACT,
    source_price_raw: LONG_EXACT,
    source_price_volume_mwh_exact: "123.456789012345678901",
    source_price_volume_raw: "123.456789012345678901",
    source_price_volume_status: "valid",
    source_price_provenance: "eex_ngp_exact_source_decimal",
    source_price_issue: null,
    source_price_issue_detail: null,
    source_price_source_system: "EEX",
    source_price_source_reference: "eex-ttf-ngp-15-mins",
    source_price_source_dataset: "ttf-ngp-15min",
    price_float_provenance: "canonical_float_of_validated_exact_decimal",
    price_semantics: "reference_index_never_an_executable_bid_or_ask",
    executable_quote: false,
    metadata_json: {
      source_system: "EEX",
      source_reference: "eex-ttf-ngp-15-mins",
      source_dataset: "ttf-ngp-15min",
      normalizer_version: "eex-ngp-receipt-v1",
      availability_basis: "response_receipt",
      publication_time_basis: "unknown",
      available_at_utc: RECEIPT,
      source_receipt_at_utc: RECEIPT,
      publication_time_utc: null,
      publication_timestamp_raw: "29/10/2026 06:00",
      revision_status: "final",
      revision_status_raw: "Final NGP",
      executable_quote: false,
      archive_id: "raw-019f2286f8124be8",
      raw_archive_id: "raw-019f2286f8124be8",
      payload_sha256: SHA256,
      ingestion_run_id: "run-eex-1",
      adapter_version: "eex-ngp-bounded-ingestor/1",
    },
  };
  return {
    ...base,
    ...overrides,
    metadata_json: {
      ...(base.metadata_json ?? {}),
      ...(overrides.metadata_json ?? {}),
    },
  };
}

function render(
  rows: NormalizedMarketObsDTO[],
  t: (key: string) => string,
  focusedHub: string | null = null,
): string {
  return renderToStaticMarkup(
    React.createElement(referenceIndex.ReferenceIndexEvidence, {
      markets: rows,
      focusedHub,
      t,
    }),
  );
}

function rowCount(html: string): number {
  return (html.match(/data-reference-index-row="true"/g) ?? []).length;
}

function fieldText(html: string, name: string): string {
  const match = html.match(
    new RegExp(`data-reference-index-field="${name}"[^>]*>([\\s\\S]*?)</dd>`),
  );
  return match?.[1] ?? "";
}

test("renders exact long precision, signed value, unit and receipt evidence", () => {
  const html = render([observation()], en);

  assert.ok(html.includes(LONG_EXACT), "the exact source string must be verbatim");
  assert.ok(html.includes("EUR/MWh"), "the backend unit must be verbatim");
  assert.ok(html.includes("Reference only — not an executable quote"));
  assert.ok(html.includes("29/10/2026 06:00"), "the raw source clock text is preserved");
  assert.ok(html.includes("Verbatim provider text"));

  assert.ok(html.includes("First received"));
  assert.ok(html.includes("Available at (UTC)"));
  const firstReceived = fieldText(html, "first-received");
  assert.ok(firstReceived.includes("2026-10-29 14:54:05 UTC"));

  const publication = fieldText(html, "publication-time");
  assert.ok(publication.includes("not inferred from the receipt"));
  assert.ok(!publication.includes("14:54:05"), "the receipt is not a publication time");

  assert.ok(html.includes("10.500000000000000000000001"));
  assert.ok(html.includes("exact_source_decimal_times_float_fx_approximation"));
  assert.ok(html.includes("2026-10-29-20261029T0600-final"));
  assert.ok(html.includes("raw-019f2286f8124be8"));
  assert.ok(html.includes(SHA256));
  assert.ok(html.includes("eex-ngp-bounded-ingestor/1"));

  assert.ok(!html.includes("777.77"), "the canonical float price is never a fallback");
  assert.ok(!html.includes("888.88"), "the numeric GBP field is not rendered as exact");
});

test("keeps distinct periods and filters on the backend hub", () => {
  const rows = [
    observation({
      observation_id: "reference-a",
      period_start_utc: "2026-10-29T05:00:00+00:00",
      period_end_utc: "2026-10-30T05:00:00+00:00",
    }),
    observation({
      observation_id: "reference-b",
      period_start_utc: "2026-10-29T05:00:00+00:00",
      period_end_utc: "2026-10-30T05:00:00+00:00",
      metadata_json: {
        revision_status: "temporary",
        revision_status_raw: "Temporary NGP",
      },
    }),
    observation({
      observation_id: "reference-c",
      period_start_utc: "2026-10-30T05:00:00+00:00",
      period_end_utc: "2026-10-31T05:00:00+00:00",
    }),
  ];

  const all = render(rows, en);
  assert.equal(rowCount(all), 3, "same period final/temporary must both remain");
  assert.ok(all.includes("2026-10-29 05:00:00 UTC"));
  assert.ok(all.includes("2026-10-30 05:00:00 UTC"));
  assert.ok(all.includes('data-reference-index-revision="final"'));
  assert.ok(all.includes('data-reference-index-revision="temporary"'));
  assert.ok(all.includes("Final"));
  assert.ok(all.includes("Temporary"));
  assert.ok(!all.toLowerCase().includes("day-ahead"), "no day-ahead class is invented");

  const a = all.indexOf('data-observation-id="reference-a"');
  const b = all.indexOf('data-observation-id="reference-b"');
  const c = all.indexOf('data-observation-id="reference-c"');
  assert.ok(a >= 0 && a < b && b < c, "period then id ordering is deterministic");

  const nbp = render(rows, en, "NBP");
  assert.equal(rowCount(nbp), 0);
  assert.ok(nbp.includes("match the focused backend hub"));
  assert.ok(nbp.includes("NBP"));

  const ttf = render(rows, en, "TTF");
  assert.equal(rowCount(ttf), 3);

  const none = render([], en);
  assert.equal(rowCount(none), 0);
  assert.ok(none.includes("This market read contains no receipt-bound EEX TTF NGP reference observations"));

  const legacy = render([
    observation({ metadata_json: { normalizer_version: null } }),
  ], en);
  assert.equal(rowCount(legacy), 0, "a legacy publication-bound EEX row is not receipt evidence");
});

test("invalid or missing exact evidence is diagnostic, never a float fallback", () => {
  const rows = [
    observation({
      observation_id: "reference-invalid",
      source_price_status: "invalid",
      source_price_exact: null,
      source_price_raw: null,
      source_price_issue: "exact_numeric_price_mismatch",
      source_price_issue_detail: "canonical float price does not equal float(index_value_exact)",
    }),
    observation({
      observation_id: "reference-missing",
      source_price_status: "missing",
      source_price_exact: null,
      source_price_raw: null,
      source_price_issue: "exact_source_price_missing",
    }),
    observation({
      observation_id: "reference-blank",
      source_price_status: "exact",
      source_price_exact: "   ",
      source_price_raw: null,
      source_price_issue: null,
    }),
  ];

  const html = render(rows, en);
  assert.equal(
    (html.match(/Exact source price unavailable/g) ?? []).length,
    3,
  );
  assert.ok(html.includes("exact_numeric_price_mismatch"));
  assert.ok(html.includes("exact_source_price_missing"));
  assert.ok(html.includes("No float, zero or client conversion is substituted."));
  assert.ok(!html.includes("777.77"));
  assert.ok(!html.includes("888.88"));
  assert.ok(!html.includes(LONG_EXACT));
});

test("paginates 51 observations at 50, shows the total, and resets on new data", () => {
  const rows = Array.from({ length: 51 }, (_, index) => {
    const month = index < 28 ? "01" : "02";
    const day = String(1 + (index % 28)).padStart(2, "0");
    return observation({
      observation_id: `reference-${String(index).padStart(3, "0")}`,
      period_start_utc: `2026-${month}-${day}T05:00:00+00:00`,
      period_end_utc: "2026-12-31T05:00:00+00:00",
    });
  });

  const html = render(rows, en);
  assert.equal(rowCount(html), 50);
  assert.ok(html.includes('data-reference-index-total="51"'));
  assert.ok(html.includes(">51<"));
  assert.ok(html.includes("Page 1 / 2"));
  assert.ok(html.includes(">Next<"));
  assert.ok(!html.includes('data-observation-id="reference-050"'));

  assert.equal(referenceIndex.REFERENCE_INDEX_PAGE_SIZE, 50);
  assert.equal(referenceIndex.clampReferenceIndexPage(3, 51), 2);
  assert.deepEqual(
    referenceIndex.reconcileReferenceIndexPage({ dataKey: "old", page: 2 }, "new", 51),
    { dataKey: "new", page: 1 },
  );
  assert.deepEqual(
    referenceIndex.reconcileReferenceIndexPage({ dataKey: "new", page: 2 }, "new", 51),
    { dataKey: "new", page: 2 },
  );

  const ordered = rows.slice().sort((left, right) => {
    const leftPeriod = left.period_start_utc ?? "";
    const rightPeriod = right.period_start_utc ?? "";
    if (leftPeriod < rightPeriod) return -1;
    if (leftPeriod > rightPeriod) return 1;
    return 0;
  });
  const secondPage = referenceIndex.referenceIndexPageRows(ordered, 2);
  assert.equal(secondPage.length, 1);
  assert.equal(secondPage[0].observation_id, "reference-050");
});

test("English and Chinese reference-index dictionaries have parity", () => {
  const enKeys = Object.keys(EN).filter((key) => key.startsWith("referenceIndex.")).sort();
  const zhKeys = Object.keys(ZH).filter((key) => key.startsWith("referenceIndex.")).sort();
  assert.deepEqual(zhKeys, enKeys);
  for (const key of enKeys) {
    assert.ok(EN[key].trim(), `missing English text for ${key}`);
    assert.ok(ZH[key].trim(), `missing Chinese text for ${key}`);
  }

  const html = render([observation()], zh);
  assert.ok(html.includes("EEX TTF NGP 参考指数"));
  assert.ok(html.includes("仅供参考——不是可执行报价"));
  assert.ok(html.includes("首次接收"));
  assert.ok(html.includes("交付时段（UTC）"));
  assert.ok(html.includes(LONG_EXACT));
  assert.ok(!html.includes("referenceIndex."));
  assert.ok(!render([observation()], en).includes("referenceIndex."));
});
