// Synthetic browser interaction for the receipt-bound EEX TTF NGP reference index.
//
// A controlled transport fixture answers only `GET /api/projections/market-context`
// while this helper is active. It fetches the actual authenticated response, keeps
// its envelope, projection metadata and every other slice, and replaces only the
// `data.slices.normalized_quotes.rows` array with 51 clearly synthetic rows whose
// shape follows the existing normalized-market DTO (the same shape the backend
// composes). The slice's source/notes/warnings/limits say that plainly. The
// fixture is transport evidence only: it is not a live EEX read, not a PostgreSQL
// read and not proof that the platform persisted these rows. If the actual read is
// not a 200 envelope carrying `slices.normalized_quotes`, it is left as the actual
// response - this helper never forges a whole market context. Every non-matching
// request is continued untouched, and the route is removed in this helper's own
// `finally` before the market page is reloaded from the real API.
//
// The fixture is deliberately exact where exactness is the contract: the first
// row carries a long, signed, retained decimal and its `EUR/MWh` unit verbatim;
// the second row carries contradictory exact/raw text so the component must show
// its invalid-claim diagnostic instead of falling back to a float; the third row
// has no first-received metadata so "unknown receipt" and "unknown publication"
// can be told apart. Publication time is unknown on every row while the receipt
// clock is retained, which is the distinction the component exists to show.
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);
const MARKET_CONTEXT_PATH = "/api/projections/market-context";
const FIXTURE_ROW_COUNT = 51;
const PAGE_SIZE = 50;
const SYNTHETIC_PREFIX = "UAT-SYNTHETIC-EEX-NGP";
const EXACT_FIRST = "-123456789012345.123456789012345";
const UNIT = "EUR/MWh";
const INVALID_FALLBACK_PRICE = 424242.42;
const INVALID_ISSUE = "exact_raw_mismatch";
const INVALID_ISSUE_DETAIL =
  "index_value_raw and index_value_exact describe different values; "
  + "refusing contradictory exact provenance";
const PERIOD_START_MS = Date.UTC(2026, 9, 1, 0, 0, 0);
const PERIOD_MS = 15 * 60 * 1000;
const OBSERVED_AT = "2026-10-02T00:05:00+00:00";
const RECEIPT_AT = "2026-10-02T00:05:00+00:00";
const AVAILABLE_AT = "2026-10-02T00:06:00+00:00";
const RAW_SOURCE_CLOCK = "UAT synthetic provider timestamp text; publication unproven";
const STATUS_EXACT = "exact";
const STATUS_INVALID = "invalid";
const PRICE_SEMANTICS = "reference_index_never_an_executable_bid_or_ask";
const SYNTHETIC_SLICE_SOURCE = "UAT_SYNTHETIC_TRANSPORT_FIXTURE";
const SYNTHETIC_MARKER =
  "UAT synthetic transport fixture: 51 synthetic rows replace the actual normalized_quotes "
  + "rows; not EEX, PostgreSQL, backend or persisted evidence";

const LABEL_KEYS = [
  "title",
  "subtitle",
  "exact_price",
  "exact_unavailable",
  "exact_unavailable_detail",
  "gbp_exact_unavailable",
  "executable_false",
  "publication_unknown",
  "unknown",
  "first_received",
  "publication_time",
  "total_rows",
  "page",
  "previous",
  "next",
  "pagination",
  "evidence_details",
];

function isoUtc(milliseconds) {
  return new Date(milliseconds).toISOString().replace(".000Z", "+00:00");
}

function syntheticSha(index) {
  return (index + 1).toString(16).padStart(2, "0").repeat(32).slice(0, 64);
}

