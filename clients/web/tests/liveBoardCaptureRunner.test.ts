/**
 * The live capture runner must refuse what it cannot substantiate, keep the session read-only,
 * match the displayed board to the *consumed* response, stay inside its bounds and never print the
 * evidence it handled.
 *
 * `scripts/uat/captureLiveBoard.mjs` is the live half of the WF-1 captured-board comparison: one
 * browser session against a caller-named deployment, the session's own storage state, no login and
 * no seed, every request classified before navigation (GET/HEAD to the target origin only,
 * service workers blocked), and the board matched to a *recorded* response whose own as-of is the
 * board's - never to a refetch. These cases hold each of those promises: the URL policy, the
 * request guard, the response usability rule, the as-of match and its bounded polling retry, the
 * board-absent/unsettled refusals, the deadline and the always-close, and the no-leak guarantee on
 * every printed path (including a tainted invocation, storage path and payload).
 *
 * The browser plumbing is mocked deterministically (a fake `playwright` module and an injected
 * clock), so the retry, deadline and cleanup paths run without a real browser. One synthetic local
 * integration case drives the real dependency when it is installed *and* its chromium can launch;
 * it skips otherwise, and never touches a customer endpoint - the only server it starts is a
 * loopback fixture this suite owns.
 */

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  CAPTURE_BOUNDS,
  boardIsSettled,
  buildCapture,
  classifyCaptureFailure,
  classifyRequest,
  main,
  readConfig,
  runLiveCapture,
  selectConsumedResponse,
  usableConsumedResponse,
  validateBaseUrl,
} from "../../../scripts/uat/captureLiveBoard.mjs";

const CLI = fileURLToPath(
  new URL("../../../scripts/uat/captureLiveBoard.mjs", import.meta.url),
);

/** Synthetic values only: this suite never needs a customer payload or a real deployment. */
const CANARY = "CANARY-live-capture-5a19";
const AS_OF = "2026-09-27T04:51:52.988900+00:00";
const EARLIER_AS_OF = "2026-09-27T04:40:00+00:00";
const HOST = "http://127.0.0.1:3000";
const MARKET_URL = `${HOST}/api/projections/market-context?gas_day=2026-09-27`;
const QUOTE_ID = `${CANARY}-quote`;
const OBSERVATION_ID = `${CANARY}-observation`;

const QUOTE_ROW = {
  quote_id: QUOTE_ID,
  source_system: CANARY,
  venue: CANARY,
  hub: "TTF",
  product: "day-ahead",
  bid_price: 42.1,
  ask_price: 42.3,
  currency: "EUR",
  unit: "MWh",
  observed_at_utc: "2026-09-27T04:00:00+00:00",
  simulated: false,
  metadata_json: {},
};

const OBSERVATION_ROW = {
  observation_id: OBSERVATION_ID,
  hub: "PSV",
  tenor: "day-ahead",
  is_gas_price: true,
  price: 32.4,
  currency: "EUR",
  unit: "EUR/MWh",
  source_system: "Trayport",
  market_venue: "Trayport",
  observed_at_utc: "2026-09-27T04:00:00+00:00",
  metadata_json: {},
};

function freshness(asOf: string) {
  return {
    state: "FRESH",
    basis: "observed_at_utc",
    evaluated_at_utc: asOf,
    last_observed_at_utc: "2026-09-27T04:00:00+00:00",
    expected_within_minutes: 60,
    expectation_source: "source_registry",
    measured: true,
    derived_from: null,
  };
}

function slice(rows: Array<Record<string, unknown>>, asOf: string) {
  return {
    available: true,
    source_references: ["runtime-postgresql"],
    row_count: rows.length,
    rows,
    payload: null,
    freshness: freshness(asOf),
    entitlement: { row_filter_applied: true, filtered_out: 0, reason: "source_family" },
    context_filter: { applied: ["hub"], rule: "exact hub match" },
    limits: { row_limit: 500, truncated: false },
    warnings: [],
    notes: [],
  };
}

/** One well-formed market-context payload, as the projection route returns it. */
function projectionBody(
  options: { asOf?: string; slices?: Record<string, unknown>; projection?: string } = {},
) {
  const asOf = options.asOf ?? AS_OF;
  const timeBasis = {
    basis: "as_of_instant",
    as_of_utc: asOf,
    gas_day: "2026-09-27",
    gas_day_calendar: "cam.v1",
    gas_day_start_utc: "2026-09-26T22:00:00+00:00",
    gas_day_end_utc: "2026-09-27T22:00:00+00:00",
    delivery_product: "day-ahead",
    hub: null,
  };
  const data = {
    projection: options.projection ?? "market-context",
    projection_version: "market-context.v1",
    as_of_utc: asOf,
    time_basis: timeBasis,
    active_context: {
      gas_day: "2026-09-27",
      gas_day_calendar: "cam.v1",
      delivery_product: "day-ahead",
      hub: null,
      as_of_utc: asOf,
    },
    slices: options.slices ?? {
      quotes: slice([QUOTE_ROW], asOf),
      normalized_quotes: slice([OBSERVATION_ROW], asOf),
    },
    warnings: [],
    research_only: true,
    human_review_required: true,
  };
  return {
    data,
    meta: {
      projection: data.projection,
      projection_version: "market-context.v1",
      as_of_utc: asOf,
      time_basis: timeBasis,
      research_only: true,
      human_review_required: true,
      source_references: ["runtime-postgresql"],
      warnings: [],
      table_lineage: ["market_quotes"],
    },
  };
}

/** One card's collected evidence, as `collectQuotedBoard` returns it. */
function card(overrides: Record<string, string> = {}) {
  return {
    recordId: QUOTE_ID,
    slice: "quotes",
    tenor: "day-ahead",
    hub: "TTF",
    priceText: "42.100 / 42.300",
    metaText: "Bid/ask · EUR/MWh · Quote age 3s",
    sourceText: CANARY,
    ...overrides,
  };
}

const CARDS = [
  card(),
  card({
    recordId: OBSERVATION_ID,
    slice: "normalized_quotes",
    hub: "PSV",
    priceText: "32.40 EUR/MWh",
    metaText: "Day ahead · Quote age n/a",
    sourceText: "Trayport",
  }),
];

function boardState(
  cells: Array<Record<string, string>> = CARDS,
  overrides: Record<string, unknown> = {},
) {
  return {
    boardTenor: "day-ahead",
    activeTenorTab: "day-ahead",
    asOf: AS_OF,
    // The displayed as-of is held to the client's own formatter (`utcInstantLabel`).
    asOfText: "Market context · As of 2026-09-27 04:51:52 UTC · gas day 2026-09-27",
    cells,
    ...overrides,
  };
}

