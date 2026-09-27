/**
 * The capacity operating board's own read state: a joined board cannot tell a refused read from a
 * measured zero, so each state names what the board actually knows.
 *
 * The recorded defect this covers is the board's empty state: `0 / 0` beside "No operating points
 * match the current filters." while the capacity read had not answered
 * (`docs/release/FUNCTIONAL_ACCEPTANCE_REPORT.md`, 2026-09-27 capacity diagnosis). The states are
 * pure (`app/model/capacityOperatingBoardRead.ts`), so they are asserted directly, and the facts
 * they derive from are asserted through the actual store with answers the test settles by hand -
 * the same harness the registry and runtime-loader tests use.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";

import type { EndpointRetryState } from "../src/app/model/endpointFailures.ts";
import type {
  CapacityOperatingBoardReadFacts,
  CapacityOperatingBoardReadSurface,
} from "../src/app/model/capacityOperatingBoardRead.ts";
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
  facts: CapacityOperatingBoardReadFacts,
  t: (key: string, options?: Record<string, unknown>) => string,
) => CapacityOperatingBoardReadSurface;

/** The model, loaded through the harness's own module pipeline (the `@` alias included). */
async function loadModel(harness: ApiStoreHarness): Promise<Model> {
  const module = await harness.load<{ capacityOperatingBoardRead: Model }>(
    "/src/app/model/capacityOperatingBoardRead.ts",
  );
  return module.capacityOperatingBoardRead;
}

/** Put the session past the identity gate, as a resolved sign-in does, and hand the store back. */
function authenticated(harness: ApiStoreHarness) {
  harness.store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  return harness.store;
}

const FLOW_ROW = {
  observation_id: "flow-1",
  point_id: "P1",
  point_name: "Point One",
  direction: "entry",
  flow_mcm_d: 10,
  observed_at_utc: "2026-09-27T03:00:00+00:00",
};

const CAPACITY_ROW = {
  observation_id: "cap-1",
  point_id: "P1",
  point_name: "Point One",
  direction: "entry",
  capacity_type: "Firm Technical",
  capacity_mcm_d: 20,
  observed_at_utc: "2026-09-27T03:00:00+00:00",
};

/** The board the store currently supports, through the same model the cockpit renders. */
function surfaceOf(
  store: ApiStoreHarness["store"],
  model: Model,
  t: (key: string, options?: Record<string, unknown>) => string = translator(en),
): CapacityOperatingBoardReadSurface {
  const state = store.getState();
  return model(
    {
      flows: {
        rows: state.flows.length,
        error: state.endpointErrors.flows,
        errorCode: state.endpointErrorCodes.flows,
      },
      capacity: {
        rows: state.capacity.length,
        error: state.endpointErrors.capacity,
        errorCode: state.endpointErrorCodes.capacity,
      },
      loading: state.workspaceLoading,
      committedPasses: state.workspaceLoadsCommitted,
      retry: {
        busy: state.endpointRetryBusy,
        attempts: state.endpointRetryAttempts,
        lastAttemptAtUtc: state.endpointRetryLastAttemptAtUtc,
      },
    },
    t,
  );
}

