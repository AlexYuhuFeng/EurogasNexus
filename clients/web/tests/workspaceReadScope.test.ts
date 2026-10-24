import assert from "node:assert/strict";
import test, { after } from "node:test";
import type { CurrentUserDTO } from "../src/api/client.ts";
import { needsCommercialWorkspaceReads, workspaceReadNeeded } from "../src/stores/workspaceReadScope.ts";
import { closeApiStoreHarness, loadApiStore, settle } from "./support/apiStoreHarness.ts";
import { apiRegistry } from "./support/mockApiClient.ts";
import { AUTHENTICATED_AUTH_STATE } from "../src/stores/workspaceLoading.ts";

after(closeApiStoreHarness);
const admin = { role: "ADMIN", roles: ["ADMIN"], permissions: ["identity.manage", "runtime.read"] } as CurrentUserDTO;

test("administration composition excludes commercial reads and preserves overlapping roles", () => {
  assert.equal(needsCommercialWorkspaceReads(admin), false);
  assert.equal(needsCommercialWorkspaceReads({ ...admin, roles: ["ADMIN", "ANALYST"] }), true);
  for (const key of ["fxRates", "portfolioSnapshot", "reviewDecisions", "marketQuotes", "monitoringAlerts", "routeCandidates"]) {
    assert.equal(workspaceReadNeeded(key, admin), false, key);
  }
  for (const key of ["sources", "runtimeDb", "credentialProviders", "pipelineHealth", "referenceNodes"]) {
    assert.equal(workspaceReadNeeded(key, admin), true, key);
  }
});

test("ADMIN-only workspace and refreshes issue no commercial reads and keep genuine failures visible", async () => {
  const harness = await loadApiStore();
  const { store } = harness;
  const { calls, handlers } = apiRegistry();
  store.setState({ authState: AUTHENTICATED_AUTH_STATE, currentUser: admin } as Parameters<typeof store.setState>[0]);
  handlers.me = () => ({ data: admin, meta: {} });
  await store.getState().fetchWorkspace();
  await store.getState().refreshMarketData();
  await store.getState().refreshMonitoring();
  await settle();
  const methods = calls.map((call) => call.method);
  for (const method of ["fxRates", "portfolioSnapshot", "reviewDecisions", "marketQuotes", "marketContext", "monitoringAlerts", "strategySummary", "strategyRuns"]) {
    assert.equal(methods.includes(method), false, method);
  }
  assert.ok(methods.includes("sources"));
  assert.ok(methods.includes("credentialProviders"));
  assert.ok(methods.includes("runtimeDb"));
  assert.deepEqual(store.getState().endpointErrors, {});
  handlers.runtimeDb = () => { throw new Error("runtime unavailable"); };
  await store.getState().fetchWorkspace();
  assert.match(store.getState().endpointErrors.runtimeDb, /runtime unavailable/);
});

test("review composition retains evidence reads without issuing governed resource preparation reads", async () => {
  const { store } = await loadApiStore();
  const { calls, handlers } = apiRegistry();
  const reviewer = { role: "REVIEWER", roles: ["REVIEWER"], permissions: ["portfolio.read", "review.read", "review.record"] } as CurrentUserDTO;
  store.setState({ authState: AUTHENTICATED_AUTH_STATE, currentUser: reviewer } as Parameters<typeof store.setState>[0]);
  handlers.me = () => ({ data: reviewer, meta: {} });
  await store.getState().fetchWorkspace();
  const methods = calls.map((call) => call.method);
  assert.equal(methods.includes("upstreamContracts"), false);
  assert.ok(methods.includes("reviewDecisions"));
  assert.ok(methods.includes("portfolioSnapshot"));
  assert.equal(workspaceReadNeeded("upstreamContracts", { ...reviewer, permissions: [...reviewer.permissions, "scenario.create"] }), true);
});
