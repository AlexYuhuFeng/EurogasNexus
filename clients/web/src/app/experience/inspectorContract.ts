/**
 * Canonical Inspector contract (Architecture V2 Wave 1).
 *
 * Architecture V2 section 6 of
 * `docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md` requires one
 * Inspector for object detail instead of a new top-level page per object kind. The
 * W0-01 client inventory records the current alternatives - rails, drawers and
 * master-detail panes built per surface - as REFACTOR work.
 *
 * This module defines the Inspector as a pure, dependency-free state machine: which
 * object kinds each workspace may hand over, what a subject is, and how open, close
 * and back behave. It deliberately does not render anything yet: Wave 1 fixes the
 * contract, Wave 9 moves surfaces onto it. Keeping it pure also keeps it testable
 * without a browser.
 *
 * The Inspector presents detail; it never becomes an authority boundary. A subject
 * carries only what the caller already received from the backend under the current
 * identity's entitlement.
 */

import type { WorkspacePageId } from "@/workspaceNavigation";
import { inspectorSubjectsForPage } from "./workspacePatterns.ts";
import { isInspectorSubjectKind, type InspectorSubjectKind } from "./vocabulary.ts";

export interface InspectorSubject {
  readonly kind: InspectorSubjectKind;
  /** Stable identifier of the selected object, as returned by the backend. */
  readonly ref: string;
  /** Already-localised display label for the inspector header. */
  readonly label: string;
  /** Page the selection came from, so the Inspector can be closed back into context. */
  readonly originPage: WorkspacePageId;
}

export interface InspectorState {
  readonly subject: InspectorSubject | null;
  /** Previously inspected subjects, most recent last; bounded by `INSPECTOR_HISTORY_LIMIT`. */
  readonly history: readonly InspectorSubject[];
}

export const INSPECTOR_HISTORY_LIMIT = 10;

export const EMPTY_INSPECTOR_STATE: InspectorState = { subject: null, history: [] };

export type InspectorEvent =
  | { readonly type: "open"; readonly subject: InspectorSubject }
  | { readonly type: "close" }
  | { readonly type: "back" }
  | { readonly type: "reset" };

export function openInspector(subject: InspectorSubject): InspectorEvent {
  return { type: "open", subject };
}

/**
 * Whether a workspace may hand an object kind to the Inspector. Unknown pages and
 * undeclared kinds are refused rather than rendered as an empty panel, so a surface
 * cannot accidentally promise detail it has no contract for.
 */
export function canOpenInspector(kind: InspectorSubjectKind, page: WorkspacePageId): boolean {
  if (!isInspectorSubjectKind(kind)) return false;
  return inspectorSubjectsForPage(page).includes(kind);
}

export function inspectorReducer(state: InspectorState, event: InspectorEvent): InspectorState {
  switch (event.type) {
    case "open": {
      if (!event.subject.ref) return state;
      const history = state.subject
        ? [...state.history, state.subject].slice(-INSPECTOR_HISTORY_LIMIT)
        : state.history;
      return { subject: event.subject, history };
    }
    case "close":
      return { subject: null, history: state.history };
    case "back": {
      const previous = state.history.at(-1);
      if (!previous) return { subject: null, history: state.history };
      return { subject: previous, history: state.history.slice(0, -1) };
    }
    case "reset":
      return EMPTY_INSPECTOR_STATE;
    default:
      return state;
  }
}

export function inspectorIsOpen(state: InspectorState): boolean {
  return state.subject !== null;
}

/** True when the Inspector is showing detail that belongs to the page the user is on. */
export function inspectorMatchesPage(state: InspectorState, page: WorkspacePageId): boolean {
  return state.subject?.originPage === page;
}
