import { useCallback, useEffect, useReducer, useRef } from "react";

import { api, type CapacityBillingMetaDTO, type CapacityBillingResultDTO } from "@/api/client";
import {
  capacityBillingReadiness,
  capacityBillingRefusal,
  capacityBillingRequest,
  capacityBillingReducer,
  initialCapacityBillingState,
  type CapacityBillingDraft,
  type CapacityBillingReadiness,
  type CapacityBillingRefusal,
} from "@/app/model/capacityBillingModel";

export interface CapacityBillingController {
  readonly draft: CapacityBillingDraft;
  readonly updateDraft: (updater: (current: CapacityBillingDraft) => CapacityBillingDraft) => void;
  readonly readiness: CapacityBillingReadiness;
  readonly busy: boolean;
  readonly result: CapacityBillingResultDTO | null;
  readonly meta: CapacityBillingMetaDTO | null;
  readonly refusal: CapacityBillingRefusal | null;
  readonly error: unknown;
  readonly run: () => Promise<void>;
}

/**
 * State and transport for one capacity-billing sandbox run.
 *
 * The state reducer owns the result lifecycle: changing the draft, starting a run, a refusal and a
 * transport failure all drop the previous result. This hook adds the transport guard the reducer
 * cannot express - a run carries a sequence number and an `AbortController`, so a response for an
 * older draft can never be applied after the operator edits the form or starts another run.
 */
export function useCapacityBilling(): CapacityBillingController {
  const [state, dispatch] = useReducer(capacityBillingReducer, undefined, () =>
    initialCapacityBillingState(),
  );
  // The draft is mirrored synchronously so two edits in one tick compose against the latest text
  // rather than a render that has not committed yet.
  const draftRef = useRef(state.draft);
  const runSequence = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  // `busy` only becomes visible after React commits. This ref is the synchronous guard that makes
  // a second click or Ctrl+Enter in the same tick a no-op.
  const inFlightRef = useRef(false);

  useEffect(
    () => () => {
      runSequence.current += 1;
      inFlightRef.current = false;
      abortRef.current?.abort();
      abortRef.current = null;
    },
    [],
  );

  const updateDraft = useCallback(
    (updater: (current: CapacityBillingDraft) => CapacityBillingDraft) => {
      // Editing invalidates the answer and any request still describing the previous draft. The
      // edit also ends the previous submission's guard, so a corrected draft can be submitted
      // immediately while the stale response is ignored by the sequence check.
      runSequence.current += 1;
      inFlightRef.current = false;
      abortRef.current?.abort();
      abortRef.current = null;
      const next = updater(draftRef.current);
      draftRef.current = next;
      dispatch({ type: "draft_changed", draft: next });
    },
    [],
  );

  const run = useCallback(async () => {
    if (inFlightRef.current) return;
    const body = capacityBillingRequest(draftRef.current);
    if (!body) return;
    inFlightRef.current = true;
    runSequence.current += 1;
    const sequence = runSequence.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    dispatch({ type: "run_started" });
    try {
      const response = await api.capacityBilling(body, { signal: controller.signal });
      if (sequence !== runSequence.current) return;
      dispatch({
        type: "run_succeeded",
        result: response.data,
        meta: response.meta,
      });
    } catch (error) {
      if (sequence !== runSequence.current) return;
      const refusal = capacityBillingRefusal(error);
      dispatch({ type: "run_failed", refusal, error });
    } finally {
      // A stale request must not release the guard for a newer run.
      if (sequence === runSequence.current) {
        inFlightRef.current = false;
        abortRef.current = null;
      }
    }
  }, []);

  return {
    draft: state.draft,
    updateDraft,
    readiness: capacityBillingReadiness(state.draft),
    busy: state.busy,
    result: state.result,
    meta: state.meta,
    refusal: state.refusal,
    error: state.error,
    run,
  };
}
