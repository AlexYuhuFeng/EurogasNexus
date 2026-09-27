/**
 * The Source Center's registry read state: pending is not zero, a failure is not an empty
 * registry, and a measured empty is its own answer.
 *
 * CI and the acceptance report recorded the defect this covers: `GET /api/sources` failing in the
 * workspace batch left the surface holding no source and rendering "Total sources 0" beside the
 * catalog's "No active warnings" - the copy of a measured zero, produced by a read that never
 * answered (`docs/release/FUNCTIONAL_ACCEPTANCE_REPORT.md`, 2026-09-25 limits). The states are
 * pure (`app/model/sourceRegistryRead.ts`), so they are asserted directly, and the facts they
 * derive from are asserted through the actual store with answers the test settles by hand - the
 * same harness the projection and runtime-loader tests use.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";

import type { EndpointRetryState } from "../src/app/model/endpointFailures.ts";
import type {
  SourceRegistryReadFacts,
  SourceRegistryReadSurface,
} from "../src/app/model/sourceRegistryRead.ts";
import { AUTHENTICATED_AUTH_STATE } from "../src/stores/workspaceLoading.ts";
import {
  closeApiStoreHarness,
  deferred,
  loadApiStore,
  settle,
  type ApiStoreHarness,
} from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

const IDLE_RETRY: EndpointRetryState = { busy: false, attempts: 0, lastAttemptAtUtc: null };

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function readLocale(name: "en" | "zh"): Record<string, string> {
  return JSON.parse(readWebSource(`i18n/${name}.json`)) as Record<string, string>;
}

/**
 * Minimal i18next-shaped translator over the real locale files, so the copy the surface renders
 * is the copy the locales declare rather than the key itself.
 */
function translator(translations: Record<string, string>) {
  return (key: string, options?: Record<string, unknown>): string => {
    const template = translations[key] ?? key;
    return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(options?.[name] ?? ""));
  };
}

const en = readLocale("en");
const zh = readLocale("zh");

type Model = (
  facts: SourceRegistryReadFacts,
  t: (key: string) => string,
) => SourceRegistryReadSurface;

/** The model, loaded through the harness's own module pipeline (the `@` alias included). */
async function loadModel(harness: ApiStoreHarness): Promise<Model> {
  const module = await harness.load<{ sourceRegistryReadSurface: Model }>(
    "/src/app/model/sourceRegistryRead.ts",
  );
  return module.sourceRegistryReadSurface;
}

/** Put the session past the identity gate, as a resolved sign-in does, and hand the store back. */
function authenticated(harness: ApiStoreHarness) {
  harness.store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  return harness.store;
}

function sourceRows(ids: string[]) {
  return ids.map((source_id) => ({
    source_id,
    source_system: source_id.toUpperCase(),
    category: "price",
  }));
}

/** The surface the store currently supports, through the same model the component renders. */
function surfaceOf(
  store: ApiStoreHarness["store"],
  model: Model,
  t: (key: string) => string = translator(en),
): SourceRegistryReadSurface {
  const state = store.getState();
  return model(
    {
      rowCount: state.sources.length,
      loading: state.workspaceLoading,
      committedPasses: state.workspaceLoadsCommitted,
      error: state.endpointErrors.sources,
      errorCode: state.endpointErrorCodes.sources,
      retry: {
        busy: state.endpointRetryBusy,
        attempts: state.endpointRetryAttempts,
        lastAttemptAtUtc: state.endpointRetryLastAttemptAtUtc,
      },
    },
    t,
  );
}

