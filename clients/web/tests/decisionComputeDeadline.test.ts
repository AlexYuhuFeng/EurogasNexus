/**
 * The bounded wait on the Decision workspace's two governed computes.
 *
 * The observed defect: an authenticated browser left `Compare Options` pending for minutes and
 * no corresponding POST reached the API access log, while the action's button stayed disabled.
 * Neither the transport call nor the store bounded the wait, so one stalled request could hold
 * the pending lane - and the primary control - for the life of the tab. These tests hold the
 * repair to the contract in `decisionActionModel.ts` and the store: the transport receives an
 * AbortSignal, the deadline releases the pending lane, a late completion commits nothing, no
 * second request is issued by the timeout, and the previous result keeps its provenance.
 *
 * The deadline is the client's own waiting bound. It does not cancel server-side work, and these
 * tests do not claim it does; they use the store's test-only `timeoutMs` override so a run dies
 * in milliseconds rather than in the product's full 30-second window.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";

import { describeFailure, presentError } from "../src/app/experience/errorPresentation.ts";
import { decisionResultContextMismatch } from "../src/app/model/decisionActionModel.ts";
import {
  AUTHENTICATED_AUTH_STATE,
  ClientWaitTimeoutError,
  DEFAULT_DECISION_COMPUTE_TIMEOUT_MS,
  decisionComputeTimeoutMs,
  withAbortTimeout,
} from "../src/stores/workspaceLoading.ts";
import {
  closeApiStoreHarness,
  deferred,
  loadApiStore,
  settle,
  type ApiStoreHarness,
} from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

/** The rendered locale text for a key, falling back to the key itself. */
function localeTranslator(locale: "en" | "zh"): (key: string) => string {
  const messages = JSON.parse(
    readFileSync(new URL(`../src/i18n/${locale}.json`, import.meta.url), "utf8"),
  ) as Record<string, string>;
  return (key) => (typeof messages[key] === "string" ? messages[key] : key);
}

/** An HTTP failure as the real client raises it: message, `detail` and the whole taxonomy body. */
function apiFailure(
  status: number,
  detail: Record<string, unknown>,
  envelope: Record<string, unknown>,
): Error {
  return Object.assign(new Error(`API ${status}: ${String(detail.error ?? "failure")}`), {
    status,
    detail,
    body: { detail, ...envelope },
  });
}

function authenticated(harness: ApiStoreHarness) {
  harness.store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  return harness.store;
}

const requested = (harness: ApiStoreHarness, method: string) =>
  harness.calls.filter((call) => call.method === method).length;

test("the named deadline is finite and an unusable override keeps the named default", () => {
  assert.equal(Number.isFinite(DEFAULT_DECISION_COMPUTE_TIMEOUT_MS), true);
  assert.ok(DEFAULT_DECISION_COMPUTE_TIMEOUT_MS > 0);
  assert.equal(decisionComputeTimeoutMs(), DEFAULT_DECISION_COMPUTE_TIMEOUT_MS);
  assert.equal(decisionComputeTimeoutMs(0), DEFAULT_DECISION_COMPUTE_TIMEOUT_MS);
  assert.equal(decisionComputeTimeoutMs(-5), DEFAULT_DECISION_COMPUTE_TIMEOUT_MS);
  assert.equal(
    decisionComputeTimeoutMs(Number.POSITIVE_INFINITY),
    DEFAULT_DECISION_COMPUTE_TIMEOUT_MS,
  );
  assert.equal(decisionComputeTimeoutMs(25), 25);
});

test("the helper rejects with its typed, stably coded error and aborts the request signal", async () => {
  let aborted = false;
  const call = withAbortTimeout(
    (signal) =>
      new Promise<never>((_, reject) => {
        signal.addEventListener("abort", () => {
          aborted = true;
          reject(new DOMException("aborted", "AbortError"));
        }, { once: true });
      }),
    10,
  );

  // The historical message is kept for the helper's existing callers (the logout path),
  // which only care that the wait ended.
  await assert.rejects(call, /timed out after 10ms/);
  assert.equal(aborted, true);
  await assert.rejects(
    withAbortTimeout(() => new Promise(() => {}), 10),
    (error: unknown) => {
      assert.equal(error instanceof ClientWaitTimeoutError, true);
      assert.equal((error as ClientWaitTimeoutError).code, "CLIENT_WAIT_TIMEOUT");
      assert.equal((error as ClientWaitTimeoutError).timeoutMs, 10);
      return true;
    },
  );
});