test("every state is named, and only a board with both reads may state a count", async () => {
  const harness = await loadApiStore();
  const model = await loadModel(harness);
  const t = translator(en);

  const facts = (
    overrides: Partial<CapacityOperatingBoardReadFacts> = {},
  ): CapacityOperatingBoardReadFacts => ({
    flows: { rows: 0 },
    capacity: { rows: 0 },
    loading: false,
    committedPasses: 0,
    retry: IDLE_RETRY,
    ...overrides,
  });

  // Nothing has been read: no count, and not the measured-empty sentence either.
  const unread = model(facts(), t);
  assert.equal(unread.state, "unread");
  assert.equal(unread.measured, false);
  assert.equal(unread.hasReading, false);
  assert.equal(unread.noticeKey, "capacity.board.unread");
  assert.deepEqual(unread.failedReads, []);
  assert.equal(unread.retry.disabled, false);

  // A pass in flight is pending, not a zero.
  const pending = model(facts({ loading: true }), t);
  assert.equal(pending.state, "pending");
  assert.equal(pending.measured, false);
  assert.equal(pending.hasReading, false);
  assert.equal(pending.noticeKey, "capacity.board.pending");
  assert.notEqual(pending.noticeKey, unread.noticeKey);

  // A pass in flight with rows held from the answered reads: the row set, the counts and the
  // latest-update instant on screen are the last committed reading, and the surface suppresses the
  // pending notice for them (the Source Center's registry notice follows the same rule).
  const pendingWithRows = model(
    facts({ loading: true, committedPasses: 1, flows: { rows: 2 } }),
    t,
  );
  assert.equal(pendingWithRows.state, "pending");
  assert.equal(pendingWithRows.hasReading, true);
  assert.equal(
    pendingWithRows.measured,
    true,
    "both reads answered in the last committed pass; the in-flight pass has not replaced them",
  );

  // Both reads answered with no row: a measurement of zero, which the board may state, and it is
  // not a filter that matched nothing.
  const empty = model(facts({ committedPasses: 1 }), t);
  assert.equal(empty.state, "empty");
  assert.equal(empty.measured, true);
  assert.equal(empty.hasReading, true);
  assert.equal(empty.noticeKey, "capacity.board.empty");

  // Rows from one or both reads: a measured board.
  const ready = model(facts({ committedPasses: 1, capacity: { rows: 3 } }), t);
  assert.equal(ready.state, "ready");
  assert.equal(ready.measured, true);
  assert.equal(ready.noticeKey, null);

  // One refused read with the other read's rows held: a partial board, explicitly incomplete. The
  // failure outranks the rows and the loading flag, and it keeps the shared taxonomy.
  const partial = model(
    facts({
      loading: true,
      committedPasses: 1,
      flows: { rows: 2 },
      capacity: { rows: 0, error: "API 503: unavailable", errorCode: "request" },
    }),
    t,
  );
  assert.equal(partial.state, "partial");
  assert.equal(partial.measured, false, "one read is not a measurement of the joined board");
  assert.equal(partial.hasReading, true, "the answered read's rows stay on screen");
  assert.equal(partial.noticeKey, "capacity.board.partial");
  assert.deepEqual(partial.failedReads, [
    {
      lane: "capacity",
      labelKey: "workspace.endpoint.capacity",
      messageKey: "workspace.failure.request",
    },
  ]);
  // Never the raw loader key, and never the backend's message.
  assert.notEqual(partial.failedReads[0].labelKey, partial.failedReads[0].lane);

  // Both refused with no rows held: failure, and nothing that reads as a count.
  const failed = model(
    facts({
      committedPasses: 1,
      flows: { rows: 0, error: "API 503: unavailable", errorCode: "request" },
      capacity: { rows: 0, error: "Workspace endpoint timed out after 10000ms.", errorCode: "timeout" },
    }),
    t,
  );
  assert.equal(failed.state, "failed");
  assert.equal(failed.measured, false);
  assert.equal(failed.hasReading, false);
  assert.equal(failed.noticeKey, "capacity.board.failed");
  assert.deepEqual(
    failed.failedReads.map((read) => read.lane).sort(),
    ["capacity", "flows"],
  );
  assert.equal(failed.failedReads.find((read) => read.lane === "flows")?.messageKey, "workspace.failure.request");
  assert.equal(failed.failedReads.find((read) => read.lane === "capacity")?.messageKey, "workspace.failure.timeout");

  // A code this client cannot read is an unclassified failure, never a success.
  const unclassified = model(
    facts({ committedPasses: 1, capacity: { error: "boom", errorCode: "gateway_5xx" } }),
    t,
  );
  assert.equal(unclassified.state, "failed");
  assert.equal(unclassified.failedReads[0].messageKey, "workspace.failure.unknown");
  assert.equal(unclassified.hasReading, false);

  // The retry control is disabled exactly while an attempt is in flight.
  const inFlight = model(
    facts({
      committedPasses: 1,
      capacity: { error: "boom", errorCode: "request" },
      retry: { busy: true, attempts: 1, lastAttemptAtUtc: "2026-09-27T03:04:05.000Z" },
    }),
    t,
  );
  assert.equal(inFlight.retry.busy, true);
  assert.equal(inFlight.retry.disabled, true);
  assert.equal(inFlight.retry.runningKey, "workspace.retry_in_progress");
  assert.equal(inFlight.retry.attempts, 1);

  // Nothing a state carries is backend prose: every string the surface renders is a key.
  for (const surface of [unread, pending, pendingWithRows, empty, ready, partial, failed, unclassified]) {
    for (const key of [surface.noticeKey, ...surface.failedReads.flatMap((read) => [read.labelKey, read.messageKey])]) {
      if (key === null) continue;
      assert.equal(typeof en[key], "string", key);
      assert.notEqual(en[key], key, key);
    }
  }
});