/** The run config the environment would produce, with short bounds for the mocked cases. */
function shortConfig(overrides: Record<string, unknown> = {}) {
  return {
    ...CAPTURE_BOUNDS,
    viewport: { ...CAPTURE_BOUNDS.viewport },
    origin: HOST,
    base: HOST,
    storageStatePath: path.join(tmpdir(), "synthetic-storage-state.json"),
    source: { commit: "synthetic-commit", deployment: "synthetic-deployment" },
    attempts: 3,
    boardPollMs: 50,
    settleTimeoutMs: 300,
    refreshWaitMs: 100,
    navigationTimeoutMs: 5_000,
    launchTimeoutMs: 5_000,
    operationTimeoutMs: 5_000,
    timeoutMs: 2_000,
    ...overrides,
  };
}

interface FakeResponseSpec {
  url?: string;
  status?: number;
  body?: unknown;
}

interface FakeControls {
  playwright: Record<string, unknown>;
  calls: {
    launch: Array<Record<string, unknown>>;
    newContext: Array<Record<string, unknown>>;
    goto: string[];
    route: Array<{ continued: number; aborted: string[] }>;
    webSockets: { routed: number; closed: number };
    evaluate: number;
    close: number;
  };
  clock: {
    now: () => number;
    sleep: (ms: number) => Promise<void>;
  };
  deliver: (spec: FakeResponseSpec) => void;
  openWebSocket: (url?: string) => Promise<void>;
}

/**
 * A deterministic fake of the Playwright surface the runner uses: the context, page, response
 * events and route handler are recorded so each scenario can drive navigation, responses, the
 * guard and the clock.
 */
function fakeEnvironment(
  options: {
    boards?: unknown[];
    onGoto?: FakeResponseSpec[];
    onGotoRequests?: Array<{ method: string; url: string }>;
    onGotoWebSocket?: string;
    onSleep?: (controls: FakeControls) => void;
    gotoFails?: boolean;
    gotoHangs?: boolean;
    launchFails?: boolean;
    newContextFails?: boolean;
    closeFails?: boolean;
    webSocketGuardMissing?: boolean;
  } = {},
): FakeControls {
  const calls = {
    launch: [] as Array<Record<string, unknown>>,
    newContext: [] as Array<Record<string, unknown>>,
    goto: [] as string[],
    route: [] as Array<{ continued: number; aborted: string[] }>,
    webSockets: { routed: 0, closed: 0 },
    evaluate: 0,
    close: 0,
  };
  const boards = options.boards ?? [];
  let boardIndex = 0;
  let clockValue = 0;
  let responseListener: ((response: unknown) => void) | null = null;
  let routeHandler: ((route: unknown) => Promise<unknown>) | null = null;
  let webSocketHandler: ((route: unknown) => unknown) | null = null;

  const controls = {} as FakeControls;

  const openWebSocket = async (url = `${HOST}/socket`) => {
    await webSocketHandler?.({
      url: () => url,
      close: async () => {
        calls.webSockets.closed += 1;
      },
    });
  };

  const deliver = (spec: FakeResponseSpec) => {
    responseListener?.({
      status: () => spec.status ?? 200,
      request: () => ({ method: () => "GET", url: () => spec.url ?? MARKET_URL }),
      json: async () => spec.body,
    });
  };

  const invokeRoute = async (request: { method: string; url: string }) => {
    const outcome = { continued: 0, aborted: [] as string[] };
    await routeHandler?.({
      // Playwright's `Request` exposes `method()`/`url()` as methods, not properties.
      request: () => ({ method: () => request.method, url: () => request.url }),
      continue: async () => {
        outcome.continued += 1;
      },
      abort: async (code: string) => {
        outcome.aborted.push(code);
      },
    });
    calls.route.push(outcome);
    return outcome;
  };

  const page = {
    setDefaultTimeout: () => {},
    setDefaultNavigationTimeout: () => {},
    on: (event: string, handler: (payload: unknown) => void) => {
      if (event === "response") responseListener = handler;
    },
    evaluate: async () => {
      calls.evaluate += 1;
      if (boards.length === 0) return null;
      const value = boards[Math.min(boardIndex, boards.length - 1)];
      boardIndex += 1;
      return value;
    },
    goto: async (url: string) => {
      calls.goto.push(url);
      if (options.gotoFails) throw new Error("synthetic navigation failure");
      if (options.gotoHangs) return new Promise(() => {});
      if (options.onGotoWebSocket) await openWebSocket(options.onGotoWebSocket);
      for (const request of options.onGotoRequests ?? []) await invokeRoute(request);
      for (const spec of options.onGoto ?? []) deliver(spec);
    },
  };

  const context: {
    route: (pattern: string, handler: (route: unknown) => Promise<unknown>) => Promise<void>;
    routeWebSocket?: (pattern: string, handler: (route: unknown) => unknown) => Promise<void>;
    newPage: () => Promise<typeof page>;
  } = {
    route: async (pattern: string, handler: (route: unknown) => Promise<unknown>) => {
      routeHandler = handler;
    },
    newPage: async () => page,
  };
  if (!options.webSocketGuardMissing) {
    context.routeWebSocket = async (pattern: string, handler: (route: unknown) => unknown) => {
      calls.webSockets.routed += 1;
      webSocketHandler = handler;
    };
  }

  const browser = {
    newContext: async (config: Record<string, unknown>) => {
      calls.newContext.push(config);
      if (options.newContextFails) throw new Error("synthetic storage state failure");
      return context;
    },
    close: async () => {
      calls.close += 1;
      if (options.closeFails) throw new Error("synthetic close failure");
    },
  };

  const playwright = {
    chromium: {
      launch: async (config: Record<string, unknown>) => {
        calls.launch.push(config);
        if (options.launchFails) throw new Error("synthetic launch failure");
        return browser;
      },
    },
  };

  controls.playwright = playwright;
  controls.calls = calls;
  controls.deliver = deliver;
  controls.openWebSocket = openWebSocket;
  controls.clock = {
    now: () => clockValue,
    sleep: async (ms: number) => {
      clockValue += ms;
      options.onSleep?.(controls);
    },
  };
  return controls;
}

function codes(summary: { reasons: Array<{ code: string }> }) {
  return summary.reasons.map((entry) => entry.code);
}

async function run(controls: FakeControls, config = shortConfig()) {
  return runLiveCapture({
    config,
    playwright: controls.playwright,
    now: controls.clock.now,
    sleep: controls.clock.sleep,
  });
}