test("every state is named, and only a committed reading may state a count", async () => {
  const harness = await loadApiStore();
  const model = await loadModel(harness);
  const t = translator(en);

  const facts = (overrides: Partial<SourceRegistryReadFacts> = {}): SourceRegistryReadFacts => ({
    rowCount: 0,
    loading: false,
    committedPasses: 0,
    error: null,
    errorCode: null,
    retry: IDLE_RETRY,
    ...overrides,
  });

  // Nothing has been read: no count, and not the empty-registry sentence either.
  const unread = model(facts(), t);
  assert.equal(unread.state, "unread");
  assert.equal(unread.hasReading, false);
  assert.equal(unread.noticeKey, "sources.registry.unread");
  assert.equal(unread.noticeKey && en[unread.noticeKey], en["sources.registry.unread"]);

  // A read in flight is pending, not a zero.
  const pending = model(facts({ loading: true }), t);
  assert.equal(pending.state, "pending");
  assert.equal(pending.hasReading, false);
  assert.equal(pending.noticeKey, "sources.registry.pending");
  assert.notEqual(pending.noticeKey, unread.noticeKey);

  // A successful read that returned nothing is a measurement of zero rows: the surface may state
  // it, and it must not be confused with the unread lane above.
  const empty = model(facts({ committedPasses: 1 }), t);
  assert.equal(empty.state, "empty");
  assert.equal(empty.hasReading, true);
  assert.equal(empty.noticeKey, null);
  assert.equal(typeof en["sources.registry.empty"], "string");

  // Rows committed and the newest read failed: the failure outranks the rows, which stay on
  // screen as the last committed reading rather than as this attempt's.
  const failedWithRows = model(
    facts({
      rowCount: 3,
      committedPasses: 2,
      error: "Workspace endpoint timed out",
      errorCode: "timeout",
    }),
    t,
  );
  assert.equal(failedWithRows.state, "failed");
  assert.equal(failedWithRows.hasReading, true);
  assert.equal(failedWithRows.noticeKey, "sources.registry.failed");
  assert.equal(failedWithRows.failureEndpointKey, "workspace.endpoint.sources");
  assert.equal(failedWithRows.failureMessageKey, "workspace.failure.timeout");
  assert.equal(en[failedWithRows.failureMessageKey], en["workspace.failure.timeout"]);

  // The batch clears the rows when its own read fails, and then no count may be stated at all.
  const failedEmpty = model(
    facts({ committedPasses: 1, error: "API 503: unavailable", errorCode: "request" }),
    t,
  );
  assert.equal(failedEmpty.state, "failed");
  assert.equal(failedEmpty.hasReading, false);
  assert.equal(failedEmpty.failureMessageKey, "workspace.failure.request");

  // A code this client cannot read is an unclassified failure, never a success.
  const unclassified = model(facts({ error: "boom", errorCode: "gateway_5xx" }), t);
  assert.equal(unclassified.failureMessageKey, "workspace.failure.unknown");
  assert.equal(unclassified.hasReading, false);

  // Measured rows.
  const ready = model(facts({ rowCount: 2, committedPasses: 1 }), t);
  assert.equal(ready.state, "ready");
  assert.equal(ready.hasReading, true);
  assert.equal(ready.noticeKey, null);

  // The retry control is disabled exactly while an attempt is in flight.
  const idle = model(facts({ error: "boom", errorCode: "request" }), t);
  assert.equal(idle.retry.disabled, false);
  const inFlight = model(
    facts({
      error: "boom",
      errorCode: "request",
      retry: { busy: true, attempts: 1, lastAttemptAtUtc: "2026-09-27T03:04:05.000Z" },
    }),
    t,
  );
  assert.equal(inFlight.retry.busy, true);
  assert.equal(inFlight.retry.disabled, true);
  assert.equal(inFlight.retry.runningKey, "workspace.retry_in_progress");
  assert.equal(inFlight.retry.attempts, 1);

  // Nothing a state carries is backend prose: every string the surface renders is a key.
  for (const surface of [unread, pending, empty, failedWithRows, failedEmpty, ready]) {
    for (const key of [surface.noticeKey, surface.failureEndpointKey, surface.failureMessageKey]) {
      if (key === null) continue;
      assert.equal(typeof en[key], "string", key);
      assert.notEqual(en[key], key, key);
    }
  }
});

test("each state names itself in both locales, and never as another state's copy", () => {
  const keys = [
    "sources.registry.title",
    "sources.registry.unread",
    "sources.registry.pending",
    "sources.registry.failed",
    "sources.registry.failed_withheld",
    "sources.registry.failed_stale",
    "sources.registry.retry",
    "sources.registry.empty",
  ];
  for (const key of keys) {
    assert.equal(typeof en[key], "string", `en ${key}`);
    assert.equal(typeof zh[key], "string", `zh ${key}`);
    assert.ok(en[key].length > 0 && zh[key].length > 0, key);
    assert.notEqual(en[key], zh[key], `${key} is untranslated`);
    assert.equal(zh[key].includes("\ufffd"), false, key);
  }
  // The three states that read as "there is no count" are distinct sentences, so a reader cannot
  // mistake a read that has not answered for a registry that answered with nothing.
  const noCount = ["sources.registry.unread", "sources.registry.pending", "sources.registry.failed"];
  assert.equal(new Set(noCount.map((key) => en[key])).size, noCount.length);
  assert.equal(new Set(noCount.map((key) => zh[key])).size, noCount.length);
  // The failed state explains which of the two things is on screen.
  assert.notEqual(en["sources.registry.failed_withheld"], en["sources.registry.failed_stale"]);
  assert.notEqual(zh["sources.registry.failed_withheld"], zh["sources.registry.failed_stale"]);
  assert.notEqual(zh["sources.registry.empty"], en["sources.registry.empty"]);
});

