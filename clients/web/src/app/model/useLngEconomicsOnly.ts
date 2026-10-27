import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { api, type LngEconomicsOnlyMetaDTO, type LngEconomicsOnlyResultDTO } from "@/api/client";
import {
  createLngEconomicsRunGate,
  initialLngEconomicsState,
  lngEconomicsReducer,
  lngEconomicsRefusal,
  lngEconomicsRequest,
  lngEconomicsReadiness,
  type LngEconomicsDraft,
  type LngEconomicsReadiness,
  type LngEconomicsRefusal,
} from "@/app/model/lngEconomicsModel";

export interface LngEconomicsController {
  readonly draft: LngEconomicsDraft;
  readonly updateDraft: (
    updater: (current: LngEconomicsDraft) => LngEconomicsDraft,
  ) => void;
  readonly readiness: LngEconomicsReadiness;
  readonly busy: boolean;
  readonly result: LngEconomicsOnlyResultDTO | null;
  readonly meta: LngEconomicsOnlyMetaDTO | null;
  readonly refusal: LngEconomicsRefusal | null;
  readonly error: unknown;
  readonly run: () => Promise<void>;
}

/**
 * State and transport for one LNG economics-only sandbox run.
 *
 * The reducer owns the result lifecycle: editing the draft, changing the selected contract
 * context, starting a run, a refusal and a transport failure all drop the previous result. This
 * hook adds the transport guard the reducer cannot express:
 *
 * - `begin()` is synchronous, so two submit events in one tick cannot start two requests;
 * - each run carries a sequence number and an `AbortController`, so an edit or a context change
 *   aborts the in-flight request and a late response for an older draft is never applied;
 * - unmount invalidates the sequence and aborts, so no state is dispatched after the panel leaves.
 *
 * The draft itself survives every failure path: a refusal or a network error replaces the result,
 * never the operator's text.
 */
export function useLngEconomicsOnly(contextKey: string): LngEconomicsController {
  const [state, dispatch] = useReducer(lngEconomicsReducer, undefined, () =>
    initialLngEconomicsState(),
  );
  // The draft is mirrored synchronously so two edits in one tick compose against the latest text.
  const draftRef = useRef(state.draft);
  // The gate is created once for this mounted panel and never re-created by a render.
  const [gate] = useState(createLngEconomicsRunGate);
  const contextRef = useRef(contextKey);

  useEffect(
    () => () => {
      gate.invalidate();
    },
    [gate],
  );

  useEffect(() => {
    // The selected contract is context, not an authoritative fact: when the caller selects a
    // different term, a result computed against the previous selection is no longer current. The
    // draft is deliberately preserved so the operator keeps their typed economics.
    if (contextRef.current === contextKey) return;
    contextRef.current = contextKey;
    gate.invalidate();
    dispatch({ type: "context_changed" });
  }, [contextKey, gate]);

  const updateDraft = useCallback(
    (updater: (current: LngEconomicsDraft) => LngEconomicsDraft) => {
      // Editing invalidates the answer and any request still describing the previous draft.
      gate.invalidate();
      const next = updater(draftRef.current);
      draftRef.current = next;
      dispatch({ type: "draft_changed", draft: next });
    },
    [gate],
  );

  const run = useCallback(async () => {
    const body = lngEconomicsRequest(draftRef.current);
    if (!body) return;
    const ticket = gate.begin();
    // Synchronous duplicate suppression: a second submit in this tick never opens a second
    // request, before React has had a chance to render `busy`.
    if (!ticket) return;
    dispatch({ type: "run_started" });
    try {
      const response = await api.lngEconomicsOnly(body, { signal: ticket.signal });
      if (!gate.isCurrent(ticket.sequence)) return;
      dispatch({
        type: "run_succeeded",
        result: response.data,
        meta: response.meta,
      });
    } catch (error) {
      if (!gate.isCurrent(ticket.sequence)) return;
      const refusal = lngEconomicsRefusal(error);
      dispatch({ type: "run_failed", refusal, error });
    } finally {
      gate.finish(ticket.sequence);
    }
  }, [gate]);

  return {
    draft: state.draft,
    updateDraft,
    readiness: lngEconomicsReadiness(state.draft),
    busy: state.busy,
    result: state.result,
    meta: state.meta,
    refusal: state.refusal,
    error: state.error,
    run,
  };
}