test("only an explicit https or loopback-http target is accepted, never a default remote URL", () => {
  const allowed: Array<[string, string, string]> = [
    ["http://127.0.0.1:3000", "http://127.0.0.1:3000", "http://127.0.0.1:3000"],
    ["http://localhost:3000", "http://localhost:3000", "http://localhost:3000"],
    ["http://[::1]:3000", "http://[::1]:3000", "http://[::1]:3000"],
    ["https://pilot.example.com", "https://pilot.example.com", "https://pilot.example.com"],
    ["https://pilot.example.com/nexus/", "https://pilot.example.com/nexus", "https://pilot.example.com"],
  ];
  for (const [input, base, origin] of allowed) {
    const result = validateBaseUrl(input);
    assert.equal(result.ok, true, input);
    assert.equal(result.base, base, input);
    assert.equal(result.origin, origin, input);
  }

  for (const input of [
    undefined,
    "",
    "   ",
    "example.com",
    "http://10.0.0.5:3000",
    "http://example.com",
    "ftp://127.0.0.1",
    "file:///tmp/state.json",
    "https://user:secret@example.com",
    "https://example.com/?redirect=elsewhere",
    "https://example.com/#fragment",
    "javascript:alert(1)",
  ]) {
    const result = validateBaseUrl(input);
    assert.equal(result.ok, false, String(input));
    assert.ok(
      result.code === "base_url_missing" || result.code === "base_url_not_allowed",
      String(input),
    );
  }
  assert.equal(validateBaseUrl(undefined).code, "base_url_missing");
  assert.equal(validateBaseUrl("http://10.0.0.5:3000").code, "base_url_not_allowed");
});

test("the request guard continues only a same-origin GET or HEAD", () => {
  assert.deepEqual(classifyRequest({ method: "GET", url: `${HOST}/api/me`, origin: HOST }), {
    action: "allow",
  });
  assert.deepEqual(classifyRequest({ method: "head", url: `${HOST}/api/me`, origin: HOST }), {
    action: "allow",
  });
  for (const method of ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"]) {
    assert.deepEqual(
      classifyRequest({ method, url: `${HOST}/api/me`, origin: HOST }),
      { action: "block", code: "readonly_guard_blocked" },
      method,
    );
  }
  for (const url of [
    "https://cdn.example.com/font.woff2",
    "http://127.0.0.1:8000/api/me",
    "http://localhost:3000/api/me",
    "ws://127.0.0.1:3000/socket",
    "data:text/plain,hello",
    "not a url",
  ]) {
    assert.deepEqual(
      classifyRequest({ method: "GET", url, origin: HOST }),
      { action: "block", code: "external_request_blocked" },
      url,
    );
  }
});

