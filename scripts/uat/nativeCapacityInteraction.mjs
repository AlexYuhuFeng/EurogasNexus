// Synthetic browser interaction for the NativeCapacityContextPanel.
//
// The panel is walked in the authenticated capacity workspace with a controlled
// transport fixture for exactly one explicit point id (`UAT-NATIVE-CONTEXT`), plus
// suffixed variants used only for the error, empty and superseded query paths.
// The fixture answers only native-basis reads whose `point_id` is one of those
// controlled ids; every other physical read is continued untouched, so the
// default-volume workspace reads and other points are never fabricated here.
// Nothing in this file is a live ENTSOG, PostgreSQL or model-accuracy claim.
import { mkdirSync } from "node:fs";
import path from "node:path";

const CONTEXT_POINT = "UAT-NATIVE-CONTEXT";
const ERROR_POINT = `${CONTEXT_POINT}-ERROR`;
const EMPTY_POINT = `${CONTEXT_POINT}-EMPTY`;
const SLOW_POINT = `${CONTEXT_POINT}-SLOW`;
const CONTROLLED_POINTS = new Set([CONTEXT_POINT, ERROR_POINT, EMPTY_POINT, SLOW_POINT]);
const INDUCED_REFUSAL_STATUS = 503;

/** Route only native-basis reads for the controlled point ids; every other read bypasses. */
function isControlledNativePhysicalRead(url) {
  if (url.pathname !== "/api/physical/flows" && url.pathname !== "/api/physical/capacity") {
    return false;
  }
  const params = url.searchParams;
  const point = params.get("point_id") ?? params.get("point") ?? "";
  return params.get("quantity_basis") === "native" && [
    "UAT-NATIVE-CONTEXT",
    "UAT-NATIVE-CONTEXT-ERROR",
    "UAT-NATIVE-CONTEXT-EMPTY",
    "UAT-NATIVE-CONTEXT-SLOW",
  ].includes(point);
}

const FLOW_EXACT = "246913578024690.246913578024690";
const CAPACITY_EXACT = "123456789012345.123456789012345";
const FLOW_SHA = "a".repeat(64);
const CAPACITY_SHA = "b".repeat(64);
const FLOW_REFERENCE = "UAT-SYNTHETIC-ENTSOG-FLOW-REF-001";
const FLOW_RECORD = "UAT-SYNTHETIC-ENTSOG-FLOW-REC-001";
const FLOW_ARCHIVE = "UAT-SYNTHETIC-ARCHIVE-FLOW-001";
const CAPACITY_REFERENCE = "UAT-SYNTHETIC-ENTSOG-CAPACITY-REF";
const CAPACITY_RECORD = "UAT-SYNTHETIC-ENTSOG-CAPACITY-REC";
const CAPACITY_ARCHIVE = "UAT-SYNTHETIC-ARCHIVE-CAPACITY";
const PERIOD_START = "2026-10-01T00:00:00Z";
const PERIOD_END = "2026-10-02T00:00:00Z";
const CAPACITY_START = "2026-09-30T00:00:00Z";
const CAPACITY_END = "2026-10-03T00:00:00Z";
const OBSERVED_AT = "2026-10-02T00:05:00Z";
const RECEIVED_AT = "2026-10-02T00:10:00Z";
const NATIVE_META = {
  research_only: true,
  human_review_required: true,
  warnings: [],
  source_references: ["UAT synthetic browser transport fixture; not a live ENTSOG read"],
  missing_inputs: [],
};

function nativeRate(value) {
  return {
    value_text: value,
    unit_text: "kWh/day",
    native_value: value,
    normalized_unit: "kWh/day",
    quantity_kind: "energy",
    rate_basis: "day",
    energy_kwh_per_day: value,
    volume_mcm_per_day: null,
    normalizer_version: "entsog-native-units-v1",
  };
}

function nativeFlow(point, index, idPrefix = "UAT-NATIVE-FLOW") {
  const suffix = String(index).padStart(3, "0");
  return {
    observation_id: `${idPrefix}-${suffix}`,
    source_record_id: `UAT-SYNTHETIC-ENTSOG-FLOW-REC-${suffix}`,
    point_id: point,
    point_name: "UAT synthetic native context point",
    direction: "entry",
    period_start_utc: PERIOD_START,
    period_end_utc: PERIOD_END,
    observed_at_utc: OBSERVED_AT,
    source_system: "ENTSOG",
    operator_key: "UAT-SYNTHETIC-TSO",
    flow_status: "confirmed",
    period_type: "day",
    source_reference: `UAT-SYNTHETIC-ENTSOG-FLOW-REF-${suffix}`,
    research_only: true,
    quantity_basis: "native",
    normalizer_version: "entsog-native-units-v1",
    native_rate_json: nativeRate(FLOW_EXACT),
    raw_archive_id: `UAT-SYNTHETIC-ARCHIVE-FLOW-${suffix}`,
    payload_sha256: FLOW_SHA,
    received_at_utc: RECEIVED_AT,
    kind: "actual",
  };
}

