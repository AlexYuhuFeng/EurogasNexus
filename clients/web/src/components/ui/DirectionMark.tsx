import i18n from "i18next";

import type { Direction } from "./dataGridModel";

/**
 * Direction as a glyph that stays on screen (UX R2): ▲ up, ▼ down, beside a signed figure. It
 * is not colour and not motion, so it reads for colour-blind users and under reduced motion.
 * `announce` adds the word for screen readers where nothing else in the cell says it (a live
 * price that ticked); beside a signed change the sign already says it, so the glyph is hidden.
 */
export function DirectionMark({ direction, announce = false }: { direction: Direction; announce?: boolean }) {
  if (!direction) return null;
  return (
    <span className="ds-direction" data-direction={direction}>
      <span aria-hidden="true">{direction === "up" ? "▲" : "▼"}</span>
      {announce ? <span className="ds-visually-hidden">{i18n.t(`grid.direction.${direction}`)}</span> : null}
    </span>
  );
}
