/** The contract work chain names each step's state and the one rule blocking it (#32). */
import assert from "node:assert/strict";
import test from "node:test";
import { contractChain, type ContractChainFacts } from "../src/app/model/contractChainModel.ts";

const base: ContractChainFacts = {
  contractId: "c-1",
  persisted: true,
  draftDirty: false,
  routeCount: 3,
  allocated: false,
  allocationStale: false,
};
const states = (facts: ContractChainFacts) => contractChain(facts).map((step) => `${step.id}:${step.state}`);

test("a draft blocks every later step with 'save first'", () => {
  const steps = contractChain({ ...base, persisted: false });
  assert.deepEqual(states({ ...base, persisted: false }), ["terms:next", "routes:blocked", "allocation:blocked", "review:blocked"]);
  assert.equal(steps[0].reasonKey, "chain.terms.draft");
  assert.ok(steps.slice(1).every((step) => step.reasonKey === "chain.blocked.save_first"));
});

test("unsaved changes to a stored contract are not counted as saved", () => {
  const steps = contractChain({ ...base, draftDirty: true });
  assert.equal(steps[0].reasonKey, "chain.terms.unsaved_changes");
  assert.equal(steps[1].state, "blocked");
});

test("a saved contract opens routes and allocation; review waits for an allocation", () => {
  assert.deepEqual(states(base), ["terms:done", "routes:next", "allocation:next", "review:blocked"]);
  assert.equal(contractChain(base)[3].reasonKey, "chain.blocked.allocate_first");
});

test("an allocation in the current run opens review; a stale run does not count", () => {
  assert.deepEqual(states({ ...base, allocated: true }), ["terms:done", "routes:next", "allocation:done", "review:next"]);
  const stale = contractChain({ ...base, allocated: true, allocationStale: true });
  assert.equal(stale[2].reasonKey, "chain.allocation.stale");
  assert.equal(stale[3].state, "blocked");
});

test("no route candidates is said as such, not as a generic not-ready", () => {
  assert.equal(contractChain({ ...base, routeCount: 0 })[1].reasonKey, "chain.routes.none");
});

test("no contract selected asks for one", () => {
  assert.equal(contractChain({ ...base, contractId: null })[0].reasonKey, "chain.terms.none");
});