function nativeCapacity(point) {
  return {
    observation_id: "UAT-NATIVE-CAPACITY-001",
    source_record_id: CAPACITY_RECORD,
    point_id: point,
    point_name: "UAT synthetic native context point",
    direction: "entry",
    period_start_utc: CAPACITY_START,
    period_end_utc: CAPACITY_END,
    observed_at_utc: OBSERVED_AT,
    source_system: "ENTSOG",
    operator_key: "UAT-SYNTHETIC-TSO",
    flow_status: "confirmed",
    period_type: "day",
    source_reference: CAPACITY_REFERENCE,
    research_only: true,
    quantity_basis: "native",
    normalizer_version: "entsog-native-units-v1",
    native_rate_json: nativeRate(CAPACITY_EXACT),
    raw_archive_id: CAPACITY_ARCHIVE,
    payload_sha256: CAPACITY_SHA,
    received_at_utc: RECEIVED_AT,
    capacity_type: "firm_technical",
  };
}

function nativeEnvelope(kind, point) {
  let data;
  if (point === EMPTY_POINT) {
    data = [];
  } else if (kind === "flows") {
    data = point === SLOW_POINT
      ? [nativeFlow(point, 1, "UAT-NATIVE-SLOW-FLOW")]
      : Array.from({ length: 51 }, (_, index) => nativeFlow(point, index + 1));
  } else {
    data = [nativeCapacity(point)];
  }
  return { data, meta: NATIVE_META };
}

/** The panel state the assertions read, serialised into the page. */
function readNativeCapacityPanel() {
  const panel = document.querySelector("[data-native-panel-state]");
  const cards = [...document.querySelectorAll("[data-native-context]")];
  const range = document.querySelector("[data-native-page-range]");
  return {
    state: panel?.getAttribute("data-native-panel-state") ?? null,
    contexts: cards.length,
    ids: cards.map((card) => card.getAttribute("data-native-context-id")),
    start: Number(range?.getAttribute("data-native-page-start")),
    end: Number(range?.getAttribute("data-native-page-end")),
    total: Number(range?.getAttribute("data-native-page-total")),
    current: document.querySelector("[data-native-page-current]")?.textContent?.trim() ?? null,
    pageCount: document.querySelector("[data-native-page-count]")?.textContent?.trim() ?? null,
    resolved: document.querySelector("[data-native-resolved-point] code")?.textContent?.trim() ?? null,
    empty: document.querySelector('[data-native-state="empty"]') !== null,
    error: document.querySelector('[data-native-state="error"]') !== null,
    errorCode: document.querySelector('[data-native-state="error"] code')?.textContent?.trim() ?? null,
  };
}

async function waitForPanelState(page, state) {
  return page
    .waitForFunction(
      (wanted) => document.querySelector("[data-native-panel-state]")
        ?.getAttribute("data-native-panel-state") === wanted,
      state,
      { timeout: 20_000 },
    )
    .then(() => true)
    .catch(() => false);
}

async function waitForPagination(page, current, rows, start, end) {
  return page
    .waitForFunction(
      ([wantedCurrent, wantedRows, wantedStart, wantedEnd]) => {
        const cards = document.querySelectorAll("[data-native-context]").length;
        const range = document.querySelector("[data-native-page-range]");
        return document.querySelector("[data-native-page-current]")?.textContent?.trim()
            === wantedCurrent
          && cards === wantedRows
          && range?.getAttribute("data-native-page-start") === wantedStart
          && range?.getAttribute("data-native-page-end") === wantedEnd;
      },
      [current, rows, start, end],
      { timeout: 15_000 },
    )
    .then(() => true)
    .catch(() => false);
}

async function captureEvidence(page, outputDir, name, fail) {
  try {
    mkdirSync(outputDir, { recursive: true });
    await page.locator("[data-native-panel-state]").scrollIntoViewIfNeeded().catch(() => {});
    await page.screenshot({ path: path.join(outputDir, name), fullPage: false });
  } catch (error) {
    fail(`could not capture ${name}: ${error}`);
  }
}

