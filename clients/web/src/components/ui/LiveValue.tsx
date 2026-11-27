import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { useScreenFreshness } from "@/app/data/connection";
import { useInstantFormatter } from "@/app/time/useInstant";
import { DirectionMark } from "./DirectionMark";
import { nextFlash, type FlashState, type SortValue } from "./dataGridModel";

/**
 * A live value (UX R2): a neutral background flash on a real tick (off under reduced motion)
 * and the direction as a glyph that stays until the next tick. A change of instrument under
 * the same place (`identity`) is not a tick. Until the first tick an invisible glyph holds the
 * glyph's place, so a column of figures does not move when one of them ticks.
 *
 * When the screen is not current (small-desk plan 3.7: browser offline, server unreachable or
 * the live connection quiet; app/data/connection.ts) the last value stays, it stops flashing,
 * and the glyph's place holds a quiet stale mark whose tooltip and accessible text give the
 * time of the last known picture. Muted, never an alarm colour: the value is old, not wrong.
 *
 * Used by the DataGrid's live cells and by key figures (Today's market and book).
 */
export function LiveValue({ watch, identity, children }: { watch: SortValue; identity: string; children: ReactNode }) {
  const [state, setState] = useState<FlashState>(() => nextFlash(null, identity, watch));
  const freshness = useScreenFreshness();
  const { t } = useTranslation();
  const format = useInstantFormatter();
  useEffect(() => {
    setState((previous) => nextFlash(previous, identity, watch));
  }, [identity, watch]);
  const ticked = state.identity === identity && state.count > 0;
  if (!freshness.current) {
    const time = freshness.since !== null ? format(freshness.since)?.text ?? "" : "";
    const label = time ? t("stale.value_since", { time }) : t("stale.value");
    return (
      <span className="ds-cell-flash" data-stale={freshness.reason}>
        {children}
        <span className="ds-direction ds-stale-mark" title={label} role="img" aria-label={label} />
      </span>
    );
  }
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
