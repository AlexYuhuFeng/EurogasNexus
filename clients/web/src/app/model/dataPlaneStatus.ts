/**
 * The shell's data-plane badge.
 *
 * The store's `dataStatus` used to be printed through `data.runtime`, so the
 * healthy header badge read "Runtime DB" - the name of the store rather than a
 * state - while the manual and runtime surfaces read it differently and the
 * market overview printed the raw enum. The UI constitution asks for one
 * operational vocabulary (Ready / Partial / Unavailable) and forbids inventing a
 * synonymous label per screen, so this maps the store's value onto that
 * vocabulary once and every surface renders the same words.
 *
 * Fail-closed: only `runtime` and `partial` are recognised as anything other
 * than unavailable. A state this module does not know - including the `delayed`
 * slot the type still carries but nothing produces - must not read as healthy.
 */

export type DataPlaneState = "ready" | "partial" | "unavailable";

export function dataPlaneState(dataStatus: string | null | undefined): DataPlaneState {
  if (dataStatus === "runtime") return "ready";
  if (dataStatus === "partial") return "partial";
  return "unavailable";
}

/** Translation key for a data-plane state, so every surface shares one label. */
export function dataPlaneLabelKey(state: DataPlaneState): string {
  return `data.${state}`;
}
