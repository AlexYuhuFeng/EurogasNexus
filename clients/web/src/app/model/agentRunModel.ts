/**
 * Governed research run model (Architecture V2 Wave 7 convergence + Wave 9 action geography).
 *
 * The research surface could always start a run, but it decided almost nothing about it: the
 * button was enabled whenever a trimmed objective was non-empty, the request named a profile
 * the client had no basis to choose, and the outcome of asking for strategy generation was
 * left for the user to discover from the run record. The route is stricter than the surface
 * was - it requires an objective of 8..4000 characters and a configured runtime PostgreSQL,
 * because the run persists its own rows - so the surface was offering an action that could
 * only fail.
 *
 * This module is the rule the surface gates on, kept pure and browser-free so it can be
 * asserted directly: the same object the header action and the panel's readiness list read.
 * It returns translation keys rather than copy, and it never grants authority - the route
 * re-authorises the caller, and a hidden or disabled control is not a permission.
 */

/**
 * The objective bounds `POST /api/agent/research` itself enforces (`min_length=8`,
 * `max_length=4000`). Mirrored, not invented: a surface that accepted a shorter objective
 * would offer a run the route refuses.
 */
export const AGENT_RUN_OBJECTIVE_MIN_LENGTH = 8;
export const AGENT_RUN_OBJECTIVE_MAX_LENGTH = 4000;

export interface AgentRunReadiness {
  /** Whether the run may be started as things stand. */
  readonly canRun: boolean;
  /** Every unsettled precondition, in a stable order, as translation keys. */
  readonly blockerKeys: readonly string[];
  /** The first blocker, for a control that can only show one explanation. */
  readonly firstBlockerKey: string | null;
}

/**
 * Whether a research run may be started, and what has to be true first.
 *
 * The runtime database is checked first because the run cannot be recorded without it - the
 * route answers 503 rather than running an unrecorded pipeline - and a run already in flight
 * is checked last so a transient state does not hide a real precondition.
 */
export function agentRunReadiness(input: {
  readonly objective: string;
  readonly runtimeDbReady: boolean;
  readonly running: boolean;
}): AgentRunReadiness {
  const blockerKeys: string[] = [];
  if (!input.runtimeDbReady) blockerKeys.push("agents.blocker.runtime_db");
  const objective = input.objective.trim();
  if (objective.length < AGENT_RUN_OBJECTIVE_MIN_LENGTH) {
    blockerKeys.push("agents.blocker.objective_short");
  } else if (objective.length > AGENT_RUN_OBJECTIVE_MAX_LENGTH) {
    blockerKeys.push("agents.blocker.objective_long");
  }
  if (input.running) blockerKeys.push("agents.blocker.in_flight");
  return {
    canRun: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys.length > 0 ? blockerKeys[0] : null,
  };
}

/** The body the surface sends. Deliberately smaller than the route's own request model. */
export interface AgentResearchRequest {
  readonly objective: string;
  readonly strategy_generation_allowed: boolean;
}

/**
 * The research request, composed from what the user actually decided.
 *
 * Two omissions are deliberate rather than accidental:
 *
 * - No `agent_profile`. The surface used to name `STRATEGY_RESEARCHER` itself, which made the
 *   client the author of a governance label: the profile is recorded on the run and scopes
 *   its tracked job, but it does not yet change what the orchestrator executes, so offering a
 *   choice would imply a capability that does not exist. The route's own declared default
 *   applies, and the surface shows the profile the run records.
 * - No `strategy_ir` and no period bounds. The run drafts its own candidate and the surface
 *   has no period evidence to send, so it sends none instead of inventing one; a run that
 *   needs a period says so in its own warnings.
 *
 * The objective is trimmed because the route's length bounds apply to the value it receives.
 */
export function agentResearchRequest(input: {
  readonly objective: string;
  readonly allowStrategy: boolean;
}): AgentResearchRequest {
  return {
    objective: input.objective.trim(),
    strategy_generation_allowed: input.allowStrategy,
  };
}

/**
 * What asking for strategy generation actually does, as translation keys.
 *
 * Freezing a strategy version and backtesting it are human acts, so a run that requests
 * generation without a frozen version terminates at `READY_FOR_HUMAN_REVIEW` with
 * `HUMAN_CONFIRMATION_REQUIRED`. The surface says that before the run instead of letting the
 * user read it out of a blocker afterwards.
 */
export function agentStrategyDisclosure(allowStrategy: boolean): readonly string[] {
  if (!allowStrategy) return ["agents.strategy.off"];
  return ["agents.strategy.human_confirmation_required", "agents.strategy.no_frozen_version"];
}

/**
 * Disclosures that hold for every run, so the surface states the same two things whether or
 * not strategy generation was requested.
 */
export const AGENT_RUN_DISCLOSURES: readonly string[] = [
  "agents.scope.disclosure",
  "agents.profile.recorded",
];
