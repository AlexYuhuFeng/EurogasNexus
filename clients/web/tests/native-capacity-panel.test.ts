/**
 * Native capacity context panel.
 *
 * The panel is loaded through Vite's SSR module runner because the repository's source
 * components are TSX and this test command runs on native Node type stripping. The
 * lifecycle tests exercise the real session and the real shared API transport against a
 * controlled fetch, and the render tests use the real `buildNativeCapacityContext` output
 * so exact canonical strings, unclipped indications and null diagnostics are pinned.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { after, afterEach, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

import { buildNativeCapacityContext } from "../src/app/model/nativeCapacityContext.ts";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const EN = JSON.parse(
  readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8"),
) as Record<string, string>;
const ZH = JSON.parse(
  readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8"),
) as Record<string, string>;
const t = (key: string): string => EN[key] ?? key;

const originalFetch = globalThis.fetch;
let vite: Awaited<ReturnType<typeof createServer>>;
let panel: {
  NativeCapacityContextPanel: (props: { t: (key: string) => string }) => unknown;
  NativeCapacityContextResults: (props: {
    read: unknown;
    t: (key: string) => string;
    page: number;
    onPageChange: (page: number) => void;
    pointId?: string | null;
  }) => unknown;
  NativeCapacityPaginationControls: (props: {
    pagination: {
      page: number;
      pageCount: number;
      start: number;
      end: number;
      total: number;
    };
    onPageChange: (page: number) => void;
    t: (key: string) => string;
  }) => unknown;
  nativeCapacityPageWindow: (
    total: number,
    requestedPage: number,
  ) => {
    page: number;
    pageCount: number;
    start: number;
    end: number;
    total: number;
  };
  nativeCapacityPageForRead: (
    previousRead: unknown,
    read: unknown,
    requestedPage: number,
  ) => number;
  NativeCapacityQuerySession: new () => {
    run: (pointId: string) => Promise<{
      state: string;
      pointId?: string;
      read?: unknown;
      error?: unknown;
    }>;
    dispose: () => void;
  };
};

before(async () => {
  vite = await createServer({
    root: ROOT,
    configFile: false,
    logLevel: "silent",
    appType: "custom",
    server: { middlewareMode: true, hmr: false },
    resolve: {
      alias: { "@": fileURLToPath(new URL("../src", import.meta.url)) },
    },
    esbuild: { jsx: "automatic" },
  });
  panel = (await vite.ssrLoadModule("/src/components/NativeCapacityContextPanel.tsx")) as typeof panel;
});

after(async () => {
  await vite?.close();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  delete (globalThis as Record<string, unknown>).window;
  delete (globalThis as Record<string, unknown>).localStorage;
});

const FLOW_START = "2026-10-28T00:00:00+00:00";
const FLOW_END = "2026-10-29T00:00:00+00:00";
const CAPACITY_START = "2026-10-27T00:00:00+00:00";
const CAPACITY_END = "2026-10-29T00:00:00+00:00";
const RECEIVED_AT = "2026-10-28T01:02:03+00:00";
const FLOW_HASH = "a".repeat(64);
const CAPACITY_HASH = "b".repeat(64);

function rate(value: string) {
  return {
    value_text: value,
    unit_text: "kWh/d",
    native_value: value,
    normalized_unit: "kWh/day",
    quantity_kind: "energy",
    rate_basis: "day",
    energy_kwh_per_day: value,
    volume_mcm_per_day: null,
    normalizer_version: "entsog-native-units-v1",
  };
}

function flow(overrides: Record<string, unknown> = {}) {
  return {
    observation_id: "flow-n1-1",
    source_record_id: "provider-flow-1",
    point_id: "ITP-00126",
    point_name: "Punto di scambio",
    direction: "entry",
    kind: "actual",
    period_start_utc: FLOW_START,
    period_end_utc: FLOW_END,
    observed_at_utc: RECEIVED_AT,
    source_system: "ENTSOG",
    operator_key: "DE-TSO-0009",
    flow_status: null,
    period_type: "day",
    source_reference: "entsog-operationaldatas;offset=0;limit=100",
    research_only: true,
    quantity_basis: "native",
    normalizer_version: "entsog-native-units-v1",
    native_rate_json: rate("92954921"),
    raw_archive_id: "raw-flow-archive",
    payload_sha256: FLOW_HASH,
    received_at_utc: RECEIVED_AT,
    ...overrides,
  };
}

function capacity(overrides: Record<string, unknown> = {}) {
  return {
    observation_id: "capacity-n1-1",
    source_record_id: "provider-capacity-1",
    point_id: "ITP-00126",
    point_name: "Punto di scambio",
    direction: "entry",
    capacity_type: "firm_technical",
    period_start_utc: CAPACITY_START,
    period_end_utc: CAPACITY_END,
    observed_at_utc: RECEIVED_AT,
    source_system: "ENTSOG",
    operator_key: "DE-TSO-0009",
    flow_status: null,
    period_type: "day",
    source_reference: "entsog-operationaldatas;offset=0;limit=100",
    research_only: true,
    quantity_basis: "native",
    normalizer_version: "entsog-native-units-v1",
    native_rate_json: rate("416592000"),
    raw_archive_id: "raw-capacity-archive",
    payload_sha256: CAPACITY_HASH,
    received_at_utc: RECEIVED_AT,
    ...overrides,
  };
}

function fixtureRead() {
  const longFlow = "92954921.123456789012345678901234567890";
  const longCapacity = "416592000.000000000000000000000000000001";
  const contexts = buildNativeCapacityContext(
    [
      flow({ observation_id: "flow-long", native_rate_json: rate(longFlow) }),
      flow({ observation_id: "flow-over", point_id: "ITP-OVER", native_rate_json: rate("200") }),
      flow({ observation_id: "flow-null", point_id: "ITP-NULL", native_rate_json: rate("5") }),
    ] as never,
    [
      capacity({ observation_id: "capacity-long", native_rate_json: rate(longCapacity) }),
      capacity({ observation_id: "capacity-over", point_id: "ITP-OVER", native_rate_json: rate("100") }),
    ] as never,
  );
  return {
    contexts,
    flowMeta: {
      research_only: true,
      human_review_required: true,
      warnings: ["FLOW_META_WARNING"],
      source_references: ["flow-meta-source"],
      missing_inputs: ["flow-meta-missing"],
    },
    capacityMeta: {
      research_only: false,
      human_review_required: false,
      warnings: ["CAPACITY_META_WARNING"],
      source_references: ["capacity-meta-source"],
      missing_inputs: ["capacity-meta-missing"],
    },
  };
}

function largeRead(count = 120) {
  const flows = Array.from({ length: count }, (_, index) => {
    const padded = String(index).padStart(3, "0");
    return flow({
      observation_id: `flow-page-${padded}`,
      source_record_id: `provider-flow-page-${padded}`,
      point_id: `ITP-PAGE-${padded}`,
      point_name: `Paged point ${padded}`,
      native_rate_json: rate(String(index + 1)),
    });
  });
  const capacities = flows.map((flowRow) =>
    capacity({
      observation_id: `capacity-${flowRow.observation_id}`,
      source_record_id: `provider-capacity-${flowRow.observation_id}`,
      point_id: flowRow.point_id,
      point_name: flowRow.point_name,
      native_rate_json: rate("1000"),
    }),
  );
  const contexts = buildNativeCapacityContext(flows as never, capacities as never);
  assert.equal(contexts.length, count);
  return {
    contexts,
    flowMeta: {
      research_only: true,
      human_review_required: false,
      warnings: [],
      source_references: [],
      missing_inputs: [],
    },
    capacityMeta: {
      research_only: true,
      human_review_required: false,
      warnings: [],
      source_references: [],
      missing_inputs: [],
    },
  };
}

function renderResults(read: unknown, page: number, pointId: string | null = null): string {
  return renderToStaticMarkup(
    createElement(panel.NativeCapacityContextResults, {
      read,
      t,
      page,
      onPageChange: () => {},
      pointId,
    }),
  );
}

function cardCount(html: string): number {
  return (html.match(/<article[^>]*data-native-context="true"/g) ?? []).length;
}

function buttonTag(html: string, action: "previous" | "next"): string {
  return (
    html.match(
      new RegExp(`<button[^>]*data-native-page-action="${action}"[^>]*>`),
    )?.[0] ?? ""
  );
}

interface ElementLike {
  readonly props: Record<string, unknown>;
}

function findElements(node: unknown, attribute: string): ElementLike[] {
  const found: ElementLike[] = [];
  const visit = (value: unknown): void => {
    if (Array.isArray(value)) {
      for (const child of value) visit(child);
      return;
    }
    if (typeof value !== "object" || value === null) return;
    const props = (value as { props?: unknown }).props;
    if (typeof props !== "object" || props === null) return;
    const record = props as Record<string, unknown>;
    if (attribute in record) found.push({ props: record });
    visit(record.children);
  };
  visit(node);
  return found;
}

function pageAction(node: unknown, action: "previous" | "next"): ElementLike {
  const element = findElements(node, "data-native-page-action").find(
    (candidate) => candidate.props["data-native-page-action"] === action,
  );
  assert.ok(element, `missing ${action} page control`);
  return element;
}

function click(element: ElementLike): void {
  const onClick = element.props.onClick;
  assert.equal(typeof onClick, "function");
  (onClick as () => void)();
}

interface PendingCall {
  url: URL;
  init: RequestInit;
  signal: AbortSignal | undefined;
  resolve: (value: Response) => void;
  reject: (reason?: unknown) => void;
}

function abortError(): Error {
  const error = new Error("aborted");
  error.name = "AbortError";
  return error;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function completePhysicalCall(call: PendingCall): void {
  const kind = call.url.pathname.endsWith("/physical/flows") ? "flows" : "capacity";
  const pointId = call.url.searchParams.get("point_id") ?? "";
  const data =
    kind === "flows"
      ? [flow({ point_id: pointId })]
      : [capacity({ point_id: pointId })];
  call.resolve(
    jsonResponse({
      data,
      meta: {
        research_only: true,
        human_review_required: false,
        warnings: [`${kind}_warning`],
        source_references: [`${kind}_source`],
      },
    }),
  );
}

function installBrowserStubs(): void {
  const storage = new Map<string, string>([
    ["eurogas.settings.api_token", "test-token"],
  ]);
  (globalThis as Record<string, unknown>).window = {
    location: { origin: "http://localhost", protocol: "http:", hostname: "localhost" },
  };
  (globalThis as Record<string, unknown>).localStorage = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
    clear: () => storage.clear(),
  };
}

function installPendingFetch(): PendingCall[] {
  const pending: PendingCall[] = [];
  (globalThis as Record<string, unknown>).fetch = (
    input: string | URL | Request,
    init?: RequestInit,
  ) =>
    new Promise<Response>((resolve, reject) => {
      const url = new URL(
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url,
      );
      const signal = init?.signal ?? undefined;
      signal?.addEventListener("abort", () => reject(abortError()), { once: true });
      pending.push({ url, init: init ?? {}, signal, resolve, reject });
    });
  return pending;
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 500; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  throw new Error("Timed out waiting for the controlled fetch.");
}

test("native panel labels have EN/ZH parity", () => {
  const english = Object.keys(EN).filter((key) => key.startsWith("nativeCapacity."));
  const chinese = Object.keys(ZH).filter((key) => key.startsWith("nativeCapacity."));
  assert.ok(english.length > 80);
  for (const key of english) assert.equal(typeof ZH[key], "string", `missing zh label: ${key}`);
  for (const key of chinese) assert.equal(typeof EN[key], "string", `missing en label: ${key}`);
});

test("the panel starts idle and asks for an explicit point_id", () => {
  const html = renderToStaticMarkup(
    createElement(panel.NativeCapacityContextPanel, { t }),
  );
  assert.match(html, /Submit an explicit point_id/);
  assert.match(html, /data-native-query-form="true"/);
  assert.ok(!html.includes("data-native-results"));
});

test("real model output keeps exact rates, unclipped ratios and null diagnostics", () => {
  const read = fixtureRead();
  const html = renderToStaticMarkup(
    createElement(panel.NativeCapacityContextResults, {
      read,
      t,
      page: 0,
      onPageChange: () => {},
    }),
  );

  assert.ok(html.includes("92954921.123456789012345678901234567890"));
  assert.ok(html.includes("416592000.000000000000000000000000000001"));
  assert.match(html, /200(?:<!-- -->)?%/);
  assert.ok(html.includes('data-native-ratio-value="200"'));
  assert.ok(html.includes("Approximate indication"));
  assert.ok(html.includes("FLOW_META_WARNING"));
  assert.ok(html.includes("CAPACITY_META_WARNING"));
  assert.ok(html.includes("flow-meta-source"));
  assert.ok(html.includes("capacity-meta-source"));
  assert.ok(html.includes("flow-meta-missing"));
  assert.ok(html.includes("capacity-meta-missing"));
  assert.ok(html.includes("DE-TSO-0009"));
  assert.ok(html.includes("2026-10-28T00:00:00+00:00"));
  assert.ok(html.includes("2026-10-29T00:00:00+00:00"));
  assert.ok(html.includes(FLOW_HASH));
  assert.ok(html.includes(CAPACITY_HASH));
  assert.ok(html.includes("raw-flow-archive"));
  assert.ok(html.includes("raw-capacity-archive"));

  const nullArticle =
    html.match(/<article[^>]*data-native-context-id="flow-null"[\s\S]*?<\/article>/)?.[0] ?? "";
  assert.ok(nullArticle.length > 0);
  assert.match(nullArticle, /Not indicated/);
  assert.match(nullArticle, /no_capacity_match/);
  assert.doesNotMatch(nullArticle, /data-native-ratio-value/);
  assert.doesNotMatch(nullArticle, /<strong>0%<\/strong>/);
});

test("pagination renders only one 50-card page and keeps the full total visible", () => {
  const read = largeRead(120);

  const first = renderResults(read, 0);
  assert.equal(cardCount(first), 50);
  assert.match(first, /Flow observations<\/span><strong>120<\/strong>/);
  assert.match(first, /data-native-page-current="1"/);
  assert.match(first, /data-native-page-count="3"/);
  assert.match(first, /data-native-page-start="1"/);
  assert.match(first, /data-native-page-end="50"/);
  assert.match(first, /data-native-page-total="120"/);
  assert.match(buttonTag(first, "previous"), /aria-label="Previous result page"/);
  assert.match(buttonTag(first, "previous"), /disabled/);
  assert.doesNotMatch(buttonTag(first, "next"), /disabled/);
  assert.match(first, /50 results per page/);
  assert.ok(first.includes("flow-page-049"));
  assert.ok(!first.includes("flow-page-050"));

  const second = renderResults(read, 1);
  assert.equal(cardCount(second), 50);
  assert.match(second, /data-native-page-current="2"/);
  assert.match(second, /data-native-page-start="51"/);
  assert.match(second, /data-native-page-end="100"/);
  assert.ok(second.includes("flow-page-050"));
  assert.ok(second.includes("flow-page-099"));
  assert.ok(!second.includes("flow-page-000"));

  const last = renderResults(read, 99);
  assert.equal(cardCount(last), 20);
  assert.match(last, /data-native-page-current="3"/);
  assert.match(last, /data-native-page-start="101"/);
  assert.match(last, /data-native-page-end="120"/);
  assert.match(last, /data-native-page-total="120"/);
  assert.match(buttonTag(last, "next"), /aria-label="Next result page"/);
  assert.match(buttonTag(last, "next"), /disabled/);
  assert.ok(last.includes("flow-page-119"));
});

test("page controls navigate real targets and disable at the edges", () => {
  const changes: number[] = [];
  const middle = panel.NativeCapacityPaginationControls({
    pagination: panel.nativeCapacityPageWindow(120, 1),
    onPageChange: (next) => changes.push(next),
    t,
  });
  const middlePrevious = pageAction(middle, "previous");
  const middleNext = pageAction(middle, "next");
  assert.equal(middlePrevious.props.disabled, false);
  assert.equal(middleNext.props.disabled, false);
  click(middlePrevious);
  click(middleNext);
  assert.deepEqual(changes, [0, 2]);

  const first = panel.NativeCapacityPaginationControls({
    pagination: panel.nativeCapacityPageWindow(120, 0),
    onPageChange: () => {},
    t,
  });
  assert.equal(pageAction(first, "previous").props.disabled, true);
  assert.equal(pageAction(first, "next").props.disabled, false);

  const last = panel.NativeCapacityPaginationControls({
    pagination: panel.nativeCapacityPageWindow(120, 99),
    onPageChange: () => {},
    t,
  });
  assert.equal(pageAction(last, "previous").props.disabled, false);
  assert.equal(pageAction(last, "next").props.disabled, true);
});

test("a new read resets the page while a shrinking read clamps it", () => {
  const first = largeRead(120);
  const replacement = largeRead(60);
  assert.equal(panel.nativeCapacityPageForRead(first, replacement, 2), 0);
  assert.equal(panel.nativeCapacityPageForRead(first, first, 2), 2);
  assert.equal(panel.nativeCapacityPageForRead(first, first, 99), 2);

  const shorter = largeRead(60);
  assert.equal(panel.nativeCapacityPageForRead(shorter, shorter, 2), 1);
  assert.equal(panel.nativeCapacityPageWindow(120, 99).page, 2);
  assert.equal(panel.nativeCapacityPageWindow(0, 9).page, 0);
});

test("the accepted query point_id labels the loaded result and a missing point_id does not", async () => {
  installBrowserStubs();
  const pending = installPendingFetch();
  const session = new panel.NativeCapacityQuerySession();
  const running = session.run("ITP-ACCEPTED");
  await waitFor(() => pending.length === 2);
  completePhysicalCall(pending[0]!);
  completePhysicalCall(pending[1]!);
  const outcome = await running;
  assert.equal(outcome.state, "success");
  if (outcome.state !== "success") return;

  const labelled = renderResults(outcome.read, 0, outcome.pointId);
  const label = labelled.match(/<p[^>]*data-native-resolved-point="true"[\s\S]*?<\/p>/)?.[0] ?? "";
  assert.ok(label.length > 0);
  assert.ok(label.includes("Loaded point_id"));
  assert.ok(label.includes("ITP-ACCEPTED"));

  const unlabelled = renderResults(outcome.read, 0, null);
  assert.ok(!unlabelled.includes("data-native-resolved-point"));
});

test("concurrent reads use limit 2000 and shared auth, and stale completions never publish", async () => {
  installBrowserStubs();
  const pending = installPendingFetch();
  const session = new panel.NativeCapacityQuerySession();

  const first = session.run("ITP-1");
  await waitFor(() => pending.length === 2);
  assert.ok(pending[0]!.url.pathname.endsWith("/physical/flows"));
  assert.ok(pending[1]!.url.pathname.endsWith("/physical/capacity"));
  assert.equal(pending[0]!.signal, pending[1]!.signal);
  assert.ok(pending[0]!.signal instanceof AbortSignal);
  for (const call of pending.slice(0, 2)) {
    assert.equal(call.url.searchParams.get("quantity_basis"), "native");
    assert.equal(call.url.searchParams.get("point_id"), "ITP-1");
    assert.equal(call.url.searchParams.get("limit"), "2000");
    assert.equal(call.init.credentials, "include");
    assert.equal(
      (call.init.headers as Record<string, string>).Authorization,
      "Bearer test-token",
    );
  }

  const second = session.run("ITP-2");
  await waitFor(() => pending.length === 4);
  assert.equal(pending[0]!.signal?.aborted, true);
  assert.equal(pending[1]!.signal?.aborted, true);
  assert.equal((await first).state, "superseded");

  completePhysicalCall(pending[2]!);
  completePhysicalCall(pending[3]!);
  const secondOutcome = await second;
  assert.equal(secondOutcome.state, "success");
  if (secondOutcome.state === "success") {
    assert.equal(secondOutcome.pointId, "ITP-2");
    const read = secondOutcome.read as { contexts: unknown[] };
    assert.equal(read.contexts.length, 1);
  }

  const third = session.run("ITP-3");
  await waitFor(() => pending.length === 6);
  session.dispose();
  assert.equal(pending[4]!.signal?.aborted, true);
  assert.equal(pending[5]!.signal?.aborted, true);
  assert.equal((await third).state, "superseded");
});

test("a failed read yields an error outcome and no result", async () => {
  installBrowserStubs();
  (globalThis as Record<string, unknown>).fetch = async () =>
    jsonResponse(
      { detail: { code: "ENTSOG_READ_FAILED", message: "read failed" } },
      502,
    );

  const session = new panel.NativeCapacityQuerySession();
  const outcome = await session.run("ITP-ERR");
  assert.equal(outcome.state, "error");
  if (outcome.state === "error") {
    assert.equal((outcome.error as { status?: number }).status, 502);
    assert.match(String((outcome.error as Error).message), /ENTSOG_READ_FAILED/);
  }
});