/**
 * The controlled route handler: only native-basis reads for the fixture points are fulfilled.
 *
 * `onInducedReadRefusal` is optional. It receives the actual request URL and the status the
 * fixture is about to return for the one deliberately refused capacity read, before that refusal
 * is fulfilled, so the caller can attribute the browser's console error to the harness's own
 * fixture rather than to the product.
 */
function createNativeCapacityRouteHandler({
  calls,
  slowGate,
  markSlowHandled,
  settleSlow,
  onSlowStarted,
  onInducedReadRefusal,
}) {
  return async (route) => {
    const request = route.request();
    if (request.method() !== "GET") {
      await route.continue();
      return;
    }
    const url = new URL(request.url());
    const kind = url.pathname.endsWith("/flows")
      ? "flows"
      : url.pathname.endsWith("/capacity")
        ? "capacity"
        : null;
    if (!kind) {
      await route.continue();
      return;
    }
    const params = url.searchParams;
    const point = params.get("point_id") ?? params.get("point") ?? "";
    if (params.get("quantity_basis") !== "native" || !CONTROLLED_POINTS.has(point)) {
      // Defensive only: the route matcher already refuses these reads.
      await route.continue();
      return;
    }
    calls.push({ kind, url: request.url(), point });
    try {
      if (point === ERROR_POINT && kind === "capacity") {
        try {
          onInducedReadRefusal?.(request.url(), INDUCED_REFUSAL_STATUS);
        } finally {
          await route.fulfill({
            status: INDUCED_REFUSAL_STATUS,
            contentType: "application/json",
            body: JSON.stringify({ detail: { error: "service_unavailable" } }),
          });
        }
        return;
      }
      if (point === SLOW_POINT && kind === "capacity") {
        onSlowStarted();
        markSlowHandled();
        try {
          await slowGate;
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(nativeEnvelope(kind, point)),
          });
        } finally {
          settleSlow();
        }
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(nativeEnvelope(kind, point)),
      });
    } catch {
      // A superseded request may be aborted before its fixture is delivered.
    }
  };
}

/** Assert both successful native reads carried the exact basis, point and bound. */
function assertNativeQueryUrls(calls, fail) {
  for (const kind of ["flows", "capacity"]) {
    if (!calls.some((call) => call.kind === kind)) {
      fail(`the successful query issued no native ${kind} read`);
    }
  }
  for (const call of calls) {
    const params = new URL(call.url).searchParams;
    if (params.get("quantity_basis") !== "native") fail(`a native read lost the native basis: ${call.url}`);
    if (params.get("point_id") !== CONTEXT_POINT) fail(`a native read lost the exact point id: ${call.url}`);
    if (params.get("limit") !== "2000") fail(`a native read did not ask for limit 2000: ${call.url}`);
  }
}

/** True when the edited input still carries the loaded query's resolved point label. */
function editedInputKeepsLoadedLabel(page, point) {
  return page
    .waitForFunction(
      (wanted) => document.querySelector("[data-native-point-id]")?.value === `${wanted}-EDITED`
        && document.querySelector("[data-native-resolved-point] code")
          ?.textContent?.trim() === wanted,
      point,
      { timeout: 5_000 },
    )
    .then(() => true)
    .catch(() => false);
}

/**
 * Walk the native capacity panel with actual browser interactions and report
 * failures in the smoke runner's `{ scope, detail }` shape.
 *
 * The route handler is registered before navigation and removed in `finally`.
 * It fulfils only `GET` native-basis reads for the controlled point ids; all
 * other physical reads reach the application unchanged. When
 * `onInducedReadRefusal` is supplied, the helper reports the one deliberate
 * capacity refusal's exact URL and status before answering it, and calls any
 * cleanup that callback returns in its own `finally` so the caller's active
 * attribution window is scoped to this interaction.
 */
