/**
 * The Decision workspace's two governed computes: gate, lifecycle and result provenance.
 *
 * The observed defect: an ADMIN session - a platform administrator, which the backend refuses
 * for commercial data - saw `Compare Options` enabled, clicking it produced a 403 no surface
 * showed, and an automatic pool-optimiser run was issued on the identity's behalf and refused
 * server-side. Two further lifecycle defects were found while tracing it: the result's context
 * key was stamped when a run *started* (so a failed retry after a context change made the old
 * result read as current), and one shared key served both actions (so a route comparison could
 * relabel a pool result).
 *
 * These tests hold the repair to the contract in `app/model/decisionActionModel.ts`: capability
 * plus inputs for the gate, `idle -> pending -> success | failure` per action, provenance
 * stamped only by a successful run, and the surface-level wiring that renders them. The
 * store-level cases run the real store through the harness, with the HTTP boundary mocked and
 * every answer settled by hand - source assertions alone could not show that a stale completion
 * writes nothing or that a second submission issues no second request.
 *
 * The follow-up extends the stamp from the trading context to the caller-known input identity
 * (`app/model/decisionResultProvenance.ts`; see `decisionResultProvenance.test.ts` for the
 * canonicalisation and request-builder cases): a completion that lands after a saved contract
 * revision, pool/market read or financing input changed commits under the request-time key and
 * reads stale for the inputs now on screen, and every consumer reads the model's gated values
 * rather than the raw lanes. The store-level cases also hold the strategy evaluation to its
 * identity generation: an answer that lands after a session invalidation commits nothing -
 * result, metadata, error, loading or follow-up reads - and reports no answer, so the caller
 * stamps no provenance for it.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";

import {
  DECISION_COMPUTE_ACTION_CAPABILITY,
  IDLE_DECISION_ACTION_STATE,
  decisionActionAvailable,
  decisionActionFailed,
  decisionActionPending,
  decisionActionSucceeded,
  decisionComputeGate,
  decisionResultContextMismatch,
} from "../src/app/model/decisionActionModel.ts";
import { describeFailure, presentError } from "../src/app/experience/errorPresentation.ts";
import { ADMINISTRATION_CAPABILITIES } from "../src/app/experience/experienceProfile.ts";
import { AUTHENTICATED_AUTH_STATE } from "../src/stores/workspaceLoading.ts";
import {
  closeApiStoreHarness,
  deferred,
  loadApiStore,
  settle,
  type ApiStoreHarness,
} from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

/** The product's own English wording, so a presented failure is checked against real copy. */
function englishTranslator(): (key: string) => string {
  const messages = JSON.parse(
    readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8"),
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

function commercialAccessDenial(): Error {
  const detail = {
    error: "commercial_access_not_granted",
    message: "This path serves commercial data, which platform administration does not grant.",
    capabilities_required: ["market.read", "portfolio.read"],
  };
  return apiFailure(403, detail, {
    error: "commercial_access_not_granted",
    family: "ENTITLEMENT",
    severity: "error",
    recoverability: "after_user_action",
    message_key: "errors.commercial_access_not_granted.message",
    action_key: "errors.commercial_access_not_granted.action",
    correlation_id: "corr-commercial-403",
  });
}

function authenticated(harness: ApiStoreHarness) {
  harness.store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  return harness.store;
}

const requested = (harness: ApiStoreHarness, method: string) =>
  harness.calls.filter((call) => call.method === method).length;

test("the gate needs a declared capability as well as ready inputs, and fails closed without a profile", () => {
  // A platform administrator's declared composition: administration capabilities only. The
  // backend refuses these paths for that identity, so the action must not be offered.
  const adminGate = decisionComputeGate("optimize_pool", {
    profileAvailable: true,
    capabilities: [...ADMINISTRATION_CAPABILITIES, "runtime.read", "provider.connection.view"],
    inputReady: true,
  });
  assert.equal(adminGate.canRun, false);
  assert.equal(adminGate.blockerKey, "decision.action.blocker_capability");
  assert.equal(decisionActionAvailable(adminGate, IDLE_DECISION_ACTION_STATE), false);
  // The automatic pool run's first condition is this same rule, so an administrator is never
  // sent an optimiser request on its own behalf (asserted at the call site below as well).

  // No profile at all is not permission: it withholds the run until the composition is known.
  const unknownIdentity = decisionComputeGate("compare_routes", {
    profileAvailable: false,
    capabilities: [],
    inputReady: true,
  });
  assert.equal(unknownIdentity.canRun, false);
  assert.equal(unknownIdentity.blockerKey, "decision.action.blocker_identity");

  // Declared capability without the action's inputs is still blocked, and says so.
  const inputsMissing = decisionComputeGate("compare_routes", {
    profileAvailable: true,
    capabilities: ["optimization.run"],
    inputReady: false,
  });
  assert.equal(inputsMissing.canRun, false);
  assert.equal(inputsMissing.blockerKey, "decision.action.blocker_inputs");

  // Capability and inputs together open the gate for both acts.
  for (const action of ["optimize_pool", "compare_routes"] as const) {
    const open = decisionComputeGate(action, {
      profileAvailable: true,
      capabilities: [DECISION_COMPUTE_ACTION_CAPABILITY[action], "portfolio.read"],
      inputReady: true,
    });
    assert.deepEqual(open, { canRun: true, blockerKey: null });
    assert.equal(decisionActionAvailable(open, IDLE_DECISION_ACTION_STATE), true);
  }

  // The capability the gate names is a commercial capability, never an administration one.
  assert.equal(DECISION_COMPUTE_ACTION_CAPABILITY.optimize_pool, "optimization.run");
  assert.equal(
    ADMINISTRATION_CAPABILITIES.includes(DECISION_COMPUTE_ACTION_CAPABILITY.optimize_pool),
    false,
    "the gate must not be satisfiable by platform administration",
  );
});

test("an action with a run in flight cannot be started again", () => {
  const gate = decisionComputeGate("optimize_pool", {
    profileAvailable: true,
    capabilities: ["optimization.run"],
    inputReady: true,
  });
  const pending = decisionActionPending(IDLE_DECISION_ACTION_STATE, "ctx-a");
  assert.equal(pending.phase, "pending");
  assert.equal(pending.requestContextKey, "ctx-a");
  assert.equal(decisionActionAvailable(gate, pending), false);
});

test("provenance is stamped by the successful request, and a failed retry cannot relabel a prior result", () => {
  const succeeded = decisionActionSucceeded(
    decisionActionPending(IDLE_DECISION_ACTION_STATE, "ctx-a"),
    "ctx-a",
  );
  assert.equal(succeeded.phase, "success");
  assert.equal(succeeded.resultContextKey, "ctx-a");
  assert.equal(decisionResultContextMismatch(succeeded, true, "ctx-a"), false);
  assert.equal(decisionResultContextMismatch(succeeded, true, "ctx-b"), true);

  // The defect: a retry started under ctx-b stamped ctx-b before the request, so a refusal
  // erased the context change and the ctx-a payload read as current.
  const retried = decisionActionPending(succeeded, "ctx-b");
  const failed = decisionActionFailed(retried, new Error("API 503: downstream refused"), "corr-1");
  assert.equal(failed.phase, "failure");
  assert.equal(failed.resultContextKey, "ctx-a");
  assert.equal(failed.requestContextKey, null);
  assert.equal(failed.correlationId, "corr-1");
  assert.equal(
    decisionResultContextMismatch(failed, true, "ctx-b"),
    true,
    "the prior result stays stale for the context the user moved to",
  );

  // A payload whose provenance the client cannot vouch for is stale, not current.
  assert.equal(decisionResultContextMismatch(IDLE_DECISION_ACTION_STATE, true, "ctx-a"), true);
  // The same holds when the caller's current inputs cannot compose a key at all (for example
  // the financing input became unknown): nothing can be vouched for, so the payload is stale.
  assert.equal(decisionResultContextMismatch(succeeded, true, null), true);
  // No payload at all is not a mismatch: there is nothing to mislabel.
  assert.equal(decisionResultContextMismatch(failed, false, "ctx-b"), false);
});

test("an allowed run succeeds, stamps its provenance and reports success", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("optimizeResourcePool", () => ({
    data: { status: "OPTIMAL", allocations: [] },
    meta: {},
  }));

  await store.getState().optimizeResourcePool({ objective: "min_cost" }, "ctx-a");
  await settle();

  const state = store.getState();
  assert.equal(state.poolOptimizeAction.phase, "success");
  assert.equal(state.poolOptimizeAction.resultContextKey, "ctx-a");
  assert.equal(state.poolOptimizeAction.error, null);
  assert.deepEqual(state.resourcePoolResult, { status: "OPTIMAL", allocations: [] });
  assert.equal(state.loading, false);
});

test("a commercial refusal keeps the structured failure and its correlation id for the surface", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("optimizeResourcePool", () => Promise.reject(commercialAccessDenial()));

  await store.getState().optimizeResourcePool({ objective: "min_cost" }, "ctx-a");
  await settle();

  const state = store.getState();
  assert.equal(state.poolOptimizeAction.phase, "failure");
  assert.equal(state.poolOptimizeAction.correlationId, "corr-commercial-403");
  assert.equal(state.resourcePoolResult, null);
  assert.equal(state.loading, false);
  // The refusal is not written into the shared, rendered-raw error string: the map's catch-all
  // alert would otherwise print the exception text, and the refusal belongs with the action.
  assert.equal(state.error, null);

  const t = englishTranslator();
  const text = presentError(t, describeFailure(state.poolOptimizeAction.error));
  assert.equal(text.title, t("errors.commercial_access_not_granted.message"));
  assert.equal(text.action, t("errors.commercial_access_not_granted.action"));
  assert.equal(text.cause, t("errors.cause.administration_is_not_commercial"));
  assert.equal(text.correlationId, "corr-commercial-403");
  // The refusal is explained; the raw exception string is never the user-facing text.
  assert.equal(text.title.includes("API 403"), false);
  assert.equal(text.action.includes("API 403"), false);
});

