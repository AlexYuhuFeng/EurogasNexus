import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import test from "node:test";
import vm from "node:vm";

const CLIENT_SOURCE = readFileSync(
  new URL("../src/api/client.ts", import.meta.url),
  "utf8",
);

const SAMPLE_READING = {
  observation_id: "obs-1",
  point_id: "point-1",
  series_id: "series-a",
  entity_id: "entity-1",
  source_system: "ECMWF_OPEN_DATA",
  provider: "ECMWF",
  model: "IFS",
  run_id: "run-1",
  issued_at_utc: "2026-01-01T00:00:00Z",
  valid_at_utc: "2026-01-02T00:00:00Z",
  available_at_utc: "2026-01-01T04:00:00Z",
  temperature_c: 2.5,
  unit: "degC",
  raw_grib_sha256: "a".repeat(64),
  record_content_sha256: "b".repeat(64),
  requested_latitude: 50.1,
  requested_longitude: 8.2,
  grid_latitude: 50.0,
  grid_longitude: 8.0,
};

const SAMPLE_META = {
  research_only: true,
  source_references: ["ECMWF_OPEN_DATA"],
  warnings: ["RESEARCH_ONLY", "HUMAN_REVIEW_REQUIRED"],
  attribution: "ECMWF Open Data (CC BY 4.0)",
  point_kind: "FORECAST_GRID_POINT",
};

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function clientHarness() {
  let nextResponse: Response | Error = jsonResponse({ data: [], meta: SAMPLE_META });
  const calls: Array<{ url: URL; init: RequestInit | undefined }> = [];

  const hostStub = [
    'const HOST_COMMANDS = { readDeploymentConfig: "read", notifyClientReady: "ready", clearSessionData: "clear" };',
    'const resolveHostKind = () => "browser";',
    'const tryHostCommand = async () => null;',
  ].join("\n");

  const withoutAliasImport = CLIENT_SOURCE.replace(
    /^import \{ HOST_COMMANDS, resolveHostKind, tryHostCommand \} from "@\/app\/host\/hostCapabilities";$/m,
    hostStub,
  ).replace("import.meta.env.VITE_EUROGAS_API_BASE_URL", "undefined");

  const executable = stripTypeScriptTypes(withoutAliasImport)
    .replace(/^export\s+/gm, "");

  const sandbox: Record<string, unknown> = {
    AbortController,
    URL,
    URLSearchParams,
    console,
    localStorage: {
      getItem: () => null,
      removeItem: () => undefined,
      setItem: () => undefined,
    },
    window: { location: { origin: "https://example.test" } },
    fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: new URL(String(input)), init });
      if (nextResponse instanceof Error) throw nextResponse;
      return nextResponse;
    },
  };

  vm.runInNewContext(
    `${executable}\nglobalThis.__weatherClient = { fetchWeatherForecasts, ApiError };`,
    sandbox,
    { filename: "client.ts" },
  );

  return {
    calls,
    client: sandbox.__weatherClient as {
      fetchWeatherForecasts: (options: unknown) => Promise<{
        data: typeof SAMPLE_READING[];
        meta: typeof SAMPLE_META;
      }>;
      ApiError: new (...args: never[]) => Error & {
        status: number;
        detail: unknown;
        body: unknown;
      };
    },
    respondWith(response: Response | Error) {
      nextResponse = response;
    },
  };
}

const VALID_OPTIONS = {
  seriesIds: ["series-a", "series-b"],
  entityIds: ["entity-1", "entity-2"],
  predictionOrigin: "2026-01-02T00:00:00Z",
  validFrom: "2026-01-02T00:00:00Z",
  validTo: "2026-01-03T00:00:00+00:00",
  limit: 256,
};