/** One clearly synthetic row in the existing normalized-market DTO shape. */
function syntheticRow(index) {
  const suffix = String(index + 1).padStart(4, "0");
  const periodStartMs = PERIOD_START_MS + index * PERIOD_MS;
  const invalid = index === 1;
  const exact = index === 0
    ? EXACT_FIRST
    : invalid
      ? "424242.42"
      : (1000 + index).toFixed(2);
  const raw = invalid ? "424242.43" : exact;
  const receipt = index === 2 ? null : RECEIPT_AT;
  const exactStatus = invalid ? STATUS_INVALID : STATUS_EXACT;
  return {
    observation_id: `${SYNTHETIC_PREFIX}-OBS-${suffix}`,
    market_venue: "EEX",
    product: "TTF NGP 15min",
    price: invalid ? INVALID_FALLBACK_PRICE : Number(exact),
    unit: UNIT,
    currency: "EUR",
    period_start_utc: isoUtc(periodStartMs),
    period_end_utc: isoUtc(periodStartMs + PERIOD_MS),
    observed_at_utc: OBSERVED_AT,
    source_system: "EEX",
    source_reference: "eex-ttf-ngp-15-mins",
    source_record_id: `${SYNTHETIC_PREFIX}-REC-${suffix}`,
    freshness: "fresh",
    quality_score: 1,
    research_only: true,
    metadata_json: {
      hub: "TTF",
      tenor: "ngp-15-mins",
      source_system: "EEX",
      source_reference: "eex-ttf-ngp-15-mins",
      source_dataset: "ttf-ngp-15min",
      index: "NGP",
      contract_type: "index",
      price_type: "index",
      executable_quote: false,
      simulated: false,
      normalizer_version: "eex-ngp-receipt-v1",
      availability_basis: "response_receipt",
      publication_time_basis: "unknown",
      available_at_utc: AVAILABLE_AT,
      source_receipt_at_utc: receipt,
      publication_time_utc: null,
      publication_timestamp_raw: RAW_SOURCE_CLOCK,
      revision_status: index % 4 === 0 ? "temporary" : "final",
      revision_status_raw: "UAT synthetic provider revision text",
      archive_id: `${SYNTHETIC_PREFIX}-ARCHIVE-${suffix}`,
      payload_sha256: syntheticSha(index),
      ingestion_run_id: `${SYNTHETIC_PREFIX}-INGEST-${suffix}`,
      adapter_version: "uat-synthetic-eex-ngp-adapter-v1",
      index_value_exact: exact,
      index_value_raw: raw,
      index_volume_mwh_exact: "10.000",
      index_volume_raw: "10.000",
    },
    hub: "TTF",
    tenor: "ngp-15-mins",
    is_gas_price: true,
    price_name: "EEX TTF NGP 15min",
    price_gbp_mwh: null,
    price_gbp_mwh_exact: null,
    price_gbp_mwh_provenance: invalid
      ? "refused_invalid_claimed_exact_decimal"
      : "exact_source_decimal_conversion_unavailable",
    source_price_status: exactStatus,
    source_price_exact: invalid ? null : exact,
    source_price_raw: raw,
    source_price_volume_mwh_exact: "10.000",
    source_price_volume_raw: "10.000",
    source_price_volume_status: "valid",
    source_price_provenance: invalid
      ? "unverified_float_claimed_exact_rejected"
      : "eex_ngp_exact_source_decimal",
    source_price_issue: invalid ? INVALID_ISSUE : null,
    source_price_issue_detail: invalid ? INVALID_ISSUE_DETAIL : null,
    source_price_source_system: "EEX",
    source_price_source_reference: "eex-ttf-ngp-15-mins",
    source_price_source_dataset: "ttf-ngp-15min",
    price_float_provenance: invalid
      ? "unverified_float_claimed_exact_rejected"
      : "canonical_float_of_validated_exact_decimal",
    price_semantics: PRICE_SEMANTICS,
    executable_quote: false,
  };
}

const FIXTURE_ROWS = Array.from(
  { length: FIXTURE_ROW_COUNT },
  (_, index) => syntheticRow(index),
);
const FIXTURE_IDS = FIXTURE_ROWS.map((row) => row.observation_id);

function appendMarker(current, marker) {
  if (Array.isArray(current)) return [...current, marker];
  if (typeof current === "string" && current.trim() !== "") return `${current} ${marker}`;
  return [marker];
}

/**
 * Replace only the slice's rows. The slice itself states that they are synthetic; the actual
 * envelope, projection metadata and every other slice stay exactly as the backend served them.
 */
function syntheticQuoteSlice(actualSlice) {
  const actualSource = actualSlice.source;
  const marked = {
    ...actualSlice,
    rows: FIXTURE_ROWS,
    synthetic: true,
    synthetic_marker: SYNTHETIC_MARKER,
    actual_source: actualSource ?? null,
    source: actualSource && typeof actualSource === "object" && !Array.isArray(actualSource)
      ? { ...actualSource, synthetic: true, synthetic_marker: SYNTHETIC_MARKER }
      : SYNTHETIC_SLICE_SOURCE,
    notes: appendMarker(actualSlice.notes, SYNTHETIC_MARKER),
    warnings: appendMarker(
      actualSlice.warnings,
      "51 synthetic transport rows; not EEX, PostgreSQL, backend or persisted evidence",
    ),
  };
  // Keep actual counts/limits consistent with the replaced rows, without inventing fields the
  // slice did not carry. A limit below 51 would otherwise truncate the fixture in the client.
  for (const key of ["row_count", "count", "returned_rows", "total_rows", "total"]) {
    if (typeof marked[key] === "number") marked[key] = FIXTURE_ROWS.length;
  }
  for (const key of ["row_limit", "limit", "max_rows", "max_rows_returned"]) {
    if (typeof marked[key] === "number") {
      marked[key] = Math.max(marked[key], FIXTURE_ROWS.length);
    }
  }
  if (Array.isArray(actualSlice.limits)) {
    marked.limits = [...actualSlice.limits, SYNTHETIC_MARKER];
  } else if (actualSlice.limits && typeof actualSlice.limits === "object") {
    marked.limits = {
      ...actualSlice.limits,
      synthetic: true,
      synthetic_marker: SYNTHETIC_MARKER,
    };
    for (const key of ["row_limit", "limit", "max_rows", "max_rows_returned"]) {
      if (typeof marked.limits[key] === "number") {
        marked.limits[key] = Math.max(marked.limits[key], FIXTURE_ROWS.length);
      }
    }
  } else {
    marked.limits = { synthetic: true, synthetic_marker: SYNTHETIC_MARKER };
  }
  return marked;
}