test("the environment is validated before any browser work, and the state file is only located", () => {
  const missing = readConfig({} as Record<string, string>);
  assert.equal(missing.ok, false);
  assert.deepEqual(
    [...missing.codes.keys()].sort(),
    ["base_url_missing", "source_label_missing", "storage_state_missing"],
  );

  const directory = mkdtempSync(path.join(tmpdir(), "eurogas-live-capture-"));
  try {
    const base = {
      EUROGAS_UAT_BASE_URL: HOST,
      EUROGAS_UAT_CAPTURE_COMMIT: "synthetic-commit",
      EUROGAS_UAT_CAPTURE_DEPLOYMENT: "synthetic-deployment",
    };

    const unreadable = readConfig({ ...base, EUROGAS_UAT_STORAGE_STATE: directory });
    assert.equal(unreadable.ok, false);
    assert.deepEqual([...unreadable.codes.keys()], ["storage_state_unreadable"]);

    const stateFile = path.join(directory, "state.json");
    writeFileSync(stateFile, JSON.stringify({ cookies: [], origins: [] }));
    const parsed = readConfig({
      ...base,
      EUROGAS_UAT_BASE_URL: `${HOST}/`,
      EUROGAS_UAT_STORAGE_STATE: stateFile,
      EUROGAS_UAT_CAPTURE_TIMEOUT_MS: "30000",
    });
    assert.equal(parsed.ok, true);
    assert.equal(parsed.config.origin, HOST);
    assert.equal(parsed.config.base, HOST);
    assert.equal(parsed.config.timeoutMs, 30_000);
    assert.equal(parsed.config.storageStatePath, stateFile);
    assert.deepEqual(parsed.config.source, {
      commit: "synthetic-commit",
      deployment: "synthetic-deployment",
    });
    assert.equal(parsed.config.attempts, CAPTURE_BOUNDS.attempts);

    for (const value of ["5", "soon", "600001", "-1"]) {
      const timeout = readConfig({
        ...base,
        EUROGAS_UAT_STORAGE_STATE: stateFile,
        EUROGAS_UAT_CAPTURE_TIMEOUT_MS: value,
      });
      assert.equal(timeout.ok, false, value);
      assert.ok([...timeout.codes.keys()].includes("invocation_invalid"), value);
    }
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("the capture's hub scope is the displayed cards' own hubs, never a hardcoded list", () => {
  const capture = buildCapture({
    source: { commit: "synthetic-commit", deployment: "synthetic-deployment" },
    board: boardState([card({ hub: "TTF" }), card({ hub: " psv " }), card({ hub: "TTF" })]),
    response: { status: 200, body: projectionBody() },
  });

  assert.deepEqual(capture.hub_scope, ["TTF", "PSV"]);
  assert.equal(capture.projection.status, 200);
  assert.deepEqual(capture.projection.body, projectionBody());
  assert.deepEqual(Object.keys(capture.board), [
    "boardTenor",
    "activeTenorTab",
    "asOf",
    "asOfText",
    "cells",
  ]);
  // A card set with no usable hub label states no scope, so the comparator refuses the capture
  // rather than this function inventing one.
  const empty = buildCapture({
    source: { commit: "synthetic-commit", deployment: "synthetic-deployment" },
    board: boardState([card({ hub: "" })]),
    response: { status: 200, body: projectionBody() },
  });
  assert.deepEqual(empty.hub_scope, []);
});

test("a board is matched only to a recorded response carrying its own as-of instant", () => {
  const earlier = {
    status: 200,
    usable: true,
    body: { data: { as_of_utc: EARLIER_AS_OF } },
    query: { gas_day: "2026-09-27" },
  };
  const matched = {
    status: 200,
    usable: true,
    body: { data: { as_of_utc: AS_OF } },
    query: { gas_day: "2026-09-27" },
  };
  const sameInstantOtherFormat = {
    status: 200,
    usable: true,
    body: { data: { as_of_utc: AS_OF.replace("+00:00", "Z") } },
    query: { gas_day: "2026-09-27" },
  };
  const unusable = { status: 200, usable: false, body: { data: { as_of_utc: AS_OF } }, query: {} };

  assert.equal(selectConsumedResponse([earlier, matched], AS_OF), matched);
  assert.equal(selectConsumedResponse([earlier], AS_OF), null);
  assert.equal(selectConsumedResponse([unusable], AS_OF), null);
  assert.equal(selectConsumedResponse([unusable, matched], AS_OF), matched);
  assert.equal(selectConsumedResponse([unusable, sameInstantOtherFormat], AS_OF), sameInstantOtherFormat);
  assert.equal(selectConsumedResponse([matched], ""), null);
  assert.equal(selectConsumedResponse([matched], "not a timestamp"), null);
});

test("a recorded response is usable only as the projection read for the query the browser sent", () => {
  const body = projectionBody();
  const usable = {
    status: 200,
    body,
    query: { gas_day: "2026-09-27", delivery_product: "day-ahead" },
  };

  assert.equal(usableConsumedResponse(usable), true);
  assert.equal(usableConsumedResponse({ ...usable, status: 503 }), false);
  assert.equal(usableConsumedResponse({ ...usable, body: null }), false);
  assert.equal(usableConsumedResponse({ ...usable, query: {} }), false);
  assert.equal(usableConsumedResponse({ ...usable, query: { gas_day: " " } }), false);
  assert.equal(usableConsumedResponse({ ...usable, query: { gas_day: "2026-09-28" } }), false);
  assert.equal(
    usableConsumedResponse({
      ...usable,
      query: { gas_day: "2026-09-27", delivery_product: "weekend" },
    }),
    false,
  );
  assert.equal(
    usableConsumedResponse({ ...usable, query: { gas_day: "2026-09-27", hub: "NBP" } }),
    false,
  );
  assert.equal(
    usableConsumedResponse({
      ...usable,
      body: { data: { projection: "portfolio-snapshot", as_of_utc: AS_OF, active_context: {} } },
    }),
    false,
  );
});

test("the failure classification separates absence, a refusal, an unusable answer and a race", () => {
  assert.equal(classifyCaptureFailure([]), "no_consumed_response");
  assert.equal(
    classifyCaptureFailure([{ status: 503, usable: false }]),
    "projection_status_not_200",
  );
  assert.equal(
    classifyCaptureFailure([{ status: 200, usable: false }, { status: 503, usable: false }]),
    "consumed_response_unusable",
  );
  assert.equal(
    classifyCaptureFailure([{ status: 200, usable: true }]),
    "capture_race_unmatched",
  );
});

test("a live session that consumed the board's own response passes through the comparator", async () => {
  const controls = fakeEnvironment({
    boards: [null, boardState()],
    onGoto: [{ body: projectionBody() }],
  });
  const result = await run(controls);

  assert.equal(result.summary.verdict, "pass");
  assert.equal(result.exitCode, 0);
  assert.deepEqual(result.summary.reasons, []);
  assert.equal(result.summary.coverage.kind, "displayed_hub_scope_and_tenor");
  assert.equal(result.summary.coverage.board_cards, 2);
  // The offline qualifier is the one statement a live run does establish; the rest stay.
  assert.equal(result.summary.unverified.includes("live_capture_automation"), false);
  assert.equal(result.summary.unverified.includes("capture_authenticity"), true);
  assert.equal(result.summary.unverified.includes("customer_acceptance"), true);
  // The session is driven read-only: one navigation, the minimal market/curves route, the supplied
  // storage state, service workers blocked, and the browser closed.
  assert.deepEqual(controls.calls.goto, [`${HOST}/?workspace=market&task=curves`]);
  assert.deepEqual(controls.calls.launch, [
    { headless: true, timeout: shortConfig().launchTimeoutMs },
  ]);
  assert.equal(controls.calls.newContext[0].serviceWorkers, "block");
  assert.equal(controls.calls.newContext[0].storageState, shortConfig().storageStatePath);
  assert.equal(controls.calls.close, 1);
  // No payload value, id, source or path reaches the printed summary.
  const rendered = JSON.stringify(result.summary);
  for (const value of [CANARY, QUOTE_ID, OBSERVATION_ID, AS_OF, HOST, MARKET_URL]) {
    assert.equal(rendered.includes(value), false, value);
  }
});

test("the polling race is retried boundedly, and an older consumed response may be the match", async () => {
  const controls = fakeEnvironment({
    boards: [boardState()],
    // The first recorded answer is the previous poll; the board still states its own 04:51 instant.
    onGoto: [{ body: projectionBody({ asOf: EARLIER_AS_OF }) }],
    // While the runner waits one refresh interval, the session's next poll lands.
    onSleep: (fake) => fake.deliver({ body: projectionBody() }),
  });
  const result = await run(controls);

  assert.equal(result.summary.verdict, "pass");
  assert.equal(result.exitCode, 0);
  assert.equal(controls.calls.goto.length, 1);
  assert.equal(controls.calls.close, 1);
});

test("a board that never matches a consumed response is refused, never refetched", async () => {
  const controls = fakeEnvironment({
    boards: [boardState()],
    onGoto: [{ body: projectionBody({ asOf: EARLIER_AS_OF }) }],
  });
  const result = await run(controls, shortConfig({ attempts: 2, refreshWaitMs: 100 }));

  assert.equal(result.summary.verdict, "refused");
  assert.equal(result.exitCode, 1);
  assert.deepEqual(result.summary.reasons, [{ code: "capture_race_unmatched", count: 1 }]);
  assert.equal(result.summary.coverage, null);
  assert.equal(controls.calls.goto.length, 1);
  assert.equal(controls.calls.close, 1);
  // One evaluation per attempt, plus one per settle poll: the retry is bounded, not a spin.
  assert.ok(controls.calls.evaluate <= 10, `evaluations: ${controls.calls.evaluate}`);
});

test("a missing or unsettled board is refused, never guessed into a comparison", async () => {
  const absent = await run(fakeEnvironment({ boards: [null] }));
  assert.equal(absent.summary.verdict, "refused");
  assert.deepEqual(absent.summary.reasons, [{ code: "board_not_displayed", count: 1 }]);

  const unsettled = await run(fakeEnvironment({ boards: [boardState(CARDS, { asOf: "" })] }));
  assert.equal(unsettled.summary.verdict, "refused");
  assert.deepEqual(unsettled.summary.reasons, [{ code: "board_not_settled", count: 1 }]);

  assert.equal(boardIsSettled(boardState()), true);
  assert.equal(boardIsSettled(null), false);
  assert.equal(boardIsSettled(boardState(CARDS, { asOf: "" })), false);
  assert.equal(boardIsSettled(boardState(CARDS, { boardTenor: "" })), false);
});

test("responses that are absent, refused or not the projection read are distinguished", async () => {
  const none = await run(fakeEnvironment({ boards: [boardState()] }));
  assert.deepEqual(codes(none.summary), ["no_consumed_response"]);

  const degraded = await run(
    fakeEnvironment({
      boards: [boardState()],
      onGoto: [{ status: 503, body: { detail: CANARY } }],
    }),
  );
  assert.equal(degraded.summary.verdict, "refused");
  assert.deepEqual(codes(degraded.summary), ["projection_status_not_200"]);
  assert.equal(JSON.stringify(degraded.summary).includes(CANARY), false);

  const unusable = await run(
    fakeEnvironment({
      boards: [boardState()],
      onGoto: [{ body: { data: { projection: "portfolio-snapshot" } } }],
    }),
  );
  assert.deepEqual(codes(unusable.summary), ["consumed_response_unusable"]);

  const wrongQuery = await run(
    fakeEnvironment({
      boards: [boardState()],
      onGoto: [
        {
          url: `${HOST}/api/projections/market-context?gas_day=2026-09-28`,
          body: projectionBody(),
        },
      ],
    }),
  );
  assert.deepEqual(codes(wrongQuery.summary), ["consumed_response_unusable"]);
});

test("a request the read-only guard refuses refuses the attempt, even when the board matched", async () => {
  const mutation = await run(
    fakeEnvironment({
      boards: [boardState()],
      onGoto: [{ body: projectionBody() }],
      onGotoRequests: [{ method: "POST", url: `${HOST}/api/telemetry` }],
    }),
  );
  assert.equal(mutation.summary.verdict, "refused");
  assert.deepEqual(mutation.summary.reasons, [{ code: "readonly_guard_blocked", count: 1 }]);
  assert.equal(mutation.exitCode, 1);

  const external = await run(
    fakeEnvironment({
      boards: [boardState()],
      onGoto: [{ body: projectionBody() }],
      onGotoRequests: [{ method: "GET", url: "https://cdn.example.com/font.woff2" }],
    }),
  );
  assert.deepEqual(external.summary.reasons, [{ code: "external_request_blocked", count: 1 }]);

  const allowedControls = fakeEnvironment({
    boards: [boardState()],
    onGoto: [{ body: projectionBody() }],
    onGotoRequests: [{ method: "GET", url: `${HOST}/api/me` }],
  });
  const allowed = await run(allowedControls);
  assert.equal(allowed.summary.verdict, "pass");
  assert.deepEqual(allowedControls.calls.route, [{ continued: 1, aborted: [] }]);

  // The aborted request carries Playwright's own refusal code, never the request itself.
  const abortedControls = fakeEnvironment({
    boards: [boardState()],
    onGoto: [{ body: projectionBody() }],
    onGotoRequests: [{ method: "DELETE", url: `${HOST}/api/portfolio/orders/1` }],
  });
  const aborted = await run(abortedControls);
  assert.equal(aborted.summary.verdict, "refused");
  assert.deepEqual(abortedControls.calls.route, [{ continued: 0, aborted: ["blockedbyclient"] }]);
  assert.equal(JSON.stringify(aborted.summary).includes("orders/1"), false);
});

test("the capture is bounded by its deadline and the browser is always closed", async () => {
  const timedOut = fakeEnvironment({ boards: [null], closeFails: true });
  const refused = await run(
    timedOut,
    shortConfig({ timeoutMs: 1_000, settleTimeoutMs: 600, boardPollMs: 100 }),
  );
  assert.equal(refused.summary.verdict, "refused");
  assert.deepEqual(refused.summary.reasons, [{ code: "board_not_displayed", count: 1 }]);
  // The browser was closed even though its own close failed, and the polling stayed bounded.
  assert.equal(timedOut.calls.close, 1);
  assert.ok(timedOut.calls.evaluate <= 10, `evaluations: ${timedOut.calls.evaluate}`);

  const navigation = await run(fakeEnvironment({ gotoFails: true }));
  assert.deepEqual(navigation.summary.reasons, [{ code: "navigation_failed", count: 1 }]);

  const state = fakeEnvironment({ newContextFails: true });
  const unreadable = await run(state);
  assert.equal(unreadable.summary.verdict, "invalid");
  assert.equal(unreadable.exitCode, 2);
  assert.deepEqual(unreadable.summary.reasons, [{ code: "storage_state_unreadable", count: 1 }]);
  assert.equal(state.calls.close, 1);

  const launched = await run(fakeEnvironment({ launchFails: true }));
  assert.deepEqual(launched.summary.reasons, [{ code: "capture_launch_failed", count: 1 }]);

  const unavailable = await runLiveCapture({
    config: shortConfig(),
    playwright: {},
    now: () => 0,
    sleep: async () => {},
  });
  assert.deepEqual(unavailable.summary.reasons, [{ code: "playwright_unavailable", count: 1 }]);
  assert.equal(unavailable.summary.coverage, null);
  assert.equal(unavailable.summary.unverified.includes("live_capture_automation"), true);
});

test("a response body or evaluation that never settles is bounded, refuses with the fixed code and still closes the browser", async () => {
  // A hanging body parse: the per-operation bound ends the wait long before the whole-run budget,
  // so a never-parsing response cannot consume the capture.
  const bodyControls = fakeEnvironment({
    boards: [boardState()],
    onGoto: [{ body: new Promise(() => {}) }],
  });
  const bodyStarted = Date.now();
  const body = await run(bodyControls, shortConfig({ timeoutMs: 60_000, operationTimeoutMs: 150 }));
  const bodyElapsed = Date.now() - bodyStarted;
  assert.equal(body.summary.verdict, "refused");
  assert.equal(body.exitCode, 1);
  assert.deepEqual(body.summary.reasons, [{ code: "capture_timeout", count: 1 }]);
  assert.equal(bodyControls.calls.close, 1);
  assert.ok(bodyElapsed >= 100 && bodyElapsed < 10_000, `elapsed: ${bodyElapsed}`);

  // A hanging evaluation: `page.setDefaultTimeout` does not bound `page.evaluate`, so the runner
  // must - one unanswered sample ends the polling instead of hanging the capture.
  const evaluateControls = fakeEnvironment({ boards: [new Promise(() => {})] });
  const evaluateStarted = Date.now();
  const evaluate = await run(
    evaluateControls,
    shortConfig({ timeoutMs: 60_000, operationTimeoutMs: 150 }),
  );
  const evaluateElapsed = Date.now() - evaluateStarted;
  assert.equal(evaluate.summary.verdict, "refused");
  assert.deepEqual(evaluate.summary.reasons, [{ code: "capture_timeout", count: 1 }]);
  assert.equal(evaluateControls.calls.close, 1);
  assert.ok(evaluateElapsed >= 100 && evaluateElapsed < 10_000, `elapsed: ${evaluateElapsed}`);

  // A navigation that never answers is bounded by the whole-run watchdog alone (the per-operation
  // bound is far away), which closes the browser and refuses with the same fixed code.
  const watchdogControls = fakeEnvironment({ gotoHangs: true });
  const watchdogStarted = Date.now();
  const watchdog = await run(
    watchdogControls,
    shortConfig({ timeoutMs: 300, operationTimeoutMs: 60_000 }),
  );
  const watchdogElapsed = Date.now() - watchdogStarted;
  assert.equal(watchdog.summary.verdict, "refused");
  assert.deepEqual(watchdog.summary.reasons, [{ code: "capture_timeout", count: 1 }]);
  assert.equal(watchdogControls.calls.close, 1);
  assert.ok(watchdogElapsed >= 250 && watchdogElapsed < 10_000, `elapsed: ${watchdogElapsed}`);
});

test("a completed capture leaves no capture timer behind", async () => {
  const activeTimeouts = () =>
    process.getActiveResourcesInfo().filter((name) => name === "Timeout").length;
  const before = activeTimeouts();
  const controls = fakeEnvironment({ boards: [boardState()], onGoto: [{ body: projectionBody() }] });
  const result = await run(controls);
  assert.equal(result.summary.verdict, "pass");
  // The whole-run watchdog (and every per-operation bound) was cleared on the normal path, so a
  // finished capture cannot hold the process open.
  assert.ok(activeTimeouts() <= before, "a capture timer survived the run");
});

test("an operation abandoned at the deadline cannot surface as an unhandled rejection", async () => {
  const unhandled: unknown[] = [];
  const onUnhandled = (reason: unknown) => {
    unhandled.push(reason);
  };
  process.on("unhandledRejection", onUnhandled);
  try {
    let rejectLate: (error: Error) => void = () => {};
    const late = new Promise((_, reject) => {
      rejectLate = reject;
    });
    const controls = fakeEnvironment({ boards: [late] });
    const result = await run(controls, shortConfig({ timeoutMs: 150, operationTimeoutMs: 60_000 }));
    assert.deepEqual(result.summary.reasons, [{ code: "capture_timeout", count: 1 }]);
    assert.equal(controls.calls.close, 1);
    // The abandoned evaluation now fails, after the runner already returned its refusal.
    rejectLate(new Error(`late synthetic failure ${CANARY}`));
    await new Promise((resolve) => setTimeout(resolve, 50));
  } finally {
    process.off("unhandledRejection", onUnhandled);
  }
  assert.deepEqual(unhandled, []);
});

test("the runner fails closed before navigating when the installed Playwright has no WebSocket guard", async () => {
  const controls = fakeEnvironment({
    boards: [boardState()],
    onGoto: [{ body: projectionBody() }],
    webSocketGuardMissing: true,
  });
  const result = await run(controls);

  assert.equal(result.summary.verdict, "invalid");
  assert.equal(result.exitCode, 2);
  assert.deepEqual(result.summary.reasons, [{ code: "websocket_guard_unavailable", count: 1 }]);
  // Fail closed means before navigation: the session is never opened unguarded.
  assert.deepEqual(controls.calls.goto, []);
  assert.equal(controls.calls.close, 1);
});

test("a WebSocket channel is closed before it reaches a server, and refuses the attempt", async () => {
  const controls = fakeEnvironment({
    boards: [boardState()],
    onGoto: [{ body: projectionBody() }],
    onGotoWebSocket: "ws://127.0.0.1:3000/socket",
  });
  const result = await run(controls);

  // The board and its response matched; the channel alone makes the session one the guard had to
  // restrain, which is never a capture of the operator's own session.
  assert.equal(result.summary.verdict, "refused");
  assert.equal(result.exitCode, 1);
  assert.deepEqual(result.summary.reasons, [{ code: "websocket_blocked", count: 1 }]);
  assert.equal(controls.calls.webSockets.routed, 1);
  assert.equal(controls.calls.webSockets.closed, 1);
  assert.equal(controls.calls.close, 1);
  // The fixed reason code travels; the channel's URL never does.
  assert.equal(JSON.stringify(result.summary).includes("ws://127.0.0.1:3000/socket"), false);
});

const MANAGED_ENV = [
  "EUROGAS_UAT_BASE_URL",
  "EUROGAS_UAT_STORAGE_STATE",
  "EUROGAS_UAT_CAPTURE_COMMIT",
  "EUROGAS_UAT_CAPTURE_DEPLOYMENT",
  "EUROGAS_UAT_CAPTURE_TIMEOUT_MS",
  "EUROGAS_UAT_PLAYWRIGHT_PATH",
];

/**
 * Run the operator entrypoint in-process with an explicitly constructed environment, capturing
 * what it writes. The real `main` is exercised - argument handling, environment validation, the
 * dependency load, the exit code it returns and every byte it prints - without requiring this
 * machine to allow spawning a child process.
 */
async function runMain(args: string[], environment: Record<string, string>) {
  const saved = new Map<string, string | undefined>();
  for (const name of MANAGED_ENV) {
    saved.set(name, process.env[name]);
    delete process.env[name];
  }
  Object.assign(process.env, environment);
  const out: string[] = [];
  const err: string[] = [];
  const stdoutWrite = process.stdout.write.bind(process.stdout);
  const stderrWrite = process.stderr.write.bind(process.stderr);
  process.stdout.write = ((chunk: unknown) => {
    out.push(String(chunk));
    return true;
  }) as typeof process.stdout.write;
  process.stderr.write = ((chunk: unknown) => {
    err.push(String(chunk));
    return true;
  }) as typeof process.stderr.write;
  try {
    const status = await main([process.execPath, CLI, ...args]);
    return { status, stdout: out.join(""), stderr: err.join("") };
  } finally {
    process.stdout.write = stdoutWrite;
    process.stderr.write = stderrWrite;
    for (const [name, value] of saved) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  }
}

/** Whether this machine lets a test spawn a child process at all (some sandboxes do not). */
function canSpawnNode(): boolean {
  const probe = spawnSync(process.execPath, ["-e", "process.exit(0)"], {
    encoding: "utf8",
    windowsHide: true,
    timeout: 30_000,
  });
  return probe.status === 0;
}

test("the entrypoint refuses invocation and environment defects without echoing a path or payload", async () => {
  const argument = await runMain([`--token=${CANARY}`], {});
  assert.equal(argument.status, 2);
  assert.deepEqual(JSON.parse(argument.stdout).reasons, [{ code: "invocation_invalid", count: 1 }]);
  assert.equal(`${argument.stdout}${argument.stderr}`.includes(CANARY), false);

  const absent = await runMain([], {});
  assert.equal(absent.status, 2);
  assert.deepEqual(codes(JSON.parse(absent.stdout)), [
    "base_url_missing",
    "source_label_missing",
    "storage_state_missing",
  ]);

  const unreadableState = await runMain([], {
    EUROGAS_UAT_BASE_URL: `${HOST}/${CANARY}`,
    EUROGAS_UAT_STORAGE_STATE: path.join(tmpdir(), `${CANARY}-absent.json`),
    EUROGAS_UAT_CAPTURE_COMMIT: CANARY,
    EUROGAS_UAT_CAPTURE_DEPLOYMENT: CANARY,
  });
  assert.equal(unreadableState.status, 2);
  assert.deepEqual(JSON.parse(unreadableState.stdout).reasons, [
    { code: "storage_state_unreadable", count: 1 },
  ]);
  assert.equal(`${unreadableState.stdout}${unreadableState.stderr}`.includes(CANARY), false);

  const directory = mkdtempSync(path.join(tmpdir(), "eurogas-live-capture-cli-"));
  try {
    const stateFile = path.join(directory, "state.json");
    writeFileSync(stateFile, JSON.stringify({ cookies: [], origins: [] }));
    const noPlaywright = await runMain([], {
      EUROGAS_UAT_BASE_URL: HOST,
      EUROGAS_UAT_STORAGE_STATE: stateFile,
      EUROGAS_UAT_CAPTURE_COMMIT: CANARY,
      EUROGAS_UAT_CAPTURE_DEPLOYMENT: CANARY,
      EUROGAS_UAT_PLAYWRIGHT_PATH: path.join(directory, `${CANARY}-playwright.js`),
    });
    assert.equal(noPlaywright.status, 2);
    assert.deepEqual(JSON.parse(noPlaywright.stdout).reasons, [
      { code: "playwright_unavailable", count: 1 },
    ]);
    assert.equal(`${noPlaywright.stdout}${noPlaywright.stderr}`.includes(CANARY), false);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }

  const help = await runMain(["--help"], {});
  assert.equal(help.status, 0);
  assert.equal(help.stderr, "");
  assert.match(help.stdout, /usage: node scripts\/uat\/captureLiveBoard\.mjs/);
  assert.match(help.stdout, /EUROGAS_UAT_STORAGE_STATE/);
});

test(
  "the process entrypoint exits with the summary's code and prints nothing else",
  { skip: canSpawnNode() ? false : "this machine does not allow spawning a node child process" },
  () => {
    const env: Record<string, string> = {
      ...process.env,
      EUROGAS_UAT_BASE_URL: `${HOST}/${CANARY}`,
    } as Record<string, string>;
    for (const name of MANAGED_ENV) {
      if (name !== "EUROGAS_UAT_BASE_URL") delete env[name];
    }
    const result = spawnSync(process.execPath, [CLI], {
      encoding: "utf8",
      env,
      timeout: 60_000,
      windowsHide: true,
    });

    assert.equal(result.status, 2);
    assert.deepEqual(JSON.parse(result.stdout).reasons, [
      { code: "source_label_missing", count: 1 },
      { code: "storage_state_missing", count: 1 },
    ]);
    assert.equal(result.stdout.includes(CANARY), false);
    assert.equal(result.stderr, "");
  },
);

/**
 * The real dependency, when this machine can actually launch it. This is a capability probe: the
 * web CI job has no Playwright, and a restricted sandbox can have it installed but refuse to spawn
 * the browser - neither is a defect in the runner, so the synthetic integration cases skip with
 * the reason, and the mocked cases above own the behaviour.
 */
async function chromiumSkipReason(): Promise<string | null> {
  let playwright: {
    chromium?: {
      launch: (options: Record<string, unknown>) => Promise<{ close: () => Promise<void> }>;
    };
  };
  try {
    playwright = createRequire(import.meta.url)(
      process.env.EUROGAS_UAT_PLAYWRIGHT_PATH || "playwright",
    );
  } catch {
    return "playwright is not installed";
  }
  if (typeof playwright?.chromium?.launch !== "function") return "playwright has no chromium";
  let browser: { close: () => Promise<void> } | null = null;
  try {
    browser = await playwright.chromium.launch({ headless: true, timeout: 30_000 });
    return null;
  } catch {
    return "chromium cannot be launched in this environment";
  } finally {
    if (browser !== null) await browser.close().catch(() => {});
  }
}

/** The exact module path to hand the spawned CLI, when the dependency exists. */
function resolvedPlaywrightPath(): string | null {
  try {
    return createRequire(import.meta.url).resolve(
      process.env.EUROGAS_UAT_PLAYWRIGHT_PATH || "playwright",
    );
  } catch {
    return null;
  }
}

interface FixtureServer {
  origin: string;
  close: () => Promise<void>;
}

/**
 * A loopback fixture this suite owns: one page that renders the market board from the projection
 * response it fetched itself, and the projection route it reads. It is a synthetic stand-in for
 * the app's own page, never a customer endpoint.
 */
function startFixtureServer(
  options: { mutate?: boolean; webSocket?: boolean } = {},
): Promise<FixtureServer> {
  const payload = projectionBody();
  const script = `
    ${options.mutate ? 'fetch("/api/mutate", { method: "POST" }).catch(() => {});' : ""}
    ${options.webSocket ? 'try { new WebSocket("ws://" + location.host + "/socket"); } catch {}' : ""}
    const response = await fetch("/api/projections/market-context?gas_day=2026-09-27");
    const body = await response.json();
    const board = document.querySelector('[data-market-board="hub-prices"]');
    const rows = [
      ...(body.data.slices.quotes.rows ?? []),
      ...(body.data.slices.normalized_quotes.rows ?? []),
    ];
    for (const row of rows) {
      const quote = "quote_id" in row;
      const unit = row.unit.toUpperCase().includes(row.currency.toUpperCase())
        ? row.unit
        : row.currency + "/" + row.unit;
      const card = document.createElement("div");
      card.setAttribute("data-record", "market-hub-price");
      card.setAttribute("data-record-id", quote ? row.quote_id : row.observation_id);
      card.setAttribute("data-record-slice", quote ? "quotes" : "normalized_quotes");
      card.setAttribute("data-price-tenor", quote ? row.product : row.tenor);
      card.innerHTML = [
        "<span data-price-hub-label>", row.hub, "</span>",
        "<strong data-price-value>",
        quote ? row.bid_price + " / " + row.ask_price : row.price + " " + unit,
        "</strong>",
        "<small data-price-meta>",
        quote
          ? "Bid/ask \\u00b7 " + unit + " \\u00b7 Quote age 3s"
          : "Day ahead \\u00b7 Quote age n/a",
        "</small>",
        "<em data-price-source>", row.source_system, "</em>",
      ].join("");
      board.appendChild(card);
    }
    const asOf = document.querySelector("[data-projection-as-of]");
    asOf.setAttribute("data-projection-as-of", body.data.as_of_utc);
    asOf.textContent =
      "Market context \\u00b7 As of "
      + body.data.as_of_utc.slice(0, 19).replace("T", " ")
      + " UTC \\u00b7 gas day "
      + body.data.time_basis.gas_day;
  `;
  const page = [
    "<!DOCTYPE html>",
    '<html lang="en"><head><meta charset="utf-8"><style>',
    '.workspace-page { display: block; width: 1200px; height: 600px; }',
    '[data-market-board="hub-prices"] { display: block; width: 1200px; height: 200px; }',
    '[data-record="market-hub-price"] { display: block; width: 240px; height: 60px; }',
    "</style></head><body>",
    '<div class="workspace-page workspace-market">',
    '<section data-projection-as-of=""></section>',
    '<button class="market-tenor-tab" data-tenor="day-ahead" aria-pressed="true">Day ahead</button>',
    '<div data-market-board="hub-prices" data-board-tenor="day-ahead"></div>',
    "</div>",
    `<script type="module">${script}</script>`,
    "</body></html>",
  ].join("");

  const server = createServer((request, response) => {
    const url = new URL(request.url ?? "/", "http://127.0.0.1");
    if (url.pathname === "/") {
      response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      response.end(page);
      return;
    }
    if (url.pathname === "/api/projections/market-context") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(payload));
      return;
    }
    response.writeHead(options.mutate ? 200 : 404);
    response.end();
  });

  return new Promise((resolveServer) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address !== null ? address.port : 0;
      resolveServer({
        origin: `http://127.0.0.1:${port}`,
        close: () =>
          new Promise((resolveClose) => {
            server.close(() => resolveClose());
          }),
      });
    });
  });
}