export async function inspectNativeCapacityInteraction({
  page,
  failures,
  observations,
  outputDir,
  baseUrl,
  onInducedReadRefusal,
}) {
  const scope = "interaction/native-capacity-context";
  const fail = (detail) => failures.push({ scope, detail: String(detail) });
  const note = (detail) => observations.push(`${scope}: ${detail}`);
  const calls = [];
  const inducedRefusalCleanups = [];
  let releaseSlow = () => {};
  let settleSlow = () => {};
  let markSlowHandled = () => {};
  let slowStarted = false;
  const slowGate = new Promise((resolve) => { releaseSlow = resolve; });
  const slowDone = new Promise((resolve) => { settleSlow = resolve; });
  const slowHandled = new Promise((resolve) => { markSlowHandled = resolve; });
  const handler = createNativeCapacityRouteHandler({
    calls,
    slowGate,
    markSlowHandled,
    settleSlow,
    onSlowStarted: () => { slowStarted = true; },
    onInducedReadRefusal: (url, status) => {
      const cleanup = onInducedReadRefusal?.(url, status);
      if (typeof cleanup === "function") inducedRefusalCleanups.push(cleanup);
    },
  });

  let evidence = null;
  try {
    await page.route(isControlledNativePhysicalRead, handler);
    mkdirSync(outputDir, { recursive: true });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`${baseUrl}/?workspace=capacity`, { waitUntil: "domcontentloaded" });
    const settled = await page
      .waitForFunction(
        () => [...document.querySelectorAll(".workspace-page")]
          .some((element) => element.dataset.workspaceLoadState === "settled"),
        null,
        { timeout: 20_000 },
      )
      .then(() => true)
      .catch(() => false);
    if (!settled) fail("the capacity workspace read never settled");

    const panel = page.locator("[data-native-panel-state]");
    await panel.waitFor({ state: "visible", timeout: 15_000 });
    const input = page.locator("[data-native-point-id]");
    await input.waitFor({ state: "visible", timeout: 10_000 });
    const submit = page.locator('[data-native-query-form] button[type="submit"]');
    const submitPoint = async (point) => {
      await input.fill(point);
      await submit.click();
    };

    const idle = await page.evaluate(readNativeCapacityPanel);
    if (idle.state !== "idle") fail(`the panel opens in '${idle.state}', not 'idle'`);
    if (calls.length !== 0) {
      fail(`the panel fetched ${calls.length} native-basis read(s) before any query was submitted`);
    }

    await submitPoint(ERROR_POINT);
    if (!(await waitForPanelState(page, "error"))) {
      const actual = await page.evaluate(readNativeCapacityPanel);
      fail(`the refused capacity read did not reach the error state (state '${actual.state}')`);
    } else {
      const errored = await page.evaluate(readNativeCapacityPanel);
      if (!errored.error || !/HTTP 503/.test(errored.errorCode ?? "")) {
        fail(`the error state does not name the refused read's HTTP 503: '${errored.errorCode ?? ""}'`);
      }
    }
    await captureEvidence(page, outputDir, "native-capacity-context-error.png", fail);

    await submitPoint(EMPTY_POINT);
    if (!(await waitForPanelState(page, "success"))) {
      fail("the measured-empty read did not reach the success state");
    }
    const empty = await page.evaluate(readNativeCapacityPanel);
    if (!empty.empty || empty.contexts !== 0) {
      fail(`the empty read did not replace the error with its measured-empty state (${empty.contexts} row(s))`);
    }

    const slowRequest = page.waitForRequest((request) => {
      try {
        const url = new URL(request.url());
        return url.pathname.endsWith("/physical/capacity")
          && url.searchParams.get("quantity_basis") === "native"
          && url.searchParams.get("point_id") === SLOW_POINT;
      } catch {
        return false;
      }
    }, { timeout: 20_000 });
    const slowFlows = page.waitForResponse((response) => {
      try {
        const url = new URL(response.url());
        return url.pathname.endsWith("/physical/flows")
          && url.searchParams.get("quantity_basis") === "native"
          && url.searchParams.get("point_id") === SLOW_POINT
          && response.status() === 200;
      } catch {
        return false;
      }
    }, { timeout: 20_000 }).catch(() => null);
    await submitPoint(SLOW_POINT);
    const slowSeen = await slowRequest.then(() => true).catch(() => false);
    if (!slowSeen) fail("the delayed query never issued its native capacity read");
    if (slowSeen) await slowHandled;
    // Let the immediate flows half of the slow read settle so the second submit aborts
    // only the delayed capacity read, the request this harness already owns.
    if (slowSeen) await slowFlows;
    if (!(await waitForPanelState(page, "loading"))) {
      fail("the delayed query never showed its loading state");
    }
    await submitPoint(CONTEXT_POINT);
    if (!(await waitForPanelState(page, "success"))) {
      fail("the query that superseded the delayed one did not reach success");
    }
    releaseSlow();
    if (slowSeen && slowStarted) await slowDone;
    const afterSlow = await page.evaluate(readNativeCapacityPanel);
    if (afterSlow.state !== "success" || afterSlow.resolved !== CONTEXT_POINT) {
      fail(`the delayed superseded response published over the newer query ('${afterSlow.state}')`);
    }
    if (afterSlow.ids.includes("UAT-NATIVE-SLOW-FLOW-001")) {
      fail("the delayed superseded response rendered its flow after the newer query succeeded");
    }

    const success = await page.evaluate(readNativeCapacityPanel);
    if (success.resolved !== CONTEXT_POINT) {
      fail(`the loaded query is labelled '${success.resolved ?? "(none)"}', not '${CONTEXT_POINT}'`);
    }
    if (success.contexts !== 50 || success.total !== 51 || success.start !== 1 || success.end !== 50) {
      fail(
        "the first page is not 50 of 51:"
        + ` ${success.contexts} row(s), ${success.start}-${success.end} of ${success.total}`,
      );
    }
    if (success.current !== "1" || success.pageCount !== "2") {
      fail(`the first page states page '${success.current}' of '${success.pageCount}', not 1 of 2`);
    }
    if (success.ids[0] !== "UAT-NATIVE-FLOW-001") {
      fail(`the first page opens on '${success.ids[0] ?? "(no row)"}', not the ordered first flow`);
    }

    assertNativeQueryUrls(calls.filter((call) => call.point === CONTEXT_POINT), fail);

    await page.locator('[data-native-page-action="next"]').click();
    if (!(await waitForPagination(page, "2", 1, "51", "51"))) {
      const actual = await page.evaluate(readNativeCapacityPanel);
      fail(`next did not render the single second-page row: ${JSON.stringify(actual)}`);
    }
    await page.locator('[data-native-page-action="previous"]').click();
    if (!(await waitForPagination(page, "1", 50, "1", "50"))) {
      const actual = await page.evaluate(readNativeCapacityPanel);
      fail(`previous did not restore the 50-row first page: ${JSON.stringify(actual)}`);
    }

    const first = page.locator('[data-native-context-id="UAT-NATIVE-FLOW-001"]');
    if ((await first.count()) !== 1) {
      fail("the first page does not render the first fixture flow by its own id");
    } else {
      if ((await first.getAttribute("data-native-ratio")) !== "indicated") {
        fail("the 2x-cap flow is not indicated as a comparison");
      }
      if ((await first.getAttribute("data-native-ratio-value")) !== "200") {
        fail(`the 2x-cap ratio was not preserved: '${await first.getAttribute("data-native-ratio-value")}'`);
      }
      const cardText = (await first.textContent()) ?? "";
      if (!cardText.includes(FLOW_EXACT) || !cardText.includes(CAPACITY_EXACT)) {
        fail("the exact long-decimal flow or capacity rate was not preserved verbatim");
      }
      if (!/200\s*%/.test(cardText)) fail("the panel did not render the preserved 200% ratio");
      await first.locator("details summary").click();
      await first.locator("details[open]").waitFor({ state: "visible", timeout: 5_000 });
      const evidenceText = (await first.textContent()) ?? "";
      for (const value of [
        FLOW_REFERENCE, FLOW_RECORD, FLOW_SHA, FLOW_ARCHIVE,
        CAPACITY_REFERENCE, CAPACITY_RECORD, CAPACITY_SHA, CAPACITY_ARCHIVE,
      ]) {
        if (!evidenceText.includes(value)) fail(`the expanded evidence does not carry '${value}'`);
      }
    }

    await input.fill(`${CONTEXT_POINT}-EDITED`);
    const edited = await editedInputKeepsLoadedLabel(page, CONTEXT_POINT);
    if (!edited) {
      const actual = await page.evaluate(readNativeCapacityPanel);
      fail(`editing the input relabelled the loaded query as '${actual.resolved ?? "(none)"}'`);
    }

    await captureEvidence(page, outputDir, "native-capacity-context-success.png", fail);
    evidence = {
      pointId: CONTEXT_POINT,
      flowCount: 51,
      pageSize: 50,
      firstPageRows: success.contexts,
      secondPageRows: 1,
      total: success.total,
      nativeRequests: calls.length,
      screenshotDir: outputDir,
    };
  } catch (error) {
    fail(error);
    await captureEvidence(page, outputDir, "native-capacity-context-helper-error.png", fail);
  } finally {
    releaseSlow();
    await page.unroute(isControlledNativePhysicalRead, handler).catch(() => {});
    for (const cleanup of inducedRefusalCleanups.splice(0).reverse()) {
      try {
        cleanup();
      } catch {
        // Cleanup only closes the caller's active attribution window; it must not hide the result.
      }
    }
  }
  note(
    `synthetic fixture for '${CONTEXT_POINT}' only: ${calls.length} native read(s) fulfilled;`
    + " default-volume and other-point physical reads bypassed the route entirely;"
    + ` evidence under ${outputDir}`,
  );
  return evidence;
}