test("a batch that has not answered is pending, and a measured empty registry is empty", async () => {
  const harness = await loadApiStore();
  const model = await loadModel(harness);
  const store = authenticated(harness);

  assert.equal(surfaceOf(store, model).state, "unread", "a fresh session has read nothing");

  const registry = deferred<unknown>();
  harness.answer("sources", () => registry.promise);
  const batch = store.getState().fetchWorkspace();
  await settle();

  // In flight: the surface states that the read is pending and prints no count at all.
  const pending = surfaceOf(store, model);
  assert.equal(pending.state, "pending");
  assert.equal(pending.hasReading, false);
  assert.deepEqual(store.getState().sources, []);

  registry.resolve({ data: [], meta: {} });
  await batch;
  await settle();

  // The read answered with nothing: a measured zero, which the surface may state as such.
  const empty = surfaceOf(store, model);
  assert.equal(empty.state, "empty");
  assert.equal(empty.hasReading, true);
  assert.equal(empty.noticeKey, null);
  assert.equal(store.getState().endpointErrors.sources, undefined);
});

test("a refused registry read is a failure state, never a measured zero", async () => {
  const harness = await loadApiStore();
  const model = await loadModel(harness);
  const store = authenticated(harness);
  harness.answer("sources", () => Promise.reject(new Error("API 503: source registry unavailable")));

  await store.getState().fetchWorkspace();
  await settle();

  const state = store.getState();
  assert.equal(state.workspaceLoadsCommitted, 1, "the batch committed, its read did not answer");
  assert.match(state.endpointErrors.sources, /API 503/);
  assert.deepEqual(state.sources, [], "a failed read leaves no rows behind");

  const failed = surfaceOf(store, model);
  assert.equal(failed.state, "failed");
  assert.equal(failed.hasReading, false, "no count may be stated for a read that did not answer");
  assert.equal(failed.noticeKey, "sources.registry.failed");
  assert.equal(failed.failureEndpointKey, "workspace.endpoint.sources");
  assert.equal(failed.failureMessageKey, "workspace.failure.request");
  assert.equal(failed.retry.disabled, false);
  assert.notEqual(failed.state, "empty");
  assert.notEqual(failed.state, "unread");
});

test("the scoped retry recovers the read, disabled while its attempt is in flight", async () => {
  const harness = await loadApiStore();
  const model = await loadModel(harness);
  const store = authenticated(harness);
  harness.answer("sources", () => Promise.reject(new Error("API 503: source registry unavailable")));
  await store.getState().fetchWorkspace();
  await settle();
  assert.equal(surfaceOf(store, model).state, "failed");

  // The read the surface is waiting for, answered by the retry pass.
  const recovered = deferred<unknown>();
  harness.answer("sources", () => recovered.promise);
  const retrying = store.getState().retryFailedWorkspaceEndpoints();
  await settle();

  // In flight: the control is disabled, one attempt is counted, and a second caller cannot stack
  // another pass with its own timeout budget.
  assert.equal(store.getState().endpointRetryBusy, true);
  assert.equal(store.getState().endpointRetryAttempts, 1);
  const requestsBefore = harness.calls.filter((call) => call.method === "sources").length;
  await store.getState().retryFailedWorkspaceEndpoints();
  assert.equal(
    harness.calls.filter((call) => call.method === "sources").length,
    requestsBefore,
    "a retry while one is in flight issues no second request",
  );
  const inFlight = surfaceOf(store, model);
  assert.equal(inFlight.state, "failed", "the last answer is still the failure");
  assert.equal(inFlight.retry.disabled, true);

  recovered.resolve({ data: sourceRows(["ENTSOG", "GIE"]), meta: {} });
  await retrying;
  await settle();

  const state = store.getState();
  assert.equal(state.endpointErrors.sources, undefined, "a confirmed success clears the failure");
  assert.equal(state.sources.length, 2);
  assert.equal(state.endpointRetryBusy, false);
  const ready = surfaceOf(store, model);
  assert.equal(ready.state, "ready");
  assert.equal(ready.hasReading, true);
  assert.equal(ready.noticeKey, null);
  assert.equal(ready.retry.disabled, false);
  assert.equal(ready.retry.attempts, 1, "the attempt stays counted for the surface's own copy");
});