test(
  "synthetic local fixture: the runner compares a served board with the response it consumed",
  async (t) => {
    const reason = await chromiumSkipReason();
    if (reason !== null) {
      t.skip(reason);
      return;
    }
    const server = await startFixtureServer();
    const directory = mkdtempSync(path.join(tmpdir(), "eurogas-live-capture-integration-"));
    try {
      const stateFile = path.join(directory, "state.json");
      writeFileSync(stateFile, JSON.stringify({ cookies: [], origins: [] }));
      const result = await runMain([], {
        EUROGAS_UAT_BASE_URL: server.origin,
        EUROGAS_UAT_STORAGE_STATE: stateFile,
        EUROGAS_UAT_CAPTURE_COMMIT: "synthetic-fixture-commit",
        EUROGAS_UAT_CAPTURE_DEPLOYMENT: "synthetic-fixture",
        EUROGAS_UAT_CAPTURE_TIMEOUT_MS: "60000",
        EUROGAS_UAT_PLAYWRIGHT_PATH: resolvedPlaywrightPath() ?? "",
      });

      assert.equal(result.status, 0, result.stdout);
      const summary = JSON.parse(result.stdout);
      assert.equal(summary.verdict, "pass");
      assert.equal(summary.coverage.board_cards, 2);
      assert.equal(summary.coverage.priced_cards, 2);
      assert.equal(result.stderr, "");
      for (const value of [CANARY, QUOTE_ID, OBSERVATION_ID, AS_OF, server.origin]) {
        assert.equal(result.stdout.includes(value), false, value);
      }
    } finally {
      rmSync(directory, { recursive: true, force: true });
      await server.close();
    }
  },
);

