import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { IdentityReadCoordinator } from "../src/stores/workspaceLoading.ts";

const store = readFileSync(new URL("../src/stores/api.ts", import.meta.url), "utf8");

const MUTATIONS = [
  "saveProviderCredential",
  "testProviderConnection",
  "saveDraftContract",
  "recordReviewDecision",
  "recommendRouteAllocation",
  "optimizeResourcePool",
] as const;

const FOLLOW_UP_READS: Record<string, string> = {
  saveProviderCredential: "api.credentialProviders()",
  testProviderConnection: "api.credentialProviders()",
  saveDraftContract: "api.upstreamContracts()",
  recordReviewDecision: "api.reviewDecisions()",
};

function actionBody(name: string): string {
  const start = store.indexOf(`  ${name}: async `);
  assert.ok(start >= 0, `${name} is missing from the store`);
  const end = store.indexOf("\n  },\n", start);
  assert.ok(end > start, `${name} has no closing brace`);
  return store.slice(start, end);
}

test("mutation responses are committed only for their identity generation", () => {
  for (const name of MUTATIONS) {
    const body = actionBody(name);
    assert.match(body, /if \(logoutInProgress\) return;/, `${name} needs a logout guard`);
    assert.equal(
      body.match(/identityReadCoordinator\.capture\(\)/g)?.length,
      1,
      `${name} should capture one identity generation`,
    );
    assert.ok(
      (body.match(/followUpReadIsCurrent\(requestGeneration\)/g)?.length ?? 0) >= 2,
      `${name} needs guarded success and failure paths`,
    );
    const followUp = FOLLOW_UP_READS[name];
    if (followUp) {
      const mutationResponse = body.indexOf("await api.");
      const firstGuard = body.indexOf("followUpReadIsCurrent(requestGeneration)");
      const followUpRead = body.indexOf(followUp);
      assert.ok(mutationResponse < firstGuard && firstGuard < followUpRead, `${name} must guard before readback`);
    }
  }
});

test("a sign-out invalidation drops a deferred mutation response", async () => {
  const coordinator = new IdentityReadCoordinator();
  const generation = coordinator.capture();
  const response = Promise.resolve({ serverMutationApplied: true });
  coordinator.invalidate();

  const resolved = await response;
  let committed = false;
  if (coordinator.isCurrent(generation)) committed = resolved.serverMutationApplied;

  assert.equal(resolved.serverMutationApplied, true);
  assert.equal(committed, false);
});

test("a stale mutation response starts neither readback nor state commit", async () => {
  const coordinator = new IdentityReadCoordinator();
  const generation = coordinator.capture();
  let followUpCalls = 0;
  let stateWrites = 0;

  const firstResponse = Promise.resolve({ serverMutationApplied: true });
  const runMutationResponse = async () => {
    const result = await firstResponse;
    if (!coordinator.isCurrent(generation)) return;
    followUpCalls += 1;
    await Promise.resolve(result);
    if (coordinator.isCurrent(generation)) stateWrites += 1;
  };

  coordinator.invalidate();
  await runMutationResponse();

  assert.equal(followUpCalls, 0);
  assert.equal(stateWrites, 0);
});