test("a validation refusal and a transport failure are both classified, never raw", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const t = englishTranslator();

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
  await store.getState().recommendRouteAllocation({}, "ctx-a");
  await settle();
  const validation = presentError(t, describeFailure(store.getState().routeCompareAction.error));
  assert.equal(validation.title, t("errors.validation_failed.message"));
  assert.equal(validation.correlationId, "corr-validation");
  assert.equal(validation.title.includes("API 422"), false);

  // A transport failure has no server body: it reads as the taxonomy's generic system problem
  // rather than exposing the exception text (which can carry host and query detail).
  harness.answer("recommendRouteAllocation", () => Promise.reject(new Error("Failed to fetch")));
  await store.getState().recommendRouteAllocation({}, "ctx-a");
  await settle();
  const transport = presentError(t, describeFailure(store.getState().routeCompareAction.error));
  assert.equal(transport.title, t("errors.unclassified.message"));
  assert.equal(transport.title.includes("Failed to fetch"), false);
});

test("a second submission while one run is in flight issues no second request", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const answer = deferred<unknown>();
  harness.answer("optimizeResourcePool", () => answer.promise);

  const first = store.getState().optimizeResourcePool({ objective: "min_cost" }, "ctx-a");
  await settle();
  await store.getState().optimizeResourcePool({ objective: "min_cost" }, "ctx-a");
  await settle();

  assert.equal(requested(harness, "optimizeResourcePool"), 1, "one click, one request");
  assert.equal(store.getState().poolOptimizeAction.phase, "pending");

  answer.resolve({ data: { status: "OPTIMAL" }, meta: {} });
  await first;
  await settle();
  assert.equal(store.getState().poolOptimizeAction.phase, "success");
  assert.equal(requested(harness, "optimizeResourcePool"), 1);
});

