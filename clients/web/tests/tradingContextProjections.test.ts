/**
 * The selected trading context reaches the projection reads (Architecture V2 Wave 5).
 *
 * The September 23 authenticated HMI audit recorded a selected gas day of 2026-09-07 while the
 * market and portfolio projection strips showed 2026-09-22: every lane asked the backend for
 * `undefined` context, so each payload declared the gas day the backend derived from its own clock.
 * These tests drive the real store with mocked answers and deferred promises, so the repair is
 * exercised rather than read: the request carries the published context, a context change re-reads
 * every lane the session has asked for, an answer is written only while it still owns its lane, and
 * a switch clears the reading it invalidated instead of showing another context's figures under the
 * new selector.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";
import { apiRegistry } from "./support/mockApiClient.ts";

import { DEFAULT_TRADER_CONTEXT } from "../src/app/context/traderContext.ts";
import { projectionRequestContext } from "../src/app/model/projectionContext.ts";
import {
  declaredGasDayCalendar,
  declaredTimeBasisKey,
} from "../src/app/model/projectionModel.ts";
import {
  AUTHENTICATED_AUTH_STATE,
  UNAUTHENTICATED_AUTH_STATE,
} from "../src/stores/workspaceLoading.ts";
import {
  closeApiStoreHarness,
  deferred,
  loadApiStore,
  settle,
  type ApiStoreHarness,
  type Deferred,
} from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

const CONTEXT_A = { gasDay: "2026-09-07", deliveryProduct: "all", hubId: null };
const CONTEXT_B = { gasDay: "2026-09-08", deliveryProduct: "day-ahead", hubId: "NBP" };
const CONTEXT_C = { gasDay: "2026-09-09", deliveryProduct: "within-day", hubId: "TTF" };

function webSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

/** A projection payload that declares, like the route's, the context and instant it was read for. */
function projection(
  name: string,
  gasDay: string,
  asOfUtc = "2026-09-07T09:30:00+00:00",
): Record<string, unknown> {
  return {
    projection: name,
    projection_version: `${name}/v1`,
    as_of_utc: asOfUtc,
    time_basis: { basis: "as_of_instant", gas_day: gasDay, gas_day_calendar: "EU-CAM-UTC-2025" },
    slices: {},
  };
}

/** The context a stored payload declares for itself - never the one a selector is showing. */
function declaredGasDay(payload: Record<string, unknown> | null): unknown {
  const basis = payload?.time_basis as { gas_day?: unknown } | undefined;
  return basis?.gas_day ?? null;
}

function declaredAsOf(payload: Record<string, unknown> | null): unknown {
  return payload?.as_of_utc ?? null;
}

/** The ids of the quote rows a market read left in the state, in order. */
function quoteIds(quotes: unknown[]): string[] {
  return quotes.map((quote) => String((quote as { quote_id?: unknown }).quote_id));
}

/** The queries the store sent for one endpoint, in order. */
function askedFor(harness: ApiStoreHarness, method: string): Array<Record<string, unknown>> {
  return harness.calls
    .filter((call) => call.method === method)
    .map((call) => (call.args[0] ?? {}) as Record<string, unknown>);
}

/** Answer every request of one endpoint with a promise the test settles itself. */
function deferEndpoint(
  harness: ApiStoreHarness,
  method: string,
  answers: Array<{ gasDay: unknown; answer: Deferred<unknown> }>,
): void {
  harness.answer(method, (query) => {
    const answer = deferred<unknown>();
    answers.push({ gasDay: (query as { gasDay?: unknown }).gasDay, answer });
    return answer.promise;
  });
}

// ---------------------------------------------------------------------------
// The request the canonical context produces
// ---------------------------------------------------------------------------