test("each state names itself in both locales, and never as another state's copy", () => {
  const keys = [
    "capacity.board.title",
    "capacity.board.unread",
    "capacity.board.pending",
    "capacity.board.failed",
    "capacity.board.partial",
    "capacity.board.empty",
    "capacity.board.retry",
  ];
  for (const key of keys) {
    assert.equal(typeof en[key], "string", `en ${key}`);
    assert.equal(typeof zh[key], "string", `zh ${key}`);
    assert.ok(en[key].length > 0 && zh[key].length > 0, key);
    assert.notEqual(en[key], zh[key], `${key} is untranslated`);
    assert.equal(zh[key].includes("\ufffd"), false, key);
  }
  // The four states that name "there is no count" are distinct sentences, so a reader cannot
  // mistake a read that has not answered for a board that answered with nothing, and the measured
  // empty result is not the filter sentence (`capacity.no_matching_points`).
  const noCount = [
    "capacity.board.unread",
    "capacity.board.pending",
    "capacity.board.failed",
    "capacity.board.partial",
  ];
  assert.equal(new Set(noCount.map((key) => en[key])).size, noCount.length);
  assert.equal(new Set(noCount.map((key) => zh[key])).size, noCount.length);
  assert.notEqual(en["capacity.board.empty"], en["capacity.no_matching_points"]);
  assert.notEqual(zh["capacity.board.empty"], zh["capacity.no_matching_points"]);
  // Neither the measured-empty sentence nor the failure sentence may claim a filter result, and
  // none of the new copy may carry the whole-page heuristic's own words for an empty surface.
  for (const key of [...noCount, "capacity.board.empty"]) {
    assert.doesNotMatch(en[key], /match(es)? the current filters/i, key);
    assert.doesNotMatch(en[key], /\bn\/a\b|unavailable|no records|no data|not (?:available|read|configured)/i, key);
  }
});

test("a pass that has not answered is pending, and a measured empty board is empty", async () => {
  const harness = await loadApiStore();
  const model = await loadModel(harness);
  const store = authenticated(harness);

  assert.equal(surfaceOf(store, model).state, "unread", "a fresh session has read nothing");

  const flows = deferred<unknown>();
  const capacity = deferred<unknown>();
  harness.answer("flowObservations", () => flows.promise);
  harness.answer("capacityObservations", () => capacity.promise);
  const batch = store.getState().fetchWorkspace();
  await settle();

  const pending = surfaceOf(store, model);
  assert.equal(pending.state, "pending");
  assert.equal(pending.hasReading, false);
  assert.equal(pending.measured, false);

  flows.resolve({ data: [], meta: {} });
  capacity.resolve({ data: [], meta: {} });
  await batch;
  await settle();

  const state = store.getState();
  assert.equal(state.endpointErrors.flows, undefined);
  assert.equal(state.endpointErrors.capacity, undefined);
  const empty = surfaceOf(store, model);
  assert.equal(empty.state, "empty");
  assert.equal(empty.measured, true, "both reads answered: a measured zero may be stated");
  assert.equal(empty.noticeKey, "capacity.board.empty");
});