test("a prior result survives a context change and a failed retry as the stale payload it is", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("optimizeResourcePool", () => ({
    data: { status: "OPTIMAL", allocations: [{ option_id: "route-1" }] },
    meta: {},
  }));
  await store.getState().optimizeResourcePool({ objective: "min_cost" }, "ctx-a");
  await settle();
  const prior = store.getState().resourcePoolResult;

  // The caller moves to another trading context and retries; the retry is refused.
  harness.answer("optimizeResourcePool", () => Promise.reject(commercialAccessDenial()));
  await store.getState().optimizeResourcePool({ objective: "min_cost" }, "ctx-b");
  await settle();

  const state = store.getState();
  assert.equal(state.resourcePoolResult, prior, "the earlier result is kept, not replaced");
  assert.equal(state.poolOptimizeAction.phase, "failure");
  assert.equal(state.poolOptimizeAction.resultContextKey, "ctx-a");
  assert.equal(
    decisionResultContextMismatch(state.poolOptimizeAction, state.resourcePoolResult !== null, "ctx-b"),
    true,
    "the kept result must read stale for the context the caller moved to",
  );
});

test("concurrent compare and optimize keep separate provenance, and one completes without touching the other", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const compare = deferred<unknown>();
  const optimize = deferred<unknown>();
  harness.answer("recommendRouteAllocation", () => compare.promise);
  harness.answer("optimizeResourcePool", () => optimize.promise);

  const compareRun = store.getState().recommendRouteAllocation({}, "ctx-compare");
  const optimizeRun = store.getState().optimizeResourcePool({ objective: "min_cost" }, "ctx-pool");
  await settle();
  assert.equal(store.getState().routeCompareAction.phase, "pending");
  assert.equal(store.getState().poolOptimizeAction.phase, "pending");

  compare.resolve({ data: { status: "SUCCESS", allocations: [] }, meta: {} });
  await compareRun;
  await settle();
  assert.equal(store.getState().routeCompareAction.resultContextKey, "ctx-compare");
  assert.equal(
    store.getState().poolOptimizeAction.resultContextKey,
    null,
    "the comparison must not stamp the pool result's provenance",
  );
  assert.equal(store.getState().resourcePoolResult, null);

  optimize.resolve({ data: { status: "OPTIMAL", allocations: [] }, meta: {} });
  await optimizeRun;
  await settle();
  assert.equal(store.getState().poolOptimizeAction.resultContextKey, "ctx-pool");
  assert.equal(
    store.getState().routeCompareAction.resultContextKey,
    "ctx-compare",
    "the pool run must not relabel the comparison's result",
  );
});

