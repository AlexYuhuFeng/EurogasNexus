/**
 * The contract work chain (#32): terms → route economics → pool allocation → review.
 *
 * Each step says whether it is done, can be opened next, or is blocked, and for a blocked step
 * the one rule that blocks it. The chain carries the contract it is about; it never claims a
 * step is done from a draft, and it opens assessment pages only (no nomination, dispatch or
 * trade is submitted anywhere in the chain).
 */
export type ContractChainStepId = "terms" | "routes" | "allocation" | "review";
export type ContractChainState = "done" | "next" | "blocked";

export interface ContractChainStep {
  readonly id: ContractChainStepId;
  readonly state: ContractChainState;
  /** Translation key of the reason or status line under the step. */
  readonly reasonKey: string;
}

export interface ContractChainFacts {
  /** The contract the chain is about, or null when none is selected. */
  readonly contractId: string | null;
  /** Whether that contract is stored (not only a draft in the editor). */
  readonly persisted: boolean;
  /** Whether the editor holds changes not yet saved. */
  readonly draftDirty: boolean;
  /** Route candidates in the current context. */
  readonly routeCount: number;
  /** Whether a current (not stale) pool run allocated volume to this contract. */
  readonly allocated: boolean;
  /** Whether the pool run's inputs no longer match the current context. */
  readonly allocationStale: boolean;
}

export function contractChain(facts: ContractChainFacts): ContractChainStep[] {
  const saved = Boolean(facts.contractId) && facts.persisted && !facts.draftDirty;
  const terms: ContractChainStep = !facts.contractId
    ? { id: "terms", state: "next", reasonKey: "chain.terms.none" }
    : saved
      ? { id: "terms", state: "done", reasonKey: "chain.terms.saved" }
      : { id: "terms", state: "next", reasonKey: facts.persisted ? "chain.terms.unsaved_changes" : "chain.terms.draft" };
  const routes: ContractChainStep = !saved
    ? { id: "routes", state: "blocked", reasonKey: "chain.blocked.save_first" }
    : facts.routeCount === 0
      ? { id: "routes", state: "blocked", reasonKey: "chain.routes.none" }
      : { id: "routes", state: "next", reasonKey: "chain.routes.ready" };
  const allocation: ContractChainStep = !saved
    ? { id: "allocation", state: "blocked", reasonKey: "chain.blocked.save_first" }
    : facts.allocationStale
      ? { id: "allocation", state: "next", reasonKey: "chain.allocation.stale" }
      : facts.allocated
        ? { id: "allocation", state: "done", reasonKey: "chain.allocation.done" }
        : { id: "allocation", state: "next", reasonKey: "chain.allocation.ready" };
  const review: ContractChainStep =
    allocation.state === "done"
      ? { id: "review", state: "next", reasonKey: "chain.review.ready" }
      : { id: "review", state: "blocked", reasonKey: saved ? "chain.blocked.allocate_first" : "chain.blocked.save_first" };
  return [terms, routes, allocation, review];
}