test("one refused read is partial with the other read's rows, never a joined zero", async () => {
  const harness = await loadApiStore();
  const model = await loadModel(harness);
  const store = authenticated(harness);
  harness.answer("flowObservations", () => ({ data: [FLOW_ROW], meta: {} }));
  harness.answer("capacityObservations", () =>
    Promise.reject(new Error("API 503: capacity unavailable")),
  );

  await store.getState().fetchWorkspace();
  await settle();

  const state = store.getState();
  assert.equal(state.workspaceLoadsCommitted, 1, "the batch committed, one read did not answer");
  assert.match(state.endpointErrors.capacity, /API 503/);
  assert.deepEqual(state.capacity, [], "a failed read leaves no rows behind");
  assert.equal(state.flows.length, 1, "the answered read's rows are held");

  const partial = surfaceOf(store, model);
  assert.equal(partial.state, "partial");
  assert.equal(partial.measured, false, "the board may state no KPI from one read");
  assert.equal(partial.hasReading, true, "the rows the answered read holds stay on screen");
  assert.equal(partial.noticeKey, "capacity.board.partial");
  assert.deepEqual(partial.failedReads, [
    {
      lane: "capacity",
      labelKey: "workspace.endpoint.capacity",
      messageKey: "workspace.failure.request",
    },
  ]);
  assert.notEqual(partial.state, "empty");
  assert.notEqual(partial.state, "ready");
  assert.notEqual(partial.state, "unread");
});

test("both reads refused with no rows is a failure, not a board of zero", async () => {
  const harness = await loadApiStore();
  const model = await loadModel(harness);
  const store = authenticated(harness);
  const refused = () => Promise.reject(new Error("API 503: unavailable"));
  harness.answer("flowObservations", refused);
  harness.answer("capacityObservations", refused);

  await store.getState().fetchWorkspace();
  await settle();

  const failed = surfaceOf(store, model);
  assert.equal(failed.state, "failed");
  assert.equal(failed.hasReading, false, "no count may be stated for reads that did not answer");
  assert.equal(failed.measured, false);
  assert.equal(failed.noticeKey, "capacity.board.failed");
  assert.equal(failed.retry.disabled, false);
  assert.notEqual(failed.state, "empty");
});

test("the scoped retry recovers the board, disabled while its attempt is in flight", async () => {
  const harness = await loadApiStore();
  const model = await loadModel(harness);
  const store = authenticated(harness);
  harness.answer("flowObservations", () => ({ data: [FLOW_ROW], meta: {} }));
  harness.answer("capacityObservations", () =>
    Promise.reject(new Error("API 503: capacity unavailable")),
  );
  await store.getState().fetchWorkspace();
  await settle();
  assert.equal(surfaceOf(store, model).state, "partial");

  // The read the board is waiting for, answered by the retry pass.
  const recovered = deferred<unknown>();
  harness.answer("capacityObservations", () => recovered.promise);
  const retrying = store.getState().retryFailedWorkspaceEndpoints();
  await settle();

  // In flight: the control is disabled, one attempt is counted, and a second caller cannot stack
  // another pass with its own timeout budget.
  assert.equal(store.getState().endpointRetryBusy, true);
  assert.equal(store.getState().endpointRetryAttempts, 1);
  const requestsBefore = harness.calls.filter((call) => call.method === "capacityObservations").length;
  await store.getState().retryFailedWorkspaceEndpoints();
  assert.equal(
    harness.calls.filter((call) => call.method === "capacityObservations").length,
    requestsBefore,
    "a retry while one is in flight issues no second request",
  );
  const inFlight = surfaceOf(store, model);
  assert.equal(inFlight.state, "partial", "the last answer is still the failure");
  assert.equal(inFlight.retry.disabled, true);

  recovered.resolve({ data: [CAPACITY_ROW], meta: {} });
  await retrying;
  await settle();

  const state = store.getState();
  assert.equal(state.endpointErrors.capacity, undefined, "a confirmed success clears the failure");
  assert.equal(state.capacity.length, 1);
  assert.equal(state.endpointRetryBusy, false);
  const ready = surfaceOf(store, model);
  assert.equal(ready.state, "ready");
  assert.equal(ready.measured, true);
  assert.equal(ready.noticeKey, null);
  assert.deepEqual(ready.failedReads, []);
  assert.equal(ready.retry.disabled, false);
  assert.equal(ready.retry.attempts, 1, "the attempt stays counted for the surface's own copy");
});