/**
 * True only for the projection read this helper owns while active. `route.fetch()` keeps the
 * request's own query (gas day, product, focused hub) - the fixture never rewrites the filters.
 */
function isControlledMarketContextRead(url) {
  return url.pathname === MARKET_CONTEXT_PATH;
}

/** The actual projection's normalized-quote slice, or null when the envelope is not that shape. */
function actualProjectionSlice(body) {
  const slice = body?.data?.slices?.normalized_quotes;
  if (!slice || typeof slice !== "object" || Array.isArray(slice)) return null;
  if (!Array.isArray(slice.rows)) return null;
  return slice;
}

/** True for transport-level aborts that superseded this request, not a bad backend answer. */
function isAbortedTransport(error) {
  return /aborted|Target page, context or browser has been closed|Request is already handled|ERR_ABORTED|NS_BINDING_ABORTED/i
    .test(String(error));
}

function safeName(value) {
  return value.replaceAll(/[^a-zA-Z0-9._-]+/g, "-");
}

function loadReferenceLabels(language) {
  const source = JSON.parse(
    readFileSync(
      path.join(REPO_ROOT, "clients", "web", "src", "i18n", language.i18n),
      "utf8",
    ),
  );
  const labels = {};
  for (const key of LABEL_KEYS) {
    const value = source[`referenceIndex.${key}`];
    if (typeof value !== "string" || value.trim() === "") {
      throw new Error(`i18n ${language.i18n} carries no referenceIndex.${key} label`);
    }
    labels[key] = value;
  }
  return labels;
}

