import { useEffect, useState, type ReactNode } from "react";

import { DirectionMark } from "./DirectionMark";
import { nextFlash, type FlashState, type SortValue } from "./dataGridModel";

/**
 * A live value (UX R2): a neutral background flash on a real tick (off under reduced motion)
 * and the direction as a glyph that stays until the next tick. A change of instrument under
 * the same place (`identity`) is not a tick. Until the first tick an invisible glyph holds the
 * glyph's place, so a column of figures does not move when one of them ticks.
 *
 * Used by the DataGrid's live cells and by key figures (Today's market and book).
 */
export function LiveValue({ watch, identity, children }: { watch: SortValue; identity: string; children: ReactNode }) {
  const [state, setState] = useState<FlashState>(() => nextFlash(null, identity, watch));
  useEffect(() => {
    setState((previous) => nextFlash(previous, identity, watch));
  }, [identity, watch]);
  const ticked = state.identity === identity && state.count > 0;
  return (
    <span className="ds-cell-flash" data-flash={ticked ? (state.count % 2 ? "a" : "b") : undefined}>
      {children}
      {ticked && state.direction ? (
        <DirectionMark direction={state.direction} announce />
      ) : (
        <span className="ds-direction" data-direction="none" aria-hidden="true" />
      )}
    </span>
  );
}