test("losing the identity leaves the board unread, not failed and not empty", async () => {
  const harness = await loadApiStore();
  const model = await loadModel(harness);
  const store = authenticated(harness);
  const refused = () => Promise.reject(new Error("API 503: unavailable"));
  harness.answer("flowObservations", refused);
  harness.answer("capacityObservations", refused);
  await store.getState().fetchWorkspace();
  await settle();
  assert.equal(surfaceOf(store, model).state, "failed");

  // The session is lost mid-read: the reset clears the failure with every other identity-scoped
  // fact, so the board is a new unread session - it may not keep claiming a failure whose session
  // no longer exists, and it may not become a measured empty board either.
  const expired = () => Promise.reject(new Error("API 401: session expired"));
  harness.answer("flowObservations", expired);
  harness.answer("capacityObservations", expired);
  await store.getState().fetchWorkspace();
  await settle();

  const state = store.getState();
  assert.equal(state.authState, "unauthenticated");
  assert.deepEqual(state.endpointErrors, {});
  assert.deepEqual(state.flows, []);
  assert.deepEqual(state.capacity, []);
  assert.equal(state.workspaceLoadsCommitted, 0);
  const surface = surfaceOf(store, model);
  assert.equal(surface.state, "unread");
  assert.equal(surface.hasReading, false);
  assert.equal(surface.noticeKey, "capacity.board.unread");
  assert.equal(surface.retry.disabled, false, "no retry is in flight for the new session");
});

test("the board renders the state it was given, and its retry is the store's own path", () => {
  const component = readWebSource("components/CapacityWorkspace.tsx");
  const cockpit = readWebSource("components/MarketCockpit.tsx");
  const harness = readFileSync(
    new URL("../../../scripts/uat/browser_workflow_smoke.mjs", import.meta.url),
    "utf8",
  );

  // One declared state attribute on the surface, driven by the model's own state.
  assert.match(component, /data-capacity-read-state=\{boardRead\.state\}/);
  assert.match(component, /data-capacity-notice=\{read\.state\}/);
  assert.match(component, /data-capacity-board-retry="true"/);
  assert.match(component, /disabled=\{read\.retry\.disabled\}/);
  assert.match(component, /aria-busy=\{read\.retry\.busy\}/);
  assert.match(component, /onClick=\{onRetry\}/);
  // The KPI strip and the failure notice exclude each other: counts are a measurement of both
  // required reads.
  assert.match(component, /\{boardRead\.measured && \(\s*<div className="capacity-kpi-strip">/);
  // The measured-empty and the filter sentences are separate declared markers, and the filter
  // sentence is only reachable for a fully measured board.
  assert.match(component, /data-empty-state=\{boardEmptyState\.marker\}/);
  assert.match(component, /key: "capacity\.board\.empty", marker: "capacity-operating-points"/);
  assert.match(component, /key: "capacity\.no_matching_points", marker: "capacity-filter-no-match"/);
  assert.match(component, /boardRead\.measured && filtersApplied && filteredRows\.length === 0/);
  // The rows carry their own record id, so a later scoped comparison can name them.
  assert.match(component, /data-record="capacity-point" data-record-id=\{row\.key\}/);
  // The vocabulary is the shared endpoint taxonomy, not a second one.
  assert.match(component, /t\(failedRead\.labelKey\)/);
  assert.match(component, /t\(failedRead\.messageKey\)/);

  // The cockpit derives the board's state from the store's facts through the model, and offers the
  // store's existing bounded retry rather than a fetch path of its own.
  assert.match(cockpit, /capacityOperatingBoardRead\(/);
  assert.match(cockpit, /error: api\.endpointErrors\.capacity/);
  assert.match(cockpit, /errorCode: api\.endpointErrorCodes\.flows/);
  assert.match(cockpit, /committedPasses: api\.workspaceLoadsCommitted/);
  assert.match(cockpit, /onRetryBoardRead=\{\(\) => void api\.retryFailedWorkspaceEndpoints\(\)\}/);

  // The browser check refuses exactly the board's own capacity read and holds it to the pure
  // rules; the joined rows are compared by the sweep's own probe, so no component gains a fetch
  // of its own.
  assert.match(harness, /const CAPACITY_READ_ROUTE = \/\\\/api\\\/physical\\\/capacity\(\\\?\.\*\)\?\$\/;/);
  assert.match(harness, /evaluateRefusedCapacityBoard\(refused\)/);
  assert.match(harness, /evaluateCapacityBoardRecovery\(surface, served\)/);
  assert.equal(component.includes("fetch("), false);
});