function normalizedText(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

async function captureEvidence(page, outputDir, language, viewport, name, fail) {
  const target = path.join(
    outputDir,
    safeName(language.id),
    viewport.id,
    name,
  );
  try {
    mkdirSync(path.dirname(target), { recursive: true });
    await page.locator(".reference-index-evidence").scrollIntoViewIfNeeded().catch(() => {});
    await page.screenshot({ path: target, fullPage: false });
    return target;
  } catch (error) {
    fail(`could not capture ${name}: ${error}`);
    return null;
  }
}

async function renderedIds(page) {
  return page
    .locator('[data-reference-index-row="true"]')
    .evaluateAll((rows) => rows.map((row) => row.getAttribute("data-observation-id")));
}

async function openCardDetails(card) {
  const details = card.locator("details").first();
  if ((await details.getAttribute("open")) === null) {
    await details.locator("summary").click();
  }
  await card.locator("details[open]").waitFor({ state: "visible", timeout: 5_000 });
}

async function waitForReferencePage(page, labels, current, rows) {
  return page
    .waitForFunction(
      ({ pageLabel, wantedCurrent, wantedRows }) => {
        const nav = document.querySelector(".reference-index-pagination");
        const indicator = nav?.querySelector("span")?.textContent
          ?.replace(/\s+/g, " ")
          .trim();
        const rendered = document.querySelectorAll(
          '[data-reference-index-row="true"]',
        ).length;
        return indicator === `${pageLabel} ${wantedCurrent} / 2`
          && rendered === wantedRows;
      },
      { pageLabel: labels.page, wantedCurrent: current, wantedRows: rows },
      { timeout: 15_000 },
    )
    .then(() => true)
    .catch(() => false);
}

/**
 * Walk the real market terminal's `ReferenceIndexEvidence` with a controlled
 * `GET /api/projections/market-context` slice and report in the smoke runner's
 * `{ scope, detail }` shape.
 *
 * The handler fetches the actual authenticated projection, keeps its envelope,
 * metadata and every slice other than `normalized_quotes`, and replaces only that
 * slice's `rows` with 51 synthetic rows. The request's own query is preserved -
 * including the focused `hub=TTF` when the terminal issues it. A non-200 read, an
 * envelope without the slice, or a failed fetch is left as the actual response;
 * this helper never substitutes a fabricated whole context. The route is
 * registered before navigation and removed in `finally`, then the market page is
 * reloaded from the real API so the store cannot keep the fixture. Only the
 * market task that renders the evidence component is opened; the focused hub is
 * set to TTF through the terminal's own hub control (the same state the
 * application uses), never by writing a fake DOM. Every assertion is about the
 * rendered component and the fixture it was given: this helper never claims a
 * backend or database read.
 */
export async function inspectReferenceIndexInteraction({
  page,
  failures,
  observations,
  outputDir,
  baseUrl,
  language,
  viewport,
}) {
  const scope = `interaction/reference-index-evidence/${language.id}/${viewport.id}`;
  const fail = (detail) => failures.push({ scope, detail: String(detail) });
  const note = (detail) => observations.push(`${scope}: ${detail}`);
  const calls = [];
  let eligibleCalls = 0;
  let fixtureFulfilled = 0;
  let routeRegistered = false;
  const originalViewport = page.viewportSize();
  const expectedFirstPage = FIXTURE_IDS.slice(0, PAGE_SIZE);
  let labels = null;
  let screenshot = null;
  let evidence = null;

  const handler = async (route) => {
    const request = route.request();
    if (request.method() !== "GET") {
      await route.continue();
      return;
    }
    const url = new URL(request.url());
    if (!isControlledMarketContextRead(url)) {
      await route.continue();
      return;
    }
    calls.push({
      url: request.url(),
      criteria: `${request.method()} ${url.pathname}`
        + ` gas_day=${url.searchParams.get("gas_day") ?? "(none)"}`
        + ` product=${url.searchParams.get("delivery_product") ?? "(all)"}`
        + ` hub=${url.searchParams.get("hub") ?? "(none)"}`,
      hub: url.searchParams.get("hub"),
    });
    if (url.searchParams.has("hub") && url.searchParams.get("hub") !== "TTF") {
      // Only unscoped or TTF reads are replaced; the terminal focus is a local row filter.
      await route.continue();
      return;
    }
    eligibleCalls += 1;

    let actual;
    try {
      // The request's own row filters (gas day, product, hub) are preserved exactly as the market
      // lane sent them; only the returned normalized-quote rows are replaced.
      actual = await route.fetch();
    } catch (error) {
      // A navigation or newer read may abort this request. Never fabricate a context for it.
      if (!isAbortedTransport(error)) {
        fail(`the actual ${MARKET_CONTEXT_PATH} read for unscoped or TTF context failed to fetch: ${error}`);
      }
      await route.continue().catch(() => {});
      return;
    }

    let body = null;
    try {
      body = await actual.json();
    } catch {
      body = null;
    }
    const slice = actualProjectionSlice(body);
    if (actual.status() !== 200 || slice === null) {
      fail(
        `the actual ${MARKET_CONTEXT_PATH} read for unscoped or TTF context answered HTTP ${actual.status()}`
        + " without data.slices.normalized_quotes.rows; the actual response was left untouched"
        + " and no synthetic context was substituted",
      );
      // No forged fallback: the browser sees the backend's own answer, and a 501 or malformed
      // envelope stays visible as its own console/network evidence.
      await route.fulfill({ response: actual }).catch((error) => {
        // An aborted navigation may prevent even the actual response from being delivered.
        if (!isAbortedTransport(error)) {
          fail(`could not deliver the actual ${MARKET_CONTEXT_PATH} response: ${error}`);
        }
      });
      return;
    }

    body.data.slices.normalized_quotes = syntheticQuoteSlice(slice);
    const headers = { ...actual.headers() };
    delete headers["content-encoding"];
    delete headers["content-length"];
    delete headers["transfer-encoding"];
    headers["content-type"] = "application/json; charset=utf-8";
    headers["cache-control"] = "no-store";
    try {
      await route.fulfill({
        status: 200,
        headers,
        body: JSON.stringify(body),
      });
      fixtureFulfilled += 1;
    } catch (error) {
      // An aborted fulfil is not evidence that the backend was bad, and it is never replaced with
      // a forged context; anything else is a delivery failure worth reporting.
      if (!isAbortedTransport(error)) {
        fail(`could not deliver the synthetic ${MARKET_CONTEXT_PATH} slice: ${error}`);
      }
    }
  };

  try {
    labels = loadReferenceLabels(language);
    await page.route(isControlledMarketContextRead, handler);
    routeRegistered = true;
    mkdirSync(outputDir, { recursive: true });
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(
      `${baseUrl}/?workspace=market&task=curves`,
      { waitUntil: "domcontentloaded" },
    );
    await page.locator("main").waitFor({ state: "visible", timeout: 15_000 });

    const settled = await page
      .waitForFunction(
        () => [...document.querySelectorAll(".workspace-page")]
          .some((element) => element.dataset.workspaceLoadState === "settled"),
        null,
        { timeout: 20_000 },
      )
      .then(() => true)
      .catch(() => false);
    if (!settled) fail("the market workspace read never settled");

    const evidenceSection = page.locator(".reference-index-evidence");
    await evidenceSection.waitFor({ state: "visible", timeout: 20_000 });

    const htmlLang = await page.evaluate(() => document.documentElement.lang);
    if (!String(htmlLang).toLowerCase().startsWith(language.htmlPrefix.toLowerCase())) {
      fail(`document language is '${htmlLang}', not '${language.htmlPrefix}'`);
    }

    // The index filters by the terminal's focused hub. Select TTF through the
    // product's own hub control; if it is already selected, do not toggle it off.
    const ttfButton = page
      .locator(".market-hub-focus-button")
      .filter({ hasText: "TTF" })
      .first();
    await ttfButton.waitFor({ state: "visible", timeout: 10_000 });
    if ((await ttfButton.getAttribute("aria-pressed")) !== "true") {
      await ttfButton.click();
    }
    const hubApplied = await page
      .waitForFunction(
        () => {
          const button = [...document.querySelectorAll(".market-hub-focus-button")]
            .find((element) => element.textContent?.trim() === "TTF");
          return button?.getAttribute("aria-pressed") === "true";
        },
        null,
        { timeout: 5_000 },
      )
      .then(() => true)
      .catch(() => false);
    if (!hubApplied) fail("the market terminal did not focus hub TTF");

    const ready = await page
      .waitForFunction(
        (wantedRows) => {
          const total = document.querySelector("[data-reference-index-total]");
          const section = document.querySelector(".reference-index-evidence");
          return total?.getAttribute("data-reference-index-total") === String(wantedRows)
            && section?.querySelectorAll('[data-reference-index-row="true"]').length === 50;
        },
        FIXTURE_ROW_COUNT,
        { timeout: 20_000 },
      )
      .then(() => true)
      .catch(() => false);
    if (!ready) {
      const actual = await page.evaluate(() => ({
        total: document.querySelector("[data-reference-index-total]")
          ?.getAttribute("data-reference-index-total") ?? null,
        rows: document.querySelectorAll('[data-reference-index-row="true"]').length,
        empty: document.querySelector("[data-reference-index-empty]") !== null,
        text: (document.querySelector(".reference-index-evidence")?.textContent ?? "")
          .replace(/\s+/g, " ")
          .trim()
          .slice(0, 240),
      }));
      actual.requests = calls.map((call) => call.criteria);
      actual.eligibleRequests = eligibleCalls;
      throw new Error(
        "the 51-row synthetic fixture did not reach the reference index:"
        + ` ${JSON.stringify(actual)}`,
      );
    }
    if (calls.length === 0) {
      fail(`the controlled GET ${MARKET_CONTEXT_PATH} route was never requested`);
    } else if (eligibleCalls === 0) {
      fail(
        `the controlled GET ${MARKET_CONTEXT_PATH} route was never requested for unscoped or TTF context, so the`
        + " synthetic rows cannot be attributed to the focused hub",
      );
    }

    const title = normalizedText(await page.locator("#reference-index-title").textContent());
    if (title !== labels.title) fail(`title '${title}' is not '${labels.title}'`);
    const subtitle = normalizedText(
      await page.locator(".reference-index-evidence .panel-copy").first().textContent(),
    );
    if (subtitle !== labels.subtitle) fail(`subtitle '${subtitle}' is not '${labels.subtitle}'`);
    const paginationLabel = await page
      .locator(".reference-index-pagination")
      .getAttribute("aria-label");
    if (paginationLabel !== labels.pagination) {
      fail(`pagination label '${paginationLabel}' is not '${labels.pagination}'`);
    }

    const totalAttribute = await page
      .locator("[data-reference-index-total]")
      .first()
      .getAttribute("data-reference-index-total");
    if (totalAttribute !== String(FIXTURE_ROW_COUNT)) {
      fail(`total is '${totalAttribute}', not ${FIXTURE_ROW_COUNT}`);
    }
    const metaText = normalizedText(
      await page.locator(".reference-index-meta").first().textContent(),
    );
    if (!metaText.includes(labels.total_rows) || !metaText.includes(String(FIXTURE_ROW_COUNT))) {
      fail(`the total-row label is not the measured total: '${metaText}'`);
    }

    const pagination = page.locator(".reference-index-pagination");
    const pageButtons = pagination.locator("button");
    const pageIndicator = async () => normalizedText(
      await pagination.locator("span").first().textContent(),
    );
    if (normalizedText(await pageButtons.nth(0).textContent()) !== labels.previous) {
      fail("the previous-page control does not carry the i18n label");
    }
    if (normalizedText(await pageButtons.nth(1).textContent()) !== labels.next) {
      fail("the next-page control does not carry the i18n label");
    }
    if ((await pageIndicator()) !== `${labels.page} 1 / 2`) {
      fail(`first page states '${await pageIndicator()}', not '${labels.page} 1 / 2'`);
    }

    const firstPageIds = await renderedIds(page);
    if (firstPageIds.length !== PAGE_SIZE) {
      fail(`first page renders ${firstPageIds.length} row(s), not ${PAGE_SIZE}`);
    }
    if (JSON.stringify(firstPageIds) !== JSON.stringify(expectedFirstPage)) {
      fail(
        "first page does not retain the first 50 periods in order:"
        + ` expected ${JSON.stringify(expectedFirstPage.slice(0, 2))}...;`
        + ` received ${JSON.stringify(firstPageIds.slice(0, 2))}...`,
      );
    }

    // The component's own exact-price element, held to the retained string and
    // unit rather than to a formatted or converted value.
    const firstCard = page.locator(
      `[data-reference-index-row="true"][data-observation-id="${FIXTURE_IDS[0]}"]`,
    );
    if ((await firstCard.count()) !== 1) {
      fail("the first fixture period is not rendered by its own observation id");
    } else {
      const exactField = firstCard.locator('[data-reference-index-field="exact-price"]');
      const exactText = normalizedText(await exactField.locator("strong").first().textContent());
      if (exactText !== EXACT_FIRST) {
        fail(`exact price text '${exactText}' is not '${EXACT_FIRST}'`);
      }
      const unitText = normalizedText(
        await exactField.locator(".reference-index-unit").first().textContent(),
      );
      if (unitText !== UNIT) fail(`exact price unit '${unitText}' is not '${UNIT}'`);
      if (normalizedText(await exactField.locator("span").first().textContent())
        !== labels.exact_price) {
        fail("the exact-price field does not carry its i18n label");
      }

      const executableField = firstCard.locator(
        '[data-reference-index-field="executable-quote"]',
      );
      const executableText = normalizedText(await executableField.textContent());
      if (executableText !== labels.executable_false) {
        fail(`source index is labelled '${executableText}', not '${labels.executable_false}'`);
      }
      const executableClass = (await executableField.getAttribute("class")) ?? "";
      if (!executableClass.split(/\s+/).includes("is-reference-only")) {
        fail("the source index is not styled as reference-only");
      }

      // Unknown publication and the retained receipt are separate facts: the
      // publication field must say unknown, while first-received names the
      // receipt clock. The receipt is never substituted for publication.
      const publicationText = normalizedText(
        await firstCard.locator('[data-reference-index-field="publication-time"]').textContent(),
      );
      if (publicationText !== labels.publication_unknown) {
        fail(`publication is '${publicationText}', not '${labels.publication_unknown}'`);
      }
      const receivedText = normalizedText(
        await firstCard.locator('[data-reference-index-field="first-received"]').textContent(),
      );
      if (receivedText === labels.unknown || receivedText === "") {
        fail("the retained receipt clock is rendered as unknown");
      }
      const sourceClock = normalizedText(
        await firstCard.locator('[data-reference-index-field="source-clock"]').textContent(),
      );
      if (!sourceClock.includes(RAW_SOURCE_CLOCK)) {
        fail("the raw provider clock text is not retained in the evidence");
      }
      const factsText = normalizedText(
        await firstCard.locator(".reference-index-facts").textContent(),
      );
      for (const label of [labels.first_received, labels.publication_time]) {
        if (!factsText.includes(label)) {
          fail(`the evidence facts do not carry the '${label}' label`);
        }
      }

      // The raw lineage is in the component's own details disclosure. The
      // synthetic archive/record/run values below are fixture evidence only.
      await openCardDetails(firstCard);
      const detailsSummary = normalizedText(
        await firstCard.locator("details summary").textContent(),
      );
      if (detailsSummary !== labels.evidence_details) {
        fail(`the details summary is '${detailsSummary}', not '${labels.evidence_details}'`);
      }
      const detailsText = normalizedText(await firstCard.textContent());
      const lineageValues = [
        `${SYNTHETIC_PREFIX}-ARCHIVE-0001`,
        `${SYNTHETIC_PREFIX}-REC-0001`,
        `${SYNTHETIC_PREFIX}-INGEST-0001`,
        syntheticSha(0),
        "uat-synthetic-eex-ngp-adapter-v1",
        "eex-ngp-receipt-v1",
        "response_receipt",
        RECEIPT_AT,
        AVAILABLE_AT,
        RAW_SOURCE_CLOCK,
        EXACT_FIRST,
        "eex_ngp_exact_source_decimal",
        "canonical_float_of_validated_exact_decimal",
        PRICE_SEMANTICS,
        "10.000",
        "valid",
        "ttf-ngp-15min",
        "eex-ttf-ngp-15-mins",
      ];
      for (const value of lineageValues) {
        if (!detailsText.includes(value)) {
          fail(`the raw lineage does not carry '${value}'`);
        }
      }

      // A contradictory exact claim is a diagnostic, never the canonical float.
      const invalidCard = page.locator(
        `[data-reference-index-row="true"][data-observation-id="${FIXTURE_IDS[1]}"]`,
      );
      if ((await invalidCard.count()) !== 1) {
        fail("the invalid-claim period is not rendered by its own observation id");
      } else {
        const invalidExact = invalidCard.locator(
          '[data-reference-index-field="exact-price"]',
        );
        const invalidText = normalizedText(await invalidExact.textContent());
        for (const value of [
          labels.exact_unavailable,
          labels.exact_unavailable_detail,
          STATUS_INVALID,
          INVALID_ISSUE,
          INVALID_ISSUE_DETAIL,
        ]) {
          if (!invalidText.includes(value)) {
            fail(`the invalid exact claim does not show '${value}'`);
          }
        }
        if (invalidText.includes(String(INVALID_FALLBACK_PRICE))) {
          fail("the invalid exact claim fell back to the canonical float");
        }
        if ((await invalidExact.locator(".reference-index-unavailable").count()) !== 1) {
          fail("the invalid exact claim has no explicit unavailable diagnostic");
        }
        const gbpText = normalizedText(
          await invalidCard.locator(".reference-index-gbp-exact").textContent(),
        );
        if (!gbpText.includes(labels.gbp_exact_unavailable)) {
          fail("the invalid exact claim fabricated a GBP exact value");
        }
      }

      // The third row has no first-received receipt metadata; the component must
      // say unknown for the receipt while publication remains its own unknown.
      const missingReceipt = page.locator(
        `[data-reference-index-row="true"][data-observation-id="${FIXTURE_IDS[2]}"]`,
      );
      if ((await missingReceipt.count()) !== 1) {
        fail("the missing-receipt period is not rendered by its own observation id");
      } else {
        const receiptText = normalizedText(
          await missingReceipt.locator('[data-reference-index-field="first-received"]').textContent(),
        );
        const publicationText = normalizedText(
          await missingReceipt.locator('[data-reference-index-field="publication-time"]').textContent(),
        );
        if (receiptText !== labels.unknown) {
          fail(`a missing receipt is rendered as '${receiptText}', not '${labels.unknown}'`);
        }
        if (publicationText !== labels.publication_unknown) {
          fail(
            `a missing publication is rendered as '${publicationText}', not`
            + ` '${labels.publication_unknown}'`,
          );
        }
        if (labels.unknown === labels.publication_unknown) {
          fail("the i18n labels conflate an unknown receipt with an unknown publication");
        }
      }
    }

    // First page of 50, next page of 1, then back to the same 50.
    if (await pageButtons.nth(0).isDisabled() !== true) {
      fail("the previous-page control is enabled on first page");
    }
    if (await pageButtons.nth(1).isDisabled() !== false) {
      fail("the next-page control is disabled on first page");
    }
    await pageButtons.nth(1).click();
    if (!(await waitForReferencePage(page, labels, "2", 1))) {
      fail("next did not render the single second-page period");
    }
    const secondPageIds = await renderedIds(page);
    if (secondPageIds.length !== 1 || secondPageIds[0] !== FIXTURE_IDS[50]) {
      fail(
        "second page does not retain the 51st period:"
        + ` ${JSON.stringify(secondPageIds)}`,
      );
    }
    if (await pageButtons.nth(1).isDisabled() !== true) {
      fail("the next-page control is enabled on the last page");
    }
    if (await pageButtons.nth(0).isDisabled() !== false) {
      fail("the previous-page control is disabled on the last page");
    }
    await pageButtons.nth(0).click();
    if (!(await waitForReferencePage(page, labels, "1", PAGE_SIZE))) {
      fail("previous did not restore the 50-row first page");
    }
    const restoredIds = await renderedIds(page);
    if (JSON.stringify(restoredIds) !== JSON.stringify(expectedFirstPage)) {
      fail("returning to the first page did not retain the same 50 periods");
    }
    const retained = [...firstPageIds, ...secondPageIds];
    if (retained.length !== FIXTURE_ROW_COUNT
      || new Set(retained).size !== FIXTURE_ROW_COUNT
      || FIXTURE_IDS.some((id) => !retained.includes(id))) {
      fail(
        `the two pages retain ${retained.length}/${FIXTURE_ROW_COUNT} distinct periods`,
      );
    }

    // Re-open the lineage on the restored first page so the screenshot and the
    // overflow measurement cover the evidence state, not just the closed list.
    const restoredFirst = page.locator(
      `[data-reference-index-row="true"][data-observation-id="${FIXTURE_IDS[0]}"]`,
    );
    if ((await restoredFirst.count()) === 1) {
      await openCardDetails(restoredFirst);
    }

    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    if (overflow.scrollWidth > overflow.clientWidth + 2) {
      fail(
        `document horizontal overflow ${overflow.scrollWidth}px >`
        + ` ${overflow.clientWidth}px at ${viewport.width}px`,
      );
    }

    screenshot = await captureEvidence(
      page,
      outputDir,
      language,
      viewport,
      "reference-index-evidence.png",
      fail,
    );
    evidence = {
      language: language.id,
      viewport: viewport.id,
      fixturePath: MARKET_CONTEXT_PATH,
      fixtureRows: FIXTURE_ROW_COUNT,
      fixtureSlice: "data.slices.normalized_quotes.rows",
      fixtureRequests: calls.length,
      eligibleRequests: eligibleCalls,
      fixtureFulfilled,
      requestCriteria: [...new Set(calls.map((call) => call.criteria))],
      firstPageRows: firstPageIds.length,
      secondPageRows: secondPageIds.length,
      totalRows: Number(totalAttribute),
      periodsRetained: retained.length,
      requests: calls.length,
      htmlLang,
      document: overflow,
      screenshot,
      fixture: "synthetic transport only; rows replaced in data.slices.normalized_quotes with explicit slice markers; no backend or database proof",
    };
  } catch (error) {
    fail(error);
    await captureEvidence(
      page,
      outputDir,
      language,
      viewport,
      "reference-index-evidence-error.png",
      fail,
    );
  } finally {
    const routeRemoved = await page
      .unroute(isControlledMarketContextRead, handler)
      .then(() => true)
      .catch((error) => {
        fail(`could not remove the controlled ${MARKET_CONTEXT_PATH} route: ${error}`);
        return false;
      });
    if (routeRegistered && routeRemoved) {
      // Remove the route before reloading: the store keeps the last projection it read, and a
      // synthetic slice must not leak into an unrelated check. A failed reload is reported as the
      // actual navigation failure, never patched with the fixture.
      await page
        .goto(`${baseUrl}/?workspace=market&task=curves`, { waitUntil: "domcontentloaded" })
        .catch((error) => {
          fail(`could not reload the actual market page after removing the fixture: ${error}`);
        });
      await page.locator("main").waitFor({ state: "visible", timeout: 15_000 }).catch(() => {});
      const actualTtf = page
        .locator(".market-hub-focus-button")
        .filter({ hasText: "TTF" })
        .first();
      await actualTtf.waitFor({ state: "visible", timeout: 15_000 }).catch(() => {});
      const actualTtfCount = await actualTtf.count().catch(() => 0);
      const actualTtfPressed = actualTtfCount === 1
        ? await actualTtf.getAttribute("aria-pressed").catch(() => null)
        : null;
      if (actualTtfCount === 1 && actualTtfPressed !== "true") {
        await actualTtf.click().catch((error) => {
          fail(`could not focus TTF on the actual market reload: ${error}`);
        });
      }
    }
    if (originalViewport) {
      await page.setViewportSize(originalViewport).catch((error) => {
        fail(`could not restore viewport: ${error}`);
      });
    }
  }
  note(
    `synthetic ${MARKET_CONTEXT_PATH} slice fixture only: ${calls.length} read(s) observed,`
    + ` ${eligibleCalls} for unscoped or TTF context (${fixtureFulfilled} fulfilled); only`
    + ` data.slices.normalized_quotes.rows replaced with ${FIXTURE_ROW_COUNT} synthetic rows;`
    + (fixtureFulfilled > 0
      ? " actual envelope, metadata and other slices preserved;"
      : " no synthetic slice was substituted;")
    + ` ${PAGE_SIZE}+1 pagination, EN/ZH labels, reference-only and unknown`
    + " publication/receipt checks attempted; verdict is in failures/results; no backend or database proof;"
    + ` evidence under ${outputDir}`,
  );
  return evidence;
}
