/**
 * Canonical Inspector store (Architecture V2 Wave 9).
 *
 * The Wave 1 contract (`app/experience/inspectorContract.ts`) is a pure reducer;
 * this store is the runtime wrapper the shell renders from. Keeping the reducer
 * pure means the selection rules stay testable without a browser, while the store
 * only adds identity-reset behaviour.
 *
 * The Inspector is presentation: it shows what the caller already received under
 * the current identity's entitlement, and never fetches entitlement-restricted
 * detail of its own.
 */

import { create } from "zustand";

import {
  EMPTY_INSPECTOR_STATE,
  inspectorReducer,
  type InspectorEvent,
  type InspectorSubject,
} from "@/app/experience/inspectorContract";

interface InspectorStore {
  subject: InspectorSubject | null;
  history: InspectorSubject[];
  open: (subject: InspectorSubject) => void;
  close: () => void;
  back: () => void;
  reset: () => void;
}

export const useInspectorStore = create<InspectorStore>((set, get) => ({
  subject: EMPTY_INSPECTOR_STATE.subject,
  history: [...EMPTY_INSPECTOR_STATE.history],
  open: (subject) => set((state) => apply(state, { type: "open", subject })),
  close: () => set((state) => apply(state, { type: "close" })),
  back: () => set((state) => apply(state, { type: "back" })),
  reset: () => {
    if (get().subject === null && get().history.length === 0) return;
    set({ subject: null, history: [] });
  },
}));

function apply(
  state: { subject: InspectorSubject | null; history: InspectorSubject[] },
  event: InspectorEvent,
): { subject: InspectorSubject | null; history: InspectorSubject[] } {
  const next = inspectorReducer({ subject: state.subject, history: state.history }, event);
  return { subject: next.subject, history: [...next.history] };
}