test("a completion that lands after the context changed is stamped with the context it was requested under", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const answer = deferred<unknown>();
  harness.answer("optimizeResourcePool", () => answer.promise);

  const run = store.getState().optimizeResourcePool({ objective: "min_cost" }, "ctx-a");
  await settle();
  // The caller moves to another trading context while the run is still in flight, then the
  // answer lands. It is committed (the run did happen) but provenanced to the context it was
  // computed for, so the surface reports it stale for the context on screen.
  store.setState({
    tradingContext: { gasDay: "2026-10-02", deliveryProduct: "day-ahead", hubId: "TTF" },
  });
  answer.resolve({ data: { status: "OPTIMAL", allocations: [] }, meta: {} });
  await run;
  await settle();

  const state = store.getState();
  assert.equal(state.poolOptimizeAction.phase, "success");
  assert.equal(state.poolOptimizeAction.resultContextKey, "ctx-a");
  assert.equal(decisionResultContextMismatch(state.poolOptimizeAction, true, "ctx-a"), false);
  assert.equal(decisionResultContextMismatch(state.poolOptimizeAction, true, "ctx-b"), true);
});

test("a completion that lands after the inputs changed is stamped with the inputs it was sent with", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const answer = deferred<unknown>();
  harness.answer("optimizeResourcePool", () => answer.promise);

  // The same trading context, two input identities: the caller edits a saved contract revision
  // (or the pool read refreshes) while the run is in flight.
  const keyBefore = "optimize_pool::2026-10-01|day-ahead|NBP::request-a";
  const keyAfter = "optimize_pool::2026-10-01|day-ahead|NBP::request-b";
  const run = store.getState().optimizeResourcePool({ objective: "min_cost" }, keyBefore);
  await settle();
  answer.resolve({ data: { status: "OPTIMAL", allocations: [{ option_id: "route-1" }] }, meta: {} });
  await run;
  await settle();

  const state = store.getState();
  assert.equal(state.poolOptimizeAction.phase, "success");
  assert.equal(
    state.poolOptimizeAction.resultContextKey,
    keyBefore,
    "the committed run keeps the request-time inputs, not whatever replaced them",
  );
  assert.equal(
    decisionResultContextMismatch(state.poolOptimizeAction, state.resourcePoolResult !== null, keyBefore),
    false,
  );
  assert.equal(
    decisionResultContextMismatch(state.poolOptimizeAction, state.resourcePoolResult !== null, keyAfter),
    true,
    "the landed result must read stale for the inputs the caller now knows",
  );
});

