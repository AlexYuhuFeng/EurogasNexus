import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  attemptClockUtc,
  describeEndpointFailures,
  describeEndpointRetry,
  ENDPOINT_FAILURE_CODE_KEYS,
  ENDPOINT_FAILURE_COUNT_KEY,
  ENDPOINT_FAILURE_LABEL_KEYS,
  ENDPOINT_FAILURE_SHOWING_KEY,
  ENDPOINT_RETRY_ATTEMPTS_KEY,
  ENDPOINT_RETRY_LAST_ATTEMPT_KEY,
  ENDPOINT_RETRY_RUNNING_KEY,
  MAX_ENDPOINT_FAILURE_DETAILS,
  UNKNOWN_ENDPOINT_FAILURE_LABEL_KEY,
} from "../src/app/model/endpointFailures.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

/**
 * Minimal i18next-shaped translator over the real locale files: the point is to
 * exercise the same `{{placeholder}}` interpolation the banner relies on, so a
 * template that cannot interpolate fails here instead of in the browser.
 */
function translator(translations: Record<string, string>) {
  return (key: string, options?: Record<string, unknown>): string => {
    const template = translations[key] ?? key;
    return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(options?.[name] ?? ""));
  };
}

const t = translator(en);

/** Loader keys the store can actually write into `endpointErrors`. */
function workspaceLoaderKeys(): string[] {
  const store = readWebSource("stores/api.ts");
  const block = /function workspaceLoaders\([\s\S]*?\n\}/.exec(store)?.[0] ?? "";
  return [...block.matchAll(/\["([A-Za-z0-9_]+)",/g)].map((match) => match[1]);
}

const MARKET_LANE_KEYS = [
  "normalizedMarkets",
  "marketSpreads",
  "marketQuotes",
  "intradayOpportunities",
  "fxRates",
];

test("known loader keys become translated endpoint labels with safe codes", () => {
  const surface = describeEndpointFailures(
    {
      normalizedMarkets: "API 503: upstream dataops scheduler unavailable",
      marketSpreads: "Workspace endpoint timed out after 10000ms.",
    },
    { normalizedMarkets: "request", marketSpreads: "timeout" },
    t,
  );

  assert.equal(surface.total, 2);
  assert.equal(surface.entries.length, 2);
  assert.equal(surface.truncated, false);
  assert.equal(surface.truncatedSummary, null);
  assert.equal(surface.summary, "2 affected endpoints");
  assert.equal(surface.summaryKey, ENDPOINT_FAILURE_COUNT_KEY);

  const byKey = new Map(surface.entries.map((entry) => [entry.key, entry]));
  const spreads = byKey.get("marketSpreads");
  const markets = byKey.get("normalizedMarkets");
  assert.ok(spreads && markets);

  // Worst first: a timeout outranks a rejected read.
  assert.deepEqual(surface.entries.map((entry) => entry.code), ["timeout", "request"]);

  assert.equal(spreads.labelKey, "workspace.endpoint.market_spreads");
  assert.equal(spreads.label, en["workspace.endpoint.market_spreads"]);
  assert.equal(spreads.code, "timeout");
  assert.equal(spreads.codeKey, ENDPOINT_FAILURE_CODE_KEYS.timeout);
  assert.equal(spreads.message, en["workspace.failure.timeout"]);

  assert.equal(markets.label, en["workspace.endpoint.normalized_markets"]);
  assert.equal(markets.message, en["workspace.failure.request"]);

  // Rendered text never contains a raw loader key or the backend message.
  const rendered = surface.entries
    .map((entry) => `${entry.label} ${entry.code} ${entry.message}`)
    .join(" ");
  for (const rawKey of ["normalizedMarkets", "marketSpreads"]) {
    assert.equal(rendered.includes(rawKey), false, rawKey);
  }
  assert.equal(rendered.includes("API 503"), false);
  assert.equal(rendered.includes("dataops scheduler"), false);
  assert.equal(rendered.includes("10000ms"), false);
});

test("a timeout or an unclassified failure is never rendered as a success", () => {
  const surface = describeEndpointFailures(
    { marketQuotes: "ACME gateway 503 during spread recomputation" },
    { marketQuotes: "timeout" },
    t,
  );

  assert.equal(surface.total, 1);
  assert.equal(surface.entries[0].code, "timeout");
  assert.equal(surface.entries[0].message, en["workspace.failure.timeout"]);
  assert.notEqual(surface.entries[0].code, "ok");
});

test("an empty failure map yields an unmountable zero surface", () => {
  for (const errors of [{}, null, undefined]) {
    const surface = describeEndpointFailures(errors, {}, t);
    assert.equal(surface.total, 0);
    assert.deepEqual(surface.entries, []);
    assert.equal(surface.truncated, false);
    assert.equal(surface.truncatedSummary, null);
    assert.equal(surface.summary, "0 affected endpoints");
  }
});

test("the detail list is bounded to five entries with a showing N of M summary", () => {
  const codes = ["request", "timeout", "aborted", "request", "timeout", "aborted", "unknown", "request"];
  const errors = Object.fromEntries(MARKET_LANE_KEYS.map((key) => [key, "failed"]));
  errors.referenceNodes = "failed";
  errors.sources = "failed";
  errors.runtimeDb = "failed";
  const errorCodes = Object.fromEntries(
    [...MARKET_LANE_KEYS, "referenceNodes", "sources", "runtimeDb"].map((key, index) => [
      key,
      codes[index],
    ]),
  );

  const surface = describeEndpointFailures(errors, errorCodes, t);

  assert.equal(surface.total, 8);
  assert.equal(MAX_ENDPOINT_FAILURE_DETAILS, 5);
  assert.equal(surface.entries.length, 5);
  assert.equal(surface.hiddenCount, 3);
  assert.equal(surface.truncated, true);
  assert.equal(surface.summary, "8 affected endpoints");
  assert.equal(surface.truncatedSummaryKey, ENDPOINT_FAILURE_SHOWING_KEY);
  assert.equal(surface.truncatedSummary, "Showing 5 of 8");
  assert.equal(
    surface.entries.filter((entry) => entry.code === "timeout").length,
    2,
    "both timeouts stay inside the bound",
  );

  // The bound is stable: the same facts produce the same five rows.
  const again = describeEndpointFailures(errors, errorCodes, t);
  assert.deepEqual(again.entries.map((entry) => entry.key), surface.entries.map((entry) => entry.key));
});

test("exactly five failures stay untruncated", () => {
  const errors = Object.fromEntries(MARKET_LANE_KEYS.map((key) => [key, "failed"]));
  const errorCodes = Object.fromEntries(MARKET_LANE_KEYS.map((key) => [key, "timeout"]));
  const surface = describeEndpointFailures(errors, errorCodes, t);

  assert.equal(surface.total, 5);
  assert.equal(surface.entries.length, 5);
  assert.equal(surface.truncated, false);
  assert.equal(surface.truncatedSummary, null);
});

test("unknown loader keys and unknown codes fall back to generic translated text", () => {
  const surface = describeEndpointFailures(
    { mysteryLane: "internal stack trace at loader.ts:42" },
    { mysteryLane: "gateway_5xx" },
    t,
  );

  assert.equal(surface.total, 1);
  const entry = surface.entries[0];
  assert.equal(entry.labelKey, UNKNOWN_ENDPOINT_FAILURE_LABEL_KEY);
  assert.equal(entry.label, en["workspace.endpoint.unknown"]);
  assert.notEqual(entry.label, zh["workspace.endpoint.unknown"], "the fallback is translated per locale");
  assert.notEqual(entry.label, "mysteryLane");
  assert.equal(entry.code, "unknown");
  assert.equal(entry.codeKey, ENDPOINT_FAILURE_CODE_KEYS.unknown);
  assert.equal(entry.message, en["workspace.failure.unknown"]);

  const rendered = `${entry.label} ${entry.code} ${entry.message}`;
  for (const leak of ["mysteryLane", "gateway_5xx", "loader.ts:42", "stack trace"]) {
    assert.equal(rendered.includes(leak), false, leak);
  }

  // A missing code is an unclassified failure, not a success and not a crash.
  const missing = describeEndpointFailures({ pipelineHealth: "failed" }, {}, t);
  assert.equal(missing.entries[0].code, "unknown");
  assert.equal(missing.total, 1);
});

test("every endpoint label and safe code key exists in both locales", () => {
  const loaderKeys = workspaceLoaderKeys();
  assert.ok(loaderKeys.length >= 25, `expected the full loader list, saw ${loaderKeys.length}`);

  for (const key of loaderKeys) {
    assert.ok(ENDPOINT_FAILURE_LABEL_KEYS[key], `missing label mapping for ${key}`);
  }
  for (const key of MARKET_LANE_KEYS) {
    assert.ok(loaderKeys.includes(key), key);
  }

  const keys = [
    ...Object.values(ENDPOINT_FAILURE_LABEL_KEYS),
    UNKNOWN_ENDPOINT_FAILURE_LABEL_KEY,
    ...Object.values(ENDPOINT_FAILURE_CODE_KEYS),
    ENDPOINT_FAILURE_COUNT_KEY,
    ENDPOINT_FAILURE_SHOWING_KEY,
    ENDPOINT_RETRY_ATTEMPTS_KEY,
    ENDPOINT_RETRY_LAST_ATTEMPT_KEY,
    ENDPOINT_RETRY_RUNNING_KEY,
  ];
  assert.equal(new Set(keys).size, keys.length, "duplicate i18n key");

  for (const key of keys) {
    assert.equal(typeof en[key], "string", `en ${key}`);
    assert.equal(typeof zh[key], "string", `zh ${key}`);
    assert.ok(en[key].length > 0 && zh[key].length > 0, key);
    assert.equal(en[key].includes("?"), false, `en ${key}`);
    assert.equal(zh[key].includes("?"), false, `zh ${key}`);
    assert.equal(zh[key].includes("\ufffd"), false, `zh ${key}`);
  }

  // The banner must translate, not merely label: EN and zh-CN stay distinct.
  assert.equal(zh[ENDPOINT_FAILURE_COUNT_KEY].includes("{{total}}"), true);
  assert.equal(en[ENDPOINT_FAILURE_SHOWING_KEY].includes("{{shown}}"), true);
  assert.equal(zh[ENDPOINT_FAILURE_SHOWING_KEY].includes("{{total}}"), true);
});

test("the retry surface is bounded, labelled and busy-aware", () => {
  const idle = describeEndpointRetry(
    { busy: false, attempts: 2, lastAttemptAtUtc: "2026-01-02T03:04:05.678Z" },
    t,
  );
  assert.equal(idle.busy, false);
  assert.equal(idle.disabled, false);
  assert.equal(idle.attempts, 2);
  assert.equal(idle.attemptsLabel, "Attempts: 2");
  assert.equal(idle.lastAttemptAtUtc, "2026-01-02T03:04:05.678Z");
  assert.equal(idle.lastAttemptLabel, "Last retry attempt 03:04:05 UTC");
  assert.equal(idle.runningKey, null);
  assert.equal(idle.runningLabel, null);

  const busy = describeEndpointRetry(
    { busy: true, attempts: 3, lastAttemptAtUtc: "2026-01-02T03:04:05.678Z" },
    t,
  );
  assert.equal(busy.disabled, true, "a retry in flight disables the control");
  assert.equal(busy.runningKey, ENDPOINT_RETRY_RUNNING_KEY);
  assert.equal(busy.runningLabel, en["workspace.retry_in_progress"]);

  const fresh = describeEndpointRetry({ busy: false, attempts: 0, lastAttemptAtUtc: null }, t);
  assert.equal(fresh.attemptsLabel, "Attempts: 0");
  assert.equal(fresh.lastAttemptLabel, null);

  const nonsense = describeEndpointRetry(
    { busy: false, attempts: Number.NaN, lastAttemptAtUtc: "not-a-date" },
    t,
  );
  assert.equal(nonsense.attempts, 0);
  assert.equal(nonsense.lastAttemptAtUtc, "not-a-date");
  assert.equal(nonsense.lastAttemptLabel, null, "an unparsable timestamp is not printed");
});

test("attempt clock times are UTC and never Invalid Date", () => {
  assert.equal(attemptClockUtc("2026-01-02T03:04:05.678Z"), "03:04:05");
  assert.equal(attemptClockUtc("2026-01-02T23:59:59.000Z"), "23:59:59");
  for (const value of [null, undefined, "", "not-a-date"]) {
    assert.equal(attemptClockUtc(value), null, String(value));
  }
});

test("the shell renders one bounded structured surface instead of raw loader keys", () => {
  const shell = readWebSource("app/shell/AppShell.tsx");
  const store = readWebSource("stores/api.ts");
  const loading = readWebSource("stores/workspaceLoading.ts");

  // The old raw-key banner is gone: no joined loader keys, no "failed endpoints" list.
  assert.equal(shell.includes("Object.keys(api.endpointErrors)"), false);
  assert.equal(shell.includes('.join(", ")'), false);
  assert.equal(shell.includes('t("workspace.failed_endpoints")'), false);

  // One surface, still a polite status region in normal flow, now also busy-aware.
  assert.equal(shell.match(/className="endpoint-error-banner"/g)?.length, 1);
  assert.match(shell, /role="status"/);
  assert.match(shell, /aria-live="polite"/);
  assert.match(shell, /aria-busy=\{endpointRetry\.busy\}/);

  // The safe machine codes now reach the UI through the store's code map.
  assert.match(shell, /describeEndpointFailures\(api\.endpointErrors, api\.endpointErrorCodes, t\)/);
  assert.match(shell, /\{entry\.label\}/);
  assert.match(shell, /\{entry\.code\}/);
  assert.match(shell, /\{entry\.message\}/);
  assert.match(shell, /\{endpointFailures\.summary\}/);
  assert.match(shell, /\{endpointFailures\.truncatedSummary\}/);
  assert.ok(shell.includes("key={entry.key}"), "the loader key is only a React key");
  assert.equal(
    shell.match(/entry\.key/g)?.length,
    1,
    "the loader key must appear once, as the React key, and never as text",
  );
  assert.equal(shell.includes('role="tab"'), false);

  // Bounded retry: disabled and aria-busy while running, with attempt evidence.
  assert.match(shell, /disabled=\{endpointRetry\.disabled\}/);
  assert.match(shell, /aria-busy=\{endpointRetry\.busy\}/);
  assert.match(shell, /\{endpointRetry\.attemptsLabel\}/);
  assert.match(shell, /\{endpointRetry\.lastAttemptLabel\}/);
  assert.match(shell, /onClick=\{\(\) => void api\.retryFailedWorkspaceEndpoints\(\)\}/);

  // The store refuses a second concurrent attempt before any request is issued.
  assert.match(store, /if \(get\(\)\.endpointRetryBusy\) return;/);
  assert.match(store, /endpointRetryAttempts: state\.endpointRetryAttempts \+ 1/);
  assert.match(store, /endpointRetryLastAttemptAtUtc: new Date\(\)\.toISOString\(\)/);
  assert.ok(
    store.indexOf("if (get().endpointRetryBusy) return;") <
      store.indexOf(
        "const load = startWorkspaceLoad();",
        store.indexOf("retryFailedWorkspaceEndpoints: async"),
      ),
    "the busy refusal must precede the retry request",
  );

  // Unchanged retry semantics: per-attempt 10s timeout, inner retry, supersession.
  assert.match(loading, /export const DEFAULT_WORKSPACE_READ_TIMEOUT_MS = 10_000;/);
  assert.match(store, /timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS/);
  assert.match(store, /workspaceLoadCoordinator\.isCurrent\(load\.generation, load\.signal\)/);
  assert.match(loading, /workspaceLoadHasIdentityDenial/);

  // Fail closed stays fail closed: a failed retry outcome is recorded as a
  // failure with its code, and only a confirmed success clears the surface.
  assert.match(store, /delete endpointErrors\[key\];/);
  assert.match(store, /endpointErrors\[key\] = outcome\.error\.message;/);
  assert.match(store, /endpointErrorCodes\[key\] = outcome\.error\.code;/);
  assert.match(loading, /endpointRetryBusy: false/);
});
