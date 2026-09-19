import { useCallback, useState } from "react";

import { api, type NetbackOutcomeDTO, type RouteCostOutcomeDTO } from "@/api/client";
import {
  emptyRouteCostDraft,
  netbackReadiness,
  netbackRequest,
  routeCostReadiness,
  routeCostRequest,
  type RouteCostDraft,
  type RouteCostReadiness,
} from "@/app/model/routeCostModel";

export interface RouteCostWhatIf {
  readonly draft: RouteCostDraft;
  readonly updateDraft: (updater: (current: RouteCostDraft) => RouteCostDraft) => void;
  readonly readiness: RouteCostReadiness;
  readonly netbackCanRun: boolean;
  readonly netbackBlockerKey: string | null;
  readonly busy: boolean;
  readonly cost: RouteCostOutcomeDTO | null;
  readonly netback: NetbackOutcomeDTO | null;
  readonly error: unknown;
  /** Run both engines: the cost first, then the netback over the cost the engine returned. */
  readonly run: () => Promise<void>;
}

/**
 * The route-cost and netback what-if's state and its run (slice D of the D3 decision).
 *
 * The state lives with the task rather than inside the panel because the action geography puts a
 * `compute` in the workspace header's primary slot: the panel configures the run and reports the
 * result, the header starts it, and both read the same readiness rule instead of each deriving its
 * own opinion.
 *
 * The netback is not a second act. One run costs the route and, when the caller supplied a
 * destination market price, values the netback over **the cost the engine returned** - never over a
 * total summed in the browser, which would be a second opinion about the same number.
 */
export function useRouteCostWhatIf(): RouteCostWhatIf {
  const [draft, setDraft] = useState<RouteCostDraft>(() => emptyRouteCostDraft());
  const [busy, setBusy] = useState(false);
  const [cost, setCost] = useState<RouteCostOutcomeDTO | null>(null);
  const [netback, setNetback] = useState<NetbackOutcomeDTO | null>(null);
  const [error, setError] = useState<unknown>(null);

  const readiness = routeCostReadiness(draft);
  const netbackState = netbackReadiness(draft, cost ? cost.total_cost_eur_mwh : null);

  const updateDraft = useCallback(
    (updater: (value: RouteCostDraft) => RouteCostDraft) => {
      setDraft(updater);
    },
    [],
  );

  const run = useCallback(async () => {
    const body = routeCostRequest(draft);
    if (!body) return;
    setBusy(true);
    setError(null);
    try {
      const costResponse = await api.routeCost(body);
      setCost(costResponse.data);
      setNetback(null);
      // The netback is offered only when it would be a statement about the same inputs: a market
      // price the caller supplied, over the cost the engine just returned.
      const netbackBody = netbackRequest(draft, costResponse.data.total_cost_eur_mwh);
      if (netbackBody) {
        const netbackResponse = await api.netback(netbackBody);
        setNetback(netbackResponse.data);
      }
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }, [draft]);

  return {
    draft,
    updateDraft,
    readiness,
    netbackCanRun: netbackState.canCompute,
    netbackBlockerKey: netbackState.firstBlockerKey,
    busy,
    cost,
    netback,
    error,
    run,
  };
}