test("a stalled Compare Options run is released by the deadline", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const answer = deferred<unknown>();
  let transportSignal: AbortSignal | null = null;
  harness.answer("recommendRouteAllocation", (_request, options) => {
    transportSignal = (options as { signal?: AbortSignal } | undefined)?.signal ?? null;
    return answer.promise;
  });

  await store.getState().recommendRouteAllocation({}, "ctx-a", { timeoutMs: 25 });

  const state = store.getState();
  assert.equal(transportSignal !== null, true, "the transport must receive a signal");
  assert.equal((transportSignal as AbortSignal | null)?.aborted, true, "the deadline aborts it");
  assert.equal(state.routeCompareAction.phase, "failure", "pending is released as a failure");
  assert.equal(state.routeCompareAction.requestContextKey, null);
  assert.equal(state.routeRecommendation, null);
  assert.equal(state.loading, false);
  // The failure stays in the action's own lane; the shared rendered-raw error stays unset.
  assert.equal(state.error, null);
  const text = presentError(localeTranslator("en"), describeFailure(state.routeCompareAction.error));
  assert.equal(text.title, "The wait deadline expired before an answer arrived.");
  assert.equal(text.correlationId, null);
  assert.equal(String(text.title).includes("CLIENT_WAIT_TIMEOUT"), false, "no raw code is rendered");
  assert.equal(String(text.cause).includes("ClientWaitTimeoutError"), false, "no raw exception text");
});

test("the expired deadline is explained honestly in both locales", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("recommendRouteAllocation", () => new Promise(() => {}));

  await store.getState().recommendRouteAllocation({}, "ctx-a", { timeoutMs: 25 });

  const failure = store.getState().routeCompareAction.error;
  // The store's module copy of the class is loaded by a separate pipeline, so the stable code -
  // not `instanceof` across that boundary - is what proves the typed error arrived.
  assert.equal((failure as { code?: string }).code, "CLIENT_WAIT_TIMEOUT");

  const english = presentError(localeTranslator("en"), describeFailure(failure));
  assert.equal(english.title, "The wait deadline expired before an answer arrived.");
  assert.equal(english.cause.includes("stopped waiting"), true);
  assert.equal(english.cause.includes("cannot confirm whether the backend is still working"), true);
  assert.equal(english.action.includes("No retry was sent automatically"), true);
  assert.equal(english.action.includes("unchanged"), true);
  assert.equal(english.action.includes("server may still be working"), true);
  assert.match(english.impact, /previous|unaffected|untouched|keeps? (their|its)/i);
  assert.equal(english.title.includes("cancelled"), false);
  assert.equal(english.action.includes("cancelled"), false);
  assert.equal(english.correlationId, null);

  const chinese = presentError(localeTranslator("zh"), describeFailure(failure));
  assert.equal(chinese.title, "等待期限已过，仍未收到应答。");
  assert.equal(chinese.title.length > 0 && chinese.impact.length > 0, true);
  assert.equal(chinese.cause.includes("停止等待"), true);
  assert.equal(chinese.cause.includes("无法确认后端是否仍在工作"), true);
  assert.equal(chinese.action.includes("未自动发送重试"), true);
  assert.equal(chinese.action.includes("保持不变"), true);
  assert.equal(chinese.action.includes("服务器可能仍在处理"), true);
  assert.match(chinese.impact, /保留|不受影响|未受影响/);
  assert.equal(chinese.title.includes("取消"), false);
  assert.equal(chinese.action.includes("取消"), false);
  assert.equal(chinese.correlationId, null);

  for (const [locale, text] of [["en", english], ["zh", chinese]] as const) {
    for (const [field, value] of Object.entries(text)) {
      if (field === "correlationId") continue;
      assert.ok(String(value).trim(), `${locale}.${field}`);
      assert.doesNotMatch(String(value), /^errors\./, `${locale}.${field}`);
    }
  }
});

test("a late answer after the deadline commits nothing and issues no retry", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const answer = deferred<unknown>();
  // The transport is handed a signal but ignores it, which is exactly the hostile case the
  // helper's race still bounds: the client stops waiting either way.
  harness.answer("recommendRouteAllocation", () => answer.promise);

  await store.getState().recommendRouteAllocation({}, "ctx-a", { timeoutMs: 25 });
  assert.equal(store.getState().routeCompareAction.phase, "failure");
  assert.equal(requested(harness, "recommendRouteAllocation"), 1);

  // The answer arrives after the run was already decided. It is discarded: no result, no
  // provenance, and no second request is issued on the timeout's behalf.
  answer.resolve({ data: { status: "SUCCESS", allocations: [{ route_id: "late" }] }, meta: {} });
  await settle();

  const state = store.getState();
  assert.equal(state.routeRecommendation, null);
  assert.equal(state.routeCompareAction.phase, "failure");
  assert.equal(state.routeCompareAction.resultContextKey, null);
  assert.equal(requested(harness, "recommendRouteAllocation"), 1);
});

