import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import test from "node:test";
import vm from "node:vm";

const CLIENT_SOURCE = readFileSync(
  new URL("../src/api/client.ts", import.meta.url),
  "utf8",
);

const NATIVE_RATE_KEYS = [
  "value_text",
  "unit_text",
  "native_value",
  "normalized_unit",
  "quantity_kind",
  "rate_basis",
  "energy_kwh_per_day",
  "volume_mcm_per_day",
  "normalizer_version",
];

const NATIVE_FLOW_KEYS = [
  "observation_id",
  "source_record_id",
  "point_id",
  "point_name",
  "direction",
  "kind",
  "period_start_utc",
  "period_end_utc",
  "observed_at_utc",
  "source_system",
  "operator_key",
  "flow_status",
  "period_type",
  "source_reference",
  "research_only",
  "quantity_basis",
  "normalizer_version",
  "native_rate_json",
  "raw_archive_id",
  "payload_sha256",
  "received_at_utc",
];

const NATIVE_CAPACITY_KEYS = NATIVE_FLOW_KEYS.map((key) =>
  key === "kind" ? "capacity_type" : key,
);

const SAMPLE_RATE = {
  value_text: "12345678901234567890.123456789012345678901234567890",
  unit_text: "MWh/d",
  native_value: "12345678901234567890.123456789012345678901234567890",
  normalized_unit: "MWh/day",
  quantity_kind: "energy",
  rate_basis: "day",
  energy_kwh_per_day: "12345678901234567890123.456789012345678901234567890",
  volume_mcm_per_day: null,
  normalizer_version: "entsog-native-units-v1",
};

const SAMPLE_FLOW = {
  observation_id: "flow-observation-1",
  source_record_id: "source-record-1",
  point_id: "point-1",
  point_name: "Oude Statenzijl",
  direction: "entry",
  kind: "flow",
  period_start_utc: "2026-01-01T05:00:00Z",
  period_end_utc: "2026-01-01T06:00:00Z",
  observed_at_utc: null,
  source_system: "ENTSOG",
  operator_key: null,
  flow_status: "confirmed",
  period_type: "hour",
  source_reference: "entsog:flow:1",
  research_only: true,
  quantity_basis: "native",
  normalizer_version: "entsog-native-units-v1",
  native_rate_json: SAMPLE_RATE,
  raw_archive_id: "archive-1",
  payload_sha256: "a".repeat(64),
  received_at_utc: "2026-01-01T06:05:00Z",
};

const SAMPLE_CAPACITY = {
  observation_id: "capacity-observation-1",
  source_record_id: "source-record-2",
  point_id: "point-2",
  point_name: "Mallnow",
  direction: "exit",
  capacity_type: "firm",
  period_start_utc: "2026-01-01T05:00:00Z",
  period_end_utc: "2026-01-01T06:00:00Z",
  observed_at_utc: "2026-01-01T06:01:00Z",
  source_system: "ENTSOG",
  operator_key: "GASCADE",
  flow_status: null,
  period_type: "hour",
  source_reference: "entsog:capacity:1",
  research_only: true,
  quantity_basis: "native",
  normalizer_version: "entsog-native-units-v1",
  native_rate_json: {
    value_text: "0.000000000000000000000001",
    unit_text: "mcm/h",
    native_value: "0.000000000000000000000001",
    normalized_unit: "mcm/hour",
    quantity_kind: "volume",
    rate_basis: "hour",
    energy_kwh_per_day: null,
    volume_mcm_per_day: "0.000000000000000000000001",
    normalizer_version: "entsog-native-units-v1",
  },
  raw_archive_id: null,
  payload_sha256: null,
  received_at_utc: null,
};