test("a projection read declares the selected context in the route's own query names", async () => {
  const harness = await loadApiStore();
  const requests: URL[] = [];
  const globals = globalThis as { window?: unknown; fetch?: unknown };
  const previous = { window: globals.window, fetch: globals.fetch };
  globals.window = { location: { origin: "http://localhost:3000" } };
  globals.fetch = (input: unknown) => {
    requests.push(new URL(String(input)));
    return Promise.resolve(
      new Response(JSON.stringify({ data: null, meta: {} }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
  };
  try {
    const client = await harness.load<{
      api: {
        portfolioSnapshot(query: unknown): Promise<unknown>;
        marketContext(query: unknown): Promise<unknown>;
      };
    }>("/src/api/client.ts");

    await client.api.portfolioSnapshot(projectionRequestContext(CONTEXT_B));
    assert.equal(requests[0].pathname, "/api/projections/portfolio-snapshot");
    assert.equal(requests[0].searchParams.get("gas_day"), CONTEXT_B.gasDay);
    assert.equal(requests[0].searchParams.get("delivery_product"), CONTEXT_B.deliveryProduct);
    assert.equal(requests[0].searchParams.get("hub"), CONTEXT_B.hubId);

    // An unfocused dimension is omitted rather than sent as a value the route would match exactly,
    // and no read invents the instant its figures will be measured against.
    await client.api.marketContext(projectionRequestContext(DEFAULT_TRADER_CONTEXT));
    assert.deepEqual([...requests[1].searchParams.keys()], ["gas_day"]);
  } finally {
    globals.window = previous.window;
    globals.fetch = previous.fetch;
  }
});

// ---------------------------------------------------------------------------
// Pending first reads, context changes and the order answers come back in
// ---------------------------------------------------------------------------

test("a context change answers a lane whose first read is still pending", async () => {
  const harness = await loadApiStore();
  const { store } = harness;
  store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  const portfolioAnswers: Array<{ gasDay: unknown; answer: Deferred<unknown> }> = [];
  const reviewAnswers: Array<{ gasDay: unknown; answer: Deferred<unknown> }> = [];
  deferEndpoint(harness, "portfolioSnapshot", portfolioAnswers);
  deferEndpoint(harness, "reviewContext", reviewAnswers);

  store.getState().publishTradingContext(CONTEXT_A);
  const batch = store.getState().fetchWorkspace();
  const review = store.getState().fetchReviewContext();
  await settle();
  assert.equal(portfolioAnswers[0].gasDay, CONTEXT_A.gasDay);
  assert.equal(reviewAnswers[0].gasDay, CONTEXT_A.gasDay);

  // The caller moves on while neither the workspace's first portfolio read nor the review task's
  // read has answered.
  store.getState().publishTradingContext(CONTEXT_B);
  assert.equal(portfolioAnswers.length, 2);
  assert.equal(portfolioAnswers[1].gasDay, CONTEXT_B.gasDay);
  assert.equal(reviewAnswers.length, 2);
  assert.equal(reviewAnswers[1].gasDay, CONTEXT_B.gasDay);
  // Nothing is shown under the new selector until its own answer arrives.
  assert.equal(store.getState().portfolioSnapshot, null);

  // The first answers arrive, for a context the caller has left: they are dropped.
  portfolioAnswers[0].answer.resolve({
    data: projection("portfolio-snapshot", CONTEXT_A.gasDay),
    meta: {},
  });
  reviewAnswers[0].answer.resolve({
    data: projection("review-context", CONTEXT_A.gasDay),
    meta: {},
  });
  await batch;
  await review;
  await settle();
  assert.equal(store.getState().portfolioSnapshot, null);
  assert.equal(store.getState().reviewContext, null);

  // The answers for the context the caller is standing in are written.
  portfolioAnswers[1].answer.resolve({
    data: projection("portfolio-snapshot", CONTEXT_B.gasDay),
    meta: {},
  });
  reviewAnswers[1].answer.resolve({
    data: projection("review-context", CONTEXT_B.gasDay),
    meta: {},
  });
  await settle();
  assert.equal(declaredGasDay(store.getState().portfolioSnapshot), CONTEXT_B.gasDay);
  assert.equal(declaredGasDay(store.getState().reviewContext), CONTEXT_B.gasDay);
});

test("an answer that returns out of order cannot overwrite a newer one, even for the same context", async () => {
  const harness = await loadApiStore();
  const { store } = harness;
  store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  const answers: Array<{ gasDay: unknown; answer: Deferred<unknown> }> = [];
  deferEndpoint(harness, "marketContext", answers);

  store.getState().publishTradingContext(CONTEXT_A);
  const firstRead = store.getState().refreshMarketData();
  await settle();
  assert.equal(answers.length, 1);
  assert.equal(answers[0].gasDay, CONTEXT_A.gasDay);

  store.getState().publishTradingContext(CONTEXT_B);
  assert.equal(answers.length, 2);
  assert.equal(answers[1].gasDay, CONTEXT_B.gasDay);
  // A payload for the context the caller left is not shown as the new context's answer.
  assert.equal(store.getState().marketContext, null);
  assert.deepEqual(store.getState().marketQuotes, []);
  answers[1].answer.resolve({ data: projection("market-context", CONTEXT_B.gasDay), meta: {} });
  await settle();
  assert.equal(declaredGasDay(store.getState().marketContext), CONTEXT_B.gasDay);

  // A -> B -> A: the context key alone would look current again for the very first request.
  store.getState().publishTradingContext(CONTEXT_A);
  assert.equal(answers.length, 3);
  assert.equal(answers[2].gasDay, CONTEXT_A.gasDay);
  assert.equal(store.getState().marketContext, null);
  answers[0].answer.resolve({
    data: projection("market-context", CONTEXT_A.gasDay, "2026-09-07T08:00:00+00:00"),
    meta: {},
  });
  await firstRead;
  await settle();
  assert.equal(store.getState().marketContext, null);

  // The newest request for the context the caller is standing in is the answer that stands.
  answers[2].answer.resolve({
    data: projection("market-context", CONTEXT_A.gasDay, "2026-09-07T09:30:00+00:00"),
    meta: {},
  });
  await settle();
  assert.equal(declaredAsOf(store.getState().marketContext), "2026-09-07T09:30:00+00:00");
});

test("a failed read stays answerable for the next context, and an unasked lane stays unread", async () => {
  const harness = await loadApiStore();
  const { store } = harness;
  store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  harness.answer("marketContext", () => Promise.reject(new Error("API 503: upstream unavailable")));

  await store.getState().refreshMarketData();
  assert.match(store.getState().endpointErrors.marketContext, /API 503/);

  store.getState().publishTradingContext(CONTEXT_B);
  assert.deepEqual(
    askedFor(harness, "marketContext").map((query) => query.gasDay),
    [DEFAULT_TRADER_CONTEXT.gasDay, CONTEXT_B.gasDay],
  );
  // Task-scoped reads stay task-scoped: no surface asked for the review or portfolio projection, so
  // a context change does not start them.
  assert.equal(harness.calls.some((call) => call.method === "reviewContext"), false);
  assert.equal(harness.calls.some((call) => call.method === "portfolioSnapshot"), false);
});

test("a pass already running does not write an answer for a context the caller has left", async () => {
  const harness = await loadApiStore();
  const { store } = harness;
  store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  const answers: Array<{ gasDay: unknown; answer: Deferred<unknown> }> = [];
  deferEndpoint(harness, "marketContext", answers);

  store.getState().publishTradingContext(CONTEXT_A);
  const firstRead = store.getState().refreshMarketData();
  await settle();
  store.getState().publishTradingContext(CONTEXT_B);
  assert.equal(answers.length, 2);
  // A second change arrives while the pass for B is still in flight: it is queued behind that pass,
  // so for now the newest request in the lane is still B's.
  store.getState().publishTradingContext(CONTEXT_C);
  assert.equal(answers.length, 2);

  answers[1].answer.resolve({ data: projection("market-context", CONTEXT_B.gasDay), meta: {} });
  await settle();
  // B's answer is the newest request in its lane but not the context the caller is standing in.
  assert.equal(store.getState().marketContext, null);

  assert.equal(answers.length, 3);
  assert.equal(answers[2].gasDay, CONTEXT_C.gasDay);
  answers[2].answer.resolve({ data: projection("market-context", CONTEXT_C.gasDay), meta: {} });
  await settle();
  assert.equal(declaredGasDay(store.getState().marketContext), CONTEXT_C.gasDay);

  answers[0].answer.resolve({ data: projection("market-context", CONTEXT_A.gasDay), meta: {} });
  await firstRead;
  await settle();
  assert.equal(declaredGasDay(store.getState().marketContext), CONTEXT_C.gasDay);
});

test("a batch that lands after a projection change does not repopulate the fields the projection owns", async () => {
  const harness = await loadApiStore();
  const { store } = harness;
  store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  harness.answer("marketContext", (query) => ({
    data: {
      ...projection("market-context", String((query as { gasDay?: string }).gasDay)),
      slices: { quotes: { available: true, row_count: 1, rows: [{ quote_id: "projection" }] } },
    },
    meta: {},
  }));
  const legacyRows = deferred<unknown>();
  harness.answer("marketQuotes", () => legacyRows.promise);

  store.getState().publishTradingContext(CONTEXT_A);
  await store.getState().refreshMarketData();
  assert.deepEqual(quoteIds(store.getState().marketQuotes), ["projection"]);

  // The batch's unfiltered market read is in flight while the caller changes context.
  const batch = store.getState().fetchWorkspace();
  await settle();
  store.getState().publishTradingContext(CONTEXT_B);
  await settle();
  assert.deepEqual(quoteIds(store.getState().marketQuotes), ["projection"]);

  legacyRows.resolve({ data: [{ quote_id: "legacy" }], meta: {} });
  await batch;
  await settle();
  // The projection's rows stand: the field the lane derives from its payload is not half-replaced
  // by the legacy read behind it.
  assert.deepEqual(quoteIds(store.getState().marketQuotes), ["projection"]);
});

test("legacy batches, retries and streams cannot widen an already focused projection", async () => {
  const harness = await loadApiStore();
  const { store } = harness;
  store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  store.getState().publishTradingContext(CONTEXT_B);
  store.setState({ marketQuotes: [{ quote_id: "old-unfiltered" }] });
  harness.answer("marketContext", () => ({
    data: {
      ...projection("market-context", CONTEXT_B.gasDay),
      slices: { quotes: { available: true, rows: [{ quote_id: "focused" }] } },
    }, meta: {},
  }));
  harness.answer("marketQuotes", () => ({ data: [{ quote_id: "legacy" }], meta: {} }));
  await store.getState().refreshMarketData();
  assert.deepEqual(quoteIds(store.getState().marketQuotes), ["focused"]);
  // No context transition occurs during this batch; projection ownership still holds.
  await store.getState().fetchWorkspace();
  assert.deepEqual(quoteIds(store.getState().marketQuotes), ["focused"]);
  store.setState({ endpointErrors: { marketQuotes: "old legacy failure" } });
  await store.getState().retryFailedWorkspaceEndpoints();
  assert.deepEqual(quoteIds(store.getState().marketQuotes), ["focused"]);
  assert.equal(store.getState().endpointErrors.marketQuotes, undefined);
  store.getState().subscribeDecisionStreams();
  apiRegistry().streams["/stream/quotes"].quotes({ quote_id: "unfiltered-stream" });
  assert.deepEqual(quoteIds(store.getState().marketQuotes), ["focused"]);
});

test("a retry pass asks the question it started with, and its answer for a left context is dropped", async () => {
  const harness = await loadApiStore();
  const { store } = harness;
  store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  store.getState().publishTradingContext(CONTEXT_A);
  const answers: Array<{ gasDay: unknown; answer: Deferred<unknown> }> = [];
  deferEndpoint(harness, "reviewContext", answers);

  const firstRead = store.getState().fetchReviewContext();
  await settle();
  answers[0].answer.reject(new Error("API 503: review evidence unavailable"));
  await firstRead;
  assert.match(store.getState().endpointErrors.reviewContext, /API 503/);
  assert.deepEqual(
    askedFor(harness, "reviewContext").map((query) => query.gasDay),
    [CONTEXT_A.gasDay],
  );

  const retry = store.getState().retryFailedWorkspaceEndpoints();
  await settle();
  assert.equal(answers.length, 2);
  assert.equal(answers[1].gasDay, CONTEXT_A.gasDay);

  // The caller moves on while the retried read is in flight.
  store.getState().publishTradingContext(CONTEXT_B);
  assert.equal(answers.length, 3);
  assert.equal(answers[2].gasDay, CONTEXT_B.gasDay);
  answers[1].answer.resolve({ data: projection("review-context", CONTEXT_A.gasDay), meta: {} });
  await retry;
  await settle();
  // Neither written nor recorded as recovered: the pass answered a question the caller has left.
  assert.equal(store.getState().reviewContext, null);
  assert.equal(store.getState().endpointErrors.reviewContext, undefined);

  answers[2].answer.resolve({ data: projection("review-context", CONTEXT_B.gasDay), meta: {} });
  await settle();
  assert.equal(declaredGasDay(store.getState().reviewContext), CONTEXT_B.gasDay);
});

test("every attempt of one pass asks the pass's own question", async () => {
  const harness = await loadApiStore();
  const { store } = harness;
  store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  const attempts: unknown[] = [];
  let attempt = 0;
  harness.answer("portfolioSnapshot", (query) => {
    const gasDay = (query as { gasDay?: unknown }).gasDay;
    attempts.push(gasDay);
    attempt += 1;
    if (attempt === 1) return Promise.reject(new Error("API 503: cold start"));
    return { data: projection("portfolio-snapshot", String(gasDay)), meta: {} };
  });

  store.getState().publishTradingContext(CONTEXT_A);
  const batch = store.getState().fetchWorkspace();
  await settle();
  assert.deepEqual(attempts, [CONTEXT_A.gasDay]);

  // The context moves while the pass waits to retry a failed endpoint: the retried attempt still
  // asks the pass's own question, while the change's own re-read asks the new context's.
  store.getState().publishTradingContext(CONTEXT_B);
  await batch;
  assert.deepEqual(attempts, [CONTEXT_A.gasDay, CONTEXT_B.gasDay, CONTEXT_A.gasDay]);
  // The pass's own answer is superseded: neither written nor recorded as recovered.
  assert.equal(declaredGasDay(store.getState().portfolioSnapshot), CONTEXT_B.gasDay);
  assert.equal(store.getState().endpointErrors.portfolioSnapshot, undefined);
});

test("a sign-out drops queued work and writes nothing after it", async () => {
  const harness = await loadApiStore();
  const { store } = harness;
  store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  const answers: Array<{ gasDay: unknown; answer: Deferred<unknown> }> = [];
  deferEndpoint(harness, "portfolioSnapshot", answers);

  store.getState().publishTradingContext(CONTEXT_A);
  const batch = store.getState().fetchWorkspace();
  await settle();
  store.getState().publishTradingContext(CONTEXT_B);
  store.getState().publishTradingContext({ ...CONTEXT_A, gasDay: "2026-09-09" });
  assert.equal(answers.length, 2);

  // The backend revokes the session while a pass is running and another is queued behind it.
  harness.answer("me", () => Promise.reject(new Error("API 401: session revoked")));
  await store.getState().fetchMe();
  assert.equal(store.getState().authState, UNAUTHENTICATED_AUTH_STATE);
  assert.deepEqual(store.getState().tradingContext, DEFAULT_TRADER_CONTEXT);
  const requestsAfterSignOut = harness.calls.length;

  for (const { answer } of answers) {
    answer.resolve({ data: projection("portfolio-snapshot", CONTEXT_A.gasDay), meta: {} });
  }
  await batch;
  await settle();
  await settle();
  assert.equal(store.getState().portfolioSnapshot, null);
  assert.equal(harness.calls.length, requestsAfterSignOut);
});

test("a 401 on the context re-read's own portfolio read fails the session closed", async () => {
  const harness = await loadApiStore();
  const { store } = harness;
  store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  let attempt = 0;
  harness.answer("portfolioSnapshot", () => {
    attempt += 1;
    return attempt === 1
      ? { data: projection("portfolio-snapshot", CONTEXT_A.gasDay), meta: {} }
      : Promise.reject(new Error("API 401: session revoked"));
  });

  store.getState().publishTradingContext(CONTEXT_A);
  await store.getState().fetchWorkspace();
  assert.equal(declaredGasDay(store.getState().portfolioSnapshot), CONTEXT_A.gasDay);

  // The lane's own re-read meets a revoked session: the store fails closed rather than recording a
  // failure inside a shell that still reads as signed in.
  store.getState().publishTradingContext(CONTEXT_B);
  await settle();
  assert.equal(store.getState().authState, UNAUTHENTICATED_AUTH_STATE);
  assert.deepEqual(store.getState().tradingContext, DEFAULT_TRADER_CONTEXT);
  assert.equal(store.getState().portfolioSnapshot, null);
});

// ---------------------------------------------------------------------------
// The session transition and the initial URL
// ---------------------------------------------------------------------------

test("a session restores the URL's context, and publishes it before the first projection read", async () => {
  const harness = await loadApiStore();
  const session = await harness.load<{
    resolveSessionTraderContext(inputs: {
      authState: string;
      search: string;
      persisted: Record<string, unknown>;
    }): { gasDay: string; deliveryProduct: string; hubId: string | null };
  }>("/src/app/context/sessionTraderContext.ts");

  assert.deepEqual(
    session.resolveSessionTraderContext({
      authState: AUTHENTICATED_AUTH_STATE,
      search: "?workspace=market&gasDay=2026-09-07&product=day-ahead&hub=nbp",
      persisted: {},
    }),
    { gasDay: "2026-09-07", deliveryProduct: "day-ahead", hubId: "NBP" },
  );
  // What the URL does not declare comes from the persisted preference, and an unauthenticated
  // session restores nothing at all.
  assert.deepEqual(
    session.resolveSessionTraderContext({
      authState: AUTHENTICATED_AUTH_STATE,
      search: "",
      persisted: { gasDay: "2026-09-06", deliveryProduct: "within-day", hubId: "TTF" },
    }),
    { gasDay: "2026-09-06", deliveryProduct: "within-day", hubId: "TTF" },
  );
  assert.deepEqual(
    session.resolveSessionTraderContext({
      authState: UNAUTHENTICATED_AUTH_STATE,
      search: "?gasDay=2026-09-07",
      persisted: { gasDay: "2026-09-06" },
    }),
    DEFAULT_TRADER_CONTEXT,
  );

  // The store asks about the context it was given before that batch, which is the order the hook's
  // identity transition produces.
  const { store } = harness;
  store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  store.getState().publishTradingContext({
    gasDay: "2026-09-07",
    deliveryProduct: "day-ahead",
    hubId: "NBP",
  });
  const batch = store.getState().fetchWorkspace();
  await settle();
  assert.deepEqual(askedFor(harness, "portfolioSnapshot")[0], {
    gasDay: "2026-09-07",
    product: "day-ahead",
    hub: "NBP",
  });
  await batch;

  // The hook resolves the context on the identity transition and publishes it there, so it reaches
  // the store before the runtime's own load effect runs.
  const hook = webSource("app/context/useTraderContext.ts");
  assert.match(hook, /const nextContext = traderContextForSession\(authState\);/);
  assert.match(hook, /publishTradingContext\(nextContext\);/);
});

// ---------------------------------------------------------------------------
// The declared time basis the strip renders
// ---------------------------------------------------------------------------

test("the strip reads the basis the payload declares", () => {
  const basis = {
    basis: "as_of_instant",
    as_of_utc: "2026-09-07T09:30:00+00:00",
    gas_day: "2026-09-07",
    gas_day_calendar: "EU-CAM-UTC-2025",
    delivery_product: "day-ahead",
    hub: "NBP",
  };

  assert.equal(declaredTimeBasisKey(basis), "data_product.time_basis.as_of_instant");
  assert.equal(declaredGasDayCalendar(basis), "EU-CAM-UTC-2025");

  // A basis the client has no label for is shown as its own code rather than as a translation the
  // client does not have, and an absent or blank declaration reports nothing rather than a guess.
  assert.equal(
    declaredTimeBasisKey({ basis: "delivery_period" }),
    "data_product.time_basis.delivery_period",
  );
  assert.equal(declaredTimeBasisKey({ basis: "some_future_basis" }), "some_future_basis");
  for (const value of [null, undefined, {}, { basis: "" }, { basis: "   " }, { basis: 7 }]) {
    assert.equal(declaredTimeBasisKey(value as Record<string, unknown> | null), null, String(value));
  }
  for (const value of [null, undefined, {}, { gas_day_calendar: "" }, { gas_day_calendar: 2025 }]) {
    assert.equal(
      declaredGasDayCalendar(value as Record<string, unknown> | null),
      null,
      String(value),
    );
  }
});

test("the shared strip renders the declared basis and calendar for every projection surface", () => {
  const strip = webSource("components/ProjectionContextStrip.tsx");

  assert.match(strip, /const basisKey = declaredTimeBasisKey\(basis\);/);
  assert.match(strip, /const gasDayCalendar = declaredGasDayCalendar\(basis\);/);
  assert.match(strip, /\{basisKey \? t\(basisKey\) : t\(key\("not_reported"\)\)\}/);
  assert.match(
    strip,
    /\{gasDayCalendar \? ` · \$\{t\(key\("gas_day_calendar"\)\)\} \$\{gasDayCalendar\}` : ""\}/,
  );
  // The name the payload does not carry is gone: the client does not look for `basis_id`.
  assert.equal(strip.includes("basis_id"), false);

  const en = JSON.parse(webSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(webSource("i18n/zh.json")) as Record<string, string>;
  const namespaces = ["market_context", "portfolio_context", "review_context"];
  for (const namespace of namespaces) {
    assert.ok(en[`${namespace}.gas_day_calendar`]?.trim(), `en ${namespace}`);
    assert.ok(zh[`${namespace}.gas_day_calendar`]?.trim(), `zh ${namespace}`);
    assert.notEqual(en[`${namespace}.gas_day_calendar`], zh[`${namespace}.gas_day_calendar`]);
  }
  // One reading, three surfaces: the template is identical per language, as the other entries are.
  assert.equal(new Set(namespaces.map((item) => en[`${item}.gas_day_calendar`])).size, 1);
  assert.equal(new Set(namespaces.map((item) => zh[`${item}.gas_day_calendar`])).size, 1);
});