test("the deadline preserves the previous Optimize result and its provenance", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("optimizeResourcePool", () => ({
    data: { status: "OPTIMAL", allocations: [{ option_id: "route-1" }] },
    meta: {},
  }));
  await store.getState().optimizeResourcePool({ objective: "min_cost" }, "ctx-a");
  await settle();
  const prior = store.getState().resourcePoolResult;

  // The caller moves to another context and retries; the retry never answers.
  harness.answer("optimizeResourcePool", () => new Promise(() => {}));
  await store.getState().optimizeResourcePool({ objective: "min_cost" }, "ctx-b", {
    timeoutMs: 25,
  });

  const state = store.getState();
  assert.equal(state.resourcePoolResult, prior, "the earlier result is kept, not replaced");
  assert.equal(state.poolOptimizeAction.phase, "failure");
  assert.equal(state.poolOptimizeAction.resultContextKey, "ctx-a");
  assert.equal(
    decisionResultContextMismatch(state.poolOptimizeAction, state.resourcePoolResult !== null, "ctx-b"),
    true,
    "the kept result must read stale for the context the caller moved to",
  );
  assert.equal(requested(harness, "optimizeResourcePool"), 2, "one retry, one request");
});

test("a structured API failure is still handed to the presentation unchanged", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("recommendRouteAllocation", () =>
    Promise.reject(
      apiFailure(
        422,
        { error: "validation_failed", message: "The submitted input did not pass validation." },
        {
          error: "validation_failed",
          family: "VALIDATION",
          severity: "warning",
          recoverability: "after_user_action",
          message_key: "errors.validation_failed.message",
          action_key: "errors.validation_failed.action",
          correlation_id: "corr-validation",
        },
      ),
    ),
  );

  await store.getState().recommendRouteAllocation({}, "ctx-a", { timeoutMs: 25 });

  const failure = store.getState().routeCompareAction.error;
  assert.equal((failure as { code?: string }).code, undefined, "a server answer is not a timeout");
  const t = localeTranslator("en");
  const text = presentError(t, describeFailure(failure));
  assert.equal(text.title, t("errors.validation_failed.message"));
  assert.equal(text.cause, t("errors.family.VALIDATION.cause"));
  assert.equal(text.action, t("errors.validation_failed.action"));
  assert.equal(text.correlationId, "corr-validation");
  assert.equal(store.getState().routeCompareAction.correlationId, "corr-validation");
  assert.equal(text.title.includes("deadline"), false);
});

test("an identity change during the timeout publishes no failure for the new session", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("recommendRouteAllocation", () => new Promise(() => {}));

  const run = store.getState().recommendRouteAllocation({}, "ctx-a", { timeoutMs: 25 });
  await settle();
  assert.equal(store.getState().routeCompareAction.phase, "pending");

  // The session is invalidated while the run is in flight; the identity reset drops the lane.
  harness.answer("me", () => Promise.reject(new Error("API 401: unauthenticated")));
  await store.getState().fetchMe();
  await settle();

  await run;
  const state = store.getState();
  assert.equal(state.authState, "unauthenticated");
  assert.equal(state.routeCompareAction.phase, "idle");
  assert.equal(state.routeCompareAction.error, null);
  assert.equal(state.routeCompareAction.correlationId, null);
  assert.equal(state.routeRecommendation, null);
  assert.equal(state.error, null);
  assert.equal(state.loading, false);
});

test("a manual retry succeeds while the earlier request resolves late", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const first = deferred<unknown>();
  const second = deferred<unknown>();
  let calls = 0;
  harness.answer("recommendRouteAllocation", () => {
    calls += 1;
    return calls === 1 ? first.promise : second.promise;
  });

  await store.getState().recommendRouteAllocation({}, "ctx-a", { timeoutMs: 25 });
  assert.equal(store.getState().routeCompareAction.phase, "failure");

  // The user's own retry: same action, same context, the product deadline.
  const retry = store.getState().recommendRouteAllocation({}, "ctx-a");
  await settle();
  second.resolve({ data: { status: "SUCCESS", allocations: [{ route_id: "current" }] }, meta: {} });
  await retry;
  await settle();

  // The timed-out request answers after the retry committed; it must not overwrite that result.
  first.resolve({ data: { status: "SUCCESS", allocations: [{ route_id: "late" }] }, meta: {} });
  await settle();

  const state = store.getState();
  assert.equal(calls, 2, "the timeout issued no request of its own");
  assert.deepEqual(state.routeRecommendation, {
    status: "SUCCESS",
    allocations: [{ route_id: "current" }],
  });
  assert.equal(state.routeCompareAction.phase, "success");
  assert.equal(state.routeCompareAction.resultContextKey, "ctx-a");
  assert.equal(state.loading, false);
});