const SAMPLE_META = {
  research_only: true,
  human_review_required: true,
  source_references: ["ENTSOG"],
  warnings: ["NATIVE_UNITS_PRESERVED", "HUMAN_REVIEW_REQUIRED"],
  missing_inputs: [],
  precision: "exact-decimal-tokens",
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
  const storage: Record<string, string> = {
    "eurogas.settings.api_token": "stored-token",
    "eurogas.settings.operator_principal": "reviewer@example.test",
  };

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
      getItem: (key: string) => storage[key] ?? null,
      removeItem: (key: string) => {
        delete storage[key];
      },
      setItem: (key: string, value: string) => {
        storage[key] = String(value);
      },
    },
    window: { location: { origin: "https://example.test" } },
    fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: new URL(String(input)), init });
      if (init?.signal?.aborted) {
        throw new DOMException("The operation was aborted.", "AbortError");
      }
      if (nextResponse instanceof Error) throw nextResponse;
      return nextResponse;
    },
  };

  vm.runInNewContext(
    `${executable}\nglobalThis.__nativePhysicalClient = { fetchNativeFlows, fetchNativeCapacity, setDesktopSessionToken, ApiError };`,
    sandbox,
    { filename: "client.ts" },
  );

  return {
    calls,
    client: sandbox.__nativePhysicalClient as {
      fetchNativeFlows: (options?: unknown) => Promise<{
        data: Array<typeof SAMPLE_FLOW>;
        meta: typeof SAMPLE_META;
      }>;
      fetchNativeCapacity: (options?: unknown) => Promise<{
        data: Array<typeof SAMPLE_CAPACITY>;
        meta: typeof SAMPLE_META;
      }>;
      setDesktopSessionToken: (token: string, csrfToken?: string) => void;
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

test("fetchNativeFlows sends the canonical native query, shared headers and exact decimals", async () => {
  const harness = clientHarness();
  const envelope = { data: [SAMPLE_FLOW], meta: SAMPLE_META };
  harness.respondWith(jsonResponse(envelope));
  const controller = new AbortController();
  harness.client.setDesktopSessionToken("desktop-session-token", "csrf-token");

  const result = await harness.client.fetchNativeFlows({
    pointId: "  point-1  ",
    limit: 1000,
    signal: controller.signal,
  });

  assert.equal(harness.calls.length, 1);
  const [{ url, init }] = harness.calls;
  assert.equal(url.pathname, "/api/physical/flows");
  assert.equal(url.searchParams.get("quantity_basis"), "native");
  assert.equal(url.searchParams.get("point_id"), "point-1");
  assert.equal(url.searchParams.get("limit"), "1000");
  assert.deepEqual(
    [...url.searchParams.keys()],
    ["quantity_basis", "point_id", "limit"],
  );
  assert.equal(init?.signal, controller.signal);
  assert.equal(init?.credentials, "include");

  const headers = (init?.headers ?? {}) as Record<string, string>;
  assert.equal(headers.Authorization, "Bearer desktop-session-token");
  assert.equal(headers["X-Eurogas-Principal"], "reviewer@example.test");
  assert.equal(headers["X-Eurogas-CSRF"], "csrf-token");

  assert.deepEqual(JSON.parse(JSON.stringify(result)), envelope);
  assert.deepEqual(
    Object.keys(result.data[0]).sort(),
    [...NATIVE_FLOW_KEYS].sort(),
  );
  assert.deepEqual(
    Object.keys(result.data[0].native_rate_json).sort(),
    [...NATIVE_RATE_KEYS].sort(),
  );

  const rate = result.data[0].native_rate_json;
  assert.equal(rate.value_text, SAMPLE_RATE.value_text);
  assert.equal(rate.native_value, SAMPLE_RATE.native_value);
  assert.equal(rate.energy_kwh_per_day, SAMPLE_RATE.energy_kwh_per_day);
  assert.equal(rate.volume_mcm_per_day, null);
  assert.equal(typeof rate.native_value, "string");
  assert.deepEqual(
    JSON.parse(JSON.stringify(result.meta.warnings)),
    ["NATIVE_UNITS_PRESERVED", "HUMAN_REVIEW_REQUIRED"],
  );
  assert.deepEqual(JSON.parse(JSON.stringify(result.meta.missing_inputs)), []);
  assert.equal(result.meta.precision, "exact-decimal-tokens");
});

test("native physical ranges keep explicit offsets and exact meta on both reads", async () => {
  const harness = clientHarness();
  const fromUtc = "2026-01-01T01:00:00+01:00";
  const toUtc = "2026-01-01T03:30:00.250+01:00";
  const flowEnvelope = { data: [SAMPLE_FLOW], meta: SAMPLE_META };
  harness.respondWith(jsonResponse(flowEnvelope));

  const flowResult = await harness.client.fetchNativeFlows({ fromUtc, toUtc });

  assert.equal(harness.calls.length, 1);
  const [{ url: flowUrl }] = harness.calls;
  assert.equal(flowUrl.pathname, "/api/physical/flows");
  assert.equal(flowUrl.searchParams.get("from_utc"), fromUtc);
  assert.equal(flowUrl.searchParams.get("to_utc"), toUtc);
  assert.deepEqual(
    [...flowUrl.searchParams.keys()],
    ["quantity_basis", "limit", "from_utc", "to_utc"],
  );
  // The positive sign survives as %2B; it is never decoded into a space.
  assert.match(flowUrl.search, /from_utc=2026-01-01T01%3A00%3A00%2B01%3A00/);
  assert.match(flowUrl.search, /to_utc=2026-01-01T03%3A30%3A00.250%2B01%3A00/);
  assert.deepEqual(JSON.parse(JSON.stringify(flowResult)), flowEnvelope);

  const capacityEnvelope = { data: [SAMPLE_CAPACITY], meta: SAMPLE_META };
  harness.respondWith(jsonResponse(capacityEnvelope));
  const capacityResult = await harness.client.fetchNativeCapacity({
    pointId: "point-2",
    fromUtc,
    toUtc,
  });

  assert.equal(harness.calls.length, 2);
  const capacityUrl = harness.calls[1].url;
  assert.equal(capacityUrl.pathname, "/api/physical/capacity");
  assert.equal(capacityUrl.searchParams.get("from_utc"), fromUtc);
  assert.equal(capacityUrl.searchParams.get("to_utc"), toUtc);
  assert.deepEqual(
    [...capacityUrl.searchParams.keys()],
    ["quantity_basis", "point_id", "limit", "from_utc", "to_utc"],
  );
  assert.deepEqual(JSON.parse(JSON.stringify(capacityResult)), capacityEnvelope);
});

test("native physical ranges accept UTC Z and leap-day boundaries", async () => {
  const harness = clientHarness();
  harness.respondWith(jsonResponse({ data: [], meta: SAMPLE_META }));

  await harness.client.fetchNativeFlows({
    fromUtc: "2024-02-29T23:59:59.999999Z",
    toUtc: "2024-03-01T00:00:00Z",
  });

  assert.equal(harness.calls.length, 1);
  const [{ url }] = harness.calls;
  assert.equal(url.searchParams.get("from_utc"), "2024-02-29T23:59:59.999999Z");
  assert.equal(url.searchParams.get("to_utc"), "2024-03-01T00:00:00Z");
});

test("native physical ranges compare exact microseconds on both reads", async () => {
  const harness = clientHarness();

  const windows = [
    [
      "one microsecond",
      "2026-01-01T00:00:00.000001Z",
      "2026-01-01T00:00:00.000002Z",
    ],
    [
      "seven-digit fractions",
      "2026-01-01T00:00:00.1234567Z",
      "2026-01-01T00:00:00.1234570Z",
    ],
    [
      "eight-digit fractions",
      "2026-01-01T00:00:00.12345678Z",
      "2026-01-01T00:00:00.12345700Z",
    ],
    [
      "nine-digit fractions",
      "2026-01-01T00:00:00.123456789Z",
      "2026-01-01T00:00:00.123457000Z",
    ],
  ] as const;

  const fetchers = [
    ["flows", harness.client.fetchNativeFlows],
    ["capacity", harness.client.fetchNativeCapacity],
  ] as const;

  for (const [label, fromUtc, toUtc] of windows) {
    for (const [name, fetcher] of fetchers) {
          harness.respondWith(jsonResponse({ data: [], meta: SAMPLE_META }));
      await fetcher({ fromUtc, toUtc });
      const [{ url }] = harness.calls.slice(-1);
      assert.equal(
        url.searchParams.get("from_utc"),
        fromUtc,
        `${name}: ${label} fromUtc`,
      );
      assert.equal(
        url.searchParams.get("to_utc"),
        toUtc,
        `${name}: ${label} toUtc`,
      );
    }
  }

  assert.equal(harness.calls.length, windows.length * fetchers.length);
});

test("fetchNativeCapacity defaults to 200 and omits an unset point_id", async () => {
  const harness = clientHarness();
  const envelope = { data: [SAMPLE_CAPACITY], meta: SAMPLE_META };
  harness.respondWith(jsonResponse(envelope));

  const result = await harness.client.fetchNativeCapacity();

  assert.equal(harness.calls.length, 1);
  const [{ url }] = harness.calls;
  assert.equal(url.pathname, "/api/physical/capacity");
  assert.equal(url.searchParams.get("quantity_basis"), "native");
  assert.equal(url.searchParams.get("point_id"), null);
  assert.equal(url.searchParams.get("limit"), "200");
  assert.deepEqual([...url.searchParams.keys()], ["quantity_basis", "limit"]);

  assert.deepEqual(JSON.parse(JSON.stringify(result)), envelope);
  assert.deepEqual(
    Object.keys(result.data[0]).sort(),
    [...NATIVE_CAPACITY_KEYS].sort(),
  );
  assert.deepEqual(
    Object.keys(result.data[0].native_rate_json).sort(),
    [...NATIVE_RATE_KEYS].sort(),
  );
  assert.equal(result.data[0].capacity_type, "firm");
  assert.equal(result.data[0].native_rate_json.quantity_kind, "volume");
  assert.equal(result.data[0].native_rate_json.rate_basis, "hour");
  assert.equal(
    result.data[0].native_rate_json.volume_mcm_per_day,
    "0.000000000000000000000001",
  );
});

test("invalid native physical queries reject before any request is made", async () => {
  const harness = clientHarness();
  const cases: Array<[string, unknown, RegExp]> = [
    ["missing options", null, /options are required/i],
    ["array options", [], /options are required/i],
    ["blank point id", { pointId: "   " }, /pointId/i],
    ["overlong point id", { pointId: "p".repeat(129) }, /128/],
    ["non-string point id", { pointId: 42 }, /pointId/i],
    ["zero limit", { limit: 0 }, /limit/i],
    ["limit above maximum", { limit: 2001 }, /limit/i],
    ["fractional limit", { limit: 1.5 }, /limit/i],
    ["null limit", { limit: null }, /limit/i],
    ["string limit", { limit: "200" }, /limit/i],
    ["boolean limit", { limit: true }, /limit/i],
    ["NaN limit", { limit: Number.NaN }, /limit/i],
    ["missing fromUtc partner", { toUtc: "2026-01-01T01:00:00Z" }, /together/i],
    ["missing toUtc partner", { fromUtc: "2026-01-01T00:00:00Z" }, /together/i],
    ["non-string fromUtc", { fromUtc: 42, toUtc: "2026-01-01T01:00:00Z" }, /fromUtc/i],
    ["null fromUtc", { fromUtc: null, toUtc: "2026-01-01T01:00:00Z" }, /fromUtc/i],
    ["non-string toUtc", { fromUtc: "2026-01-01T00:00:00Z", toUtc: 42 }, /toUtc/i],
    ["null toUtc", { fromUtc: "2026-01-01T00:00:00Z", toUtc: null }, /toUtc/i],
    ["naive fromUtc", { fromUtc: "2026-01-01T00:00:00", toUtc: "2026-01-01T01:00:00Z" }, /timezone/i],
    ["naive toUtc", { fromUtc: "2026-01-01T00:00:00Z", toUtc: "2026-01-01T01:00:00" }, /timezone/i],
    ["compact offset", { fromUtc: "2026-01-01T00:00:00+0100", toUtc: "2026-01-01T01:00:00Z" }, /timezone/i],
    ["lowercase z zone", { fromUtc: "2026-01-01T00:00:00z", toUtc: "2026-01-01T01:00:00Z" }, /timezone/i],
    ["impossible February date", { fromUtc: "2026-02-30T00:00:00Z", toUtc: "2026-03-01T00:00:00Z" }, /calendar/i],
    ["non-leap February 29", { fromUtc: "2026-02-29T00:00:00Z", toUtc: "2026-03-01T00:00:00Z" }, /calendar/i],
    ["month zero", { fromUtc: "2026-00-01T00:00:00Z", toUtc: "2026-01-01T00:00:00Z" }, /calendar/i],
    ["month thirteen", { fromUtc: "2026-13-01T00:00:00Z", toUtc: "2027-01-01T00:00:00Z" }, /calendar/i],
    ["day zero", { fromUtc: "2026-01-00T00:00:00Z", toUtc: "2026-01-01T00:00:00Z" }, /calendar/i],
    ["hour twenty-four", { fromUtc: "2026-01-01T24:00:00Z", toUtc: "2026-01-02T00:00:00Z" }, /calendar/i],
    ["minute sixty", { fromUtc: "2026-01-01T00:60:00Z", toUtc: "2026-01-01T01:00:00Z" }, /calendar/i],
    ["second sixty", { fromUtc: "2026-01-01T00:00:60Z", toUtc: "2026-01-01T00:01:00Z" }, /calendar/i],
    ["invalid offset", { fromUtc: "2026-01-01T00:00:00+24:00", toUtc: "2026-01-01T01:00:00Z" }, /timezone/i],
    ["reversed range", { fromUtc: "2026-01-01T02:00:00Z", toUtc: "2026-01-01T01:00:00Z" }, /earlier/i],
    ["equal range", { fromUtc: "2026-01-01T01:00:00+01:00", toUtc: "2026-01-01T00:00:00Z" }, /earlier/i],
    ["offset-equivalent microseconds", { fromUtc: "2026-01-01T01:00:00.000001+01:00", toUtc: "2026-01-01T00:00:00.000001Z" }, /earlier/i],
    ["seven-digit fraction truncates to equal instant", { fromUtc: "2026-01-01T00:00:00.1234567Z", toUtc: "2026-01-01T00:00:00.1234568Z" }, /earlier/i],
    ["eight-digit fraction truncates to equal instant", { fromUtc: "2026-01-01T00:00:00.12345678Z", toUtc: "2026-01-01T00:00:00.12345679Z" }, /earlier/i],
    ["nine-digit fraction truncates to equal instant", { fromUtc: "2026-01-01T00:00:00.123456789Z", toUtc: "2026-01-01T00:00:00.123456999Z" }, /earlier/i],
  ];

  const fetchers = [
    ["flows", harness.client.fetchNativeFlows],
    ["capacity", harness.client.fetchNativeCapacity],
  ] as const;

  for (const [label, options, expected] of cases) {
    for (const [name, fetcher] of fetchers) {
      await assert.rejects(
        () => fetcher(options),
        expected,
        `${name}: ${label}`,
      );
      assert.equal(
        harness.calls.length,
        0,
        `${name}: ${label} must not issue a request`,
      );
    }
  }
});

test("fetchNativeFlows forwards the caller abort signal and does not swallow aborts", async () => {
  const harness = clientHarness();
  const controller = new AbortController();
  controller.abort();

  await assert.rejects(
    () => harness.client.fetchNativeFlows({ signal: controller.signal }),
    (error: unknown) =>
      typeof error === "object" &&
      error !== null &&
      (error as { name?: unknown }).name === "AbortError",
  );
  assert.equal(harness.calls.length, 1);
  assert.equal(harness.calls[0].init?.signal, controller.signal);
});

test("native physical HTTP failures propagate as the existing structured ApiError", async () => {
  const harness = clientHarness();
  const detail = {
    error: "native_physical_unavailable",
    message: "Native physical read is unavailable.",
    research_only: true,
  };
  harness.respondWith(jsonResponse({ detail }, 422));

  let failure: unknown;
  try {
    await harness.client.fetchNativeCapacity({ pointId: "point-1" });
  } catch (error) {
    failure = error;
  }

  const error = failure as Error & {
    status: number;
    detail: unknown;
    body: unknown;
  };
  assert.ok(error instanceof harness.client.ApiError);
  assert.equal(error.status, 422);
  assert.deepEqual(JSON.parse(JSON.stringify(error.detail)), detail);
  assert.deepEqual(JSON.parse(JSON.stringify(error.body)), { detail });
  assert.match(error.message, /^API 422: native_physical_unavailable/);
  assert.match(error.message, /Native physical read is unavailable\./);
  assert.equal(harness.calls.length, 1);
});