test("fetchWeatherForecasts sends repeated explicit query fields and keeps typed meta", async () => {
  const harness = clientHarness();
  const envelope = { data: [SAMPLE_READING], meta: SAMPLE_META };
  harness.respondWith(jsonResponse(envelope));
  const controller = new AbortController();

  const result = await harness.client.fetchWeatherForecasts({
    ...VALID_OPTIONS,
    signal: controller.signal,
  });

  assert.equal(harness.calls.length, 1);
  const [{ url, init }] = harness.calls;
  assert.equal(url.pathname, "/api/weather/forecasts");
  assert.deepEqual(url.searchParams.getAll("series_ids"), ["series-a", "series-b"]);
  assert.deepEqual(url.searchParams.getAll("entity_ids"), ["entity-1", "entity-2"]);
  assert.equal(url.searchParams.get("prediction_origin"), VALID_OPTIONS.predictionOrigin);
  assert.equal(url.searchParams.get("valid_from"), VALID_OPTIONS.validFrom);
  assert.equal(url.searchParams.get("valid_to"), VALID_OPTIONS.validTo);
  assert.equal(url.searchParams.get("limit"), "256");
  assert.deepEqual(
    [...url.searchParams.keys()],
    [
      "series_ids",
      "series_ids",
      "entity_ids",
      "entity_ids",
      "prediction_origin",
      "valid_from",
      "valid_to",
      "limit",
    ],
  );
  assert.equal(init?.signal, controller.signal);

  assert.deepEqual(JSON.parse(JSON.stringify(result)), envelope);
  assert.equal(result.meta.research_only, true);
  assert.equal(result.meta.point_kind, "FORECAST_GRID_POINT");
  assert.deepEqual(
    JSON.parse(JSON.stringify(result.meta.warnings)),
    ["RESEARCH_ONLY", "HUMAN_REVIEW_REQUIRED"],
  );
  assert.equal(result.meta.attribution, "ECMWF Open Data (CC BY 4.0)");
});

test("invalid forecast queries reject before any request is made", async () => {
  const harness = clientHarness();
  const tooManySeries = Array.from({ length: 257 }, (_, index) => `series-${index}`);

  const cases: Array<[string, unknown, RegExp]> = [
    ["missing options", null, /options are required/i],
    ["empty series list", { ...VALID_OPTIONS, seriesIds: [] }, /seriesIds/i],
    ["blank entity id", { ...VALID_OPTIONS, entityIds: ["entity-1", " "] }, /entityIds\[1\]/i],
    [
      "too many identifiers",
      { ...VALID_OPTIONS, seriesIds: tooManySeries },
      /at most 256/i,
    ],
    [
      "overlong series id",
      { ...VALID_OPTIONS, seriesIds: ["s".repeat(161)] },
      /at most 160/i,
    ],
    ["missing limit", { ...VALID_OPTIONS, limit: undefined }, /limit/i],
    ["zero limit", { ...VALID_OPTIONS, limit: 0 }, /limit/i],
    ["limit above maximum", { ...VALID_OPTIONS, limit: 257 }, /limit/i],
    ["fractional limit", { ...VALID_OPTIONS, limit: 1.5 }, /limit/i],
    [
      "non-UTC prediction origin",
      { ...VALID_OPTIONS, predictionOrigin: "2026-01-02T01:00:00+01:00" },
      /predictionOrigin/i,
    ],
    [
      "timestamp without timezone",
      { ...VALID_OPTIONS, validFrom: "2026-01-02T00:00:00" },
      /validFrom/i,
    ],
    [
      "window longer than 32 days",
      { ...VALID_OPTIONS, validTo: "2026-02-04T00:00:00Z" },
      /32 days/i,
    ],
    [
      "empty window",
      { ...VALID_OPTIONS, validTo: VALID_OPTIONS.validFrom },
      /after validFrom/i,
    ],
  ];

  for (const [label, options, expected] of cases) {
    await assert.rejects(
      () => harness.client.fetchWeatherForecasts(options),
      expected,
      label,
    );
    assert.equal(harness.calls.length, 0, `${label} must not issue a request`);
  }
});

test("HTTP failures propagate as the existing structured ApiError", async () => {
  const harness = clientHarness();
  const detail = {
    error: "invalid_forecast_query",
    message: "Forecast query is out of bounds.",
    research_only: true,
  };
  harness.respondWith(jsonResponse({ detail }, 400));

  let failure: unknown;
  try {
    await harness.client.fetchWeatherForecasts(VALID_OPTIONS);
  } catch (error) {
    failure = error;
  }

  assert.ok(failure instanceof harness.client.ApiError);
  assert.equal(failure.status, 400);
  assert.deepEqual(JSON.parse(JSON.stringify(failure.detail)), detail);
  assert.deepEqual(JSON.parse(JSON.stringify(failure.body)), { detail });
  assert.match(failure.message, /^API 400: invalid_forecast_query/);
  assert.match(failure.message, /Forecast query is out of bounds\./);
  assert.equal(harness.calls.length, 1);
});