test(
  "synthetic local fixture: a page that tries to mutate is refused by the guard",
  async (t) => {
    const reason = await chromiumSkipReason();
    if (reason !== null) {
      t.skip(reason);
      return;
    }
    const server = await startFixtureServer({ mutate: true });
    const directory = mkdtempSync(path.join(tmpdir(), "eurogas-live-capture-integration-"));
    try {
      const stateFile = path.join(directory, "state.json");
      writeFileSync(stateFile, JSON.stringify({ cookies: [], origins: [] }));
      const result = await runMain([], {
        EUROGAS_UAT_BASE_URL: server.origin,
        EUROGAS_UAT_STORAGE_STATE: stateFile,
        EUROGAS_UAT_CAPTURE_COMMIT: "synthetic-fixture-commit",
        EUROGAS_UAT_CAPTURE_DEPLOYMENT: "synthetic-fixture",
        EUROGAS_UAT_CAPTURE_TIMEOUT_MS: "60000",
        EUROGAS_UAT_PLAYWRIGHT_PATH: resolvedPlaywrightPath() ?? "",
      });

      assert.notEqual(result.status, 0);
      const summary = JSON.parse(result.stdout);
      assert.equal(summary.verdict, "refused");
      assert.ok(codes(summary).includes("readonly_guard_blocked"), codes(summary).join(", "));
    } finally {
      rmSync(directory, { recursive: true, force: true });
      await server.close();
    }
  },
);