test("a completion that lands after the identity changed writes no result and no provenance", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const answer = deferred<unknown>();
  harness.answer("optimizeResourcePool", () => answer.promise);

  const run = store.getState().optimizeResourcePool({ objective: "min_cost" }, "ctx-a");
  await settle();
  assert.equal(store.getState().poolOptimizeAction.phase, "pending");

  // The session is invalidated while the run is in flight: the identity reset drops the lane.
  harness.answer("me", () => Promise.reject(new Error("API 401: unauthenticated")));
  await store.getState().fetchMe();
  await settle();
  assert.equal(store.getState().poolOptimizeAction.phase, "idle");
  assert.equal(store.getState().loading, false);

  answer.resolve({ data: { status: "OPTIMAL", allocations: [] }, meta: {} });
  await run;
  await settle();

  const state = store.getState();
  assert.equal(state.resourcePoolResult, null, "a superseded identity's result is dropped");
  assert.equal(state.poolOptimizeAction.phase, "idle");
  assert.equal(state.poolOptimizeAction.resultContextKey, null);
});

test("a strategy evaluation that succeeds after the identity changed commits nothing and starts no follow-up", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const answer = deferred<unknown>();
  harness.answer("evaluateStrategyLab", () => answer.promise);

  const run = store.getState().evaluateStrategyLab({ scenario_id: "scenario-a" });
  await settle();
  assert.equal(requested(harness, "evaluateStrategyLab"), 1, "the evaluation is in flight");
  assert.equal(store.getState().loading, true, "the run holds the shared busy flag");

  // The session is invalidated while the evaluation is still in flight.
  harness.answer("me", () => Promise.reject(new Error("API 401: unauthenticated")));
  await store.getState().fetchMe();
  await settle();

  answer.resolve({ data: { status: "OK", allocation_targets: [] }, meta: { source: "evaluation" } });
  assert.equal(await run, null, "a superseded identity's evaluation reports no answer");
  await settle();

  const state = store.getState();
  assert.equal(state.strategyResult, null, "the stale result is not committed");
  assert.equal(state.meta, null, "its metadata is not committed either");
  assert.equal(state.error, null, "nor is the shared error");
  assert.equal(state.loading, false, "nor is the busy flag");
  assert.equal(requested(harness, "strategySummary"), 0, "no summary follow-up for a dropped answer");
  assert.equal(requested(harness, "strategyRuns"), 0, "no runs follow-up either");
});

test("a strategy evaluation that fails after the identity changed records no error", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const answer = deferred<unknown>();
  harness.answer("evaluateStrategyLab", () => answer.promise);

  const run = store.getState().evaluateStrategyLab({ scenario_id: "scenario-a" });
  await settle();

  harness.answer("me", () => Promise.reject(new Error("API 401: unauthenticated")));
  await store.getState().fetchMe();
  await settle();

  answer.reject(new Error("API 500: strategy evaluation failed"));
  assert.equal(await run, null, "a superseded identity's failure reports no answer");
  await settle();

  const state = store.getState();
  assert.equal(state.error, null, "the stale failure is not written");
  assert.equal(state.loading, false);
  assert.equal(state.strategyResult, null);
  assert.equal(requested(harness, "strategySummary"), 0);
  assert.equal(requested(harness, "strategyRuns"), 0);
});