test("losing the identity leaves the registry unread, not failed and not empty", async () => {
  const harness = await loadApiStore();
  const model = await loadModel(harness);
  const store = authenticated(harness);
  harness.answer("sources", () => Promise.reject(new Error("API 503: source registry unavailable")));
  await store.getState().fetchWorkspace();
  await settle();
  assert.equal(surfaceOf(store, model).state, "failed");

  // The session is lost mid-read: the reset clears the failure with every other identity-scoped
  // fact, so the surface is a new unread session - it may not keep claiming a failure whose
  // session no longer exists, and it may not become a measured empty registry either.
  harness.answer("sources", () => Promise.reject(new Error("API 401: session expired")));
  await store.getState().fetchWorkspace();
  await settle();

  const state = store.getState();
  assert.equal(state.authState, "unauthenticated");
  assert.deepEqual(state.endpointErrors, {});
  assert.deepEqual(state.sources, []);
  assert.equal(state.workspaceLoadsCommitted, 0);
  const surface = surfaceOf(store, model);
  assert.equal(surface.state, "unread");
  assert.equal(surface.hasReading, false);
  assert.equal(surface.noticeKey, "sources.registry.unread");
  assert.equal(surface.retry.disabled, false, "no retry is in flight for the new session");
});

test("the surface renders the state it was given, and its retry is the store's own path", () => {
  const component = readWebSource("components/SourceCenter.tsx");
  const controller = readWebSource("app/hooks/useSourceCenterController.ts");
  const appController = readWebSource("app/hooks/useAppController.ts");
  const renderer = readWebSource("app/workspaces/WorkspaceRenderer.tsx");

  // One declared state attribute on the surface, driven by the model.
  assert.match(component, /data-source-registry-state=\{registryRead\.state\}/);
  assert.match(component, /data-registry-notice=\{read\.state\}/);
  assert.match(component, /data-source-registry-retry="true"/);
  assert.match(component, /disabled=\{read\.retry\.disabled\}/);
  assert.match(component, /aria-busy=\{read\.retry\.busy\}/);
  assert.match(component, /onClick=\{onRetry\}/);
  // The pending / failed states and the counts exclude each other: a strip is rendered only while
  // a reading exists, and the empty-registry sentence is its own copy.
  assert.match(component, /\{registryRead\.hasReading && \(\s*<MetricStrip/);
  assert.match(component, /\{registryRead\.hasReading \? \(\s*<table/);
  assert.match(component, /sources\.length === 0 \? "sources\.registry\.empty" : "sources\.registry\.no_matches"/);
  assert.equal(component.includes('t("review.no_warnings")'), false);
  // The vocabulary is the shared endpoint taxonomy, not a second one.
  assert.match(component, /read\.failureEndpointKey \?\? "workspace\.endpoint\.unknown"/);
  assert.match(component, /read\.failureMessageKey \?\? "workspace\.failure\.unknown"/);

  // The controller derives the state from the store's own facts through the model.
  assert.match(controller, /sourceRegistryReadSurface\(/);
  assert.match(controller, /retryRegistryRead: \(\) => \{\s*void retryFailedWorkspaceEndpoints\(\);/);
  assert.match(appController, /error: api\.endpointErrors\.sources/);
  assert.match(appController, /retryBusy: api\.endpointRetryBusy/);
  assert.match(appController, /retryFailedWorkspaceEndpoints: api\.retryFailedWorkspaceEndpoints/);
  assert.match(renderer, /registryRead=\{sources\.registryRead\}/);
  assert.match(renderer, /onRegistryRetry=\{sources\.retryRegistryRead\}/);
});