test(
  "synthetic local fixture: a WebSocket channel is closed before it reaches the server",
  async (t) => {
    const reason = await chromiumSkipReason();
    if (reason !== null) {
      t.skip(reason);
      return;
    }
    const server = await startFixtureServer({ webSocket: true });
    const directory = mkdtempSync(path.join(tmpdir(), "eurogas-live-capture-integration-"));
    try {
      const stateFile = path.join(directory, "state.json");
      writeFileSync(stateFile, JSON.stringify({ cookies: [], origins: [] }));
      const result = await runMain([], {
        EUROGAS_UAT_BASE_URL: server.origin,
        EUROGAS_UAT_STORAGE_STATE: stateFile,
        EUROGAS_UAT_CAPTURE_COMMIT: "synthetic-fixture-commit",
        EUROGAS_UAT_CAPTURE_DEPLOYMENT: "synthetic-fixture",
        EUROGAS_UAT_CAPTURE_TIMEOUT_MS: "60000",
        EUROGAS_UAT_PLAYWRIGHT_PATH: resolvedPlaywrightPath() ?? "",
      });

      // The board still matched, but the channel the guard had to close refuses the attempt.
      assert.equal(result.status, 1);
      const summary = JSON.parse(result.stdout);
      assert.equal(summary.verdict, "refused");
      assert.ok(codes(summary).includes("websocket_blocked"), codes(summary).join(", "));
      assert.equal(result.stdout.includes(server.origin), false);
      assert.equal(result.stdout.includes("/socket"), false);
    } finally {
      rmSync(directory, { recursive: true, force: true });
      await server.close();
    }
  },
);