test("a strategy evaluation for the current identity commits its result and launches the follow-ups", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const result = { status: "OK", allocation_targets: [{ resource_id: "resource-1" }] };
  harness.answer("evaluateStrategyLab", () => ({
    data: result,
    meta: { source_references: ["strategy-run-1"] },
  }));
  harness.answer("strategySummary", () => ({ data: { cumulative_pnl_gbp: 12.5 }, meta: {} }));
  harness.answer("strategyRuns", () => ({ data: [{ run_id: "strategy-run-1" }], meta: {} }));

  assert.deepEqual(
    await store.getState().evaluateStrategyLab({ scenario_id: "scenario-a" }),
    result,
  );
  await settle();

  const state = store.getState();
  assert.deepEqual(state.strategyResult, result);
  assert.deepEqual(state.meta, { source_references: ["strategy-run-1"] });
  assert.deepEqual(state.strategySummary, { cumulative_pnl_gbp: 12.5 });
  assert.deepEqual(state.strategyRuns, [{ run_id: "strategy-run-1" }]);
  assert.equal(state.loading, false);
  assert.equal(state.error, null);
  assert.equal(requested(harness, "strategySummary"), 1);
  assert.equal(requested(harness, "strategyRuns"), 1);
});

test("the automatic pool run is issued only through the gated, provenance-carrying path", () => {
  const model = readWebSource("app/model/usePortfolioDecisionModel.ts");

  // One readiness rule for the auto-run and the header action, derived from the declared
  // capability and the action's own state.
  assert.match(
    model,
    /const canRunPoolOptimizer = decisionActionAvailable\(poolOptimizeGate, api\.poolOptimizeAction\);/,
  );
  // The auto-run is additionally refused while the draft/saved financing rate is unknown (no
  // composed request exists), or while the inputs cannot compose a provenance key: it never
  // issues a run with an invented rate or an unlabelled provenance.
  assert.match(
    model,
    /if \(!canRunPoolOptimizer \|\| api\.loading \|\| resourcePoolOptimizationRequest === null\) return;/,
  );
  assert.match(model, /if \(optimizerProvenanceKey === null\) return;/);
  assert.match(model, /const canCompareRoutes = decisionActionAvailable\(routeCompareGate, api\.routeCompareAction\);/);
  // Both call sites carry the per-action provenance key - trading context plus the canonical
  // input identity of the request being sent (`app/model/decisionResultProvenance.ts`) - and
  // neither stamps a key before the request: the provenance is the store's, written only when a
  // run succeeds.
  assert.match(
    model,
    /const optimizerProvenanceKey = useMemo\([\s\S]*?"optimize_pool",\s*currentContextKey,\s*decisionInputIdentity\(\{/,
  );
  assert.match(
    model,
    /const compareProvenanceKey = useMemo\([\s\S]*?"compare_routes",[\s\S]*?decisionInputIdentity\(\{/,
  );
  assert.equal(
    (model.match(/savedContracts: api\.upstreamContracts/g) ?? []).length,
    4,
    "both governed actions and both strategy call sites bind the saved-contract revision",
  );
  assert.equal(
    (model.match(/api\.optimizeResourcePool\(resourcePoolOptimizationRequest, optimizerProvenanceKey\)/g) ?? [])
      .length,
    2,
    "the automatic run and the header action are the only callers",
  );
  assert.match(model, /api\.recommendRouteAllocation\(routeRecommendationRequest, compareProvenanceKey\)/);
  assert.equal(model.includes("setOptimizerResultContextKey"), false);
  // The gate handlers refuse to start an unavailable action at all.
  assert.match(
    model,
    /function optimizeResourcePoolForCurrentContext\(\) \{\s*\/\/[\s\S]*?\s*if \(!canRunPoolOptimizer \|\| resourcePoolOptimizationRequest === null\) return;\s*if \(optimizerProvenanceKey === null\) return;/,
  );
  assert.match(
    model,
    /function recommendRouteAllocationForCurrentContext\(\) \{\s*if \(!canCompareRoutes\) return;/,
  );
  // The strategy evaluation stamps its own provenance key only after a successful answer, built
  // from the payload actually sent: a failure cannot relabel the previous strategy result.
  assert.match(model, /const payload = strategyEvaluationPayload\(overrides\);/);
  assert.match(model, /if \(completed\) setStrategyResultContextKey\(provenanceKey\);/);
  assert.equal(model.includes("setStrategyResultContextKey(currentContextKey)"), false);
});

test("the store writes provenance only on a successful response", () => {
  const store = readWebSource("stores/api.ts");

  assert.match(
    store,
    /recommendRouteAllocation: async \(request, provenanceKey, options\) => \{[\s\S]*?if \(get\(\)\.routeCompareAction\.phase === "pending"\) return;[\s\S]*?routeCompareAction: decisionActionPending\(state\.routeCompareAction, provenanceKey\)/,
  );
  // The awaited request runs under the bounded client deadline and receives its signal, while the
  // provenance is still stamped only after that answer: a timeout cannot relabel a prior result.
  assert.match(
    store,
    /const result = await withAbortTimeout\(\s*\(signal\) => api\.recommendRouteAllocation\(request, \{ signal \}\),\s*decisionComputeTimeoutMs\(options\?\.timeoutMs\),\s*\);[\s\S]{0,300}?routeCompareAction: decisionActionSucceeded\(state\.routeCompareAction, provenanceKey\)/,
  );
  assert.match(
    store,
    /const result = await withAbortTimeout\(\s*\(signal\) => api\.optimizeResourcePool\(withoutLegacyFlag\(request\), \{ signal \}\),\s*decisionComputeTimeoutMs\(options\?\.timeoutMs\),\s*\);[\s\S]{0,300}?poolOptimizeAction: decisionActionSucceeded\(state\.poolOptimizeAction, provenanceKey\)/,
  );
  assert.match(store, /poolOptimizeAction: decisionActionFailed\(\s*state\.poolOptimizeAction,\s*e,\s*describeFailure\(e\)\.correlationId,\s*\)/);
  assert.match(store, /routeCompareAction: decisionActionFailed\(\s*state\.routeCompareAction,\s*e,\s*describeFailure\(e\)\.correlationId,\s*\)/);
  // The strategy run returns its result or null, so the caller's stamp is written only by a run
  // that produced one; a refusal leaves the previous result's provenance in place.
  assert.match(
    store,
    /return result\.data;[\s\S]{0,200}?catch \(e\) \{[\s\S]{0,120}?return null;/,
  );
  // The strategy answer is also held to the identity that asked: both the success and the
  // failure path test `followUpReadIsCurrent` before any write (or follow-up read).
  assert.match(
    store,
    /const result = await api\.evaluateStrategyLab\(withoutLegacyFlag\(scenario\)\);[\s\S]{0,160}?if \(!followUpReadIsCurrent\(requestGeneration\)\) return null;[\s\S]{0,300}?strategyResult: result\.data/,
  );
  assert.match(
    store,
    /catch \(e\) \{\s*if \(!followUpReadIsCurrent\(requestGeneration\)\) return null;\s*set\(\{ error: String\(e\), loading: false \}\);/,
  );
  // The identity reset drops both lanes with the results they label.
  const reset = readWebSource("stores/workspaceLoading.ts");
  assert.match(reset, /poolOptimizeAction: IDLE_DECISION_ACTION_STATE,/);
  assert.match(reset, /routeCompareAction: IDLE_DECISION_ACTION_STATE,/);
});

test("the Decision surface renders the action's own state next to the action and its result", () => {
  const decision = readWebSource("components/DecisionWorkspace.tsx");
  const status = readWebSource("components/decision/DecisionActionStatus.tsx");

  // Both governed computes report their own lane, and the buttons read the shared gates.
  assert.match(decision, /state=\{portfolio\.routeCompareAction\}/);
  assert.match(decision, /state=\{portfolio\.poolOptimizeAction\}/);
  assert.match(decision, /blockerKey=\{portfolio\.routeCompareGate\.blockerKey\}/);
  assert.match(decision, /blockerKey=\{portfolio\.poolOptimizeGate\.blockerKey\}/);
  assert.match(decision, /disabled=\{!portfolio\.canRunPoolOptimizer\}/);
  assert.match(decision, /disabled=\{!portfolio\.canCompareRoutes\}/);
  // The Scenario panel's mismatch banner covers both results it displays, and the Optimize
  // panels and Review workspace state a stale pool result rather than presenting it as current.
  assert.match(decision, /contextMismatch=\{portfolio\.resultsContextMismatch\}/);
  assert.match(decision, /poolResultContextMismatch=\{portfolio\.optimizerContextMismatch\}/);
  assert.match(readWebSource("components/ReviewWorkspace.tsx"), /poolResultContextMismatch && resourcePoolResult !== null/);

  // The presentation itself: taxonomy copy, the correlation id, and no raw error string.
  assert.match(status, /presentError\(t, describeFailure\(state\.error\)\)/);
  assert.match(status, /failure\.correlationId/);
  assert.match(status, /role="alert"/);
  assert.match(status, /role="status"/);
  // Currency is stated from a settled run only, and it stays visible under a later failure
  // because the retained result is still the older run's.
  assert.match(status, /const currencyText = !pending && hasResult/);
  assert.match(status, /result_current/);
  assert.match(status, /result_stale/);
  assert.match(status, /failure\.action\}<\/p>\s*\{currencyText && <p/);
  assert.equal(status.includes("String(state.error)"), false);
  assert.equal(status.includes("state.error.message"), false);
});

test("every consumer derives from the model's results provenanced to the current inputs", () => {
  const model = readWebSource("app/model/usePortfolioDecisionModel.ts");
  const portfolio = readWebSource("components/PortfolioWorkspace.tsx");
  const market = readWebSource("components/MarketCockpit.tsx");
  const decision = readWebSource("components/DecisionWorkspace.tsx");
  const review = readWebSource("components/ReviewWorkspace.tsx");

  // One gate in the model: a payload whose provenance is not the inputs the caller now knows is
  // withheld (null) rather than presented as current. The gate covers the strategy result too.
  assert.match(
    model,
    /const currentResourcePoolResult = optimizerContextMismatch \? null : api\.resourcePoolResult;/,
  );
  assert.match(
    model,
    /const currentRouteRecommendation = routeRecommendationContextMismatch\s*\? null\s*: api\.routeRecommendation;/,
  );
  assert.match(
    model,
    /const currentStrategyResult = strategyContextMismatch \? null : api\.strategyResult;/,
  );
  // The derived figures the map and the Portfolio strip display read the gated values.
  assert.match(model, /currentResourcePoolResult\?\.total_net_pnl_gbp_per_day \?\?/);
  assert.match(model, /const firstStrategyTarget = currentStrategyResult\?\.allocation_targets\[0\];/);

  // Portfolio's route verdicts and PnL metrics read the model's provenanced values...
  assert.match(
    portfolio,
    /const poolResult = portfolio\.currentResourcePoolResult;/,
  );
  assert.match(
    portfolio,
    /const recommendation = portfolio\.currentRouteRecommendation;/,
  );
  assert.match(portfolio, /classifyRouteFeasibility\(\s*route,\s*recommendation,\s*poolResult,\s*api\.resourcePoolOptions,\s*\)/);
  assert.match(portfolio, /const allocation = poolResult\?\.allocations\.find\(/);
  assert.match(portfolio, /money\(poolResult\?\.total_net_pnl_gbp_per_day, "\/d"\)/);
  // ...the map does the same for its decision rail and strategy signal, and states a stale
  // strategy result rather than showing the previous one as live...
  assert.match(market, /routeRecommendation=\{portfolio\.currentRouteRecommendation\}/);
  assert.match(market, /resourcePoolResult=\{portfolio\.currentResourcePoolResult\}/);
  assert.match(market, /strategyResult=\{portfolio\.currentStrategyResult\}/);
  assert.match(market, /strategyContextMismatch=\{portfolio\.strategyContextMismatch\}/);
  assert.equal(market.includes("routeRecommendation={api.routeRecommendation}"), false);
  assert.equal(market.includes("resourcePoolResult={api.resourcePoolResult}"), false);
  // ...the Scenario and Optimize panels read the same gated payloads...
  assert.match(decision, /routeRecommendation=\{portfolio\.currentRouteRecommendation\}/);
  assert.match(decision, /resourcePoolResult=\{portfolio\.currentResourcePoolResult\}/);
  assert.match(decision, /const result = portfolio\.currentResourcePoolResult;/);
  // ...and the Review task gates its evidence pack with the same flag, naming a withheld run
  // instead of presenting it as evidence.
  assert.match(review, /const poolResult = poolResultContextMismatch \? null : resourcePoolResult;/);
  assert.match(review, /poolResultContextMismatch && resourcePoolResult !== null/);
  assert.match(review, /\{poolResult \? \(/);
});
